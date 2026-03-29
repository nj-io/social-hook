"""Content planning models — topics, suggestions, evaluation cycles, patterns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from social_hook.models.enums import SUGGESTION_STATUSES, TOPIC_STATUSES
from social_hook.parsing import safe_json_loads


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

    def __post_init__(self):
        if self.status not in TOPIC_STATUSES:
            raise ValueError(
                f"Invalid status '{self.status}', must be one of {sorted(TOPIC_STATUSES)}"
            )

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
    def from_dict(cls, d: dict[str, Any]) -> ContentTopic:
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

    def __post_init__(self):
        if self.status not in SUGGESTION_STATUSES:
            raise ValueError(
                f"Invalid status '{self.status}', must be one of {sorted(SUGGESTION_STATUSES)}"
            )

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
    def from_dict(cls, d: dict[str, Any]) -> ContentSuggestion:
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
    commit_analysis_json: str | None = None
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "trigger_type": self.trigger_type,
            "trigger_ref": self.trigger_ref,
            "commit_analysis_id": self.commit_analysis_id,
            "commit_analysis_json": self.commit_analysis_json,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EvaluationCycle:
        return cls(
            id=d["id"],
            project_id=d["project_id"],
            trigger_type=d["trigger_type"],
            trigger_ref=d.get("trigger_ref"),
            commit_analysis_id=d.get("commit_analysis_id"),
            commit_analysis_json=d.get("commit_analysis_json"),
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
    def from_dict(cls, d: dict[str, Any]) -> DraftPattern:
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
