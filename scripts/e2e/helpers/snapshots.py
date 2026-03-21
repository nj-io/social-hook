"""Snapshot-based rollback for E2E scenarios.

Saves the DB before a test block and restores it after, ensuring
synthetic events and other mutations don't leak between scenarios.
"""

import shutil
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def snapshot_rollback(harness):
    """Context manager: save DB before, restore after.

    Usage::

        with snapshot_rollback(harness):
            # mutate DB (insert events, modify drafts, etc.)
            # run assertions
        # DB is restored to pre-test state

    Uses direct file copy (not CLI snapshot restore) because the CLI
    has bot daemon checks and confirmation prompts unsuitable for E2E.
    """
    from social_hook.filesystem import get_db_path

    db_path = get_db_path()
    backup_fd, backup_path = tempfile.mkstemp(suffix=".db")

    try:
        # Checkpoint WAL and copy DB
        harness.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        shutil.copy2(str(db_path), backup_path)

        yield harness

    finally:
        # Always restore and reopen, even if the test block raised
        try:
            harness.conn.close()
            shutil.copy2(backup_path, str(db_path))
            # Remove stale WAL/SHM files
            for suffix in ("-wal", "-shm"):
                stale = Path(str(db_path) + suffix)
                if stale.exists():
                    stale.unlink()
        finally:
            # Reopen connection no matter what
            harness.conn = sqlite3.connect(str(db_path))
            harness.conn.row_factory = sqlite3.Row
            # Clean up temp file
            Path(backup_path).unlink(missing_ok=True)
