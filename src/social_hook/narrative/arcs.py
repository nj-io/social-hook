"""Arc management with business rules (T19)."""

import logging
import sqlite3
from datetime import datetime, timezone

from social_hook.db import operations as ops
from social_hook.errors import MaxArcsError
from social_hook.filesystem import generate_id
from social_hook.models import Arc, ArcStatus

logger = logging.getLogger(__name__)


def create_arc(
    conn: sqlite3.Connection,
    project_id: str,
    theme: str,
    strategy: str = "",
    max_arcs: int = 3,
) -> str:
    """Create a new active narrative arc, enforcing max active arcs per strategy.

    Args:
        conn: Database connection
        project_id: Project owning the arc
        theme: Theme/topic of the arc
        strategy: Strategy this arc belongs to (default "" for backward compat)
        max_arcs: Maximum active arcs per strategy (default 3)

    Returns:
        The new arc ID

    Raises:
        MaxArcsError: If max active arcs already exist for the strategy
    """
    active = ops.get_active_arcs(conn, project_id, strategy=strategy)
    if len(active) >= max_arcs:
        themes = [a.theme for a in active]
        raise MaxArcsError(
            f"Cannot create arc: {max_arcs} active arcs already exist "
            f"for strategy {strategy!r}: {themes}"
        )

    arc = Arc(
        id=generate_id("arc"),
        project_id=project_id,
        theme=theme,
        strategy=strategy,
    )
    logger.info("Arc %s: created (strategy=%r)", arc.id, strategy)
    return ops.insert_arc(conn, arc)


def propose_arc(
    conn: sqlite3.Connection,
    project_id: str,
    theme: str,
    strategy: str,
    reasoning: str,
) -> str:
    """Create a proposed arc. Does not enforce max active arcs.

    Args:
        conn: Database connection
        project_id: Project owning the arc
        theme: Theme/topic of the arc
        strategy: Strategy this arc belongs to
        reasoning: Evaluator reasoning for the proposal

    Returns:
        The new arc ID
    """
    arc = Arc(
        id=generate_id("arc"),
        project_id=project_id,
        theme=theme,
        strategy=strategy,
        status=ArcStatus.PROPOSED.value,
        reasoning=reasoning,
    )
    logger.info("Arc %s: proposed (strategy=%r)", arc.id, strategy)
    return ops.insert_arc(conn, arc)


def activate_arc(
    conn: sqlite3.Connection,
    arc_id: str,
    max_arcs: int = 3,
) -> bool:
    """Move a proposed arc to active. Enforces max active arcs per strategy.

    Args:
        conn: Database connection
        arc_id: Arc to activate
        max_arcs: Maximum active arcs per strategy (default 3)

    Returns:
        True if the arc was activated

    Raises:
        MaxArcsError: If activating would exceed the strategy limit
        ValueError: If the arc is not found or not in proposed status
    """
    arc = ops.get_arc(conn, arc_id)
    if arc is None:
        raise ValueError(f"Arc not found: {arc_id}")
    if arc.status != ArcStatus.PROPOSED.value:
        raise ValueError(f"Arc {arc_id} is {arc.status!r}, must be proposed to activate")

    active = ops.get_active_arcs(conn, arc.project_id, strategy=arc.strategy)
    if len(active) >= max_arcs:
        themes = [a.theme for a in active]
        raise MaxArcsError(
            f"Cannot activate arc: {max_arcs} active arcs already exist "
            f"for strategy {arc.strategy!r}: {themes}"
        )

    logger.info("Arc %s: %s -> %s", arc_id, ArcStatus.PROPOSED.value, ArcStatus.ACTIVE.value)
    return ops.update_arc(conn, arc_id, status=ArcStatus.ACTIVE.value)


def abandon_arc(conn: sqlite3.Connection, arc_id: str) -> bool:
    """Move a proposed or active arc to abandoned.

    Args:
        conn: Database connection
        arc_id: Arc to abandon

    Returns:
        True if the arc was abandoned

    Raises:
        ValueError: If the arc is not found or already terminal
    """
    arc = ops.get_arc(conn, arc_id)
    if arc is None:
        raise ValueError(f"Arc not found: {arc_id}")
    if arc.status in (ArcStatus.COMPLETED.value, ArcStatus.ABANDONED.value):
        raise ValueError(f"Arc {arc_id} is already {arc.status!r}")

    logger.info("Arc %s: %s -> %s", arc_id, arc.status, ArcStatus.ABANDONED.value)
    return ops.update_arc(conn, arc_id, status=ArcStatus.ABANDONED.value)


def get_active_arcs(
    conn: sqlite3.Connection,
    project_id: str,
    strategy: str | None = None,
) -> list[Arc]:
    """Get active arcs for a project, optionally filtered by strategy."""
    return ops.get_active_arcs(conn, project_id, strategy=strategy)


def get_arc(conn: sqlite3.Connection, arc_id: str) -> Arc | None:
    """Get a single arc by ID."""
    return ops.get_arc(conn, arc_id)


def increment_arc_post_count(conn: sqlite3.Connection, arc_id: str) -> bool:
    """Increment an arc's post count and update last_post_at.

    Args:
        conn: Database connection
        arc_id: Arc to update

    Returns:
        True if the arc was updated, False if not found
    """
    arc = ops.get_arc(conn, arc_id)
    if arc is None:
        return False
    return ops.update_arc(
        conn,
        arc_id,
        post_count=arc.post_count + 1,
        last_post_at=datetime.now(timezone.utc).isoformat(),
    )


def resume_arc(
    conn: sqlite3.Connection,
    arc_id: str,
    project_id: str,
    strategy: str = "",
    max_arcs: int = 3,
) -> bool:
    """Resume a completed/abandoned arc, enforcing max active arcs per strategy.

    Returns:
        True if the arc was resumed

    Raises:
        MaxArcsError: If max active arcs already exist for the strategy
        ValueError: If the arc is already active or not found
    """
    arc = ops.get_arc(conn, arc_id)
    if arc is None:
        raise ValueError(f"Arc not found: {arc_id}")
    if arc.status == ArcStatus.ACTIVE.value:
        raise ValueError("Arc is already active")

    # Use the arc's own strategy if the caller passes default
    effective_strategy = arc.strategy if strategy == "" else strategy
    active = ops.get_active_arcs(conn, project_id, strategy=effective_strategy)
    if len(active) >= max_arcs:
        themes = [a.theme for a in active]
        raise MaxArcsError(
            f"Cannot resume arc: {max_arcs} active arcs already exist "
            f"for strategy {effective_strategy!r}: {themes}"
        )

    logger.info("Arc %s: %s -> %s", arc_id, arc.status, ArcStatus.ACTIVE.value)
    return ops.update_arc(conn, arc_id, status=ArcStatus.ACTIVE.value)


def update_arc(
    conn: sqlite3.Connection,
    arc_id: str,
    status: str | None = None,
    post_count: int | None = None,
    last_post_at: str | None = None,
    notes: str | None = None,
    strategy: str | None = None,
    reasoning: str | None = None,
) -> bool:
    """Update an arc."""
    return ops.update_arc(
        conn,
        arc_id,
        status=status,
        post_count=post_count,
        last_post_at=last_post_at,
        notes=notes,
        strategy=strategy,
        reasoning=reasoning,
    )
