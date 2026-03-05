"""Usage logging helper. Social-hook-specific — not part of the reusable layer."""

import sqlite3
from typing import Any, Optional

from social_hook.filesystem import generate_id
from social_hook.models import UsageLog


def log_usage(
    db: Any,
    operation_type: str,
    model_id: str,
    usage: Any,
    project_id: Optional[str] = None,
    commit_hash: Optional[str] = None,
    cost_cents: float = 0.0,
) -> None:
    """Write a UsageLog row. No-op if db or operation_type is falsy."""
    if not (db and operation_type):
        return
    from social_hook.db import operations as ops

    # Auto-extract cost_cents from usage object if caller didn't pass it explicitly
    if cost_cents == 0.0:
        cost_cents = getattr(usage, "cost_cents", 0.0)

    usage_log = UsageLog(
        id=generate_id("usage"),
        project_id=project_id,
        operation_type=operation_type,
        model=model_id,
        input_tokens=getattr(usage, "input_tokens", 0),
        output_tokens=getattr(usage, "output_tokens", 0),
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
        cost_cents=cost_cents,
        commit_hash=commit_hash,
    )
    if hasattr(db, "insert_usage"):
        db.insert_usage(usage_log)
    elif isinstance(db, sqlite3.Connection):
        ops.insert_usage(db, usage_log)
