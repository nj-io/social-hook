"""ContentSource resolver registry -- assembles drafter context.

Each source type maps to a resolver function. The routing layer
calls resolve() with the evaluator's ContextSourceSpec and gets
assembled context for the drafter.

Registry pattern -- new source types added by registering a resolver.
The registry class itself has zero social-hook domain imports.
"""

from __future__ import annotations

import logging
import sqlite3
import subprocess
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# Approximate chars-per-token ratio (1 token ≈ 4 chars)
_CHARS_PER_TOKEN = 4


class ContentSourceRegistry:
    """Registry of content source resolvers.

    The registry itself is domain-agnostic. Resolvers are registered
    with a source type name and called with keyword arguments.
    """

    def __init__(self) -> None:
        self._resolvers: dict[str, Callable[..., str]] = {}

    def register(self, source_type: str, resolver: Callable[..., str]) -> None:
        """Register a resolver for a source type."""
        self._resolvers[source_type] = resolver

    def resolve(
        self,
        source_types: list[str],
        **kwargs: Any,
    ) -> dict[str, str]:
        """Resolve all sources in the spec, return assembled context.

        Iterates source_types. For each type, looks up the registered
        resolver and calls it. Logs warning + skips for unknown types.

        Returns:
            Dict mapping source type -> resolved content string.
        """
        result: dict[str, str] = {}
        for source_type in source_types:
            resolver = self._resolvers.get(source_type)
            if resolver is None:
                logger.warning("Unknown content source type: %s", source_type)
                continue
            try:
                content = resolver(**kwargs)
                if content:
                    result[source_type] = content
            except Exception:
                logger.warning("Content source resolver '%s' failed", source_type, exc_info=True)
        return result


# =============================================================================
# Built-in resolvers
# =============================================================================


def resolve_brief(
    conn: sqlite3.Connection,
    project_id: str,
    **kwargs: Any,
) -> str:
    """Return project brief/summary sections."""
    from social_hook.db import operations as ops
    from social_hook.llm.brief import get_brief_sections

    project = ops.get_project(conn, project_id)
    if project and project.summary:
        sections = get_brief_sections(project.summary)
        if sections:
            parts = []
            for section_name, section_text in sections.items():
                parts.append(f"## {section_name}\n{section_text}")
            return "\n\n".join(parts)

    # Fallback: raw project summary
    summary = ops.get_project_summary(conn, project_id)
    if summary:
        return f"## Project Summary\n{summary}"
    return ""


def _get_repo_path(conn: sqlite3.Connection, project_id: str) -> str | None:
    """Get repo_path for a project. Returns None if not found."""
    from social_hook.db import operations as ops

    project = ops.get_project(conn, project_id)
    if project and project.repo_path:
        return project.repo_path
    return None


def _get_commit_diff(repo_path: str, commit_hash: str, max_file_size: int) -> str | None:
    """Get the diff for a single commit via git show.

    Returns the diff text, or None if the commit doesn't exist or git fails.
    """
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "show", "--stat", "--patch", commit_hash],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            logger.warning(
                "git show failed for %s in %s: %s",
                commit_hash,
                repo_path,
                result.stderr.strip(),
            )
            return None
        output = result.stdout
        if len(output) > max_file_size:
            output = output[:max_file_size] + "\n... [truncated at file size limit]"
        return output
    except subprocess.TimeoutExpired:
        logger.warning("git show timed out for %s in %s", commit_hash, repo_path)
        return None
    except FileNotFoundError:
        logger.warning("git not found when running git show for %s", commit_hash)
        return None


