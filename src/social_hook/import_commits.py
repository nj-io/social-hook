"""Import historical git commits as 'imported' decisions."""

import logging
import sqlite3
import subprocess

from social_hook.db import operations as ops
from social_hook.filesystem import generate_id
from social_hook.models import Decision

logger = logging.getLogger(__name__)


def _git_log_commits(
    repo_path: str, branch: str | None = None, limit: int | None = None
) -> list[dict[str, str]]:
    """Get commits from a repo/branch via git log.

    Args:
        repo_path: Path to git repository
        branch: Branch filter (None = all branches)
        limit: Maximum number of commits to return (None = no limit).
            Returns the most recent N commits (git log runs newest-first,
            reversed to chronological order, then truncated).

    Returns list of dicts with keys: hash, message, date.
    """
    cmd = [
        "git",
        "-C",
        repo_path,
        "log",
        "--format=%H%x00%s%x00%aI",  # hash, subject, author date ISO
    ]
    if limit:
        # git log is newest-first; -n gives most recent N; we reverse in Python below
        cmd.extend(["-n", str(limit)])
    else:
        cmd.append("--reverse")
    if branch:
        cmd.append(branch)
    else:
        cmd.append("--all")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"git log failed: {e.stderr}")
        return []

    commits = []
    seen_hashes: set[str] = set()
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("\x00")
        if len(parts) != 3:
            continue
        commit_hash, message, date = parts
        if commit_hash in seen_hashes:
            continue
        seen_hashes.add(commit_hash)
        commits.append(
            {
                "hash": commit_hash,
                "message": message,
                "date": date,
            }
        )
    # When limit is set, git log returns newest-first; reverse to chronological
    if limit:
        commits.reverse()
    return commits


def _resolve_branch_for_commit(
    repo_path: str, commit_hash: str, target_branch: str | None
) -> str | None:
    """Resolve the branch name for a commit.

    If target_branch is specified, use it. Otherwise try to find the
    first branch containing this commit.
    """
    if target_branch:
        return target_branch
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                repo_path,
                "branch",
                "--contains",
                commit_hash,
                "--format=%(refname:short)",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        branches = [b.strip() for b in result.stdout.strip().split("\n") if b.strip()]
        return branches[0] if branches else None
    except subprocess.CalledProcessError:
        return None


def get_import_preview(
    conn: sqlite3.Connection,
    project_id: str,
    repo_path: str,
    branch: str | None = None,
    limit: int | None = None,
) -> dict[str, int]:
    """Preview how many commits would be imported.

    Returns dict with total_commits, already_tracked, importable.
    """
    commits = _git_log_commits(repo_path, branch, limit=limit)
    total = len(commits)

    if total == 0:
        return {"total_commits": 0, "already_tracked": 0, "importable": 0}

    hashes = [c["hash"] for c in commits]
    placeholders = ",".join("?" * len(hashes))
    tracked = conn.execute(
        f"SELECT COUNT(*) FROM decisions WHERE project_id = ? AND commit_hash IN ({placeholders})",
        [project_id] + hashes,
    ).fetchone()[0]

    return {
        "total_commits": total,
        "already_tracked": tracked,
        "importable": total - tracked,
    }


def import_project_commits(
    conn: sqlite3.Connection,
    project_id: str,
    repo_path: str,
    branch: str | None = None,
    limit: int | None = None,
) -> dict[str, int]:
    """Import historical git commits as 'imported' decisions.

    When no branch is specified, defaults to the project's trigger_branch
    (if configured). This ensures imports match the branch the system follows.
    Falls back to all branches if no trigger_branch is set.

    Args:
        conn: Database connection
        project_id: Project to import into
        repo_path: Path to git repository
        branch: Optional branch filter (None = use trigger_branch or all)
        limit: Maximum number of recent commits to import (None = all)

    Returns:
        Dict with imported, skipped, total counts.
    """
    if branch is None:
        project = ops.get_project(conn, project_id)
        if project and project.trigger_branch:
            branch = project.trigger_branch
            logger.info("Import defaulting to trigger branch: %s", branch)

    commits = _git_log_commits(repo_path, branch, limit=limit)
    total = len(commits)

    if total == 0:
        return {"imported": 0, "skipped": 0, "total": 0}

    decisions_with_dates: list[tuple[Decision, str]] = []
    for c in commits:
        commit_branch = _resolve_branch_for_commit(repo_path, c["hash"], branch)
        d = Decision(
            id=generate_id("decision"),
            project_id=project_id,
            commit_hash=c["hash"],
            decision="imported",
            reasoning="",
            commit_message=c["message"],
            branch=commit_branch,
        )
        decisions_with_dates.append((d, c["date"]))

    inserted = ops.insert_decisions_batch(conn, decisions_with_dates)

    return {
        "imported": inserted,
        "skipped": total - inserted,
        "total": total,
    }
