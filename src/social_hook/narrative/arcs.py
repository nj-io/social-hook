"""Arc management with business rules (T19)."""

import sqlite3
from datetime import datetime, timezone

from social_hook.db import operations as ops
from social_hook.errors import MaxArcsError
from social_hook.filesystem import generate_id
from social_hook.models import Arc


def create_arc(conn: sqlite3.Connection, project_id: str, theme: str) -> str:
    """Create a new narrative arc, enforcing max 3 active arcs.

    Args:
        conn: Database connection
        project_id: Project owning the arc
        theme: Theme/topic of the arc

    Returns:
        The new arc ID

    Raises:
        MaxArcsError: If 3 active arcs already exist
    """
    active = ops.get_active_arcs(conn, project_id)
    if len(active) >= 3:
        themes = [a.theme for a in active]
        raise MaxArcsError(
            f"Cannot create arc: 3 active arcs already exist for project {project_id}: {themes}"
        )

    arc = Arc(
        id=generate_id("arc"),
        project_id=project_id,
        theme=theme,
    )
    return ops.insert_arc(conn, arc)


def get_active_arcs(conn: sqlite3.Connection, project_id: str) -> list[Arc]:
    """Get active arcs for a project (max 3)."""
    return ops.get_active_arcs(conn, project_id)


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


def update_arc(
    conn: sqlite3.Connection,
    arc_id: str,
    status: str | None = None,
    post_count: int | None = None,
    last_post_at: str | None = None,
    notes: str | None = None,
) -> bool:
    """Update an arc."""
    return ops.update_arc(
        conn,
        arc_id,
        status=status,
        post_count=post_count,
        last_post_at=last_post_at,
        notes=notes,
    )
