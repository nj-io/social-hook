"""Database CRUD operations."""

import json
import logging
import sqlite3
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

from social_hook.models.content import (
    ContentSuggestion,
    ContentTopic,
    DraftPattern,
    EvaluationCycle,
)
from social_hook.models.core import Decision, Draft, DraftChange, DraftPart, Post, Project
from social_hook.models.infra import AdvisoryItem, OAuthToken, SystemErrorRecord, UsageLog
from social_hook.models.narrative import Arc, Lifecycle, NarrativeDebt

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
        INSERT INTO projects (id, name, repo_path, repo_origin, summary, summary_updated_at, paused)
        VALUES (?, ?, ?, ?, ?, ?, ?)
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
    draft_parts (via drafts), posts (via drafts), drafts, decisions, then project.

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
        conn.execute("DELETE FROM draft_parts WHERE draft_id = ?", (draft_id,))

    conn.execute("DELETE FROM advisory_items WHERE project_id = ?", (project_id,))
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


def register_project(
    conn: sqlite3.Connection,
    repo_path: str,
    name: str | None = None,
) -> tuple[Project, str | None]:
    """Register a project from a repo path.

    Supports both git and non-git directories. If git: extracts origin.
    If not git: repo_origin=None, no git hook needed.

    Returns (project, repo_origin) on success.
    Raises ValueError on duplicate registration.
    """
    from pathlib import Path

    from social_hook.filesystem import generate_id
    from social_hook.trigger_git import is_git_repo

    path = Path(repo_path).resolve()

    # Optional git detection
    repo_origin = None
    if is_git_repo(str(path)):
        origin_result = subprocess.run(
            ["git", "-C", str(path), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
        )
        repo_origin = origin_result.stdout.strip() if origin_result.returncode == 0 else None

    if not name:
        name = path.name

    # Check duplicates
    existing = get_project_by_path(conn, str(path))
    if existing:
        raise ValueError(f"Project already registered: {existing.name} ({existing.id})")

    if repo_origin:
        matches = get_project_by_origin(conn, repo_origin)
        if matches:
            raise ValueError(f"Repository origin already registered as: {matches[0].name}")

    project = Project(
        id=generate_id("project"),
        name=name,
        repo_path=str(path),
        repo_origin=repo_origin,
    )
    insert_project(conn, project)

    lifecycle = Lifecycle(project_id=project.id, phase="research", confidence=0.3)
    insert_lifecycle(conn, lifecycle)

    debt = NarrativeDebt(project_id=project.id, debt_counter=0)
    insert_narrative_debt(conn, debt)

    return project, repo_origin


def delete_decision(conn: sqlite3.Connection, decision_id: str) -> bool:
    """Delete a decision and all associated data.

    Cascades to: draft_changes, draft_parts, posts, drafts for this decision.
    Returns True if the decision was deleted.
    """
    # TODO: backport reference NULL-out from rewind_decision() — superseded_by
    # and reference_post_id on other decisions' drafts can cause FK violations
    # with PRAGMA foreign_keys = ON when cross-references exist.
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
        conn.execute("DELETE FROM draft_parts WHERE draft_id = ?", (draft_id,))

    conn.execute(
        "DELETE FROM posts WHERE draft_id IN (SELECT id FROM drafts WHERE decision_id = ?)",
        (decision_id,),
    )
    conn.execute("DELETE FROM drafts WHERE decision_id = ?", (decision_id,))
    conn.execute("DELETE FROM decisions WHERE id = ?", (decision_id,))
    conn.commit()
    return True


def rewind_decision(conn: sqlite3.Connection, decision_id: str, force: bool = False) -> dict | None:
    """Rewind a decision to its evaluation point, removing all downstream artifacts.

    Keeps the decision row but deletes drafts, draft_parts, draft_changes,
    and posts. Resets the decision to unprocessed state (processed=0,
    processed_at=NULL, batch_id=NULL). Decrements the arc post_count if
    applicable and resets audience_introduced if the only intro drafts were
    deleted.

    This function operates on decision_id and is trigger-source-agnostic — it
    works whether the decision originated from a git commit, a plugin-injected
    event, or a user-initiated campaign. Commit-hash-based lookup is a CLI
    convenience layer, not part of this operation.

    Args:
        conn: Database connection.
        decision_id: The decision to rewind.
        force: If True, allow rewind even when drafts have been posted
            (the content remains live on the platform — only DB rows are removed).

    Returns:
        Summary dict on success, None if decision not found.

    Raises:
        ValueError: If any draft has status='posted' and force is False.
    """
    decision = get_decision(conn, decision_id)
    if not decision:
        return None

    # Fetch all drafts for this decision
    draft_rows = conn.execute(
        "SELECT id, status, is_intro, platform FROM drafts WHERE decision_id = ?",
        (decision_id,),
    ).fetchall()
    draft_ids = [r[0] for r in draft_rows]

    # Safety gate: refuse if posted drafts exist unless forced
    posted_statuses = [r for r in draft_rows if r[1] == "posted"]
    if posted_statuses and not force:
        raise ValueError(
            f"Decision has {len(posted_statuses)} posted draft(s). "
            "Use force=True to rewind anyway (cannot un-publish from platform)."
        )

    # Fetch post IDs being deleted (needed for reference NULL-out and count)
    if draft_ids:
        placeholders = ",".join("?" * len(draft_ids))
        post_rows = conn.execute(
            f"SELECT id FROM posts WHERE draft_id IN ({placeholders})",
            draft_ids,
        ).fetchall()
        post_ids = [r[0] for r in post_rows]
    else:
        post_ids = []

    # NULL out all references to artifacts being deleted — including same-decision
    # drafts that may reference their own posts. Required to avoid FK violations
    # with PRAGMA foreign_keys = ON.
    if draft_ids:
        placeholders_d = ",".join("?" * len(draft_ids))
        conn.execute(
            f"UPDATE drafts SET superseded_by = NULL WHERE superseded_by IN ({placeholders_d})",
            draft_ids,
        )
    if post_ids:
        placeholders_p = ",".join("?" * len(post_ids))
        conn.execute(
            f"UPDATE drafts SET reference_post_id = NULL WHERE reference_post_id IN ({placeholders_p})",
            post_ids,
        )

    # Delete in FK dependency order
    for did in draft_ids:
        conn.execute("DELETE FROM draft_changes WHERE draft_id = ?", (did,))
        conn.execute("DELETE FROM draft_parts WHERE draft_id = ?", (did,))

    if draft_ids:
        placeholders_d = ",".join("?" * len(draft_ids))
        conn.execute(
            f"DELETE FROM posts WHERE draft_id IN ({placeholders_d})",
            draft_ids,
        )
    conn.execute("DELETE FROM drafts WHERE decision_id = ?", (decision_id,))

    # Decrement arc post_count (raw SQL to avoid intermediate commit from update_arc)
    arc_decremented = False
    if decision.arc_id and draft_ids:
        conn.execute(
            "UPDATE arcs SET post_count = MAX(0, post_count - 1) WHERE id = ?",
            (decision.arc_id,),
        )
        arc_decremented = True

    # Reset platform_introduced for platforms whose intro drafts were deleted
    audience_reset = False
    intro_drafts = [r for r in draft_rows if r[2]]
    if intro_drafts:
        intro_platforms = set(r[3] for r in intro_drafts)
        for plat in intro_platforms:
            remaining = conn.execute(
                """SELECT COUNT(*) FROM drafts
                   WHERE project_id = ? AND is_intro = 1 AND decision_id != ? AND platform = ?""",
                (decision.project_id, decision_id, plat),
            ).fetchone()[0]
            if remaining == 0:
                reset_platform_introduced(conn, decision.project_id, plat)
                audience_reset = True

    # Reset decision to unprocessed state
    conn.execute(
        "UPDATE decisions SET processed = 0, processed_at = NULL, batch_id = NULL WHERE id = ?",
        (decision_id,),
    )
    conn.commit()

    return {
        "decision_id": decision_id,
        "commit_hash": decision.commit_hash,
        "drafts_deleted": len(draft_ids),
        "posts_deleted": len(post_ids),
        "arc_decremented": arc_decremented,
        "audience_reset": audience_reset,
        "had_posted_drafts": bool(posted_statuses),
    }


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


def upsert_file_summaries(
    conn: sqlite3.Connection, project_id: str, file_summaries: list[dict[str, str]]
) -> None:
    """Replace all file summaries for a project. Deletes existing summaries first
    to remove stale entries from previous discovery runs, then inserts new ones."""
    conn.execute("DELETE FROM file_summaries WHERE project_id = ?", (project_id,))
    for fs in file_summaries:
        conn.execute(
            "INSERT INTO file_summaries (project_id, file_path, summary) VALUES (?, ?, ?)",
            (project_id, fs["path"], fs["summary"]),
        )
    conn.commit()


def get_file_summaries(conn: sqlite3.Connection, project_id: str) -> list[dict[str, str]]:
    """Get all file summaries for a project. Returns [{"path": str, "summary": str}]."""
    rows = conn.execute(
        "SELECT file_path, summary FROM file_summaries WHERE project_id = ? ORDER BY file_path",
        (project_id,),
    ).fetchall()
    return [{"path": row[0], "summary": row[1]} for row in rows]


def update_prompt_docs(conn: sqlite3.Connection, project_id: str, prompt_docs: list[str]) -> None:
    """Store LLM-selected prompt docs for a project."""
    conn.execute(
        "UPDATE projects SET prompt_docs = ? WHERE id = ?",
        (json.dumps(prompt_docs), project_id),
    )
    conn.commit()


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
            reference_posts, branch, trigger_source, processed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        decision.to_row(),
    )
    conn.commit()
    return decision.id


