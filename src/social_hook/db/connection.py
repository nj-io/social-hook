"""Database connection management."""

import sqlite3
from pathlib import Path

from social_hook.db.schema import apply_migrations, create_schema
from social_hook.errors import DatabaseError


class ResilientConnection:
    """SQLite connection wrapper that survives DB file replacement.

    When a snapshot restore or manual copy replaces the DB file on disk,
    existing connections can become corrupt (stale WAL state). This wrapper
    detects the replacement via mtime change and reconnects transparently.

    Usage:
        rc = ResilientConnection(db_path)
        # In a polling loop:
        conn = rc.check()  # reconnects if needed, returns current conn
        conn.execute(...)
        # When done:
        rc.close()
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute("PRAGMA busy_timeout = 5000")
        self.conn.row_factory = sqlite3.Row
        self._mtime = self._get_mtime()

    def _get_mtime(self) -> float:
        try:
            return self.db_path.stat().st_mtime
        except OSError:
            return 0.0

    def check(self) -> sqlite3.Connection:
        """Return the current connection, reconnecting if the DB file changed."""
        current_mtime = self._get_mtime()
        if current_mtime != self._mtime:
            self.conn.close()
            self.conn = sqlite3.connect(str(self.db_path))
            self.conn.execute("PRAGMA busy_timeout = 5000")
            self.conn.row_factory = sqlite3.Row
            self._mtime = current_mtime
        return self.conn

    def close(self) -> None:
        self.conn.close()


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    """Get a database connection with proper settings.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        sqlite3.Connection with WAL mode and foreign keys enabled
    """
    db_path = Path(db_path)

    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        conn = sqlite3.connect(str(db_path))

        # Enable WAL mode for concurrent access (multiple worktrees)
        conn.execute("PRAGMA journal_mode = WAL")

        # Wait up to 5 seconds for locks before failing
        conn.execute("PRAGMA busy_timeout = 5000")

        # Enable foreign key enforcement
        conn.execute("PRAGMA foreign_keys = ON")

        # Return dict-like rows
        conn.row_factory = sqlite3.Row

        return conn

    except sqlite3.Error as e:
        raise DatabaseError(f"Failed to connect to database: {e}") from e


def init_database(
    db_path: str | Path, conn: sqlite3.Connection | None = None
) -> sqlite3.Connection:
    """Initialize the database with schema and apply pending migrations.

    Args:
        db_path: Path to the SQLite database file
        conn: Optional existing connection to use

    Returns:
        sqlite3.Connection with schema applied
    """
    if conn is None:
        conn = get_connection(db_path)

    # Apply migrations first to add any new columns to existing databases,
    # then run create_schema() which creates tables (IF NOT EXISTS) and indexes.
    # On fresh DBs: migrations are no-ops (no schema_version table yet),
    # create_schema() builds everything from scratch.
    # On existing DBs: migrations add missing columns, then create_schema()
    # adds any new indexes that reference those columns.
    migrations_dir = Path(__file__).parent / "migrations"
    apply_migrations(conn, migrations_dir)

    create_schema(conn)

    return conn
