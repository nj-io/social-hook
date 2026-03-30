"""Narrative/strategy models — lifecycle, arcs, narrative debt."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from social_hook.models._helpers import _from_iso, _to_iso
from social_hook.models.enums import ArcStatus, LifecyclePhase
from social_hook.parsing import safe_json_loads


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
    def from_dict(cls, d: dict[str, Any]) -> Lifecycle:
        evidence = d.get("evidence", [])
        if isinstance(evidence, str):
            evidence = safe_json_loads(evidence, "Lifecycle.evidence", default=[])
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
    strategy: str = ""
    status: str = "active"  # ArcStatus value
    reasoning: str | None = None
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
            "strategy": self.strategy,
            "status": self.status,
            "reasoning": self.reasoning,
            "post_count": self.post_count,
            "last_post_at": _to_iso(self.last_post_at),
            "notes": self.notes,
            "started_at": _to_iso(self.started_at),
            "ended_at": _to_iso(self.ended_at),
            "updated_at": _to_iso(self.updated_at),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Arc:
        return cls(
            id=d["id"],
            project_id=d["project_id"],
            theme=d["theme"],
            strategy=d.get("strategy", ""),
            status=d.get("status", "active"),
            reasoning=d.get("reasoning"),
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
            self.strategy,
            self.status,
            self.reasoning,
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
    def from_dict(cls, d: dict[str, Any]) -> NarrativeDebt:
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
