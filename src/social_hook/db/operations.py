"""Database CRUD operations."""

import json
import sqlite3
from typing import Optional

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
    result = conn.execute(
        "SELECT COALESCE(MAX(version), 0) FROM schema_version"
    ).fetchone()
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
        INSERT INTO projects (id, name, repo_path, repo_origin, summary, summary_updated_at, audience_introduced)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        project.to_row(),
    )
    conn.commit()
    return project.id


def get_project(conn: sqlite3.Connection, project_id: str) -> Optional[Project]:
    """Get a project by ID."""
    row = conn.execute(
        "SELECT * FROM projects WHERE id = ?", (project_id,)
    ).fetchone()
    if row:
        return Project.from_dict(dict(row))
    return None


def get_all_projects(conn: sqlite3.Connection) -> list[Project]:
    """Get all projects."""
    rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    return [Project.from_dict(dict(row)) for row in rows]


# =============================================================================
# Decisions
# =============================================================================


def insert_decision(conn: sqlite3.Connection, decision: Decision) -> str:
    """Insert a new decision.

    Returns the decision ID.
    """
    conn.execute(
        """
        INSERT INTO decisions (id, project_id, commit_hash, decision, reasoning, angle, episode_type, post_category, arc_id, media_tool, platforms)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        decision.to_row(),
    )
    conn.commit()
    return decision.id


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


# =============================================================================
# Drafts
# =============================================================================


def insert_draft(conn: sqlite3.Connection, draft: Draft) -> str:
    """Insert a new draft.

    Returns the draft ID.
    """
    conn.execute(
        """
        INSERT INTO drafts (id, project_id, decision_id, platform, status, content, media_paths, suggested_time, scheduled_time, reasoning, superseded_by, retry_count, last_error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        draft.to_row(),
    )
    conn.commit()
    return draft.id


def get_draft(conn: sqlite3.Connection, draft_id: str) -> Optional[Draft]:
    """Get a draft by ID."""
    row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    if row:
        return Draft.from_dict(dict(row))
    return None


def update_draft(
    conn: sqlite3.Connection,
    draft_id: str,
    status: Optional[str] = None,
    content: Optional[str] = None,
    scheduled_time: Optional[str] = None,
    retry_count: Optional[int] = None,
    last_error: Optional[str] = None,
) -> bool:
    """Update a draft.

    Returns True if a row was updated.
    """
    updates = []
    params = []

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


def supersede_draft(
    conn: sqlite3.Connection, old_draft_id: str, new_draft_id: str
) -> bool:
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
          AND status IN ('draft', 'approved', 'scheduled')
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
        WHERE status IN ('draft', 'approved', 'scheduled')
        ORDER BY created_at DESC
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


def get_recent_posts(
    conn: sqlite3.Connection, project_id: str, days: int = 7
) -> list[Post]:
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


def get_lifecycle(conn: sqlite3.Connection, project_id: str) -> Optional[Lifecycle]:
    """Get lifecycle for a project."""
    row = conn.execute(
        "SELECT * FROM lifecycles WHERE project_id = ?", (project_id,)
    ).fetchone()
    if row:
        return Lifecycle.from_dict(dict(row))
    return None


def update_lifecycle(
    conn: sqlite3.Connection,
    project_id: str,
    phase: Optional[str] = None,
    confidence: Optional[float] = None,
    evidence: Optional[list[str]] = None,
    last_strategy_moment: Optional[str] = None,
) -> bool:
    """Update a lifecycle.

    Returns True if a row was updated.
    """
    updates = []
    params = []

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
    status: Optional[str] = None,
    post_count: Optional[int] = None,
    last_post_at: Optional[str] = None,
    notes: Optional[str] = None,
) -> bool:
    """Update an arc.

    Returns True if a row was updated.
    """
    updates = []
    params = []

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


def get_arc(conn: sqlite3.Connection, arc_id: str) -> Optional[Arc]:
    """Get a single arc by ID."""
    row = conn.execute(
        "SELECT * FROM arcs WHERE id = ?", (arc_id,)
    ).fetchone()
    if row:
        return Arc.from_dict(dict(row))
    return None


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


def set_audience_introduced(
    conn: sqlite3.Connection, project_id: str, value: bool
) -> bool:
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


def get_narrative_debt(
    conn: sqlite3.Connection, project_id: str
) -> Optional[NarrativeDebt]:
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
        INSERT INTO usage_log (id, project_id, operation_type, model, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, cost_cents)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        usage.to_row(),
    )
    conn.commit()
    return usage.id


def get_usage_summary(
    conn: sqlite3.Connection, days: int = 30
) -> list[dict]:
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


def get_project_summary(conn: sqlite3.Connection, project_id: str) -> Optional[str]:
    """Get project summary for Gatekeeper context injection.

    Returns the summary text, or None if no summary exists.
    """
    row = conn.execute(
        "SELECT summary FROM projects WHERE id = ?", (project_id,)
    ).fetchone()
    if row and row[0]:
        return row[0]
    return None


def get_summary_freshness(
    conn: sqlite3.Connection, project_id: str
) -> dict:
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
            "SELECT julianday('now') - julianday(?)",
            (summary_updated_at,)
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
    return summary["id"]


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
