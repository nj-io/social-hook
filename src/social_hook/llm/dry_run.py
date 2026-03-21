"""DryRunContext: wraps DB operations, skipping writes in dry-run mode."""

import logging
import sqlite3
from typing import Any

from social_hook.db import operations as ops

logger = logging.getLogger(__name__)

# Read operations always pass through, even in dry-run.
# Everything else is treated as a write and skipped.
_READ_PREFIXES = ("get_",)


class DryRunContext:
    """Wraps db.operations module, skipping writes during dry-run.

    Read operations (get_*) pass through to db.operations with the connection.
    All other operations are skipped when dry_run=True — no prefix list to maintain.

    Args:
        conn: SQLite database connection
        dry_run: If True, skip all write operations
    """

    def __init__(self, conn: sqlite3.Connection, dry_run: bool = False) -> None:
        self.conn = conn
        self.dry_run = dry_run
        self.trigger_source: str = "auto"

    def __getattr__(self, name: str) -> Any:
        """Delegate to db.operations, intercepting writes in dry-run mode."""
        func = getattr(ops, name, None)
        if func is None:
            raise AttributeError(
                f"'DryRunContext' has no attribute '{name}' (not found in db.operations)"
            )

        if self.dry_run and not name.startswith(_READ_PREFIXES):
            return _make_noop(name, func)

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(self.conn, *args, **kwargs)

        return wrapper


def _make_noop(name: str, func: Any) -> Any:
    """Create a no-op wrapper for a write operation.

    Returns appropriate defaults based on the operation pattern:
    - insert_*: returns the first positional arg's .id if it has one, else None
    - increment_*: returns 0
    - update_*/reset_*/set_*/supersede_*: returns False
    - Others (delete_*, mark_*, cleanup_*, execute_*, emit_*, etc.): returns None
    """

    def noop(*args: Any, **kwargs: Any) -> Any:
        logger.debug("DryRun: skipping %s", name)
        if name.startswith("insert_"):
            if args and hasattr(args[0], "id"):
                return args[0].id
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
