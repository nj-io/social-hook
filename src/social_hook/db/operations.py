"""Database CRUD operations."""

import json
import logging
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)

from social_hook.models import (
    Arc,
    Decision,
    Draft,
    DraftChange,
    DraftTweet,
    Lifecycle,
    NarrativeDebt,
    Post,
    Project,
    UsageLog,
)

# =============================================================================
# Schema Version
# =============================================================================


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Get current schema version."""
    result = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()
    return result[0] if result else 0


# =============================================================================
# Projects
# =============================================================================


def insert_project(conn: sqlite3.Connection, project: Project) -> str:
    """Insert a new project.

    Returns the project ID.
    """
    conn.execute(
        """
        INSERT INTO projects (id, name, repo_path, repo_origin, summary, summary_updated_at, audience_introduced, paused)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        project.to_row(),
    )
    conn.commit()
    return project.id


def get_project(conn: sqlite3.Connection, project_id: str) -> Project | None:
    """Get a project by ID."""
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row:
        return Project.from_dict(dict(row))
    return None


def get_all_projects(conn: sqlite3.Connection) -> list[Project]:
    """Get all projects."""
    rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    return [Project.from_dict(dict(row)) for row in rows]


def get_project_by_path(conn: sqlite3.Connection, repo_path: str) -> Project | None:
    """Get a project by its repository path."""
    row = conn.execute("SELECT * FROM projects WHERE repo_path = ?", (repo_path,)).fetchone()
    if row:
        return Project.from_dict(dict(row))
    return None


def get_project_by_origin(conn: sqlite3.Connection, repo_origin: str) -> list[Project]:
    """Get projects by their git remote origin."""
    rows = conn.execute("SELECT * FROM projects WHERE repo_origin = ?", (repo_origin,)).fetchall()
    return [Project.from_dict(dict(row)) for row in rows]


def set_project_paused(conn: sqlite3.Connection, project_id: str, paused: bool) -> None:
    """Set a project's paused state."""
    conn.execute(
        "UPDATE projects SET paused = ? WHERE id = ?",
        (1 if paused else 0, project_id),
    )
    conn.commit()


def set_project_trigger_branch(
    conn: sqlite3.Connection, project_id: str, branch: str | None
) -> None:
    """Set trigger branch filter. None = all branches."""
    conn.execute(
        "UPDATE projects SET trigger_branch = ? WHERE id = ?",
        (branch, project_id),
    )
    conn.commit()