def upsert_decision(conn: sqlite3.Connection, decision: Decision) -> str:
    """Insert or replace a decision, keeping the same ID.

    Used by retrigger: the existing row (e.g. 'imported' or 'evaluating') is
    replaced in-place so the decision_id stays stable and the frontend row
    doesn't disappear during re-evaluation.
    """
    conn.execute("DELETE FROM decisions WHERE id = ?", (decision.id,))
    conn.execute(
        """
        INSERT INTO decisions (id, project_id, commit_hash, commit_message,
            decision, reasoning, angle, episode_type, episode_tags, post_category,
            arc_id, media_tool, platforms, targets, commit_summary, consolidate_with,
            reference_posts, branch, trigger_source, processed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def get_decision_by_commit(
    conn: sqlite3.Connection, project_id: str, commit_hash: str
) -> Decision | None:
    """Get a decision by project and commit hash.

    Leverages the UNIQUE(project_id, commit_hash) constraint.
    """
    row = conn.execute(
        "SELECT * FROM decisions WHERE project_id = ? AND commit_hash = ?",
        (project_id, commit_hash),
    ).fetchone()
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
        WHERE project_id = ? AND decision NOT IN ('imported', 'deferred_eval')
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
    before = int(conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0])
    conn.executemany(
        """
        INSERT OR IGNORE INTO decisions (id, project_id, commit_hash, commit_message,
            decision, reasoning, angle, episode_type, episode_tags, post_category,
            arc_id, media_tool, platforms, targets, commit_summary, consolidate_with,
            reference_posts, branch, trigger_source, processed, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [d.to_row() + (created_at,) for d, created_at in decisions],
    )
    conn.commit()
    after = int(conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0])

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
            reasoning, superseded_by, retry_count, last_error, is_intro, vehicle,
            reference_type, reference_files, reference_post_id,
            target_id, evaluation_cycle_id, topic_id, suggestion_id, pattern_id,
            preview_mode, arc_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        draft.to_row(),
    )
    conn.commit()
    return draft.id


def delete_drafts_for_decision(conn: sqlite3.Connection, decision_id: str) -> None:
    """Delete all drafts (and related draft_changes, draft_parts) for a decision."""
    conn.execute(
        "DELETE FROM draft_changes WHERE draft_id IN (SELECT id FROM drafts WHERE decision_id = ?)",
        (decision_id,),
    )
    conn.execute(
        "DELETE FROM draft_parts WHERE draft_id IN (SELECT id FROM drafts WHERE decision_id = ?)",
        (decision_id,),
    )
    conn.execute("DELETE FROM drafts WHERE decision_id = ?", (decision_id,))


def clear_draft_preview_mode(conn: sqlite3.Connection, draft_id: str) -> None:
    """Clear preview_mode flag on a draft (e.g. after connecting an account)."""
    conn.execute("UPDATE drafts SET preview_mode = 0 WHERE id = ?", (draft_id,))
    conn.commit()


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
    vehicle: str | None = None,
    reference_type: str | None = None,
    reference_files: list[str] | None = None,
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
    if vehicle is not None:
        updates.append("vehicle = ?")
        params.append(vehicle)
    if reference_type is not None:
        updates.append("reference_type = ?")
        params.append(reference_type)
    if reference_files is not None:
        updates.append("reference_files = ?")
        params.append(json.dumps(reference_files))
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
    tag: str | None = None,
) -> list[Draft]:
    """Get drafts with optional status, project, decision, commit, and tag filters."""
    clauses, params = [], []
    need_join = commit_hash is not None or tag is not None
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
    if tag:
        clauses.append("dec.episode_tags LIKE ?")
        params.append(f'%"{tag}"%')
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
# Draft Parts
# =============================================================================


