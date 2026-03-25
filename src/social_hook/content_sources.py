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
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


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


def resolve_commits(
    conn: sqlite3.Connection,
    project_id: str,
    topic_id: str | None = None,
    **kwargs: Any,
) -> str:
    """Return commit file contents and messages for context.

    Include commit messages alongside file contents -- commit messages
    regularly provide great context about why changes were made.
    """
    from social_hook.db import operations as ops

    # Get recent decisions with their commit info
    decisions = ops.get_recent_decisions(conn, project_id, limit=5)
    if not decisions:
        return ""

    parts = []
    for d in decisions:
        commit_hash = d.commit_hash or "unknown"
        # Include the evaluator's reasoning as commit context
        reason = d.reasoning or ""
        parts.append(f"- {commit_hash[:8]}: {reason[:200]}")

    return "## Recent Commits\n" + "\n".join(parts)


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


# =============================================================================
# Module-level singleton
# =============================================================================

content_sources = ContentSourceRegistry()
content_sources.register("brief", resolve_brief)
content_sources.register("commits", resolve_commits)
content_sources.register("topic", resolve_topic)
content_sources.register("operator_suggestion", resolve_operator_suggestion)