def delete_project(conn: sqlite3.Connection, project_id: str) -> bool:
    """Delete a project and all associated data.

    Uses explicit ordered deletes (not ON DELETE CASCADE) for safety.
    Deletes: narrative_debt, lifecycles, arcs, draft_changes (via drafts),
    draft_tweets (via drafts), posts (via drafts), drafts, decisions, then project.

    Returns True if the project was deleted.
    """
    # Check project exists
    row = conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        return False

    # Get all draft IDs for this project (needed for child table cleanup)
    draft_rows = conn.execute(
        "SELECT id FROM drafts WHERE project_id = ?", (project_id,)
    ).fetchall()
    draft_ids = [r[0] for r in draft_rows]

    # Delete in dependency order
    for draft_id in draft_ids:
        conn.execute("DELETE FROM draft_changes WHERE draft_id = ?", (draft_id,))
        conn.execute("DELETE FROM draft_tweets WHERE draft_id = ?", (draft_id,))

    conn.execute("DELETE FROM posts WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM drafts WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM decisions WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM narrative_debt WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM arcs WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM lifecycles WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM usage_log WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM milestone_summaries WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    return True


def delete_decision(conn: sqlite3.Connection, decision_id: str) -> bool:
    """Delete a decision and all associated data.

    Cascades to: draft_changes, draft_tweets, posts, drafts for this decision.
    Returns True if the decision was deleted.
    """
    row = conn.execute("SELECT id FROM decisions WHERE id = ?", (decision_id,)).fetchone()
    if not row:
        return False

    # Get all draft IDs for this decision
    draft_rows = conn.execute(
        "SELECT id FROM drafts WHERE decision_id = ?", (decision_id,)
    ).fetchall()
    draft_ids = [r[0] for r in draft_rows]

    # Delete in dependency order
    for draft_id in draft_ids:
        conn.execute("DELETE FROM draft_changes WHERE draft_id = ?", (draft_id,))
        conn.execute("DELETE FROM draft_tweets WHERE draft_id = ?", (draft_id,))

    conn.execute(
        "DELETE FROM posts WHERE draft_id IN (SELECT id FROM drafts WHERE decision_id = ?)",
        (decision_id,),
    )
    conn.execute("DELETE FROM drafts WHERE decision_id = ?", (decision_id,))
    conn.execute("DELETE FROM decisions WHERE id = ?", (decision_id,))
    conn.commit()
    return True


def update_discovery_files(
    conn: sqlite3.Connection,
    project_id: str,
    files: list[str],
) -> bool:
    """Update project discovery files.

    Stores the list of files selected during two-pass project discovery
    as a JSON-serialized string.

    Args:
        conn: Database connection
        project_id: Project ID to update
        files: List of file paths selected by discovery

    Returns True if a row was updated.
    """
    cursor = conn.execute(
        "UPDATE projects SET discovery_files = ? WHERE id = ?",
        (json.dumps(files), project_id),
    )
    conn.commit()
    return cursor.rowcount > 0


# =============================================================================
# Decisions
# =============================================================================


def insert_decision(conn: sqlite3.Connection, decision: Decision) -> str:
    """Insert a new decision.

    Returns the decision ID.
    """
    conn.execute(
        """
        INSERT INTO decisions (id, project_id, commit_hash, commit_message,
            decision, reasoning, angle, episode_type, episode_tags, post_category,
            arc_id, media_tool, platforms, targets, commit_summary, consolidate_with,
            branch)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        decision.to_row(),
    )
    conn.commit()
    return decision.id


def get_decision(conn: sqlite3.Connection, decision_id: str) -> Decision | None:
    """Get a decision by ID."""
    row = conn.execute("SELECT * FROM decisions WHERE id = ?", (decision_id,)).fetchone()
    if row:
        return Decision.from_dict(dict(row))
    return None


def get_recent_decisions(
    conn: sqlite3.Connection, project_id: str, limit: int = 30
) -> list[Decision]:
    """Get recent decisions for a project."""
    rows = conn.execute(
        """
        SELECT * FROM decisions
        WHERE project_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (project_id, limit),
    ).fetchall()
    return [Decision.from_dict(dict(row)) for row in rows]


def get_all_recent_decisions(conn: sqlite3.Connection, limit: int = 30) -> list[Decision]:
    """Get recent decisions across all projects.

    Cross-project query for the `log` command without project filter.
    """
    rows = conn.execute(
        """
        SELECT * FROM decisions
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [Decision.from_dict(dict(row)) for row in rows]


def get_recent_decisions_for_llm(
    conn: sqlite3.Connection, project_id: str, limit: int = 30
) -> list[Decision]:
    """Get recent decisions for a project, excluding imported commits.

    Used only by LLM context callers (evaluator, gatekeeper) to avoid
    polluting the model's context with historical imports.
    """
    rows = conn.execute(
        """
        SELECT * FROM decisions
        WHERE project_id = ? AND decision != 'imported'
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (project_id, limit),
    ).fetchall()
    return [Decision.from_dict(dict(row)) for row in rows]


def insert_decisions_batch(
    conn: sqlite3.Connection,
    decisions: list[tuple[Decision, str]],
) -> int:
    """Batch insert decisions with explicit created_at timestamps.

    Uses INSERT OR IGNORE to skip duplicates (UNIQUE on project_id, commit_hash).

    Args:
        conn: Database connection
        decisions: List of (Decision, iso_created_at) tuples

    Returns:
        Number of rows actually inserted.
    """
    if not decisions:
        return 0
    before = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
    conn.executemany(
        """
        INSERT OR IGNORE INTO decisions (id, project_id, commit_hash, commit_message,
            decision, reasoning, angle, episode_type, episode_tags, post_category,
            arc_id, media_tool, platforms, targets, commit_summary, consolidate_with,
            branch, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [d.to_row() + (created_at,) for d, created_at in decisions],
    )
    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
    return after - before


def get_distinct_branches(conn: sqlite3.Connection, project_id: str) -> list[str]:
    """Get sorted distinct branch names from decisions for a project."""
    rows = conn.execute(
        """
        SELECT DISTINCT branch FROM decisions
        WHERE project_id = ? AND branch IS NOT NULL
        ORDER BY branch
        """,
        (project_id,),
    ).fetchall()
    return [row[0] for row in rows]


def get_held_decisions(
    conn: sqlite3.Connection, project_id: str, limit: int = 20
) -> list[Decision]:
    """Get unprocessed hold/consolidate/deferred decisions for a project.

    Uses partial index idx_decisions_unprocessed for efficient lookup.

    Args:
        conn: Database connection
        project_id: Project ID to query
        limit: Maximum decisions to return (batch_size)

    Returns:
        List of unprocessed Decision objects, oldest first
    """
    rows = conn.execute(
        """
        SELECT * FROM decisions
        WHERE project_id = ?
          AND decision = 'hold'
          AND processed = 0
        ORDER BY created_at ASC
        LIMIT ?
        """,
        (project_id, limit),
    ).fetchall()
    return [Decision.from_dict(dict(row)) for row in rows]


def mark_decisions_processed(
    conn: sqlite3.Connection, decision_ids: list[str], batch_id: str
) -> int:
    """Mark decisions as processed with a batch ID.

    Args:
        conn: Database connection
        decision_ids: List of decision IDs to mark
        batch_id: Batch identifier for this processing run

    Returns:
        Number of rows updated
    """
    if not decision_ids:
        return 0

    placeholders = ",".join("?" for _ in decision_ids)
    cursor = conn.execute(
        f"""
        UPDATE decisions
        SET processed = 1, processed_at = datetime('now'), batch_id = ?
        WHERE id IN ({placeholders})
        """,
        [batch_id] + decision_ids,
    )
    conn.commit()
    return cursor.rowcount


def update_decision(
    conn: sqlite3.Connection,
    decision_id: str,
    decision: str | None = None,
    reasoning: str | None = None,
    angle: str | None = None,
    episode_type: str | None = None,
    post_category: str | None = None,
    arc_id: str | None = None,
    media_tool: str | None = None,
    platforms: str | None = None,
    episode_tags: list[str] | None = None,
    targets: dict | None = None,
    consolidate_with: list[str] | None = None,
) -> bool:
    """Update a decision row.

    Used by consolidation re-evaluate to upgrade a decision to draft.

    Returns True if a row was updated.
    """
    updates: list[str] = []
    params: list[Any] = []

    if decision is not None:
        updates.append("decision = ?")
        params.append(decision)
    if reasoning is not None:
        updates.append("reasoning = ?")
        params.append(reasoning)
    if angle is not None:
        updates.append("angle = ?")
        params.append(angle)
    if episode_type is not None:
        updates.append("episode_type = ?")
        params.append(episode_type)
    if post_category is not None:
        updates.append("post_category = ?")
        params.append(post_category)
    if arc_id is not None:
        updates.append("arc_id = ?")
        params.append(arc_id)
    if media_tool is not None:
        updates.append("media_tool = ?")
        params.append(media_tool)
    if platforms is not None:
        updates.append("platforms = ?")
        params.append(platforms)
    if episode_tags is not None:
        updates.append("episode_tags = ?")
        params.append(json.dumps(episode_tags))
    if targets is not None:
        updates.append("targets = ?")
        params.append(json.dumps(targets))
    if consolidate_with is not None:
        updates.append("consolidate_with = ?")
        params.append(json.dumps(consolidate_with))

    if not updates:
        return False

    params.append(decision_id)
    cursor = conn.execute(
        f"UPDATE decisions SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    conn.commit()
    return cursor.rowcount > 0


# =============================================================================
# Drafts
# =============================================================================


def insert_draft(conn: sqlite3.Connection, draft: Draft) -> str:
    """Insert a new draft.

    Returns the draft ID.
    """
    conn.execute(
        """
        INSERT INTO drafts (id, project_id, decision_id, platform, status, content,
            media_paths, media_type, media_spec, media_spec_used, suggested_time, scheduled_time,
            reasoning, superseded_by, retry_count, last_error, is_intro, post_format, reference_post_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        draft.to_row(),
    )
    conn.commit()
    return draft.id


def get_draft(conn: sqlite3.Connection, draft_id: str) -> Draft | None:
    """Get a draft by ID."""
    row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    if row:
        return Draft.from_dict(dict(row))
    return None


def update_draft(
    conn: sqlite3.Connection,
    draft_id: str,
    status: str | None = None,
    content: str | None = None,
    scheduled_time: str | None = None,
    retry_count: int | None = None,
    last_error: str | None = None,
    media_paths: list[str] | None = None,
    media_type: str | None = None,
    media_spec: dict | None = None,
    media_spec_used: dict | None = None,
    is_intro: bool | None = None,
    post_format: str | None = None,
    reference_post_id: str | None = None,
) -> bool:
    """Update a draft.

    Returns True if a row was updated.
    """
    updates: list[str] = []
    params: list[Any] = []

    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if content is not None:
        updates.append("content = ?")
        params.append(content)
    if scheduled_time is not None:
        updates.append("scheduled_time = ?")
        params.append(scheduled_time)
    if retry_count is not None:
        updates.append("retry_count = ?")
        params.append(retry_count)
    if last_error is not None:
        updates.append("last_error = ?")
        params.append(last_error)
    if media_paths is not None:
        updates.append("media_paths = ?")
        params.append(json.dumps(media_paths))
    if media_type is not None:
        updates.append("media_type = ?")
        params.append(media_type)
    if media_spec is not None:
        updates.append("media_spec = ?")
        params.append(json.dumps(media_spec))
    if media_spec_used is not None:
        updates.append("media_spec_used = ?")
        params.append(json.dumps(media_spec_used))
    if is_intro is not None:
        updates.append("is_intro = ?")
        params.append(1 if is_intro else 0)
    if post_format is not None:
        updates.append("post_format = ?")
        params.append(post_format)
    if reference_post_id is not None:
        updates.append("reference_post_id = ?")
        params.append(reference_post_id)

    if not updates:
        return False

    updates.append("updated_at = datetime('now')")
    params.append(draft_id)

    cursor = conn.execute(
        f"UPDATE drafts SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    conn.commit()
    return cursor.rowcount > 0


def supersede_draft(conn: sqlite3.Connection, old_draft_id: str, new_draft_id: str) -> bool:
    """Mark a draft as superseded by another.

    Returns True if a row was updated.
    """
    cursor = conn.execute(
        """
        UPDATE drafts
        SET status = 'superseded', superseded_by = ?, updated_at = datetime('now')
        WHERE id = ?
        """,
        (new_draft_id, old_draft_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def get_pending_drafts(conn: sqlite3.Connection, project_id: str) -> list[Draft]:
    """Get pending drafts for a project."""
    rows = conn.execute(
        """
        SELECT * FROM drafts
        WHERE project_id = ?
          AND status IN ('draft', 'approved', 'scheduled', 'deferred')
        ORDER BY created_at DESC
        """,
        (project_id,),
    ).fetchall()
    return [Draft.from_dict(dict(row)) for row in rows]


def get_all_pending_drafts(conn: sqlite3.Connection) -> list[Draft]:
    """Get all pending drafts across all projects."""
    rows = conn.execute(
        """
        SELECT * FROM drafts
        WHERE status IN ('draft', 'approved', 'scheduled', 'deferred')
        ORDER BY created_at DESC
        """
    ).fetchall()
    return [Draft.from_dict(dict(row)) for row in rows]


def get_drafts_filtered(
    conn: sqlite3.Connection,
    status: str | None = None,
    project_id: str | None = None,
    decision_id: str | None = None,
    commit_hash: str | None = None,
) -> list[Draft]:
    """Get drafts with optional status, project, decision, and commit filters."""
    clauses, params = [], []
    need_join = commit_hash is not None
    if status:
        clauses.append("d.status = ?")
        params.append(status)
    if project_id:
        clauses.append("d.project_id = ?")
        params.append(project_id)
    if decision_id:
        clauses.append("d.decision_id = ?")
        params.append(decision_id)
    if commit_hash:
        clauses.append("dec.commit_hash = ?")
        params.append(commit_hash)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    if need_join:
        sql = f"SELECT d.* FROM drafts d JOIN decisions dec ON d.decision_id = dec.id{where} ORDER BY d.created_at DESC"
    else:
        sql = f"SELECT d.* FROM drafts d{where} ORDER BY d.created_at DESC"
    rows = conn.execute(sql, params).fetchall()
    return [Draft.from_dict(dict(row)) for row in rows]


def get_due_drafts(conn: sqlite3.Connection) -> list[Draft]:
    """Get drafts that are scheduled and due for posting.

    Returns drafts where status='scheduled' and scheduled_time <= now,
    ordered by scheduled_time ascending (FIFO).
    """
    rows = conn.execute(
        """
        SELECT * FROM drafts
        WHERE status = 'scheduled'
          AND scheduled_time <= datetime('now')
        ORDER BY scheduled_time ASC
        """
    ).fetchall()
    return [Draft.from_dict(dict(row)) for row in rows]


def get_deferred_drafts(conn: sqlite3.Connection) -> list[Draft]:
    """Get all deferred drafts, ordered by creation time (FIFO)."""
    rows = conn.execute(
        """
        SELECT * FROM drafts
        WHERE status = 'deferred'
        ORDER BY created_at ASC
        """
    ).fetchall()
    return [Draft.from_dict(dict(row)) for row in rows]


# =============================================================================
# Draft Tweets
# =============================================================================


def insert_draft_tweet(conn: sqlite3.Connection, tweet: DraftTweet) -> str:
    """Insert a new draft tweet.

    Returns the tweet ID.
    """
    conn.execute(
        """
        INSERT INTO draft_tweets (id, draft_id, position, content, media_paths, external_id, posted_at, error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        tweet.to_row(),
    )
    conn.commit()
    return tweet.id


def get_draft_tweets(conn: sqlite3.Connection, draft_id: str) -> list[DraftTweet]:
    """Get all tweets for a draft thread."""
    rows = conn.execute(
        """
        SELECT * FROM draft_tweets
        WHERE draft_id = ?
        ORDER BY position ASC
        """,
        (draft_id,),
    ).fetchall()
    return [DraftTweet.from_dict(dict(row)) for row in rows]


def update_draft_tweet(
    conn: sqlite3.Connection,
    tweet_id: str,
    external_id: str | None = None,
    posted_at: str | None = None,
    error: str | None = None,
) -> bool:
    """Update a draft tweet after posting.

    Args:
        conn: Database connection
        tweet_id: Draft tweet ID
        external_id: External tweet ID from platform
        posted_at: ISO datetime when posted
        error: Error message if posting failed

    Returns:
        True if a row was updated.
    """
    updates: list[str] = []
    params: list[Any] = []

    if external_id is not None:
        updates.append("external_id = ?")
        params.append(external_id)
    if posted_at is not None:
        updates.append("posted_at = ?")
        params.append(posted_at)
    if error is not None:
        updates.append("error = ?")
        params.append(error)

    if not updates:
        return False

    params.append(tweet_id)

    cursor = conn.execute(
        f"UPDATE draft_tweets SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    conn.commit()
    return cursor.rowcount > 0


# =============================================================================
# Draft Changes
# =============================================================================


def insert_draft_change(conn: sqlite3.Connection, change: DraftChange) -> str:
    """Insert a draft change audit entry.

    Returns the change ID.
    """
    conn.execute(
        """
        INSERT INTO draft_changes (id, draft_id, field, old_value, new_value, changed_by)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        change.to_row(),
    )
    conn.commit()
    return change.id


def get_draft_changes(conn: sqlite3.Connection, draft_id: str) -> list[DraftChange]:
    """Get all changes for a draft."""
    rows = conn.execute(
        """
        SELECT * FROM draft_changes
        WHERE draft_id = ?
        ORDER BY changed_at DESC
        """,
        (draft_id,),
    ).fetchall()
    return [DraftChange.from_dict(dict(row)) for row in rows]


# =============================================================================
# Posts
# =============================================================================


def insert_post(conn: sqlite3.Connection, post: Post) -> str:
    """Insert a new post.

    Returns the post ID.
    """
    conn.execute(
        """
        INSERT INTO posts (id, draft_id, project_id, platform, external_id, external_url, content)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        post.to_row(),
    )
    conn.commit()
    return post.id


def get_recent_posts(conn: sqlite3.Connection, project_id: str, days: int = 7) -> list[Post]:
    """Get recent posts for a project within a time window.

    Use case: Scheduling coordination - what was posted recently.
    For context assembly, use get_recent_posts_for_context() instead.
    """
    rows = conn.execute(
        """
        SELECT * FROM posts
        WHERE project_id = ?
          AND posted_at >= datetime('now', '-' || ? || ' days')
        ORDER BY posted_at DESC
        """,
        (project_id, days),
    ).fetchall()
    return [Post.from_dict(dict(row)) for row in rows]


def get_recent_posts_for_context(
    conn: sqlite3.Connection, project_id: str, limit: int = 15
) -> list[Post]:
    """Get recent posts for LLM context assembly.

    Use case: Providing historical posts to LLM for voice consistency
    and avoiding repetition. Count-based (last N posts regardless of date).

    Args:
        conn: Database connection
        project_id: Project ID to query
        limit: Maximum posts to return (default: 15, per CONTEXT_MEMORY_ANALYSIS.md)
    """
    rows = conn.execute(
        """
        SELECT * FROM posts
        WHERE project_id = ?
        ORDER BY posted_at DESC
        LIMIT ?
        """,
        (project_id, limit),
    ).fetchall()
    return [Post.from_dict(dict(row)) for row in rows]


def get_all_recent_posts(conn: sqlite3.Connection, since_datetime: str) -> list[Post]:
    """Get recent posts across all projects since a given datetime.

    Cross-project query for scheduling coordination.

    Args:
        since_datetime: ISO datetime string (UTC). Posts at or after this time are returned.
    """
    rows = conn.execute(
        """
        SELECT * FROM posts
        WHERE posted_at >= ?
        ORDER BY posted_at DESC
        """,
        (since_datetime,),
    ).fetchall()
    return [Post.from_dict(dict(row)) for row in rows]


# =============================================================================
# Lifecycles
# =============================================================================


def insert_lifecycle(conn: sqlite3.Connection, lifecycle: Lifecycle) -> str:
    """Insert a new lifecycle.

    Returns the project ID.
    """
    conn.execute(
        """
        INSERT INTO lifecycles (project_id, phase, confidence, evidence, last_strategy_moment)
        VALUES (?, ?, ?, ?, ?)
        """,
        lifecycle.to_row(),
    )
    conn.commit()
    return lifecycle.project_id


def get_lifecycle(conn: sqlite3.Connection, project_id: str) -> Lifecycle | None:
    """Get lifecycle for a project."""
    row = conn.execute("SELECT * FROM lifecycles WHERE project_id = ?", (project_id,)).fetchone()
    if row:
        return Lifecycle.from_dict(dict(row))
    return None


def update_lifecycle(
    conn: sqlite3.Connection,
    project_id: str,
    phase: str | None = None,
    confidence: float | None = None,
    evidence: list[str] | None = None,
    last_strategy_moment: str | None = None,
) -> bool:
    """Update a lifecycle.

    Returns True if a row was updated.
    """
    updates: list[str] = []
    params: list[Any] = []

    if phase is not None:
        updates.append("phase = ?")
        params.append(phase)
    if confidence is not None:
        updates.append("confidence = ?")
        params.append(confidence)
    if evidence is not None:
        updates.append("evidence = ?")
        params.append(json.dumps(evidence))
    if last_strategy_moment is not None:
        updates.append("last_strategy_moment = ?")
        params.append(last_strategy_moment)

    if not updates:
        return False

    updates.append("updated_at = datetime('now')")
    params.append(project_id)

    cursor = conn.execute(
        f"UPDATE lifecycles SET {', '.join(updates)} WHERE project_id = ?",
        params,
    )
    conn.commit()
    return cursor.rowcount > 0


# =============================================================================
# Arcs
# =============================================================================


def insert_arc(conn: sqlite3.Connection, arc: Arc) -> str:
    """Insert a new arc.

    Returns the arc ID.
    """
    conn.execute(
        """
        INSERT INTO arcs (id, project_id, theme, status, post_count, last_post_at, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        arc.to_row(),
    )
    conn.commit()
    return arc.id


def update_arc(
    conn: sqlite3.Connection,
    arc_id: str,
    status: str | None = None,
    post_count: int | None = None,
    last_post_at: str | None = None,
    notes: str | None = None,
) -> bool:
    """Update an arc.

    Returns True if a row was updated.
    """
    updates: list[str] = []
    params: list[Any] = []

    if status is not None:
        updates.append("status = ?")
        params.append(status)
        # Set ended_at for terminal statuses
        if status in ("completed", "abandoned"):
            updates.append("ended_at = datetime('now')")
    if post_count is not None:
        updates.append("post_count = ?")
        params.append(post_count)
    if last_post_at is not None:
        updates.append("last_post_at = ?")
        params.append(last_post_at)
    if notes is not None:
        updates.append("notes = ?")
        params.append(notes)

    if not updates:
        return False

    updates.append("updated_at = datetime('now')")
    params.append(arc_id)

    cursor = conn.execute(
        f"UPDATE arcs SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    conn.commit()
    return cursor.rowcount > 0


def get_active_arcs(conn: sqlite3.Connection, project_id: str) -> list[Arc]:
    """Get active arcs for a project (max 3)."""
    rows = conn.execute(
        """
        SELECT * FROM arcs
        WHERE project_id = ? AND status = 'active'
        ORDER BY started_at DESC
        LIMIT 3
        """,
        (project_id,),
    ).fetchall()
    return [Arc.from_dict(dict(row)) for row in rows]


def get_arc(conn: sqlite3.Connection, arc_id: str) -> Arc | None:
    """Get a single arc by ID."""
    row = conn.execute("SELECT * FROM arcs WHERE id = ?", (arc_id,)).fetchone()
    if row:
        return Arc.from_dict(dict(row))
    return None


def get_arcs_by_project(
    conn: sqlite3.Connection, project_id: str, status: str | None = None
) -> list[Arc]:
    """Get arcs for a project, optionally filtered by status.

    Unlike get_active_arcs(), this returns all arcs without a LIMIT.

    Args:
        conn: Database connection
        project_id: Project to query
        status: Filter by status ('active', 'completed', 'abandoned'), or None for all
    """
    if status:
        rows = conn.execute(
            "SELECT * FROM arcs WHERE project_id = ? AND status = ? ORDER BY started_at DESC",
            (project_id, status),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM arcs WHERE project_id = ? ORDER BY started_at DESC",
            (project_id,),
        ).fetchall()
    return [Arc.from_dict(dict(row)) for row in rows]


def get_arc_posts(conn: sqlite3.Connection, arc_id: str) -> list[Post]:
    """Get published posts belonging to a specific arc.

    Traces: decisions (arc_id) → drafts (decision_id) → posts (draft_id).
    Used by Drafter context assembly when post_category == 'arc'.
    """
    rows = conn.execute(
        """
        SELECT p.* FROM posts p
        JOIN drafts d ON p.draft_id = d.id
        JOIN decisions dec ON d.decision_id = dec.id
        WHERE dec.arc_id = ?
        ORDER BY p.posted_at DESC
        """,
        (arc_id,),
    ).fetchall()
    return [Post.from_dict(dict(row)) for row in rows]


# =============================================================================
# Onboarding
# =============================================================================


def get_audience_introduced(conn: sqlite3.Connection, project_id: str) -> bool:
    """Check if the audience has been introduced for a project."""
    row = conn.execute(
        "SELECT audience_introduced FROM projects WHERE id = ?", (project_id,)
    ).fetchone()
    if row:
        return bool(row[0])
    return False


def set_audience_introduced(conn: sqlite3.Connection, project_id: str, value: bool) -> bool:
    """Update the audience_introduced flag for a project.

    Returns True if a row was updated.
    """
    cursor = conn.execute(
        "UPDATE projects SET audience_introduced = ? WHERE id = ?",
        (1 if value else 0, project_id),
    )
    conn.commit()
    return cursor.rowcount > 0


# =============================================================================
# Narrative Debt
# =============================================================================


def insert_narrative_debt(conn: sqlite3.Connection, debt: NarrativeDebt) -> str:
    """Insert narrative debt record.

    Returns the project ID.
    """
    conn.execute(
        """
        INSERT INTO narrative_debt (project_id, debt_counter, last_synthesis_at)
        VALUES (?, ?, ?)
        """,
        debt.to_row(),
    )
    conn.commit()
    return debt.project_id


def get_narrative_debt(conn: sqlite3.Connection, project_id: str) -> NarrativeDebt | None:
    """Get narrative debt for a project."""
    row = conn.execute(
        "SELECT * FROM narrative_debt WHERE project_id = ?", (project_id,)
    ).fetchone()
    if row:
        return NarrativeDebt.from_dict(dict(row))
    return None


def increment_narrative_debt(conn: sqlite3.Connection, project_id: str) -> int:
    """Increment narrative debt counter.

    Returns the new counter value.
    """
    conn.execute(
        """
        INSERT INTO narrative_debt (project_id, debt_counter)
        VALUES (?, 1)
        ON CONFLICT(project_id) DO UPDATE SET
            debt_counter = narrative_debt.debt_counter + 1
        """,
        (project_id,),
    )
    conn.commit()

    row = conn.execute(
        "SELECT debt_counter FROM narrative_debt WHERE project_id = ?", (project_id,)
    ).fetchone()
    return row[0] if row else 1


def reset_narrative_debt(conn: sqlite3.Connection, project_id: str) -> bool:
    """Reset narrative debt counter to 0.

    Returns True if a row was updated.
    """
    cursor = conn.execute(
        """
        UPDATE narrative_debt
        SET debt_counter = 0, last_synthesis_at = datetime('now')
        WHERE project_id = ?
        """,
        (project_id,),
    )
    conn.commit()
    return cursor.rowcount > 0


# =============================================================================
# Usage Log
# =============================================================================


def insert_usage(conn: sqlite3.Connection, usage: UsageLog) -> str:
    """Insert usage log entry.

    Returns the usage ID.
    """
    conn.execute(
        """
        INSERT INTO usage_log (id, project_id, operation_type, model, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, cost_cents, commit_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        usage.to_row(),
    )
    conn.commit()
    return usage.id


def get_usage_summary(conn: sqlite3.Connection, days: int = 30) -> list[dict]:
    """Get aggregated usage summary by model.

    Returns list of dicts with model, total_input, total_output, total_cost_cents.
    """
    rows = conn.execute(
        """
        SELECT
            model,
            SUM(input_tokens) as total_input,
            SUM(output_tokens) as total_output,
            SUM(cost_cents) as total_cost_cents
        FROM usage_log
        WHERE created_at >= datetime('now', '-' || ? || ' days')
        GROUP BY model
        """,
        (days,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_recent_usage(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    """Get recent individual usage log entries.

    Returns list of dicts with operation details, project name, and commit hash.
    """
    rows = conn.execute(
        """
        SELECT
            u.id,
            u.operation_type,
            u.model,
            u.input_tokens,
            u.output_tokens,
            u.cost_cents,
            u.commit_hash,
            u.created_at,
            p.name as project_name
        FROM usage_log u
        LEFT JOIN projects p ON u.project_id = p.id
        ORDER BY u.created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


# =============================================================================
# Project Summary
# =============================================================================


def update_project_summary(
    conn: sqlite3.Connection,
    project_id: str,
    summary: str,
) -> bool:
    """Update project summary.

    Called by Evaluator when it determines summary needs refresh.
    Updates both summary content and summary_updated_at timestamp.

    Returns True if a row was updated.
    """
    cursor = conn.execute(
        """
        UPDATE projects
        SET summary = ?, summary_updated_at = datetime('now')
        WHERE id = ?
        """,
        (summary, project_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def get_project_summary(conn: sqlite3.Connection, project_id: str) -> str | None:
    """Get project summary for Gatekeeper context injection.

    Returns the summary text, or None if no summary exists.
    """
    row = conn.execute("SELECT summary FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row and row[0]:
        return str(row[0])
    return None


def get_summary_freshness(conn: sqlite3.Connection, project_id: str) -> dict:
    """Get summary freshness indicators for Evaluator judgment.

    Returns dict with:
    - summary_updated_at: ISO timestamp of last update (or None)
    - commits_since_summary: count of decisions since last summary update (inclusive of same-second;
      uses >= to avoid SQLite datetime('now') second-precision timing issues)
    - days_since_summary: days since last summary update (or None if never)
    """
    row = conn.execute(
        """
        SELECT
            summary_updated_at,
            (SELECT COUNT(*) FROM decisions
             WHERE project_id = ?
               AND created_at >= COALESCE(p.summary_updated_at, '1970-01-01')) as commits_since
        FROM projects p
        WHERE id = ?
        """,
        (project_id, project_id),
    ).fetchone()

    if not row:
        return {"summary_updated_at": None, "commits_since_summary": 0, "days_since_summary": None}

    summary_updated_at = row[0]
    commits_since = row[1] or 0

    days_since = None
    if summary_updated_at:
        # Calculate days since summary
        result = conn.execute(
            "SELECT julianday('now') - julianday(?)", (summary_updated_at,)
        ).fetchone()
        days_since = int(result[0]) if result else None

    return {
        "summary_updated_at": summary_updated_at,
        "commits_since_summary": commits_since,
        "days_since_summary": days_since,
    }


# =============================================================================
# Milestone Summaries (Compaction)
# =============================================================================


def insert_milestone_summary(conn: sqlite3.Connection, summary: dict) -> str:
    """Insert a milestone summary.

    Note: Uses dict rather than dataclass because the compaction system
    is not yet built. A MilestoneSummary dataclass will be added when
    the compaction orchestration is implemented in a later workstream.

    Args:
        summary: Dict with id, project_id, milestone_type, summary, items_covered,
                 token_count, period_start, period_end

    Returns the summary ID.
    """
    conn.execute(
        """
        INSERT INTO milestone_summaries
        (id, project_id, milestone_type, summary, items_covered, token_count, period_start, period_end)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            summary["id"],
            summary["project_id"],
            summary["milestone_type"],
            summary["summary"],
            json.dumps(summary.get("items_covered", [])),
            summary.get("token_count", 0),
            summary["period_start"],
            summary["period_end"],
        ),
    )
    conn.commit()
    return str(summary["id"])


def get_milestone_summaries(
    conn: sqlite3.Connection, project_id: str, since_days: int = 180
) -> list[dict]:
    """Get milestone summaries for a project.

    Args:
        project_id: Project ID to query
        since_days: How far back to look (default: 180 days / 6 months)

    Returns list of summary dicts.
    """
    rows = conn.execute(
        """
        SELECT * FROM milestone_summaries
        WHERE project_id = ?
          AND created_at >= datetime('now', '-' || ? || ' days')
        ORDER BY created_at DESC
        """,
        (project_id, since_days),
    ).fetchall()
    return [dict(row) for row in rows]


# =============================================================================
# Chat Messages
# =============================================================================


def insert_chat_message(conn: sqlite3.Connection, chat_id: str, role: str, content: str) -> int:
    """Insert a chat message. Returns row ID."""
    cursor = conn.execute(
        """
        INSERT INTO chat_messages (chat_id, role, content)
        VALUES (?, ?, ?)
        """,
        (chat_id, role, content),
    )
    conn.commit()
    return cursor.lastrowid or 0


def get_recent_chat_messages(
    conn: sqlite3.Connection,
    chat_id: str,
    time_window_minutes: int = 15,
    limit: int = 50,
) -> list[dict]:
    """Fetch recent chat messages for a chat, newest first.

    Returns list of dicts with keys: role, content, created_at.
    """
    rows = conn.execute(
        """
        SELECT role, content, created_at FROM chat_messages
        WHERE chat_id = ?
          AND created_at >= datetime('now', ?)
        ORDER BY id DESC
        LIMIT ?
        """,
        (chat_id, f"-{time_window_minutes} minutes", limit),
    ).fetchall()
    return [dict(row) for row in rows]


def cleanup_old_chat_messages(conn: sqlite3.Connection, days: int = 7) -> int:
    """Delete chat messages older than N days. Returns rows deleted."""
    cursor = conn.execute(
        """
        DELETE FROM chat_messages
        WHERE created_at < datetime('now', ?)
        """,
        (f"-{days} days",),
    )
    conn.commit()
    return cursor.rowcount


# =============================================================================
# Data Events (WebSocket broadcast)
# =============================================================================


# =============================================================================
# Evaluator Rework Operations
# =============================================================================


def get_post(conn: sqlite3.Connection, post_id: str) -> Post | None:
    """Get a single post by ID."""
    row = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    if row:
        return Post.from_dict(dict(row))
    return None


def get_drafts_in_time_window(
    conn: sqlite3.Connection, project_id: str, hours: float
) -> list[Draft]:
    """Get pending drafts created within the last N hours."""
    rows = conn.execute(
        """
        SELECT * FROM drafts
        WHERE project_id = ?
          AND status IN ('draft', 'approved', 'scheduled')
          AND created_at >= datetime('now', ?)
        ORDER BY created_at DESC
        """,
        (project_id, f"-{hours} hours"),
    ).fetchall()
    return [Draft.from_dict(dict(row)) for row in rows]


def get_intro_draft(conn: sqlite3.Connection, project_id: str) -> Draft | None:
    """Get the most recent active intro draft for a project."""
    row = conn.execute(
        """
        SELECT * FROM drafts
        WHERE project_id = ? AND is_intro = 1
          AND status IN ('draft', 'approved', 'scheduled', 'deferred')
        ORDER BY created_at DESC LIMIT 1
        """,
        (project_id,),
    ).fetchone()
    if row:
        return Draft.from_dict(dict(row))
    return None


def get_most_recent_posted_for_arc(
    conn: sqlite3.Connection, arc_id: str, platform: str
) -> Post | None:
    """Get the most recently posted content for an arc on a given platform.

    Requires posts->drafts->decisions join since posts lacks arc_id.
    """
    row = conn.execute(
        """
        SELECT p.* FROM posts p
        JOIN drafts dr ON p.draft_id = dr.id
        JOIN decisions d ON dr.decision_id = d.id
        WHERE d.arc_id = ? AND p.platform = ?
        ORDER BY p.posted_at DESC LIMIT 1
        """,
        (arc_id, platform),
    ).fetchone()
    if row:
        return Post.from_dict(dict(row))
    return None


def execute_queue_action(
    conn: sqlite3.Connection, action_type: str, draft_id: str, reason: str
) -> None:
    """Execute an evaluator queue action on a draft.

    supersede -> update status to 'superseded'
    drop -> update status to 'cancelled' with reason
    """
    if action_type == "supersede":
        update_draft(conn, draft_id, status="superseded")
    elif action_type == "drop":
        update_draft(conn, draft_id, status="cancelled", last_error=reason)
    else:
        raise ValueError(f"Unknown queue action: {action_type}")


# =============================================================================
# Data Events (WebSocket broadcast)
# =============================================================================


def emit_data_event(
    conn: sqlite3.Connection,
    entity: str,
    action: str,
    entity_id: str = "",
    project_id: str = "",
) -> None:
    """Write a data-change event to web_events for WebSocket broadcast.

    Non-fatal: failures are logged but don't interrupt the caller.
    """
    try:
        conn.execute(
            "INSERT INTO web_events (type, data) VALUES (?, ?)",
            (
                "data_change",
                json.dumps(
                    {
                        "entity": entity,
                        "action": action,
                        "entity_id": entity_id,
                        "project_id": project_id,
                    }
                ),
            ),
        )
        conn.commit()
    except Exception:
        logger.debug("Failed to emit data event", exc_info=True)
