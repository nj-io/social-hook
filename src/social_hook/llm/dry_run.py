"""DryRunContext: wraps DB operations, skipping writes in dry-run mode.

Thin subclass of the generic ``DryRunProxy`` that targets
``social_hook.db.operations`` and prepends the SQLite connection
as the first argument to every call.
"""

import sqlite3

from social_hook.db import operations as ops
from social_hook.dry_run import DEFAULT_READ_PREFIXES as _READ_PREFIXES  # noqa: F401
from social_hook.dry_run import DryRunProxy


class DryRunContext(DryRunProxy):
    """Wraps db.operations module, skipping writes during dry-run.

    Read operations (get_*) pass through to db.operations with the connection.
    All other operations are skipped when dry_run=True.

    Args:
        conn: SQLite database connection
        dry_run: If True, skip all write operations
    """

    def __init__(self, conn: sqlite3.Connection, dry_run: bool = False) -> None:
        super().__init__(ops, first_arg=conn, dry_run=dry_run)
        self.conn = conn
        self.trigger_source: str = "auto"
