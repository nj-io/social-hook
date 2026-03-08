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
    DEFERRED = "deferred"


class DecisionType(Enum):
    """Evaluation decision for a commit."""

    DRAFT = "draft"
    HOLD = "hold"
    SKIP = "skip"
    IMPORTED = "imported"


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
    audience_introduced: bool = False
    paused: bool = False
    discovery_files: str | None = None  # JSON-serialized list of file paths
    trigger_branch: str | None = None
    created_at: datetime | None = None

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
            "discovery_files": self.discovery_files,
            "trigger_branch": self.trigger_branch,
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
            discovery_files=d.get("discovery_files"),
            trigger_branch=d.get("trigger_branch"),
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
    processed: bool = False
    processed_at: datetime | None = None
    batch_id: str | None = None
    branch: str | None = None
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
            "processed": self.processed,
            "processed_at": _to_iso(self.processed_at),
            "batch_id": self.batch_id,
            "branch": self.branch,
            "created_at": _to_iso(self.created_at),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Decision":
        import json

        platforms = d.get("platforms", {})
        if isinstance(platforms, str):
            platforms = json.loads(platforms)

        episode_tags = d.get("episode_tags", [])
        if isinstance(episode_tags, str):
            episode_tags = json.loads(episode_tags)

        targets = d.get("targets", {})
        if isinstance(targets, str):
            targets = json.loads(targets)

        consolidate_with = d.get("consolidate_with")
        if isinstance(consolidate_with, str):
            consolidate_with = json.loads(consolidate_with)

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
            processed=bool(d.get("processed", False)),
            processed_at=_from_iso(d.get("processed_at")),
            batch_id=d.get("batch_id"),
            branch=d.get("branch"),
            created_at=_from_iso(d.get("created_at")),
        )

    def to_row(self) -> tuple:
        """Return tuple for INSERT (17 columns)."""
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
            self.branch,
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
            "created_at": _to_iso(self.created_at),
            "updated_at": _to_iso(self.updated_at),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Draft":
        import json

        media_paths = d.get("media_paths", [])
        if isinstance(media_paths, str):
            media_paths = json.loads(media_paths)
        media_spec_raw = d.get("media_spec")
        if isinstance(media_spec_raw, str):
            media_spec = json.loads(media_spec_raw) if media_spec_raw else None
        else:
            media_spec = media_spec_raw
        media_spec_used_raw = d.get("media_spec_used")
        if isinstance(media_spec_used_raw, str):
            media_spec_used = json.loads(media_spec_used_raw) if media_spec_used_raw else None
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
            created_at=_from_iso(d.get("created_at")),
            updated_at=_from_iso(d.get("updated_at")),
        )

    def to_row(self) -> tuple:
        """Return tuple for INSERT (19 columns)."""
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
    audience_introduced: bool
    pending_drafts: list["Draft"]
    recent_decisions: list["Decision"]
    recent_posts: list["Post"]
    project_summary: str | None
    memories: list[dict] = field(default_factory=list)
    milestone_summaries: list[dict] = field(default_factory=list)
    context_notes: list[dict] = field(default_factory=list)
    session_narratives: list[dict] = field(default_factory=list)
    held_decisions: list["Decision"] = field(default_factory=list)