def insert_draft_part(conn: sqlite3.Connection, part: DraftPart) -> str:
    """Insert a new draft part.

    Returns the part ID.
    """
    conn.execute(
        """
        INSERT INTO draft_parts (id, draft_id, position, content, media_paths, external_id, posted_at, error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        part.to_row(),
    )
    conn.commit()
    return part.id


def get_draft_parts(conn: sqlite3.Connection, draft_id: str) -> list[DraftPart]:
    """Get all parts for a draft thread."""
    rows = conn.execute(
        """
        SELECT * FROM draft_parts
        WHERE draft_id = ?
        ORDER BY position ASC
        """,
        (draft_id,),
    ).fetchall()
    return [DraftPart.from_dict(dict(row)) for row in rows]


def update_draft_part(
    conn: sqlite3.Connection,
    part_id: str,
    external_id: str | None = None,
    posted_at: str | None = None,
    error: str | None = None,
) -> bool:
    """Update a draft part after posting.

    Args:
        conn: Database connection
        part_id: Draft part ID
        external_id: External ID from platform
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

    params.append(part_id)

    cursor = conn.execute(
        f"UPDATE draft_parts SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    conn.commit()
    return cursor.rowcount > 0


def replace_draft_parts(conn: sqlite3.Connection, draft_id: str, parts: list[DraftPart]) -> None:
    """Delete existing parts for a draft and insert replacements.

    Used when content is edited on a threaded draft to keep draft_parts
    in sync with the updated content.
    """
    conn.execute("DELETE FROM draft_parts WHERE draft_id = ?", (draft_id,))
    for part in parts:
        conn.execute(
            """
            INSERT INTO draft_parts (id, draft_id, position, content, media_paths, external_id, posted_at, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            part.to_row(),
        )
    conn.commit()


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


def get_sister_drafts(
    conn: sqlite3.Connection, draft_id: str, *, include_self: bool = False
) -> list[Draft]:
    """Get all drafts sharing the same decision_id (sister/cross-post drafts).

    Args:
        draft_id: The source draft ID
        include_self: If True, include the source draft in results

    Returns:
        List of sister Draft objects
    """
    draft = get_draft(conn, draft_id)
    if not draft:
        return []

    if include_self:
        rows = conn.execute(
            "SELECT * FROM drafts WHERE decision_id = ? ORDER BY platform",
            (draft.decision_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM drafts WHERE decision_id = ? AND id != ? ORDER BY platform",
            (draft.decision_id, draft_id),
        ).fetchall()

    return [Draft.from_dict(dict(row)) for row in rows]


def sync_media_to_drafts(
    conn: sqlite3.Connection,
    source_draft_id: str,
    target_draft_ids: list[str],
) -> int:
    """Copy media_type, media_spec, media_spec_used, and media_paths from source to targets.

    Args:
        source_draft_id: Draft to copy media from
        target_draft_ids: Draft IDs to sync to

    Returns:
        Number of drafts updated
    """
    source = get_draft(conn, source_draft_id)
    if not source:
        return 0

    count = 0
    for target_id in target_draft_ids:
        updated = update_draft(
            conn,
            target_id,
            media_type=source.media_type or "",
            media_spec=source.media_spec,
            media_spec_used=source.media_spec_used,
            media_paths=source.media_paths,
        )
        if updated:
            count += 1

    return count


# =============================================================================
# Posts
# =============================================================================


def insert_post(conn: sqlite3.Connection, post: Post) -> str:
    """Insert a new post.

    Returns the post ID.
    """
    conn.execute(
        """
        INSERT INTO posts (id, draft_id, project_id, platform, external_id, external_url,
            content, target_id, topic_tags, feature_tags, is_thread_head)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        post.to_row(),
    )
    conn.commit()
    return post.id


def _parse_posted_at(raw: str | None):
    """Parse a posted_at TEXT column into a timezone-aware datetime.

    SQLite stores datetimes as TEXT. This helper normalises to UTC if
    the stored value is naive (no tzinfo).

    Returns:
        datetime or None if *raw* is falsy.
    """
    from datetime import datetime, timezone

    if not raw:
        return None
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def get_last_post_time_by_platform(conn: sqlite3.Connection, platform: str):
    """Get the most recent post time across all projects for a platform.

    Used by cross-account scheduling gap check. Returns None if no posts exist.
    Note: posted_at is stored as TEXT in SQLite — parse to datetime before returning.

    Returns:
        datetime or None
    """
    row = conn.execute(
        "SELECT posted_at FROM posts WHERE platform = ? ORDER BY posted_at DESC LIMIT 1",
        (platform,),
    ).fetchone()
    if not row or not row[0]:
        return None
    return _parse_posted_at(row[0])


def get_last_post_time_by_account(conn: sqlite3.Connection, target_ids: list[str]):
    """Get the most recent post time for any of the given target IDs.

    Used by per-account posting gap check. Multiple targets can share the same
    account — pass all target IDs that use the account.

    Returns:
        datetime or None
    """
    if not target_ids:
        return None

    placeholders = ",".join("?" for _ in target_ids)
    row = conn.execute(
        f"SELECT posted_at FROM posts WHERE target_id IN ({placeholders}) "
        "ORDER BY posted_at DESC LIMIT 1",
        target_ids,
    ).fetchone()
    if not row or not row[0]:
        return None
    return _parse_posted_at(row[0])


def get_drafts_by_cycle(conn: sqlite3.Connection, cycle_id: str) -> list[Draft]:
    """Get all drafts produced in an evaluation cycle.

    Used by notification callback handlers for Expand All / Approve All.
    """
    rows = conn.execute(
        """
        SELECT * FROM drafts
        WHERE evaluation_cycle_id = ?
        ORDER BY created_at ASC
        """,
        (cycle_id,),
    ).fetchall()
    return [Draft.from_dict(dict(row)) for row in rows]


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


def get_posts_by_ids(conn: sqlite3.Connection, post_ids: list[str]) -> list[Post]:
    """Get multiple posts by their IDs."""
    if not post_ids:
        return []
    placeholders = ",".join("?" * len(post_ids))
    rows = conn.execute(
        f"SELECT * FROM posts WHERE id IN ({placeholders})",
        post_ids,
    ).fetchall()
    return [Post.from_dict(dict(r)) for r in rows]


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
        INSERT INTO arcs (id, project_id, theme, strategy, status, reasoning, post_count, last_post_at, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    strategy: str | None = None,
    reasoning: str | None = None,
) -> bool:
    """Update an arc.

    Returns True if a row was updated.
    """
    updates: list[str] = []
    params: list[Any] = []

    if status is not None:
        updates.append("status = ?")
        params.append(status)
        # Set ended_at for terminal statuses, clear it when reactivating
        if status in ("completed", "abandoned"):
            updates.append("ended_at = datetime('now')")
        elif status == "active":
            updates.append("ended_at = NULL")
        elif status == "proposed":
            logger.debug("Arc %s set to proposed — no ended_at change", arc_id)
        else:
            logger.warning("Arc %s: unrecognized status %r", arc_id, status)
    if post_count is not None:
        updates.append("post_count = ?")
        params.append(post_count)
    if last_post_at is not None:
        updates.append("last_post_at = ?")
        params.append(last_post_at)
    if notes is not None:
        updates.append("notes = ?")
        params.append(notes)
    if strategy is not None:
        updates.append("strategy = ?")
        params.append(strategy)
    if reasoning is not None:
        updates.append("reasoning = ?")
        params.append(reasoning)

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


def get_active_arcs(
    conn: sqlite3.Connection, project_id: str, strategy: str | None = None
) -> list[Arc]:
    """Get active arcs for a project, optionally filtered by strategy.

    When strategy is None (default), filters arcs where strategy='' (legacy behavior).
    When strategy is a non-empty string, filters arcs for that specific strategy.
    """
    if strategy is None:
        rows = conn.execute(
            """
            SELECT * FROM arcs
            WHERE project_id = ? AND status = 'active' AND strategy = ''
            ORDER BY started_at DESC
            """,
            (project_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT * FROM arcs
            WHERE project_id = ? AND status = 'active' AND strategy = ?
            ORDER BY started_at DESC
            """,
            (project_id, strategy),
        ).fetchall()
    return [Arc.from_dict(dict(row)) for row in rows]


def get_arc(conn: sqlite3.Connection, arc_id: str) -> Arc | None:
    """Get a single arc by ID."""
    row = conn.execute("SELECT * FROM arcs WHERE id = ?", (arc_id,)).fetchone()
    if row:
        return Arc.from_dict(dict(row))
    return None


def get_arcs_by_project(
    conn: sqlite3.Connection,
    project_id: str,
    status: str | None = None,
    strategy: str | None = None,
) -> list[Arc]:
    """Get arcs for a project, optionally filtered by status and/or strategy.

    Args:
        conn: Database connection
        project_id: Project to query
        status: Filter by status ('proposed', 'active', 'completed', 'abandoned'), or None for all
        strategy: Filter by strategy, or None for all strategies
    """
    conditions = ["project_id = ?"]
    params: list[Any] = [project_id]

    if status is not None:
        conditions.append("status = ?")
        params.append(status)
    if strategy is not None:
        conditions.append("strategy = ?")
        params.append(strategy)

    where = " AND ".join(conditions)
    rows = conn.execute(
        f"SELECT * FROM arcs WHERE {where} ORDER BY started_at DESC",
        params,
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
    """Check if the audience has been introduced for a project.

    DEPRECATED: Use get_all_platform_introduced() instead.
    Returns True if all tracked platforms are introduced.
    """
    rows = conn.execute(
        "SELECT introduced FROM platform_introduced WHERE project_id = ?",
        (project_id,),
    ).fetchall()
    if not rows:
        return False
    return all(bool(r[0]) for r in rows)


def set_audience_introduced(conn: sqlite3.Connection, project_id: str, value: bool) -> bool:
    """Update the audience_introduced flag for a project.

    DEPRECATED: Use set_platform_introduced() instead.
    Sets all tracked platforms to the given value.
    """
    cursor = conn.execute(
        "UPDATE platform_introduced SET introduced = ?, introduced_at = CASE WHEN ? THEN datetime('now') ELSE NULL END WHERE project_id = ?",
        (1 if value else 0, 1 if value else 0, project_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def get_platform_introduced(conn: sqlite3.Connection, project_id: str, platform: str) -> bool:
    """Check if a specific platform has been introduced for a project."""
    row = conn.execute(
        "SELECT introduced FROM platform_introduced WHERE project_id = ? AND platform = ?",
        (project_id, platform),
    ).fetchone()
    if row:
        return bool(row[0])
    return False


def set_platform_introduced(
    conn: sqlite3.Connection, project_id: str, platform: str, value: bool
) -> bool:
    """Set the introduced state for a specific platform.

    Returns True if a row was inserted/updated.
    """
    conn.execute(
        """
        INSERT INTO platform_introduced (project_id, platform, introduced, introduced_at)
        VALUES (?, ?, ?, CASE WHEN ? THEN datetime('now') ELSE NULL END)
        ON CONFLICT(project_id, platform) DO UPDATE SET
            introduced = excluded.introduced,
            introduced_at = CASE WHEN excluded.introduced THEN
                COALESCE(platform_introduced.introduced_at, excluded.introduced_at)
            ELSE NULL END
        """,
        (project_id, platform, 1 if value else 0, 1 if value else 0),
    )
    conn.commit()
    return True


def get_all_platform_introduced(conn: sqlite3.Connection, project_id: str) -> dict[str, bool]:
    """Get introduction state for all platforms of a project.

    Returns dict mapping platform name to introduced status.
    """
    rows = conn.execute(
        "SELECT platform, introduced FROM platform_introduced WHERE project_id = ?",
        (project_id,),
    ).fetchall()
    return {row[0]: bool(row[1]) for row in rows}


def reset_platform_introduced(
    conn: sqlite3.Connection, project_id: str, platform: str | None = None
) -> int:
    """Reset introduced state. If platform is None, reset all platforms for this project.

    Returns the number of rows updated.
    """
    if platform is None:
        cursor = conn.execute(
            "UPDATE platform_introduced SET introduced = 0, introduced_at = NULL WHERE project_id = ?",
            (project_id,),
        )
    else:
        cursor = conn.execute(
            "UPDATE platform_introduced SET introduced = 0, introduced_at = NULL WHERE project_id = ? AND platform = ?",
            (project_id, platform),
        )
    conn.commit()
    return cursor.rowcount


def get_first_post_date(conn: sqlite3.Connection, project_id: str, platform: str) -> str | None:
    """Return earliest posted_at for a project+platform. For identity instruction temporal context."""
    row = conn.execute(
        "SELECT MIN(posted_at) FROM posts WHERE project_id = ? AND platform = ?",
        (project_id, platform),
    ).fetchone()
    return row[0] if row and row[0] else None


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
        INSERT INTO usage_log (id, project_id, operation_type, model, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, cost_cents, commit_hash, trigger_source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def get_today_auto_evaluation_count(conn: sqlite3.Connection) -> int:
    """Count auto-triggered evaluations today (UTC).

    Used by rate limiter to enforce max_evaluations_per_day.
    """
    row = conn.execute(
        """
        SELECT COUNT(*) FROM usage_log
        WHERE operation_type = 'evaluate'
          AND trigger_source = 'auto'
          AND created_at >= date('now')
        """
    ).fetchone()
    return row[0] if row else 0


def get_last_auto_evaluation_time(conn: sqlite3.Connection) -> str | None:
    """Get the most recent auto-triggered evaluation timestamp.

    Used by rate limiter to enforce min_evaluation_gap_minutes.
    Returns ISO timestamp string or None if no auto evaluations exist.
    """
    row = conn.execute(
        """
        SELECT MAX(created_at) FROM usage_log
        WHERE operation_type = 'evaluate'
          AND trigger_source = 'auto'
        """
    ).fetchone()
    return row[0] if row and row[0] else None


def get_deferred_eval_decisions(conn: sqlite3.Connection, project_id: str) -> list[Decision]:
    """Get unprocessed deferred_eval decisions for a project.

    Returns decisions ordered by created_at ascending (oldest first)
    for drain processing.
    """
    rows = conn.execute(
        """
        SELECT * FROM decisions
        WHERE project_id = ?
          AND decision = 'deferred_eval'
          AND processed = 0
        ORDER BY created_at ASC
        """,
        (project_id,),
    ).fetchall()
    return [Decision.from_dict(dict(row)) for row in rows]


def get_interval_deferred_decisions(conn: sqlite3.Connection, project_id: str) -> list[Decision]:
    """Get interval-deferred decisions (processed=1, decision='deferred_eval').

    These are commits that were deferred by commit_analysis_interval gating,
    NOT by rate limits (which use processed=0). The batch_id IS NULL guard
    ensures we don't re-gather decisions already included in a previous batch.

    Returns decisions ordered by created_at ascending (oldest first).
    """
    rows = conn.execute(
        """
        SELECT * FROM decisions
        WHERE project_id = ?
          AND decision = 'deferred_eval'
          AND processed = 1
          AND batch_id IS NULL
        ORDER BY created_at ASC
        """,
        (project_id,),
    ).fetchall()
    return [Decision.from_dict(dict(row)) for row in rows]


def mark_decisions_processing(conn: sqlite3.Connection, decision_ids: list[str]) -> int:
    """Mark deferred decisions as 'processing' during batch evaluation.

    Pure DB operation — caller handles event emission.

    Returns number of rows updated.
    """
    if not decision_ids:
        return 0
    placeholders = ",".join("?" for _ in decision_ids)
    cursor = conn.execute(
        f"UPDATE decisions SET decision = 'processing' WHERE id IN ({placeholders})",
        decision_ids,
    )
    conn.commit()
    return cursor.rowcount


def mark_deferred_decisions_batched(
    conn: sqlite3.Connection, decision_ids: list[str], batch_cycle_id: str
) -> int:
    """Mark decisions as included in a batch evaluation.

    Reverts decision from 'processing' back to 'deferred_eval' with batch_id set.
    Sets processed=1 (essential for rate-limit-deferred to prevent re-drain),
    processed_at, batch_id, and reasoning.

    Returns number of rows updated.
    """
    if not decision_ids:
        return 0

    placeholders = ",".join("?" for _ in decision_ids)
    cursor = conn.execute(
        f"""
        UPDATE decisions
        SET decision = 'deferred_eval',
            processed = 1,
            processed_at = datetime('now'),
            batch_id = ?,
            reasoning = ?
        WHERE id IN ({placeholders})
        """,
        [batch_cycle_id, f"Included in batch evaluation {batch_cycle_id}"] + decision_ids,
    )
    conn.commit()
    return cursor.rowcount


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
    merge -> update status to 'superseded' (content merged into new draft)
    drop -> update status to 'cancelled' with reason
    """
    if action_type in ("supersede", "merge"):
        update_draft(conn, draft_id, status="superseded")
    elif action_type == "drop":
        update_draft(conn, draft_id, status="cancelled", last_error=reason)
    else:
        raise ValueError(f"Unknown queue action: {action_type}")


# =============================================================================
# Advisory Items
# =============================================================================


def insert_advisory_item(conn: sqlite3.Connection, item: AdvisoryItem) -> str:
    """Insert an advisory item. Returns the item ID."""
    conn.execute(
        """
        INSERT INTO advisory_items (
            id, project_id, category, title, description, status, urgency,
            created_by, linked_entity_type, linked_entity_id, handler_type,
            automation_level, verification_method, due_date,
            dismissed_reason, completed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        item.to_row(),
    )
    conn.commit()
    return item.id


def get_advisory_item(conn: sqlite3.Connection, item_id: str) -> AdvisoryItem | None:
    """Get an advisory item by ID."""
    row = conn.execute("SELECT * FROM advisory_items WHERE id = ?", (item_id,)).fetchone()
    if row:
        return AdvisoryItem.from_dict(dict(row))
    return None


def get_advisory_items(
    conn: sqlite3.Connection,
    project_id: str | None = None,
    status: str | None = None,
    category: str | None = None,
    urgency: str | None = None,
    linked_entity_type: str | None = None,
    linked_entity_id: str | None = None,
) -> list[AdvisoryItem]:
    """List advisory items with optional filters."""
    clauses: list[str] = []
    params: list[Any] = []

    if project_id:
        clauses.append("project_id = ?")
        params.append(project_id)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if category:
        clauses.append("category = ?")
        params.append(category)
    if urgency:
        clauses.append("urgency = ?")
        params.append(urgency)
    if linked_entity_type:
        clauses.append("linked_entity_type = ?")
        params.append(linked_entity_type)
    if linked_entity_id:
        clauses.append("linked_entity_id = ?")
        params.append(linked_entity_id)

    where = " AND ".join(clauses) if clauses else "1=1"
    rows = conn.execute(
        f"SELECT * FROM advisory_items WHERE {where} ORDER BY created_at DESC",
        params,
    ).fetchall()
    return [AdvisoryItem.from_dict(dict(r)) for r in rows]


def update_advisory_item(conn: sqlite3.Connection, item_id: str, **kwargs: Any) -> bool:
    """Update advisory item fields. Returns True if row was updated."""
    if not kwargs:
        return False
    allowed = {
        "status",
        "title",
        "description",
        "urgency",
        "category",
        "dismissed_reason",
        "completed_at",
        "due_date",
        "linked_entity_type",
        "linked_entity_id",
        "handler_type",
        "automation_level",
        "verification_method",
    }
    sets = []
    params: list[Any] = []
    for key, val in kwargs.items():
        if key not in allowed:
            logger.warning("Unknown advisory update field: %s", key)
            continue
        sets.append(f"{key} = ?")
        params.append(val)
    if not sets:
        return False
    params.append(item_id)
    result = conn.execute(
        f"UPDATE advisory_items SET {', '.join(sets)} WHERE id = ?",
        params,
    )
    conn.commit()
    return result.rowcount > 0


def delete_advisory_item(conn: sqlite3.Connection, item_id: str) -> bool:
    """Delete an advisory item. Returns True if row was deleted."""
    result = conn.execute("DELETE FROM advisory_items WHERE id = ?", (item_id,))
    conn.commit()
    return result.rowcount > 0


def count_advisory_items(
    conn: sqlite3.Connection,
    project_id: str | None = None,
    status: str | None = None,
) -> int:
    """Count advisory items with optional filters."""
    clauses: list[str] = []
    params: list[Any] = []
    if project_id:
        clauses.append("project_id = ?")
        params.append(project_id)
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = " AND ".join(clauses) if clauses else "1=1"
    row = conn.execute(
        f"SELECT COUNT(*) FROM advisory_items WHERE {where}",
        params,
    ).fetchone()
    return row[0] if row else 0


# =============================================================================
# Data Events (WebSocket broadcast)
# =============================================================================


def emit_data_event(
    conn: sqlite3.Connection,
    entity: str,
    action: str,
    entity_id: str = "",
    project_id: str = "",
    extra: dict | None = None,
) -> None:
    """Write a data-change event to web_events for WebSocket broadcast.

    Non-fatal: failures are logged but don't interrupt the caller.

    Args:
        extra: Optional dict of additional fields merged into the payload.
            Used to embed content preview, platform, etc. in draft events.
    """
    try:
        payload = {
            "entity": entity,
            "action": action,
            "entity_id": entity_id,
            "project_id": project_id,
        }
        if extra:
            payload.update(extra)
        conn.execute(
            "INSERT INTO web_events (type, data) VALUES (?, ?)",
            ("data_change", json.dumps(payload)),
        )
        conn.commit()
    except Exception:
        logger.debug("Failed to emit data event", exc_info=True)


def emit_task_stage(
    conn: sqlite3.Connection,
    task_id: str,
    stage: str,
    label: str,
    project_id: str = "",
) -> None:
    """Emit a task stage change event. Frontend updates task progress in-memory.

    Reusable by any background flow. Call via ctx.db for DryRunContext safety.
    Stage names are freeform strings. Stage data is in-memory only on the frontend.
    """
    emit_data_event(
        conn,
        "task",
        "stage",
        task_id,
        project_id,
        extra={"stage": stage, "stage_label": label},
    )


# =============================================================================
# OAuth Tokens
# =============================================================================


def upsert_oauth_token(conn: sqlite3.Connection, token: OAuthToken) -> None:
    """Insert or update an OAuth token."""
    conn.execute(
        """
        INSERT INTO oauth_tokens (account_name, platform, access_token, refresh_token,
            expires_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(account_name) DO UPDATE SET
            platform = excluded.platform,
            access_token = excluded.access_token,
            refresh_token = excluded.refresh_token,
            expires_at = excluded.expires_at,
            updated_at = excluded.updated_at
        """,
        token.to_row(),
    )
    conn.commit()


def get_oauth_token(conn: sqlite3.Connection, account_name: str) -> OAuthToken | None:
    """Get an OAuth token by account name."""
    row = conn.execute(
        "SELECT * FROM oauth_tokens WHERE account_name = ?", (account_name,)
    ).fetchone()
    if row:
        return OAuthToken.from_dict(dict(row))
    return None


def delete_oauth_token(conn: sqlite3.Connection, account_name: str) -> bool:
    """Delete an OAuth token. Returns True if a row was deleted."""
    cursor = conn.execute("DELETE FROM oauth_tokens WHERE account_name = ?", (account_name,))
    conn.commit()
    return cursor.rowcount > 0


# =============================================================================
# Content Topics
# =============================================================================


def insert_content_topic(conn: sqlite3.Connection, topic: ContentTopic) -> str:
    """Insert a content topic. Returns the topic ID."""
    conn.execute(
        """
        INSERT INTO content_topics (id, project_id, strategy, topic, description,
            priority_rank, status, commit_count, last_commit_at, last_posted_at, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        topic.to_row(),
    )
    conn.commit()
    return topic.id


def get_topics_by_strategy(
    conn: sqlite3.Connection,
    project_id: str,
    strategy: str,
    include_dismissed: bool = True,
) -> list[ContentTopic]:
    """Get all topics for a project+strategy, ordered by priority.

    Args:
        include_dismissed: When False, exclude topics with status='dismissed'.
    """
    dismissed_clause = "" if include_dismissed else "AND status != 'dismissed'"
    rows = conn.execute(
        f"""
        SELECT * FROM content_topics
        WHERE project_id = ? AND strategy = ?
            {dismissed_clause}
        ORDER BY priority_rank DESC, created_at ASC
        """,
        (project_id, strategy),
    ).fetchall()
    return [ContentTopic.from_dict(dict(row)) for row in rows]


def get_topics_by_project(
    conn: sqlite3.Connection,
    project_id: str,
    status: str | None = None,
    include_dismissed: bool = True,
) -> list[ContentTopic]:
    """Get all topics for a project, optionally filtered by status.

    Args:
        conn: Database connection
        project_id: Project to query
        status: Filter by status (e.g. "holding"), or None for all
        include_dismissed: When False, exclude topics with status='dismissed'.
    """
    conditions = ["project_id = ?"]
    params: list[str] = [project_id]

    if status is not None:
        conditions.append("status = ?")
        params.append(status)

    if not include_dismissed:
        conditions.append("status != 'dismissed'")

    where = " AND ".join(conditions)
    rows = conn.execute(
        f"""
        SELECT * FROM content_topics
        WHERE {where}
        ORDER BY strategy, priority_rank DESC, created_at ASC
        """,
        params,
    ).fetchall()
    return [ContentTopic.from_dict(dict(row)) for row in rows]


def get_topic(conn: sqlite3.Connection, topic_id: str) -> ContentTopic | None:
    """Get a content topic by ID."""
    row = conn.execute("SELECT * FROM content_topics WHERE id = ?", (topic_id,)).fetchone()
    if row:
        return ContentTopic.from_dict(dict(row))
    return None


def update_topic_status(conn: sqlite3.Connection, topic_id: str, status: str) -> bool:
    """Update a topic's status. Returns True if a row was updated."""
    cursor = conn.execute(
        "UPDATE content_topics SET status = ? WHERE id = ?",
        (status, topic_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def update_topic_hold(conn: sqlite3.Connection, topic_id: str, reason: str | None) -> bool:
    """Set topic to 'holding' with hold_reason atomically. Returns True if updated."""
    cursor = conn.execute(
        "UPDATE content_topics SET status = 'holding', hold_reason = ? WHERE id = ?",
        (reason, topic_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def update_topic_posted(conn: sqlite3.Connection, topic_id: str, status: str) -> bool:
    """Update topic after posting: set status, clear hold_reason, set last_posted_at."""
    cursor = conn.execute(
        "UPDATE content_topics SET status = ?, hold_reason = NULL, last_posted_at = datetime('now') WHERE id = ?",
        (status, topic_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def get_posts_by_topic_id(conn: sqlite3.Connection, topic_id: str) -> list:
    """Get recent posts linked to a topic via drafts. Returns list of Post objects."""
    rows = conn.execute(
        """
        SELECT p.* FROM posts p
        JOIN drafts d ON p.draft_id = d.id
        WHERE d.topic_id = ?
        ORDER BY p.posted_at DESC
        LIMIT 5
        """,
        (topic_id,),
    ).fetchall()
    return [Post.from_dict(dict(row)) for row in rows]


def update_topic_priority(conn: sqlite3.Connection, topic_id: str, priority_rank: int) -> bool:
    """Update a topic's priority rank. Returns True if a row was updated."""
    cursor = conn.execute(
        "UPDATE content_topics SET priority_rank = ? WHERE id = ?",
        (priority_rank, topic_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def get_topics_matching_tag(
    conn: sqlite3.Connection, project_id: str, tag: str
) -> list[ContentTopic]:
    """Get content topics whose topic name matches a tag (case-insensitive substring).

    Used by the pipeline to increment commit counts when episode tags match topics.
    Dismissed topics are excluded — they should not accumulate commits.
    """
    rows = conn.execute(
        """
        SELECT * FROM content_topics
        WHERE project_id = ? AND LOWER(topic) LIKE '%' || LOWER(?) || '%'
            AND status != 'dismissed'
        """,
        (project_id, tag),
    ).fetchall()
    return [ContentTopic.from_dict(dict(row)) for row in rows]


def increment_topic_commit_count(conn: sqlite3.Connection, topic_id: str) -> bool:
    """Increment a topic's commit count and update last_commit_at. Returns True if updated."""
    cursor = conn.execute(
        """
        UPDATE content_topics
        SET commit_count = commit_count + 1,
            last_commit_at = datetime('now')
        WHERE id = ?
        """,
        (topic_id,),
    )
    conn.commit()
    return cursor.rowcount > 0


# =============================================================================
# Topic Commits
# =============================================================================


def insert_topic_commit(
    conn: sqlite3.Connection, topic_id: str, commit_hash: str, matched_tag: str | None = None
) -> bool:
    """Record that a commit contributed to a topic. Returns True if inserted (not duplicate)."""
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO topic_commits (topic_id, commit_hash, matched_tag)
            VALUES (?, ?, ?)
            """,
            (topic_id, commit_hash, matched_tag),
        )
        conn.commit()
        return True
    except Exception:
        logger.warning(
            "Failed to insert topic_commit (%s, %s)", topic_id, commit_hash, exc_info=True
        )
        return False


# =============================================================================
# Content Suggestions
# =============================================================================


def insert_content_suggestion(conn: sqlite3.Connection, suggestion: ContentSuggestion) -> str:
    """Insert a content suggestion. Returns the suggestion ID."""
    conn.execute(
        """
        INSERT INTO content_suggestions (id, project_id, strategy, idea, media_refs,
            status, source)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        suggestion.to_row(),
    )
    conn.commit()
    return suggestion.id


def get_suggestion(conn: sqlite3.Connection, suggestion_id: str) -> ContentSuggestion | None:
    """Get a single suggestion by ID. Returns None if not found."""
    row = conn.execute(
        "SELECT * FROM content_suggestions WHERE id = ?",
        (suggestion_id,),
    ).fetchone()
    if not row:
        return None
    return ContentSuggestion.from_dict(dict(row))


def get_suggestions_by_project(
    conn: sqlite3.Connection, project_id: str
) -> list[ContentSuggestion]:
    """Get all suggestions for a project, newest first."""
    rows = conn.execute(
        """
        SELECT * FROM content_suggestions
        WHERE project_id = ?
        ORDER BY created_at DESC
        """,
        (project_id,),
    ).fetchall()
    return [ContentSuggestion.from_dict(dict(row)) for row in rows]


def update_suggestion_status(conn: sqlite3.Connection, suggestion_id: str, status: str) -> bool:
    """Update a suggestion's status. Returns True if a row was updated."""
    updates = "status = ?"
    params: list[Any] = [status]
    if status == "evaluated":
        updates += ", evaluated_at = datetime('now')"
    cursor = conn.execute(
        f"UPDATE content_suggestions SET {updates} WHERE id = ?",
        params + [suggestion_id],
    )
    conn.commit()
    return cursor.rowcount > 0


# =============================================================================
# Evaluation Cycles
# =============================================================================


def insert_evaluation_cycle(conn: sqlite3.Connection, cycle: EvaluationCycle) -> str:
    """Insert an evaluation cycle. Returns the cycle ID."""
    conn.execute(
        """
        INSERT INTO evaluation_cycles (id, project_id, trigger_type, trigger_ref,
            commit_analysis_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        cycle.to_row(),
    )
    conn.commit()
    return cycle.id


def get_recent_cycles(
    conn: sqlite3.Connection, project_id: str, limit: int = 20
) -> list[EvaluationCycle]:
    """Get recent evaluation cycles for a project."""
    rows = conn.execute(
        """
        SELECT * FROM evaluation_cycles
        WHERE project_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (project_id, limit),
    ).fetchall()
    return [EvaluationCycle.from_dict(dict(row)) for row in rows]


def update_cycle_analysis_json(conn: sqlite3.Connection, cycle_id: str, analysis_json: str) -> None:
    """Store commit analysis JSON on an evaluation cycle for caching."""
    conn.execute(
        "UPDATE evaluation_cycles SET commit_analysis_json = ? WHERE id = ?",
        (analysis_json, cycle_id),
    )
    conn.commit()


def update_cycle_diagnostics(
    conn: sqlite3.Connection, cycle_id: str, diagnostics_json: str
) -> None:
    """Store pipeline diagnostics JSON on an evaluation cycle."""
    conn.execute(
        "UPDATE evaluation_cycles SET diagnostics = ? WHERE id = ?",
        (diagnostics_json, cycle_id),
    )
    conn.commit()


def get_latest_cycle_with_analysis(
    conn: sqlite3.Connection, project_id: str
) -> EvaluationCycle | None:
    """Get the most recent evaluation cycle that has cached analysis JSON."""
    row = conn.execute(
        """
        SELECT * FROM evaluation_cycles
        WHERE project_id = ? AND commit_analysis_json IS NOT NULL
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (project_id,),
    ).fetchone()
    if row:
        return EvaluationCycle.from_dict(dict(row))
    return None


# =============================================================================
# Analysis Commit Count (commit_analysis_interval gating)
# =============================================================================


def increment_analysis_commit_count(conn: sqlite3.Connection, project_id: str) -> int:
    """Increment analysis_commit_count and return the new value."""
    conn.execute(
        "UPDATE projects SET analysis_commit_count = analysis_commit_count + 1 WHERE id = ?",
        (project_id,),
    )
    conn.commit()
    row = conn.execute(
        "SELECT analysis_commit_count FROM projects WHERE id = ?",
        (project_id,),
    ).fetchone()
    return row[0] if row else 0


def reset_analysis_commit_count(conn: sqlite3.Connection, project_id: str) -> None:
    """Reset analysis_commit_count to 0 after a full analysis."""
    conn.execute(
        "UPDATE projects SET analysis_commit_count = 0 WHERE id = ?",
        (project_id,),
    )
    conn.commit()


def get_analysis_commit_count(conn: sqlite3.Connection, project_id: str) -> int:
    """Get the current analysis_commit_count for a project."""
    row = conn.execute(
        "SELECT analysis_commit_count FROM projects WHERE id = ?",
        (project_id,),
    ).fetchone()
    return row[0] if row else 0


# =============================================================================
# Draft Patterns
# =============================================================================


def insert_draft_pattern(conn: sqlite3.Connection, pattern: DraftPattern) -> str:
    """Insert a draft pattern. Returns the pattern ID."""
    conn.execute(
        """
        INSERT INTO draft_patterns (id, project_id, pattern_name, description,
            example_draft_id, created_by)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        pattern.to_row(),
    )
    conn.commit()
    return pattern.id


def get_patterns_by_project(conn: sqlite3.Connection, project_id: str) -> list[DraftPattern]:
    """Get all draft patterns for a project."""
    rows = conn.execute(
        """
        SELECT * FROM draft_patterns
        WHERE project_id = ?
        ORDER BY created_at DESC
        """,
        (project_id,),
    ).fetchall()
    return [DraftPattern.from_dict(dict(row)) for row in rows]


# =============================================================================
# System Errors
# =============================================================================


def insert_system_error(conn: sqlite3.Connection, error: SystemErrorRecord) -> str:
    """Insert a system error record. Returns the error ID."""
    conn.execute(
        """
        INSERT INTO system_errors (id, severity, message, context, source, component, run_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        error.to_row(),
    )
    conn.commit()
    return error.id


def get_recent_system_errors(
    conn: sqlite3.Connection,
    limit: int = 50,
    *,
    severity: str | list[str] | None = None,
    component: str | None = None,
    source: str | None = None,
) -> list[SystemErrorRecord]:
    """Get recent system errors, newest first. Optional filters narrow results.

    severity can be a single string or a list of strings for IN queries.
    """
    query = "SELECT * FROM system_errors"
    conditions: list[str] = []
    params: list = []
    if severity is not None:
        if isinstance(severity, list):
            placeholders = ",".join("?" for _ in severity)
            conditions.append(f"severity IN ({placeholders})")
            params.extend(severity)
        else:
            conditions.append("severity = ?")
            params.append(severity)
    if component is not None:
        conditions.append("component = ?")
        params.append(component)
    if source is not None:
        conditions.append("source = ?")
        params.append(source)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    return [SystemErrorRecord.from_dict(dict(row)) for row in rows]


def get_error_health_status(conn: sqlite3.Connection) -> dict:
    """Get error counts by severity in last 24h."""
    rows = conn.execute(
        """
        SELECT severity, COUNT(*) as count
        FROM system_errors
        WHERE created_at >= datetime('now', '-1 day')
        GROUP BY severity
        """
    ).fetchall()
    result = {"info": 0, "warning": 0, "error": 0, "critical": 0}
    for row in rows:
        result[row[0]] = row[1]
    return result


def clear_system_errors(conn: sqlite3.Connection, *, older_than_days: int | None = None) -> int:
    """Delete system errors. Returns count of deleted rows.

    If older_than_days is given, only deletes errors older than that.
    Otherwise deletes all.
    """
    if older_than_days is not None:
        cursor = conn.execute(
            "DELETE FROM system_errors WHERE created_at < datetime('now', ?)",
            (f"-{older_than_days} days",),
        )
    else:
        cursor = conn.execute("DELETE FROM system_errors")
    conn.commit()
    return cursor.rowcount


def prune_system_errors(conn: sqlite3.Connection, retention_days: int = 30) -> int:
    """Delete system errors older than retention_days. Returns count deleted."""
    return clear_system_errors(conn, older_than_days=retention_days)


def compute_health_status(error_counts: dict[str, int]) -> str:
    """Derive overall health status string from severity counts.

    Returns one of: "critical", "degraded", "warning", "healthy".
    """
    if error_counts.get("critical", 0) > 0:
        return "critical"
    if error_counts.get("error", 0) > 0:
        return "degraded"
    if error_counts.get("warning", 0) > 0:
        return "warning"
    return "healthy"
