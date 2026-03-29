"""Assembled project context for LLM agent prompts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from social_hook.models.core import Decision, Draft, Post, Project
    from social_hook.models.narrative import Arc, Lifecycle


@dataclass
class ProjectContext:
    """Assembled project state for agent context."""

    project: Project
    social_context: str | None
    lifecycle: Lifecycle | None
    active_arcs: list[Arc]
    narrative_debt: int
    platform_introduced: dict[str, bool] = field(default_factory=dict)
    pending_drafts: list[Draft] = field(default_factory=list)
    recent_decisions: list[Decision] = field(default_factory=list)
    recent_posts: list[Post] = field(default_factory=list)
    project_summary: str | None = None
    memories: list[dict] = field(default_factory=list)
    milestone_summaries: list[dict] = field(default_factory=list)
    context_notes: list[dict] = field(default_factory=list)
    session_narratives: list[dict] = field(default_factory=list)
    held_decisions: list[Decision] = field(default_factory=list)
    arc_posts: dict[str, list[Post]] = field(default_factory=dict)
    file_summaries: list[dict[str, str]] = field(default_factory=list)
    identity: Any = None  # IdentityConfig | None — kept as Any to avoid circular import

    @property
    def all_introduced(self) -> bool:
        """True if all tracked platforms have been introduced."""
        if not self.platform_introduced:
            return False
        return all(self.platform_introduced.values())
