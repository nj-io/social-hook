"""Rate limit gate for evaluator calls.

Checks daily cap and minimum gap between evaluations.
Any trigger source (commit, plugin, etc.) can call this gate.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from social_hook.db import operations as ops


@dataclass
class GateResult:
    blocked: bool
    reason: str


def check_rate_limit(conn, rate_config) -> GateResult:
    """Check if an evaluation is allowed under current rate limits.

    Args:
        conn: SQLite connection
        rate_config: RateLimitsConfig with max_evaluations_per_day, min_evaluation_gap_minutes

    Returns:
        GateResult with blocked=True if evaluation should be deferred.
    """
    today_count = ops.get_today_auto_evaluation_count(conn)
    if today_count >= rate_config.max_evaluations_per_day:
        return GateResult(
            blocked=True,
            reason=f"Daily limit reached: {today_count}/{rate_config.max_evaluations_per_day}",
        )

    last_eval_time = ops.get_last_auto_evaluation_time(conn)
    if last_eval_time and rate_config.min_evaluation_gap_minutes > 0:
        now = datetime.now(timezone.utc)
        last_dt = datetime.fromisoformat(last_eval_time)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        elapsed = (now - last_dt).total_seconds() / 60
        remaining = rate_config.min_evaluation_gap_minutes - elapsed
        if remaining > 0:
            return GateResult(
                blocked=True,
                reason=f"Gap not elapsed: {remaining:.0f}m remaining",
            )

    return GateResult(blocked=False, reason="")


def get_rate_limit_status(conn, rate_config) -> dict:
    """Get current rate limit status for display in CLI and web.

    Returns dict with: evaluations_today, max_evaluations_per_day,
    manual_evaluations_today, next_available_in_seconds, queued_triggers,
    cost_today_cents.
    """
    auto_count = ops.get_today_auto_evaluation_count(conn)

    row = conn.execute(
        "SELECT COUNT(*) FROM usage_log"
        " WHERE operation_type = 'evaluate'"
        " AND trigger_source = 'manual'"
        " AND created_at >= date('now')"
    ).fetchone()
    manual_count = row[0] if row else 0

    next_available_seconds = 0
    last_eval_time = ops.get_last_auto_evaluation_time(conn)
    if last_eval_time and rate_config.min_evaluation_gap_minutes > 0:
        now = datetime.now(timezone.utc)
        last_dt = datetime.fromisoformat(last_eval_time)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        elapsed = (now - last_dt).total_seconds()
        remaining = (rate_config.min_evaluation_gap_minutes * 60) - elapsed
        if remaining > 0:
            next_available_seconds = int(remaining)

    # Daily cap reached sentinel (-1 for UI to distinguish)
    if auto_count >= rate_config.max_evaluations_per_day and next_available_seconds == 0:
        next_available_seconds = -1

    row = conn.execute(
        "SELECT COUNT(*) FROM decisions WHERE decision = 'deferred_eval' AND processed = 0"
    ).fetchone()
    queued = row[0] if row else 0

    row = conn.execute(
        "SELECT COALESCE(SUM(cost_cents), 0.0) FROM usage_log WHERE created_at >= date('now')"
    ).fetchone()
    cost_cents = round(row[0], 2) if row else 0.0

    return {
        "evaluations_today": auto_count,
        "max_evaluations_per_day": rate_config.max_evaluations_per_day,
        "manual_evaluations_today": manual_count,
        "next_available_in_seconds": next_available_seconds,
        "queued_triggers": queued,
        "cost_today_cents": cost_cents,
    }
