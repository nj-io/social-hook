"""Domain models and enums for social-hook."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


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


class DecisionType(Enum):
    """Evaluation decision for a commit."""

    POST_WORTHY = "post_worthy"
    NOT_POST_WORTHY = "not_post_worthy"
    CONSOLIDATE = "consolidate"
    DEFERRED = "deferred"


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


def _to_iso(dt: Optional[datetime]) -> Optional[str]:
    """Convert datetime to ISO string."""
    return dt.isoformat() if dt else None


def _from_iso(s: Optional[str]) -> Optional[datetime]:
    """Convert ISO string to datetime."""
    return datetime.fromisoformat(s) if s else None


def _now_iso() -> str:
    """Get current time as ISO string."""
    return datetime.now(timezone.utc).isoformat()


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass
class Project:
    """A registered project (git repository)."""

    id: str
    name: str
    repo_path: str
    repo_origin: Optional[str] = None
    summary: Optional[str] = None
    summary_updated_at: Optional[datetime] = None
    audience_introduced: bool = False
    paused: bool = False
    created_at: Optional[datetime] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "repo_path": self.repo_path,
            "repo_origin": self.repo_origin,
            "summary": self.summary,
            "summary_updated_at": _to_iso(self.summary_updated_at),
            "audience_introduced": self.audience_introduced,
            "paused": self.paused,
            "created_at": _to_iso(self.created_at),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Project":
        return cls(
            id=d["id"],
            name=d["name"],
            repo_path=d["repo_path"],
            repo_origin=d.get("repo_origin"),
            summary=d.get("summary"),
            summary_updated_at=_from_iso(d.get("summary_updated_at")),
            audience_introduced=bool(d.get("audience_introduced", False)),
            paused=bool(d.get("paused", False)),
            created_at=_from_iso(d.get("created_at")),
        )

    def to_row(self) -> tuple:
        """Return tuple for INSERT (id, name, repo_path, repo_origin, summary, summary_updated_at, audience_introduced, paused)."""
        return (
            self.id,
            self.name,
            self.repo_path,
            self.repo_origin,
            self.summary,
            _to_iso(self.summary_updated_at),
            1 if self.audience_introduced else 0,
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
    commit_message: Optional[str] = None
    angle: Optional[str] = None
    episode_type: Optional[str] = None  # EpisodeType value
    post_category: Optional[str] = None  # PostCategory value
    arc_id: Optional[str] = None
    media_tool: Optional[str] = None
    platforms: dict[str, str] = field(default_factory=dict)
    commit_summary: Optional[str] = None
    processed: bool = False
    processed_at: Optional[datetime] = None
    batch_id: Optional[str] = None
    created_at: Optional[datetime] = None

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
            "post_category": self.post_category,
            "arc_id": self.arc_id,
            "media_tool": self.media_tool,
            "platforms": self.platforms,
            "commit_summary": self.commit_summary,
            "processed": self.processed,
            "processed_at": _to_iso(self.processed_at),
            "batch_id": self.batch_id,
            "created_at": _to_iso(self.created_at),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Decision":
        platforms = d.get("platforms", {})
        if isinstance(platforms, str):
            import json

            platforms = json.loads(platforms)
        return cls(
            id=d["id"],
            project_id=d["project_id"],
            commit_hash=d["commit_hash"],
            decision=d["decision"],
            reasoning=d["reasoning"],
            commit_message=d.get("commit_message"),
            angle=d.get("angle"),
            episode_type=d.get("episode_type"),
            post_category=d.get("post_category"),
            arc_id=d.get("arc_id"),
            media_tool=d.get("media_tool"),
            platforms=platforms,
            commit_summary=d.get("commit_summary"),
            processed=bool(d.get("processed", False)),
            processed_at=_from_iso(d.get("processed_at")),
            batch_id=d.get("batch_id"),
            created_at=_from_iso(d.get("created_at")),
        )

    def to_row(self) -> tuple:
        """Return tuple for INSERT."""
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
            self.post_category,
            self.arc_id,
            self.media_tool,
            json.dumps(self.platforms),
            self.commit_summary,
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
    media_type: Optional[str] = None
    media_spec: Optional[dict] = None
    suggested_time: Optional[datetime] = None
    scheduled_time: Optional[datetime] = None
    reasoning: Optional[str] = None
    superseded_by: Optional[str] = None
    retry_count: int = 0
    last_error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        valid_statuses = [s.value for s in DraftStatus]
        if self.status not in valid_statuses:
            raise ValueError(
                f"Invalid status '{self.status}', must be one of {valid_statuses}"
            )

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
            "suggested_time": _to_iso(self.suggested_time),
            "scheduled_time": _to_iso(self.scheduled_time),
            "reasoning": self.reasoning,
            "superseded_by": self.superseded_by,
            "retry_count": self.retry_count,
            "last_error": self.last_error,
            "created_at": _to_iso(self.created_at),
            "updated_at": _to_iso(self.updated_at),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Draft":
        media_paths = d.get("media_paths", [])
        if isinstance(media_paths, str):
            import json

            media_paths = json.loads(media_paths)
        media_spec_raw = d.get("media_spec")
        if isinstance(media_spec_raw, str):
            import json

            media_spec = json.loads(media_spec_raw) if media_spec_raw else None
        else:
            media_spec = media_spec_raw
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
            suggested_time=_from_iso(d.get("suggested_time")),
            scheduled_time=_from_iso(d.get("scheduled_time")),
            reasoning=d.get("reasoning"),
            superseded_by=d.get("superseded_by"),
            retry_count=d.get("retry_count", 0),
            last_error=d.get("last_error"),
            created_at=_from_iso(d.get("created_at")),
            updated_at=_from_iso(d.get("updated_at")),
        )

    def to_row(self) -> tuple:
        """Return tuple for INSERT."""
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
            _to_iso(self.suggested_time),
            _to_iso(self.scheduled_time),
            self.reasoning,
            self.superseded_by,
            self.retry_count,
            self.last_error,
        )


@dataclass
class DraftTweet:
    """Individual tweet in a thread."""

    id: str
    draft_id: str
    position: int
    content: str
    media_paths: list[str] = field(default_factory=list)
    external_id: Optional[str] = None
    posted_at: Optional[datetime] = None
    error: Optional[str] = None

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
            import json

            media_paths = json.loads(media_paths)
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
    old_value: Optional[str]
    new_value: Optional[str]
    changed_by: str  # 'gatekeeper', 'human', 'expert'
    changed_at: Optional[datetime] = None

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
    external_id: Optional[str] = None
    external_url: Optional[str] = None
    posted_at: Optional[datetime] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "draft_id": self.draft_id,
            "project_id": self.project_id,
            "platform": self.platform,
            "external_id": self.external_id,
            "external_url": self.external_url,
            "content": self.content,
            "posted_at": _to_iso(self.posted_at),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Post":
        return cls(
            id=d["id"],
            draft_id=d["draft_id"],
            project_id=d["project_id"],
            platform=d["platform"],
            external_id=d.get("external_id"),
            external_url=d.get("external_url"),
            content=d["content"],
            posted_at=_from_iso(d.get("posted_at")),
        )

    def to_row(self) -> tuple:
        """Return tuple for INSERT."""
        return (
            self.id,
            self.draft_id,
            self.project_id,
            self.platform,
            self.external_id,
            self.external_url,
            self.content,
        )


@dataclass
class Lifecycle:
    """Project lifecycle tracking."""

    project_id: str
    phase: str = "research"  # LifecyclePhase value
    confidence: float = 0.5
    evidence: list[str] = field(default_factory=list)
    last_strategy_moment: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        valid_phases = [p.value for p in LifecyclePhase]
        if self.phase not in valid_phases:
            raise ValueError(
                f"Invalid phase '{self.phase}', must be one of {valid_phases}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be between 0.0 and 1.0")

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
            import json

            evidence = json.loads(evidence)
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
    last_post_at: Optional[datetime] = None
    notes: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        valid_statuses = [s.value for s in ArcStatus]
        if self.status not in valid_statuses:
            raise ValueError(
                f"Invalid status '{self.status}', must be one of {valid_statuses}"
            )

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
    last_synthesis_at: Optional[datetime] = None

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
    project_id: Optional[str] = None
    commit_hash: Optional[str] = None
    created_at: Optional[datetime] = None

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
    timestamp: Optional[str] = None  # ISO 8601 author date of this commit
    parent_timestamp: Optional[str] = None  # ISO 8601 author date of parent commit


@dataclass
class ProjectContext:
    """Assembled project state for agent context."""

    project: "Project"
    social_context: Optional[str]
    lifecycle: Optional["Lifecycle"]
    active_arcs: list["Arc"]
    narrative_debt: int
    audience_introduced: bool
    pending_drafts: list["Draft"]
    recent_decisions: list["Decision"]
    recent_posts: list["Post"]
    project_summary: Optional[str]
    memories: list[dict] = field(default_factory=list)
    milestone_summaries: list[dict] = field(default_factory=list)
    context_notes: list[dict] = field(default_factory=list)
    session_narratives: list[dict] = field(default_factory=list)
