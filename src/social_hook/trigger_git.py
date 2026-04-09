"""Git subprocess utilities for the trigger pipeline.

Parses commit metadata (message, diff, stat, timestamps) from git.
Near-reusable: only depends on CommitInfo dataclass and safe_int utility.
"""

from __future__ import annotations

import logging
import subprocess

from social_hook.models.core import CommitInfo
from social_hook.parsing import safe_int

logger = logging.getLogger(__name__)


def parse_commit_info(commit_hash: str, repo_path: str) -> CommitInfo:
    """Parse commit info from git.

    Args:
        commit_hash: Git commit hash
        repo_path: Path to the git repository

    Returns:
        CommitInfo with parsed data
    """
    try:
        # Get full commit message (subject + body)
        message = subprocess.run(
            ["git", "-C", repo_path, "log", "-1", "--format=%B", commit_hash],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Get author date (ISO 8601 with timezone)
        timestamp = subprocess.run(
            ["git", "-C", repo_path, "log", "-1", "--format=%aI", commit_hash],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Get parent commit's author date (fails with exit 128 on first commit)
        parent_result = subprocess.run(
            ["git", "-C", repo_path, "log", "-1", "--format=%aI", f"{commit_hash}~1"],
            capture_output=True,
            text=True,
        )
        parent_timestamp = parent_result.stdout.strip() if parent_result.returncode == 0 else None

        # Get stat summary
        stat_output = subprocess.run(
            ["git", "-C", repo_path, "show", "--stat", "--format=", commit_hash],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Parse files changed from stat
        files_changed = []
        insertions = 0
        deletions = 0
        for line in stat_output.split("\n"):
            line = line.strip()
            if "|" in line and not line.startswith(" "):
                # "filename | N +++--"
                parts = line.split("|")
                if parts:
                    files_changed.append(parts[0].strip())
            elif "changed" in line:
                # Summary line: "N files changed, N insertions(+), N deletions(-)"
                if "insertion" in line:
                    for part in line.split(","):
                        part = part.strip()
                        if "insertion" in part:
                            insertions = safe_int(part.split()[0], 0, "git stat insertions")
                        elif "deletion" in part:
                            deletions = safe_int(part.split()[0], 0, "git stat deletions")

        # Get diff
        diff = subprocess.run(
            ["git", "-C", repo_path, "diff", f"{commit_hash}~1..{commit_hash}"],
            capture_output=True,
            text=True,
        ).stdout

        # Fallback for first commit (no parent)
        if not diff:
            diff = subprocess.run(
                ["git", "-C", repo_path, "show", "--format=", commit_hash],
                capture_output=True,
                text=True,
            ).stdout

        return CommitInfo(
            hash=commit_hash,
            message=message,
            diff=diff,
            files_changed=files_changed,
            insertions=insertions,
            deletions=deletions,
            timestamp=timestamp,
            parent_timestamp=parent_timestamp,
        )
    except subprocess.CalledProcessError:
        # Return minimal info if git commands fail
        return CommitInfo(
            hash=commit_hash,
            message="(unable to parse)",
            diff="",
        )


def git_remote_origin(repo_path: str) -> str | None:
    """Get the git remote origin URL for worktree detection.

    Args:
        repo_path: Path to the git repository

    Returns:
        Remote origin URL, or None if not available
    """
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or None
    except subprocess.CalledProcessError:
        return None


def is_git_repo(path: str) -> bool:
    """Check if a path is inside a git repository.

    Args:
        path: Directory path to check

    Returns:
        True if the path is inside a git repo, False otherwise
    """
    try:
        result = subprocess.run(
            ["git", "-C", path, "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except (OSError, FileNotFoundError):
        return False


def collect_git_stats(repo_path: str) -> dict | None:
    """Collect countable project stats from git.

    Returns a dict with keys like commit_count, contributor_count,
    first_commit_date, latest_commit_date, active_branch_count.
    Returns None for non-git directories or on failure.

    Args:
        repo_path: Path to the git repository
    """
    if not is_git_repo(repo_path):
        return None

    stats: dict = {}

    try:
        # Total commit count
        result = subprocess.run(
            ["git", "-C", repo_path, "rev-list", "--count", "HEAD"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            stats["commit_count"] = safe_int(result.stdout.strip(), 0, "commit count")

        # Contributor count
        result = subprocess.run(
            ["git", "-C", repo_path, "shortlog", "-sn", "--all"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            stats["contributor_count"] = len(
                [line for line in result.stdout.strip().split("\n") if line.strip()]
            )

        # First commit date
        result = subprocess.run(
            ["git", "-C", repo_path, "log", "--reverse", "--format=%aI", "--max-count=1"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            stats["first_commit_date"] = result.stdout.strip()

        # Latest commit date
        result = subprocess.run(
            ["git", "-C", repo_path, "log", "--format=%aI", "--max-count=1"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            stats["latest_commit_date"] = result.stdout.strip()

        # Active branch count
        result = subprocess.run(
            ["git", "-C", repo_path, "branch", "--list"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            stats["active_branch_count"] = len(
                [line for line in result.stdout.strip().split("\n") if line.strip()]
            )

        # Commits in last 30 days
        result = subprocess.run(
            ["git", "-C", repo_path, "rev-list", "--count", "--since=30.days", "HEAD"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            stats["commits_last_30_days"] = safe_int(
                result.stdout.strip(), 0, "commits last 30 days"
            )

    except (OSError, FileNotFoundError):
        logger.debug("Git not available for stats collection at %s", repo_path)
        return None

    return stats if stats else None


def _get_current_branch(repo_path: str) -> str | None:
    """Get the current git branch name. Returns None for detached HEAD."""
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        branch = result.stdout.strip()
        return None if branch == "HEAD" else branch
    except (subprocess.CalledProcessError, OSError):
        return None
