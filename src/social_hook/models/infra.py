"""Infrastructure models — auth tokens, usage tracking, system errors."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from social_hook.models._helpers import _from_iso, _to_iso


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
    def from_dict(cls, d: dict[str, Any]) -> UsageLog:
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
    def from_dict(cls, d: dict[str, Any]) -> OAuthToken:
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
class SystemErrorRecord:
    """A system error record."""

    id: str
    severity: str
    message: str
    context: str = "{}"
    source: str = ""
    component: str = ""
    run_id: str = ""
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity,
            "message": self.message,
            "context": self.context,
            "source": self.source,
            "component": self.component,
            "run_id": self.run_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SystemErrorRecord:
        return cls(
            id=d["id"],
            severity=d["severity"],
            message=d["message"],
            context=d.get("context", "{}"),
            source=d.get("source", ""),
            component=d.get("component", ""),
            run_id=d.get("run_id", ""),
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
            self.component,
            self.run_id,
        )