def _assemble_diffs(
    diffs: list[tuple[str, str]],
    max_doc_tokens: int,
) -> str:
    """Assemble commit diffs into a single context string within token budget.

    Args:
        diffs: List of (commit_hash, diff_text) tuples.
        max_doc_tokens: Maximum token budget for the output.

    Returns:
        Assembled context string.
    """
    max_chars = max_doc_tokens * _CHARS_PER_TOKEN
    parts: list[str] = []
    used_chars = 0
    header = "## Recent Commit Diffs\n\n"
    used_chars += len(header)

    for commit_hash, diff_text in diffs:
        entry_header = f"### Commit {commit_hash[:8]}\n```diff\n"
        entry_footer = "\n```\n\n"
        entry_overhead = len(entry_header) + len(entry_footer)

        remaining = max_chars - used_chars - entry_overhead
        if remaining <= 0:
            break

        if len(diff_text) > remaining:
            diff_text = diff_text[:remaining] + "\n... [truncated at token budget]"

        parts.append(entry_header + diff_text + entry_footer)
        used_chars += len(parts[-1])

    if not parts:
        return ""
    return header + "".join(parts).rstrip()


def resolve_commits(
    conn: sqlite3.Connection,
    project_id: str,
    topic_id: str | None = None,
    **kwargs: Any,
) -> str:
    """Return actual file diffs from recent commits for drafter context.

    Fetches commit diffs via git show, capped at token limits.
    Prefers notable/significant commits when classifications are available.
    """
    from social_hook.config.project import ContextConfig
    from social_hook.db import operations as ops

    repo_path = _get_repo_path(conn, project_id)
    if not repo_path:
        return ""

    decisions = ops.get_recent_decisions(conn, project_id, limit=10)
    if not decisions:
        return ""

    # Load context config for token/size limits
    ctx_cfg = ContextConfig()
    try:
        from social_hook.config.project import load_project_config

        pcfg = load_project_config(repo_path)
        ctx_cfg = pcfg.context
    except Exception:
        logger.warning("Could not load project config for %s, using defaults", project_id)

    # Try to get classifications from cached analysis to prioritize commits
    _prioritized = _prioritize_decisions(conn, project_id, decisions)

    diffs: list[tuple[str, str]] = []
    for d in _prioritized:
        if not d.commit_hash:
            continue
        diff = _get_commit_diff(repo_path, d.commit_hash, ctx_cfg.max_file_size)
        if diff:
            diffs.append((d.commit_hash, diff))

    return _assemble_diffs(diffs, ctx_cfg.max_doc_tokens)


def _prioritize_decisions(
    conn: sqlite3.Connection,
    project_id: str,
    decisions: list,
) -> list:
    """Reorder decisions to prefer notable/significant-classified commits.

    Queries evaluation_cycles for cached commit_analysis_json to find
    classifications. Falls back to original order if no analysis data.
    """
    from social_hook.parsing import safe_json_loads

    # Build a map of commit_hash -> classification from evaluation cycles
    classifications: dict[str, str] = {}
    try:
        rows = conn.execute(
            """
            SELECT trigger_ref, commit_analysis_json FROM evaluation_cycles
            WHERE project_id = ? AND commit_analysis_json IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 20
            """,
            (project_id,),
        ).fetchall()
        for row in rows:
            trigger_ref = row[0]
            analysis_json = row[1]
            if trigger_ref and analysis_json:
                data = safe_json_loads(analysis_json, "evaluation_cycle_analysis", default={})
                ca = data.get("commit_analysis", {})
                classification = ca.get("classification")
                if classification:
                    classifications[trigger_ref] = classification
    except Exception:
        logger.warning("Could not query evaluation cycles for classification", exc_info=True)

    if not classifications:
        return decisions

    # Priority order: significant > notable > routine > trivial
    priority_map = {"significant": 0, "notable": 1, "routine": 2, "trivial": 3}

    def sort_key(d):
        cls = classifications.get(d.commit_hash, "routine")
        return priority_map.get(cls, 2)

    return sorted(decisions, key=sort_key)


def resolve_topic(
    conn: sqlite3.Connection,
    project_id: str,
    topic_id: str | None = None,
    **kwargs: Any,
) -> str:
    """Return topic description from content_topics."""
    if not topic_id:
        return ""

    from social_hook.db import operations as ops

    topic = ops.get_topic(conn, topic_id)
    if not topic:
        return ""

    parts = [f"## Content Topic: {topic.topic}"]
    if topic.description:
        parts.append(topic.description)
    parts.append(f"Status: {topic.status}, Commits: {topic.commit_count}")
    return "\n".join(parts)


