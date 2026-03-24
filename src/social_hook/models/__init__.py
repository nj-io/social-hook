"""Domain models and enums for social-hook."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from social_hook.parsing import safe_json_loads

# =============================================================================
# Enums (must match DB CHECK constraints)
# =============================================================================


class DraftStatus(Enum):
    """Status of a content draft."""

    DRAFT = "draft"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    POSTED = "posted"
    REJECTED = "rejected"
    FAILED = "failed"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"
    DEFERRED = "deferred"


# Single source of truth for status group checks.
# Import these instead of writing inline tuples.
TERMINAL_STATUSES = frozenset(
    {
        DraftStatus.POSTED.value,
        DraftStatus.REJECTED.value,
        DraftStatus.CANCELLED.value,
        DraftStatus.SUPERSEDED.value,
    }
)
PENDING_STATUSES = frozenset(
    {
        DraftStatus.DRAFT.value,
        DraftStatus.APPROVED.value,
        DraftStatus.SCHEDULED.value,
        DraftStatus.DEFERRED.value,
    }
)
EDITABLE_STATUSES = frozenset(
    {
        DraftStatus.DRAFT.value,
        DraftStatus.DEFERRED.value,
    }
)

TOPIC_STATUSES = frozenset({"uncovered", "holding", "partial", "covered"})
SUGGESTION_STATUSES = frozenset({"pending", "evaluated", "drafted", "dismissed"})


class DecisionType(Enum):
    """Evaluation decision for a commit."""

    DRAFT = "draft"
    HOLD = "hold"
    SKIP = "skip"
    IMPORTED = "imported"
    DEFERRED_EVAL = "deferred_eval"


class EpisodeType(Enum):
    """Post structural categories (vocabulary for angle selection)."""

    DECISION = "decision"  # Why we chose X over Y
    BEFORE_AFTER = "before_after"  # Measurable change with proof
    DEMO_PROOF = "demo_proof"  # Show the working thing
    MILESTONE = "milestone"  # Checkpoint - what changed, what's next
    POSTMORTEM = "postmortem"  # Issue -> fix -> learnings
    LAUNCH = "launch"  # Value prop + who it's for + CTA
    SYNTHESIS = "synthesis"  # Frames overall story, pays narrative debt


class PostCategory(Enum):
    """How each post relates to ongoing narrative."""

    ARC = "arc"  # Advances an active narrative arc
    OPPORTUNISTIC = "opportunistic"  # High-signal standalone post
    EXPERIMENT = "experiment"  # Testing new format, tone, or angle


class PostFormat(Enum):
    """Format of a drafted post."""

    SINGLE = "single"
    THREAD = "thread"
    QUOTE = "quote"
    REPLY = "reply"


class LifecyclePhase(Enum):
    """Project lifecycle phases."""

    RESEARCH = "research"
    BUILD = "build"
    DEMO = "demo"
    LAUNCH = "launch"
    POST_LAUNCH = "post_launch"


class ArcStatus(Enum):
    """Status of a narrative arc."""

    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


# =============================================================================
# Helper functions
# =============================================================================


def _to_iso(dt: datetime | None) -> str | None:
    """Convert datetime to ISO string."""
    return dt.isoformat() if dt else None


def _from_iso(s: str | None) -> datetime | None:
    """Convert ISO string to datetime."""
    return datetime.fromisoformat(s) if s else None


def _now_iso() -> str:
    """Get current time as ISO string."""
    return datetime.now(timezone.utc).isoformat()


def is_draftable(decision: str) -> bool:
    """Check if a decision indicates content should be drafted."""
    return decision == "draft"


def is_held(decision: str) -> bool:
    """Check if a decision is held for consolidation."""
    return decision == "hold"


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass
class Project:
    """A registered project (git repository)."""

    id: str
    name: str
    repo_path: str
    repo_origin: str | None = None
    summary: str | None = None
    summary_updated_at: datetime | None = None
    paused: bool = False
    discovery_files: str | None = None  # JSON-serialized list of file paths
    prompt_docs: str | None = None
    trigger_branch: str | None = None
    brief_section_metadata: dict | None = None
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "repo_path": self.repo_path,
            "repo_origin": self.repo_origin,
            "summary": self.summary,
            "summary_updated_at": _to_iso(self.summary_updated_at),
            "paused": self.paused,
            "discovery_files": self.discovery_files,
            "prompt_docs": self.prompt_docs,
            "trigger_branch": self.trigger_branch,
            "brief_section_metadata": self.brief_section_metadata,
            "created_at": _to_iso(self.created_at),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Project":
        brief_meta = d.get("brief_section_metadata")
        if isinstance(brief_meta, str):
            brief_meta = safe_json_loads(brief_meta, "Project.brief_section_metadata", default={})
        return cls(
            id=d["id"],
            name=d["name"],
            repo_path=d["repo_path"],
            repo_origin=d.get("repo_origin"),
            summary=d.get("summary"),
            summary_updated_at=_from_iso(d.get("summary_updated_at")),
            paused=bool(d.get("paused", False)),
            discovery_files=d.get("discovery_files"),
            prompt_docs=d.get("prompt_docs"),
            trigger_branch=d.get("trigger_branch"),
            brief_section_metadata=brief_meta,
            created_at=_from_iso(d.get("created_at")),
        )

    def to_row(self) -> tuple:
        """Return tuple for INSERT (id, name, repo_path, repo_origin, summary, summary_updated_at, paused)."""
        return (
            self.id,
            self.name,
            self.repo_path,
            self.repo_origin,
            self.summary,
            _to_iso(self.summary_updated_at),
            1 if self.paused else 0,
        )


@dataclass
class Decision:
    """An evaluation decision for a commit."""

    id: str
    project_id: str
    commit_hash: str
    decision: str  # DecisionType value
    reasoning: str
    commit_message: str | None = None
    angle: str | None = None
    episode_type: str | None = None  # EpisodeType value
    episode_tags: list[str] = field(default_factory=list)
    post_category: str | None = None  # PostCategory value
    arc_id: str | None = None
    media_tool: str | None = None
    platforms: dict[str, str] = field(default_factory=dict)
    targets: dict = field(default_factory=dict)
    commit_summary: str | None = None
    consolidate_with: list[str] | None = None
    reference_posts: list[str] | None = None
    processed: bool = False
    processed_at: datetime | None = None
    batch_id: str | None = None
    branch: str | None = None
    trigger_source: str = "commit"
    created_at: datetime | None = None

    def __post_init__(self):
        # Validate decision value
        valid_decisions = [d.value for d in DecisionType]
        if self.decision not in valid_decisions:
            raise ValueError(
                f"Invalid decision '{self.decision}', must be one of {valid_decisions}"
            )

        # Validate episode_type if provided
        if self.episode_type:
            valid_episodes = [e.value for e in EpisodeType]
            if self.episode_type not in valid_episodes:
                raise ValueError(
                    f"Invalid episode_type '{self.episode_type}', must be one of {valid_episodes}"
                )

        # Validate post_category if provided
        if self.post_category:
            valid_categories = [c.value for c in PostCategory]
            if self.post_category not in valid_categories:
                raise ValueError(
                    f"Invalid post_category '{self.post_category}', must be one of {valid_categories}"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "commit_hash": self.commit_hash,
            "commit_message": self.commit_message,
            "decision": self.decision,
            "reasoning": self.reasoning,
            "angle": self.angle,
            "episode_type": self.episode_type,
            "episode_tags": self.episode_tags,
            "post_category": self.post_category,
            "arc_id": self.arc_id,
            "media_tool": self.media_tool,
            "platforms": self.platforms,
            "targets": self.targets,
            "commit_summary": self.commit_summary,
            "consolidate_with": self.consolidate_with,
            "reference_posts": self.reference_posts,
            "processed": self.processed,
            "processed_at": _to_iso(self.processed_at),
            "batch_id": self.batch_id,
            "branch": self.branch,
            "trigger_source": self.trigger_source,
            "created_at": _to_iso(self.created_at),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Decision":
        platforms = d.get("platforms", {})
        if isinstance(platforms, str):
            platforms = safe_json_loads(platforms, "Decision.platforms", default={})

        episode_tags = d.get("episode_tags", [])
        if isinstance(episode_tags, str):
            episode_tags = safe_json_loads(episode_tags, "Decision.episode_tags", default=[])

        targets = d.get("targets", {})
        if isinstance(targets, str):
            targets = safe_json_loads(targets, "Decision.targets", default={})

        consolidate_with = d.get("consolidate_with")
        if isinstance(consolidate_with, str):
            consolidate_with = safe_json_loads(
                consolidate_with, "Decision.consolidate_with", default=[]
            )

        reference_posts = d.get("reference_posts")
        if isinstance(reference_posts, str):
            reference_posts = safe_json_loads(
                reference_posts, "Decision.reference_posts", default=[]
            )

        return cls(
            id=d["id"],
            project_id=d["project_id"],
            commit_hash=d["commit_hash"],
            decision=d["decision"],
            reasoning=d["reasoning"],
            commit_message=d.get("commit_message"),
            angle=d.get("angle"),
            episode_type=d.get("episode_type"),
            episode_tags=episode_tags,
            post_category=d.get("post_category"),
            arc_id=d.get("arc_id"),
            media_tool=d.get("media_tool"),
            platforms=platforms,
            targets=targets,
            commit_summary=d.get("commit_summary"),
            consolidate_with=consolidate_with,
            reference_posts=reference_posts,
            processed=bool(d.get("processed", False)),
            processed_at=_from_iso(d.get("processed_at")),
            batch_id=d.get("batch_id"),
            branch=d.get("branch"),
            trigger_source=d.get("trigger_source", "commit"),
            created_at=_from_iso(d.get("created_at")),
        )

    def to_row(self) -> tuple:
        """Return tuple for INSERT (19 columns)."""
        import json

        return (
            self.id,
            self.project_id,
            self.commit_hash,
            self.commit_message,
            self.decision,
            self.reasoning,
            self.angle,
            self.episode_type,
            json.dumps(self.episode_tags),
            self.post_category,
            self.arc_id,
            self.media_tool,
            json.dumps(self.platforms),
            json.dumps(self.targets),
            self.commit_summary,
            json.dumps(self.consolidate_with) if self.consolidate_with is not None else None,
            json.dumps(self.reference_posts) if self.reference_posts is not None else None,
            self.branch,
            self.trigger_source,
        )


@dataclass
class Draft:
    """A content draft for posting."""

    id: str
    project_id: str
    decision_id: str
    platform: str
    content: str
    status: str = "draft"  # DraftStatus value
    media_paths: list[str] = field(default_factory=list)
    media_type: str | None = None
    media_spec: dict | None = None
    media_spec_used: dict | None = None
    suggested_time: datetime | None = None
    scheduled_time: datetime | None = None
    reasoning: str | None = None
    superseded_by: str | None = None
    retry_count: int = 0
    last_error: str | None = None
    is_intro: bool = False
    post_format: str | None = None
    reference_post_id: str | None = None
    target_id: str | None = None
    evaluation_cycle_id: str | None = None
    topic_id: str | None = None
    suggestion_id: str | None = None
    pattern_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self):
        valid_statuses = [s.value for s in DraftStatus]
        if self.status not in valid_statuses:
            raise ValueError(f"Invalid status '{self.status}', must be one of {valid_statuses}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "decision_id": self.decision_id,
            "platform": self.platform,
            "status": self.status,
            "content": self.content,
            "media_paths": self.media_paths,
            "media_type": self.media_type,
            "media_spec": self.media_spec,
            "media_spec_used": self.media_spec_used,
            "suggested_time": _to_iso(self.suggested_time),
            "scheduled_time": _to_iso(self.scheduled_time),
            "reasoning": self.reasoning,
            "superseded_by": self.superseded_by,
            "retry_count": self.retry_count,
            "last_error": self.last_error,
            "is_intro": self.is_intro,
            "post_format": self.post_format,
            "reference_post_id": self.reference_post_id,
            "target_id": self.target_id,
            "evaluation_cycle_id": self.evaluation_cycle_id,
            "topic_id": self.topic_id,
            "suggestion_id": self.suggestion_id,
            "pattern_id": self.pattern_id,
            "created_at": _to_iso(self.created_at),
            "updated_at": _to_iso(self.updated_at),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Draft":
        media_paths = d.get("media_paths", [])
        if isinstance(media_paths, str):
            media_paths = safe_json_loads(media_paths, "Draft.media_paths", default=[])
        media_spec_raw = d.get("media_spec")
        if isinstance(media_spec_raw, str):
            media_spec = safe_json_loads(media_spec_raw, "Draft.media_spec", default=None)
        else:
            media_spec = media_spec_raw
        media_spec_used_raw = d.get("media_spec_used")
        if isinstance(media_spec_used_raw, str):
            media_spec_used = safe_json_loads(
                media_spec_used_raw, "Draft.media_spec_used", default=None
            )
        else:
            media_spec_used = media_spec_used_raw
        return cls(
            id=d["id"],
            project_id=d["project_id"],
            decision_id=d["decision_id"],
            platform=d["platform"],
            status=d.get("status", "draft"),
            content=d["content"],
            media_paths=media_paths,
            media_type=d.get("media_type"),
            media_spec=media_spec,
            media_spec_used=media_spec_used,
            suggested_time=_from_iso(d.get("suggested_time")),
            scheduled_time=_from_iso(d.get("scheduled_time")),
            reasoning=d.get("reasoning"),
            superseded_by=d.get("superseded_by"),
            retry_count=d.get("retry_count", 0),
            last_error=d.get("last_error"),
            is_intro=bool(d.get("is_intro", False)),
            post_format=d.get("post_format"),
            reference_post_id=d.get("reference_post_id"),
            target_id=d.get("target_id"),
            evaluation_cycle_id=d.get("evaluation_cycle_id"),
            topic_id=d.get("topic_id"),
            suggestion_id=d.get("suggestion_id"),
            pattern_id=d.get("pattern_id"),
            created_at=_from_iso(d.get("created_at")),
            updated_at=_from_iso(d.get("updated_at")),
        )

    def to_row(self) -> tuple:
        """Return tuple for INSERT (24 columns)."""
        import json

        return (
            self.id,
            self.project_id,
            self.decision_id,
            self.platform,
            self.status,
            self.content,
            json.dumps(self.media_paths),
            self.media_type,
            json.dumps(self.media_spec) if self.media_spec else None,
            json.dumps(self.media_spec_used) if self.media_spec_used else None,
            _to_iso(self.suggested_time),
            _to_iso(self.scheduled_time),
            self.reasoning,
            self.superseded_by,
            self.retry_count,
            self.last_error,
            1 if self.is_intro else 0,
            self.post_format,
            self.reference_post_id,
            self.target_id,
            self.evaluation_cycle_id,
            self.topic_id,
            self.suggestion_id,
            self.pattern_id,
        )


@dataclass
class DraftTweet:
    """Individual tweet in a thread."""

    id: str
    draft_id: str
    position: int
    content: str
    media_paths: list[str] = field(default_factory=list)
    external_id: str | None = None
    posted_at: datetime | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "draft_id": self.draft_id,
            "position": self.position,
            "content": self.content,
            "media_paths": self.media_paths,
            "external_id": self.external_id,
            "posted_at": _to_iso(self.posted_at),
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DraftTweet":
        media_paths = d.get("media_paths", [])
        if isinstance(media_paths, str):
            media_paths = safe_json_loads(media_paths, "DraftTweet.media_paths", default=[])
        return cls(
            id=d["id"],
            draft_id=d["draft_id"],
            position=d["position"],
            content=d["content"],
            media_paths=media_paths,
            external_id=d.get("external_id"),
            posted_at=_from_iso(d.get("posted_at")),
            error=d.get("error"),
        )

    def to_row(self) -> tuple:
        """Return tuple for INSERT."""
        import json

        return (
            self.id,
            self.draft_id,
            self.position,
            self.content,
            json.dumps(self.media_paths),
            self.external_id,
            _to_iso(self.posted_at),
            self.error,
        )


@dataclass
class DraftChange:
    """Audit trail entry for draft changes."""

    id: str
    draft_id: str
    field: str
    old_value: str | None
    new_value: str | None
    changed_by: str  # 'gatekeeper', 'human', 'expert'
    changed_at: datetime | None = None

    def __post_init__(self):
        valid_changers = ("gatekeeper", "human", "expert")
        if self.changed_by not in valid_changers:
            raise ValueError(
                f"Invalid changed_by '{self.changed_by}', must be one of {valid_changers}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "draft_id": self.draft_id,
            "field": self.field,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "changed_by": self.changed_by,
            "changed_at": _to_iso(self.changed_at),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DraftChange":
        return cls(
            id=d["id"],
            draft_id=d["draft_id"],
            field=d["field"],
            old_value=d.get("old_value"),
            new_value=d.get("new_value"),
            changed_by=d["changed_by"],
            changed_at=_from_iso(d.get("changed_at")),
        )

    def to_row(self) -> tuple:
        """Return tuple for INSERT."""
        return (
            self.id,
            self.draft_id,
            self.field,
            self.old_value,
            self.new_value,
            self.changed_by,
        )


@dataclass
class Post:
    """A published post."""

    id: str
    draft_id: str
    project_id: str
    platform: str
    content: str
    external_id: str | None = None
    external_url: str | None = None
    target_id: str | None = None
    topic_tags: list[str] = field(default_factory=list)
    feature_tags: list[str] = field(default_factory=list)
    is_thread_head: bool = False
    posted_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "draft_id": self.draft_id,
            "project_id": self.project_id,
            "platform": self.platform,
            "external_id": self.external_id,
            "external_url": self.external_url,
            "content": self.content,
            "target_id": self.target_id,
            "topic_tags": self.topic_tags,
            "feature_tags": self.feature_tags,
            "is_thread_head": self.is_thread_head,
            "posted_at": _to_iso(self.posted_at),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Post":
        topic_tags = d.get("topic_tags", [])
        if isinstance(topic_tags, str):
            topic_tags = safe_json_loads(topic_tags, "Post.topic_tags", default=[])
        feature_tags = d.get("feature_tags", [])
        if isinstance(feature_tags, str):
            feature_tags = safe_json_loads(feature_tags, "Post.feature_tags", default=[])
        return cls(
            id=d["id"],
            draft_id=d["draft_id"],
            project_id=d["project_id"],
            platform=d["platform"],
            external_id=d.get("external_id"),
            external_url=d.get("external_url"),
            content=d["content"],
            target_id=d.get("target_id"),
            topic_tags=topic_tags,
            feature_tags=feature_tags,
            is_thread_head=bool(d.get("is_thread_head", False)),
            posted_at=_from_iso(d.get("posted_at")),
        )

    def to_row(self) -> tuple:
        """Return tuple for INSERT (11 columns)."""
        import json

        return (
            self.id,
            self.draft_id,
            self.project_id,
            self.platform,
            self.external_id,
            self.external_url,
            self.content,
            self.target_id,
            json.dumps(self.topic_tags),
            json.dumps(self.feature_tags),
            1 if self.is_thread_head else 0,
        )


@dataclass
class Lifecycle:
    """Project lifecycle tracking."""

    project_id: str
    phase: str = "research"  # LifecyclePhase value
    confidence: float = 0.5
    evidence: list[str] = field(default_factory=list)
    last_strategy_moment: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self):
        valid_phases = [p.value for p in LifecyclePhase]
        if self.phase not in valid_phases:
            raise ValueError(f"Invalid phase '{self.phase}', must be one of {valid_phases}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Confidence must be between 0.0 and 1.0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "phase": self.phase,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "last_strategy_moment": _to_iso(self.last_strategy_moment),
            "updated_at": _to_iso(self.updated_at),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Lifecycle":
        evidence = d.get("evidence", [])
        if isinstance(evidence, str):
            evidence = safe_json_loads(evidence, "Lifecycle.evidence", default={})
        return cls(
            project_id=d["project_id"],
            phase=d.get("phase", "research"),
            confidence=d.get("confidence", 0.5),
            evidence=evidence,
            last_strategy_moment=_from_iso(d.get("last_strategy_moment")),
            updated_at=_from_iso(d.get("updated_at")),
        )

    def to_row(self) -> tuple:
        """Return tuple for INSERT/UPDATE."""
        import json

        return (
            self.project_id,
            self.phase,
            self.confidence,
            json.dumps(self.evidence),
            _to_iso(self.last_strategy_moment),
        )


@dataclass
class Arc:
    """A narrative arc (content theme/thread)."""

    id: str
    project_id: str
    theme: str
    status: str = "active"  # ArcStatus value
    post_count: int = 0
    last_post_at: datetime | None = None
    notes: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self):
        valid_statuses = [s.value for s in ArcStatus]
        if self.status not in valid_statuses:
            raise ValueError(f"Invalid status '{self.status}', must be one of {valid_statuses}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "theme": self.theme,
            "status": self.status,
            "post_count": self.post_count,
            "last_post_at": _to_iso(self.last_post_at),
            "notes": self.notes,
            "started_at": _to_iso(self.started_at),
            "ended_at": _to_iso(self.ended_at),
            "updated_at": _to_iso(self.updated_at),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Arc":
        return cls(
            id=d["id"],
            project_id=d["project_id"],
            theme=d["theme"],
            status=d.get("status", "active"),
            post_count=d.get("post_count", 0),
            last_post_at=_from_iso(d.get("last_post_at")),
            notes=d.get("notes"),
            started_at=_from_iso(d.get("started_at")),
            ended_at=_from_iso(d.get("ended_at")),
            updated_at=_from_iso(d.get("updated_at")),
        )

    def to_row(self) -> tuple:
        """Return tuple for INSERT."""
        return (
            self.id,
            self.project_id,
            self.theme,
            self.status,
            self.post_count,
            _to_iso(self.last_post_at),
            self.notes,
        )


@dataclass
class NarrativeDebt:
    """Narrative debt tracking for a project."""

    project_id: str
    debt_counter: int = 0
    last_synthesis_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "debt_counter": self.debt_counter,
            "last_synthesis_at": _to_iso(self.last_synthesis_at),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "NarrativeDebt":
        return cls(
            project_id=d["project_id"],
            debt_counter=d.get("debt_counter", 0),
            last_synthesis_at=_from_iso(d.get("last_synthesis_at")),
        )

    def to_row(self) -> tuple:
        """Return tuple for INSERT."""
        return (
            self.project_id,
            self.debt_counter,
            _to_iso(self.last_synthesis_at),
        )


@dataclass
class UsageLog:
    """Token usage log entry."""

    id: str
    operation_type: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_cents: float = 0.0
    project_id: str | None = None
    commit_hash: str | None = None
    trigger_source: str = "auto"
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "operation_type": self.operation_type,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "cost_cents": self.cost_cents,
            "commit_hash": self.commit_hash,
            "trigger_source": self.trigger_source,
            "created_at": _to_iso(self.created_at),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "UsageLog":
        return cls(
            id=d["id"],
            project_id=d.get("project_id"),
            operation_type=d["operation_type"],
            model=d["model"],
            input_tokens=d.get("input_tokens", 0),
            output_tokens=d.get("output_tokens", 0),
            cache_read_tokens=d.get("cache_read_tokens", 0),
            cache_creation_tokens=d.get("cache_creation_tokens", 0),
            cost_cents=d.get("cost_cents", 0.0),
            commit_hash=d.get("commit_hash"),
            trigger_source=d.get("trigger_source", "auto"),
            created_at=_from_iso(d.get("created_at")),
        )

    def to_row(self) -> tuple:
        """Return tuple for INSERT."""
        return (
            self.id,
            self.project_id,
            self.operation_type,
            self.model,
            self.input_tokens,
            self.output_tokens,
            self.cache_read_tokens,
            self.cache_creation_tokens,
            self.cost_cents,
            self.commit_hash,
            self.trigger_source,
        )


# =============================================================================
# Targets Phase 1 Models
# =============================================================================


@dataclass
class OAuthToken:
    """OAuth 2.0 token for a platform account."""

    account_name: str
    platform: str
    access_token: str
    refresh_token: str
    expires_at: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_name": self.account_name,
            "platform": self.platform,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "OAuthToken":
        return cls(
            account_name=d["account_name"],
            platform=d["platform"],
            access_token=d["access_token"],
            refresh_token=d["refresh_token"],
            expires_at=d.get("expires_at"),
            updated_at=d.get("updated_at"),
        )

    def to_row(self) -> tuple:
        """Return tuple for INSERT/UPSERT."""
        return (
            self.account_name,
            self.platform,
            self.access_token,
            self.refresh_token,
            self.expires_at,
            self.updated_at,
        )


@dataclass
class ContentTopic:
    """A content topic in the queue."""

    id: str
    project_id: str
    strategy: str
    topic: str
    description: str | None = None
    priority_rank: int = 0
    status: str = "uncovered"
    commit_count: int = 0
    last_commit_at: str | None = None
    last_posted_at: str | None = None
    created_by: str = "user"
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "strategy": self.strategy,
            "topic": self.topic,
            "description": self.description,
            "priority_rank": self.priority_rank,
            "status": self.status,
            "commit_count": self.commit_count,
            "last_commit_at": self.last_commit_at,
            "last_posted_at": self.last_posted_at,
            "created_by": self.created_by,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ContentTopic":
        return cls(
            id=d["id"],
            project_id=d["project_id"],
            strategy=d["strategy"],
            topic=d["topic"],
            description=d.get("description"),
            priority_rank=d.get("priority_rank", 0),
            status=d.get("status", "uncovered"),
            commit_count=d.get("commit_count", 0),
            last_commit_at=d.get("last_commit_at"),
            last_posted_at=d.get("last_posted_at"),
            created_by=d.get("created_by", "user"),
            created_at=d.get("created_at"),
        )

    def to_row(self) -> tuple:
        """Return tuple for INSERT."""
        return (
            self.id,
            self.project_id,
            self.strategy,
            self.topic,
            self.description,
            self.priority_rank,
            self.status,
            self.commit_count,
            self.last_commit_at,
            self.last_posted_at,
            self.created_by,
        )


@dataclass
class ContentSuggestion:
    """An operator content suggestion."""

    id: str
    project_id: str
    idea: str
    strategy: str | None = None
    media_refs: list | None = None
    status: str = "pending"
    source: str = "operator"
    created_at: str | None = None
    evaluated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "idea": self.idea,
            "strategy": self.strategy,
            "media_refs": self.media_refs,
            "status": self.status,
            "source": self.source,
            "created_at": self.created_at,
            "evaluated_at": self.evaluated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ContentSuggestion":
        media_refs = d.get("media_refs")
        if isinstance(media_refs, str):
            media_refs = safe_json_loads(media_refs, "ContentSuggestion.media_refs", default=[])
        return cls(
            id=d["id"],
            project_id=d["project_id"],
            idea=d["idea"],
            strategy=d.get("strategy"),
            media_refs=media_refs,
            status=d.get("status", "pending"),
            source=d.get("source", "operator"),
            created_at=d.get("created_at"),
            evaluated_at=d.get("evaluated_at"),
        )

    def to_row(self) -> tuple:
        """Return tuple for INSERT."""
        import json

        return (
            self.id,
            self.project_id,
            self.strategy,
            self.idea,
            json.dumps(self.media_refs) if self.media_refs is not None else "[]",
            self.status,
            self.source,
        )


@dataclass
class EvaluationCycle:
    """An evaluation cycle grouping."""

    id: str
    project_id: str
    trigger_type: str
    trigger_ref: str | None = None
    commit_analysis_id: str | None = None
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "trigger_type": self.trigger_type,
            "trigger_ref": self.trigger_ref,
            "commit_analysis_id": self.commit_analysis_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EvaluationCycle":
        return cls(
            id=d["id"],
            project_id=d["project_id"],
            trigger_type=d["trigger_type"],
            trigger_ref=d.get("trigger_ref"),
            commit_analysis_id=d.get("commit_analysis_id"),
            created_at=d.get("created_at"),
        )

    def to_row(self) -> tuple:
        """Return tuple for INSERT."""
        return (
            self.id,
            self.project_id,
            self.trigger_type,
            self.trigger_ref,
            self.commit_analysis_id,
        )


@dataclass
class DraftPattern:
    """An observational content format pattern."""

    id: str
    project_id: str
    pattern_name: str
    description: str | None = None
    example_draft_id: str | None = None
    created_by: str = "operator"
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "pattern_name": self.pattern_name,
            "description": self.description,
            "example_draft_id": self.example_draft_id,
            "created_by": self.created_by,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DraftPattern":
        return cls(
            id=d["id"],
            project_id=d["project_id"],
            pattern_name=d["pattern_name"],
            description=d.get("description"),
            example_draft_id=d.get("example_draft_id"),
            created_by=d.get("created_by", "operator"),
            created_at=d.get("created_at"),
        )

    def to_row(self) -> tuple:
        """Return tuple for INSERT."""
        return (
            self.id,
            self.project_id,
            self.pattern_name,
            self.description,
            self.example_draft_id,
            self.created_by,
        )


@dataclass
class SystemErrorRecord:
    """A system error record."""

    id: str
    severity: str
    message: str
    context: str = "{}"
    source: str = ""
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity,
            "message": self.message,
            "context": self.context,
            "source": self.source,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SystemErrorRecord":
        return cls(
            id=d["id"],
            severity=d["severity"],
            message=d["message"],
            context=d.get("context", "{}"),
            source=d.get("source", ""),
            created_at=d.get("created_at"),
        )

    def to_row(self) -> tuple:
        """Return tuple for INSERT."""
        return (
            self.id,
            self.severity,
            self.message,
            self.context,
            self.source,
        )


# =============================================================================
# WS2: LLM Integration Models
# =============================================================================


@dataclass
class CommitInfo:
    """Git commit information passed to evaluation."""

    hash: str
    message: str
    diff: str
    files_changed: list[str] = field(default_factory=list)
    insertions: int = 0
    deletions: int = 0
    timestamp: str | None = None  # ISO 8601 author date of this commit
    parent_timestamp: str | None = None  # ISO 8601 author date of parent commit


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
