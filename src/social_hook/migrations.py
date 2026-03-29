"""Generic SQL migration runner for SQLite.

Reads .sql files from a directory, applies them in order by numeric prefix,
and tracks applied versions in a schema_version table. Handles PRAGMA
statements (required for SQLite table rebuilds) by splitting them from
DDL and executing outside transactions.

REUSABILITY: This file has zero project-specific imports.
Only stdlib (sqlite3, pathlib, logging). Copy-paste safe.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


def apply_sql_migrations(
    conn: sqlite3.Connection,
    migrations_dir: str | Path,
    *,
    version_table: str = "schema_version",
) -> int:
    """Apply pending .sql migrations from a directory.

    Migration files must be named with a numeric prefix that determines
    application order: ``YYYYMMDDHHMMSS_description.sql`` or
    ``NNN_description.sql``. Only the digits before the first underscore
    matter — they become the version number stored in the tracking table.

    Migrations are applied in ascending order. Each migration runs inside
    its own transaction (via ``executescript``). PRAGMA-containing
    migrations are handled specially since PRAGMAs cannot run inside
    transactions.

    Args:
        conn: SQLite connection (must already have the version_table
            created — call ``ensure_version_table`` first for new DBs).
        migrations_dir: Directory containing .sql migration files.
        version_table: Name of the version tracking table.
            Defaults to "schema_version".

    Returns:
        Number of migrations applied.
    """
    migrations_dir = Path(migrations_dir)

    if not migrations_dir.exists():
        return 0

    # Fresh DB: version table doesn't exist yet — nothing to migrate.
    tables = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if version_table not in tables:
        return 0

    current = conn.execute(f"SELECT COALESCE(MAX(version), 0) FROM {version_table}").fetchone()[0]

    applied = 0
    for migration_file in sorted(migrations_dir.glob("*.sql")):
        try:
            version = int(migration_file.stem.split("_")[0])
        except (ValueError, IndexError):
            continue

        if version > current:
            sql = migration_file.read_text()

            if "PRAGMA" in sql:
                _apply_pragma_migration(conn, sql)
            else:
                conn.executescript(sql)

            conn.execute(
                f"INSERT INTO {version_table} (version, description) VALUES (?, ?)",
                (version, migration_file.stem),
            )
            conn.commit()
            applied += 1
            logger.debug("Applied migration: %s", migration_file.name)

    return applied


def ensure_version_table(
    conn: sqlite3.Connection,
    version_table: str = "schema_version",
) -> None:
    """Create the version tracking table if it doesn't exist.

    Args:
        conn: SQLite connection.
        version_table: Name of the version tracking table.
    """
    conn.execute(
        f"""CREATE TABLE IF NOT EXISTS {version_table} (
            version     INTEGER PRIMARY KEY,
            applied_at  TEXT NOT NULL DEFAULT (datetime('now')),
            description TEXT
        )"""
    )
    conn.commit()


def get_current_version(
    conn: sqlite3.Connection,
    version_table: str = "schema_version",
) -> int:
    """Get the current schema version.

    Returns 0 if the version table doesn't exist or is empty.

    Args:
        conn: SQLite connection.
        version_table: Name of the version tracking table.

    Returns:
        Current version number (highest applied migration).
    """
    tables = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if version_table not in tables:
        return 0
    row = conn.execute(f"SELECT COALESCE(MAX(version), 0) FROM {version_table}").fetchone()
    return int(row[0]) if row else 0


def _apply_pragma_migration(conn: sqlite3.Connection, sql: str) -> None:
    """Apply a migration containing PRAGMA statements.

    PRAGMA statements must execute outside transactions. This splits them
    from DDL/DML statements and handles each appropriately.

    PRAGMAs before any DDL run first, then DDL runs as a script,
    then PRAGMAs after DDL run last.

    Args:
        conn: SQLite connection.
        sql: Full migration SQL text containing PRAGMA statements.
    """
    pragmas_before: list[str] = []
    pragmas_after: list[str] = []
    other_lines: list[str] = []

    has_ddl = False
    for line in sql.split("\n"):
        stripped = line.strip()
        if stripped.upper().startswith("PRAGMA"):
            if has_ddl:
                pragmas_after.append(stripped)
            else:
                pragmas_before.append(stripped)
        else:
            other_lines.append(line)
            if stripped and not stripped.startswith("--"):
                has_ddl = True

    for pragma in pragmas_before:
        conn.execute(pragma)

    ddl_sql = "\n".join(other_lines).strip()
    if ddl_sql:
        conn.executescript(ddl_sql)

    for pragma in pragmas_after:
        conn.execute(pragma)
