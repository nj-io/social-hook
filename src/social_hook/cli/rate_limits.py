"""CLI command for displaying rate limit status."""

import json as json_mod
from datetime import datetime, timezone

import typer


def rate_limits(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show current rate limit status (daily cap, gap timer, queue, cost).

    Example: social-hook rate-limits
    Example: social-hook --json rate-limits
    """
    from social_hook.config.yaml import load_full_config
    from social_hook.db import operations as ops
    from social_hook.db.connection import init_database
    from social_hook.filesystem import get_db_path

    json_mode = json_output or (ctx.obj.get("json", False) if ctx.obj else False)
    config_path = ctx.obj.get("config") if ctx.obj else None

    config = load_full_config(
        yaml_path=str(config_path) if config_path else None,
    )
    rate_config = config.rate_limits

    db_path = get_db_path()
    conn = init_database(db_path)

    try:
        # Auto eval count today
        auto_count = ops.get_today_auto_evaluation_count(conn)

        # Manual eval count today
        row = conn.execute(
            """
            SELECT COUNT(*) FROM usage_log
            WHERE operation_type = 'evaluate'
              AND trigger_source = 'manual'
              AND created_at >= date('now')
            """
        ).fetchone()
        manual_count = row[0] if row else 0

        # Next available: compute seconds remaining on gap timer
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

        # Queued triggers: count unprocessed deferred_eval decisions across all projects
        row = conn.execute(
            """
            SELECT COUNT(*) FROM decisions
            WHERE decision = 'deferred_eval'
              AND processed = 0
            """
        ).fetchone()
        queued = row[0] if row else 0

        # Cost today from usage_log
        row = conn.execute(
            """
            SELECT COALESCE(SUM(cost_cents), 0.0) FROM usage_log
            WHERE created_at >= date('now')
            """
        ).fetchone()
        cost_cents = row[0] if row else 0.0

    finally:
        conn.close()

    if json_mode:
        typer.echo(
            json_mod.dumps(
                {
                    "evaluations_today": auto_count,
                    "max_evaluations_per_day": rate_config.max_evaluations_per_day,
                    "manual_evaluations_today": manual_count,
                    "next_available_in_seconds": next_available_seconds,
                    "queued_triggers": queued,
                    "cost_today_cents": cost_cents,
                },
                indent=2,
            )
        )
    else:
        # Human-readable output
        if next_available_seconds == 0:
            next_str = "now"
        else:
            mins, secs = divmod(next_available_seconds, 60)
            next_str = f"{mins}m {secs}s" if mins else f"{secs}s"

        cost_dollars = cost_cents / 100
        typer.echo(
            f"Evaluations today:  {auto_count}/{rate_config.max_evaluations_per_day} (auto)"
            f" + {manual_count} (manual)"
        )
        typer.echo(f"Next eval available: {next_str}")
        typer.echo(f"Queued triggers:    {queued}")
        typer.echo(f"Cost today:         ${cost_dollars:.2f}")
