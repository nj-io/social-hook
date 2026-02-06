"""Narrative debt management (T19)."""

import sqlite3

from social_hook.config.project import StrategyConfig
from social_hook.db import operations as ops


def get_narrative_debt(conn: sqlite3.Connection, project_id: str) -> int:
    """Get current narrative debt counter for a project.

    Returns 0 when no record exists (handles None case).
    """
    debt = ops.get_narrative_debt(conn, project_id)
    if debt is None:
        return 0
    return debt.debt_counter


def increment_narrative_debt(conn: sqlite3.Connection, project_id: str) -> int:
    """Increment narrative debt counter.

    Returns the new counter value.
    """
    return ops.increment_narrative_debt(conn, project_id)


def reset_narrative_debt(conn: sqlite3.Connection, project_id: str) -> bool:
    """Reset narrative debt counter to 0.

    Returns True if a row was updated.
    """
    return ops.reset_narrative_debt(conn, project_id)


def is_debt_high(
    conn: sqlite3.Connection,
    project_id: str,
    config: StrategyConfig | None = None,
) -> bool:
    """Check if narrative debt exceeds threshold.

    Args:
        conn: Database connection
        project_id: Project to check
        config: Strategy config with threshold (default 3)

    Returns:
        True if debt counter > threshold
    """
    if config is None:
        config = StrategyConfig()
    debt = get_narrative_debt(conn, project_id)
    return debt > config.narrative_debt_threshold
