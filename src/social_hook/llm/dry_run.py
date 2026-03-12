"""DryRunContext: wraps DB operations, skipping writes in dry-run mode."""

import sqlite3
from typing import Any

from social_hook.db import operations as ops

# Prefixes that indicate write operations (should be no-ops in dry run)
_WRITE_PREFIXES = (
    "insert_",
    "update_",
    "supersede_",
    "increment_",
    "reset_",
    "set_",
    "record_",
    "emit_",
    "upsert_",
)

# Prefixes that indicate read operations (always pass through)
_READ_PREFIXES = ("get_",)


class DryRunContext:
    """Wraps db.operations module, skipping writes during dry-run.

    Read operations (get_*) pass through to db.operations with the connection.
    Write operations (insert_*, update_*, etc.) return no-op results when dry_run=True.

    Args:
        conn: SQLite database connection
        dry_run: If True, skip all write operations
    """

    def __init__(self, conn: sqlite3.Connection, dry_run: bool = False) -> None:
        self.conn = conn
        self.dry_run = dry_run

    def __getattr__(self, name: str) -> Any:
        """Delegate to db.operations, intercepting writes in dry-run mode."""
        # Get the actual function from db.operations
        func = getattr(ops, name, None)
        if func is None:
            raise AttributeError(
                f"'DryRunContext' has no attribute '{name}' (not found in db.operations)"
            )

        if self.dry_run and name.startswith(_WRITE_PREFIXES):
            return _make_noop(name, func)

        # Read operations and non-dry-run writes: pass through with conn
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(self.conn, *args, **kwargs)

        return wrapper


def _make_noop(name: str, func: Any) -> Any:
    """Create a no-op wrapper for a write operation.

    Returns appropriate defaults based on the operation pattern:
    - insert_*: returns the first positional arg's .id if it has one, else None
    - increment_*: returns 0
    - Others: returns None
    """

    def noop(*args: Any, **kwargs: Any) -> Any:
        if name.startswith("insert_"):
            # insert_* functions take a model object and return its ID
            if args and hasattr(args[0], "id"):
                return args[0].id
            # insert_milestone_summary takes a dict
            if args and isinstance(args[0], dict):
                return args[0].get("id")
            return None
        elif name.startswith("increment_"):
            return 0
        elif (
            name.startswith("update_")
            or name.startswith("reset_")
            or name.startswith("set_")
            or name.startswith("supersede_")
        ):
            return False
        return None

    return noop
