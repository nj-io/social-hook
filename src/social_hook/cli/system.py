"""CLI commands for system health and error monitoring."""

import json as json_mod
import logging

import typer

from social_hook.parsing import safe_int

app = typer.Typer(no_args_is_help=True)
logger = logging.getLogger(__name__)


def _get_conn():
    from social_hook.db.connection import init_database
    from social_hook.filesystem import get_db_path

    return init_database(get_db_path())


@app.command()
def errors(
    ctx: typer.Context,
    limit: int = typer.Option(50, "--limit", "-n", help="Max errors to show"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show recent system errors.

    Displays the system error feed, showing recent errors from all
    processes (scheduler, CLI, web server). Read-only.

    Example: social-hook system errors
    Example: social-hook system errors --limit 10 --json
    """
    from social_hook.db import operations as ops

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)
    limit = safe_int(limit, 50, "limit")

    conn = _get_conn()
    try:
        error_records = ops.get_recent_system_errors(conn, limit=limit)

        if json_output:
            typer.echo(
                json_mod.dumps(
                    {"errors": [e.to_dict() for e in error_records]},
                    indent=2,
                )
            )
            return

        if not error_records:
            typer.echo("No system errors.")
            return

        typer.echo(f"{'Severity':<10} {'Source':<20} {'Message':<40} {'Time'}")
        typer.echo("-" * 90)
        for e in error_records:
            source = (e.source or "")[:18]
            message = e.message[:38]
            created = (e.created_at or "")[:19]
            typer.echo(f"{e.severity:<10} {source:<20} {message:<40} {created}")
    finally:
        conn.close()


@app.command()
def health(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show overall system health status.

    Displays error counts by severity in the last 24 hours.
    Useful for monitoring and alerting.

    Example: social-hook system health
    Example: social-hook system health --json
    """
    from social_hook.db import operations as ops

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        status = ops.get_error_health_status(conn)

        # Determine overall health
        if status.get("critical", 0) > 0:
            overall = "critical"
        elif status.get("error", 0) > 0:
            overall = "degraded"
        elif status.get("warning", 0) > 0:
            overall = "warning"
        else:
            overall = "healthy"

        total = sum(status.values())

        if json_output:
            typer.echo(
                json_mod.dumps(
                    {
                        "status": overall,
                        "total_24h": total,
                        "by_severity": status,
                    },
                    indent=2,
                )
            )
            return

        typer.echo(f"System health: {overall}")
        typer.echo(f"Errors in last 24h: {total}")
        if total > 0:
            for severity in ["critical", "error", "warning", "info"]:
                count = status.get(severity, 0)
                if count > 0:
                    typer.echo(f"  {severity:<10} {count}")
    finally:
        conn.close()