def resolve_operator_suggestion(
    conn: sqlite3.Connection,
    project_id: str,
    suggestion_id: str | None = None,
    **kwargs: Any,
) -> str:
    """Return operator suggestion content."""
    if not suggestion_id:
        return ""

    from social_hook.db import operations as ops

    # Get suggestion by iterating project suggestions (no get-by-id op yet)
    suggestions = ops.get_suggestions_by_project(conn, project_id)
    for s in suggestions:
        if s.id == suggestion_id:
            parts = ["## Operator Suggestion"]
            parts.append(s.idea)
            if s.strategy:
                parts.append(f"Strategy: {s.strategy}")
            return "\n".join(parts)

    logger.warning("Operator suggestion '%s' not found", suggestion_id)
    return ""


def resolve_topic_commits(
    conn: sqlite3.Connection,
    project_id: str,
    topic_id: str | None = None,
    **kwargs: Any,
) -> str:
    """Return consolidated diffs from all commits contributing to a topic.

    Queries the topic_commits table for commit hashes, fetches actual
    diffs via git show, and assembles them within token/size limits.
    """
    if not topic_id:
        return ""

    from social_hook.config.project import ContextConfig

    repo_path = _get_repo_path(conn, project_id)
    if not repo_path:
        return ""

    # Get contributing commit hashes from topic_commits table
    try:
        rows = conn.execute(
            """
            SELECT commit_hash FROM topic_commits
            WHERE topic_id = ?
            ORDER BY matched_at DESC
            """,
            (topic_id,),
        ).fetchall()
    except Exception:
        logger.warning("Could not query topic_commits for topic %s", topic_id, exc_info=True)
        return ""

    if not rows:
        return ""

    commit_hashes = [row[0] for row in rows]

    # Load context config for limits
    ctx_cfg = ContextConfig()
    try:
        from social_hook.config.project import load_project_config

        pcfg = load_project_config(repo_path)
        ctx_cfg = pcfg.context
    except Exception:
        logger.warning("Could not load project config for %s, using defaults", project_id)

    # Fetch diffs for each commit
    diffs: list[tuple[str, str]] = []
    for commit_hash in commit_hashes:
        diff = _get_commit_diff(repo_path, commit_hash, ctx_cfg.max_file_size)
        if diff:
            diffs.append((commit_hash, diff))

    if not diffs:
        return ""

    # Get topic name for header
    topic_name = topic_id
    try:
        from social_hook.db import operations as ops

        topic = ops.get_topic(conn, topic_id)
        if topic:
            topic_name = topic.topic
    except Exception:
        pass

    # Assemble with custom header
    max_chars = ctx_cfg.max_doc_tokens * _CHARS_PER_TOKEN
    header = f"## Code changes across {len(diffs)} commits for topic '{topic_name}'\n\n"
    parts: list[str] = []
    used_chars = len(header)

    for commit_hash, diff_text in diffs:
        entry_header = f"### Commit {commit_hash[:8]}\n```diff\n"
        entry_footer = "\n```\n\n"
        entry_overhead = len(entry_header) + len(entry_footer)

        remaining = max_chars - used_chars - entry_overhead
        if remaining <= 0:
            break

        if len(diff_text) > remaining:
            diff_text = diff_text[:remaining] + "\n... [truncated at token budget]"

        parts.append(entry_header + diff_text + entry_footer)
        used_chars += len(parts[-1])

    if not parts:
        return ""
    return header + "".join(parts).rstrip()


# =============================================================================
# Module-level singleton
# =============================================================================

content_sources = ContentSourceRegistry()
content_sources.register("brief", resolve_brief)
content_sources.register("commits", resolve_commits)
content_sources.register("topic", resolve_topic)
content_sources.register("topic_commits", resolve_topic_commits)
content_sources.register("operator_suggestion", resolve_operator_suggestion)
