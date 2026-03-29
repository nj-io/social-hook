"""Domain models and enums for social-hook.

Models are being split into submodules. During migration, this file
bridges imports from the new submodules for backward compatibility.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

from social_hook.models._helpers import _from_iso, _to_iso  # noqa: F401
from social_hook.models.content import (  # noqa: F401
    ContentSuggestion,
    ContentTopic,
    DraftPattern,
    EvaluationCycle,
)
from social_hook.models.core import (  # noqa: F401
    CommitInfo,
    Decision,
    Draft,
    DraftChange,
    DraftTweet,
    Post,
    Project,
)
from social_hook.models.enums import (  # noqa: F401
    ARC_STATUSES,
    EDITABLE_STATUSES,
    PENDING_STATUSES,
    SUGGESTION_STATUSES,
    TERMINAL_STATUSES,
    TOPIC_STATUSES,
    ArcStatus,
    DecisionType,
    DraftStatus,
    LifecyclePhase,
    PipelineStage,
    PostCategory,
    PostFormat,
    is_draftable,
    is_held,
)
from social_hook.models.infra import OAuthToken, SystemErrorRecord, UsageLog  # noqa: F401
from social_hook.models.narrative import Arc, Lifecycle, NarrativeDebt  # noqa: F401
from social_hook.parsing import safe_int, safe_json_loads  # noqa: F401


@dataclass
class ProjectContext:
    """Assembled project state for agent context."""

    project: "Project"
    social_context: str | None
    lifecycle: Optional["Lifecycle"]
    active_arcs: list["Arc"]
    narrative_debt: int
    platform_introduced: dict[str, bool] = field(default_factory=dict)
    pending_drafts: list["Draft"] = field(default_factory=list)
    recent_decisions: list["Decision"] = field(default_factory=list)
    recent_posts: list["Post"] = field(default_factory=list)
    project_summary: str | None = None
    memories: list[dict] = field(default_factory=list)
    milestone_summaries: list[dict] = field(default_factory=list)
    context_notes: list[dict] = field(default_factory=list)
    session_narratives: list[dict] = field(default_factory=list)
    held_decisions: list["Decision"] = field(default_factory=list)
    arc_posts: dict[str, list["Post"]] = field(default_factory=dict)
    file_summaries: list[dict[str, str]] = field(default_factory=list)
    identity: Any = None  # IdentityConfig | None — kept as Any to avoid circular import

    @property
    def all_introduced(self) -> bool:
        """True if all tracked platforms have been introduced."""
        if not self.platform_introduced:
            return False
        return all(self.platform_introduced.values())
