"""CLI commands for log queries, tailing, and health."""

import contextlib
import json as json_mod
import subprocess

import typer

app = typer.Typer(invoke_without_command=True)

VALID_LOG_COMPONENTS = (
    "trigger",
    "scheduler",
    "bot",
    "web",
    "narrative",
    "consolidation",
    "cli",
)


def _get_conn():
    from social_hook.db.connection import init_database
    from social_hook.filesystem import get_db_path

    return init_database(get_db_path())


@app.callback(invoke_without_command=True)
def logs_default(
    ctx: typer.Context,
    severity: str | None = typer.Option(None, "--severity", "-s", help="Filter by severity"),
    component: str | None = typer.Option(None, "--component", "-c", help="Filter by component"),
    source: str | None = typer.Option(None, "--source", help="Filter by source module"),
    limit: int = typer.Option(50, "--limit", "-n", help="Max errors to show"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Query system errors from the database.

    Example: social-hook logs --severity error --limit 20
    Example: social-hook logs --component trigger --json
    """
    if ctx.invoked_subcommand is not None:
        return

    from social_hook.db import operations as ops

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        error_records = ops.get_recent_system_errors(
            conn, limit=limit, severity=severity, component=component, source=source
        )

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

        typer.echo(f"{'Severity':<10} {'Component':<12} {'Source':<18} {'Message':<38} {'Time'}")
        typer.echo("-" * 98)
        for e in error_records:
            comp = (getattr(e, "component", "") or "")[:10]
            source_str = (e.source or "")[:16]
            message = e.message[:36]
            created = (e.created_at or "")[:19]
            typer.echo(f"{e.severity:<10} {comp:<12} {source_str:<18} {message:<38} {created}")
    finally:
        conn.close()


@app.command()
def tail(
    component: str | None = typer.Argument(
        None,
        help=f"Component to tail ({', '.join(VALID_LOG_COMPONENTS)}, or omit for all)",
    ),
):
    """Tail log files. Optionally filter by component.

    Interactive terminal tool -- the web dashboard has the system tab for log viewing.

    Example: social-hook logs tail trigger
    Example: social-hook logs tail
    """
    from social_hook.filesystem import get_base_path

    logs_dir = get_base_path() / "logs"
    if not logs_dir.exists():
        typer.echo(f"Logs directory not found: {logs_dir}")
        raise typer.Exit(1)

    if component:
        if component not in VALID_LOG_COMPONENTS:
            typer.echo(
                f"Unknown component: {component}. Use one of: {', '.join(VALID_LOG_COMPONENTS)}"
            )
            raise typer.Exit(1)
        log_files = [logs_dir / f"{component}.log"]
    else:
        log_files = [logs_dir / f"{c}.log" for c in VALID_LOG_COMPONENTS]

    # Filter to files that exist
    existing = [f for f in log_files if f.exists()]
    if not existing:
        typer.echo("No log files found.")
        return

    cmd = ["tail", "-f"] + [str(f) for f in existing]
    with contextlib.suppress(KeyboardInterrupt):
        subprocess.run(cmd)


@app.command()
def health(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show overall system health status.

    Displays error counts by severity in the last 24 hours.

    Example: social-hook logs health
    Example: social-hook logs health --json
    """
    from social_hook.db import operations as ops

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        status = ops.get_error_health_status(conn)
        overall = ops.compute_health_status(status)
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
            for sev in ["critical", "error", "warning", "info"]:
                count = status.get(sev, 0)
                if count > 0:
                    typer.echo(f"  {sev:<10} {count}")
    finally:
        conn.close()
