"""CLI commands for inspecting state (log, pending, usage, logs)."""

import contextlib
import subprocess

import typer

app = typer.Typer()


@app.command()
def log(
    ctx: typer.Context,
    project_id: str | None = typer.Argument(None, help="Project ID (optional)"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of entries"),
):
    """View decision log."""
    from social_hook.db import (
        get_all_recent_decisions,
        get_recent_decisions,
        init_database,
    )
    from social_hook.filesystem import get_db_path

    conn = init_database(get_db_path())
    try:
        if project_id:
            decisions = get_recent_decisions(conn, project_id, limit=limit)
        else:
            decisions = get_all_recent_decisions(conn, limit=limit)

        if not decisions:
            typer.echo("No decisions found.")
            return

        json_mode = ctx.obj.get("json", False) if ctx.obj else False
        if json_mode:
            import json

            typer.echo(json.dumps([d.to_dict() for d in decisions], indent=2, default=str))
        else:
            for d in decisions:
                typer.echo(
                    f"  {d.id[:12]}  {d.decision:16s}  {d.commit_hash[:8]}  {d.reasoning[:50]}"
                )
    finally:
        conn.close()


@app.command()
def pending(
    ctx: typer.Context,
    project_id: str | None = typer.Argument(None, help="Project ID (optional)"),
):
    """View pending drafts."""
    from social_hook.db import (
        get_all_pending_drafts,
        get_pending_drafts,
        init_database,
    )
    from social_hook.filesystem import get_db_path

    conn = init_database(get_db_path())
    try:
        if project_id:
            drafts = get_pending_drafts(conn, project_id)
        else:
            drafts = get_all_pending_drafts(conn)

        if not drafts:
            typer.echo("No pending drafts.")
            return

        json_mode = ctx.obj.get("json", False) if ctx.obj else False
        if json_mode:
            import json

            typer.echo(json.dumps([d.to_dict() for d in drafts], indent=2, default=str))
        else:
            for d in drafts:
                typer.echo(f"  {d.id[:12]}  [{d.status:10s}]  {d.platform:8s}  {d.content[:50]}")
    finally:
        conn.close()


@app.command()
def usage(
    ctx: typer.Context,
    days: int = typer.Option(30, "--days", "-d", help="Number of days"),
    recent: int | None = typer.Option(
        None, "--recent", "-r", help="Show last N individual operations"
    ),
):
    """View token usage and costs."""
    from social_hook.db import get_recent_usage, get_usage_summary, init_database
    from social_hook.filesystem import get_db_path

    conn = init_database(get_db_path())
    try:
        if recent is not None:
            entries = get_recent_usage(conn, limit=recent)
            if not entries:
                typer.echo("No usage data found.")
                return

            json_mode = ctx.obj.get("json", False) if ctx.obj else False
            if json_mode:
                import json

                typer.echo(json.dumps(entries, indent=2, default=str))
            else:
                typer.echo(f"Recent operations (last {recent}):\n")
                for e in entries:
                    project = e.get("project_name") or "—"
                    op = e.get("operation_type", "?")
                    model = e.get("model", "?")
                    inp = e.get("input_tokens", 0) or 0
                    out = e.get("output_tokens", 0) or 0
                    cost = (e.get("cost_cents", 0) or 0) / 100.0
                    commit = e.get("commit_hash") or ""
                    commit_str = commit[:8] if commit else "—"
                    time_str = e.get("created_at", "?")
                    typer.echo(
                        f"  {time_str}  {project:20s}  {op:14s}  {commit_str:8s}  "
                        f"in:{inp:>8,}  out:{out:>8,}  ${cost:.3f}  ({model})"
                    )
            return

        rows = get_usage_summary(conn, days=days)

        if not rows:
            typer.echo("No usage data found.")
            return

        json_mode = ctx.obj.get("json", False) if ctx.obj else False
        if json_mode:
            import json

            typer.echo(json.dumps(rows, indent=2))
        else:
            typer.echo(f"Usage (last {days} days):\n")
            total_input = 0
            total_output = 0
            total_cost = 0.0
            for r in rows:
                model = r.get("model", "unknown")
                inp = r.get("total_input", 0) or 0
                out = r.get("total_output", 0) or 0
                cost = (r.get("total_cost_cents", 0) or 0) / 100.0
                typer.echo(f"  {model:30s}  in:{inp:>10,}  out:{out:>10,}  ${cost:.2f}")
                total_input += inp
                total_output += out
                total_cost += cost
            typer.echo(
                f"\n  {'Total':30s}  in:{total_input:>10,}  out:{total_output:>10,}  ${total_cost:.2f}"
            )
    finally:
        conn.close()


@app.command()
def platforms(
    ctx: typer.Context,
):
    """List configured platforms with enabled/disabled status."""
    from social_hook.config import load_full_config

    config_path = ctx.obj.get("config") if ctx.obj else None
    config = load_full_config(str(config_path) if config_path else None)

    json_mode = ctx.obj.get("json", False) if ctx.obj else False

    platform_list = []
    for pname, pcfg in config.platforms.items():
        platform_list.append(
            {
                "name": pname,
                "enabled": pcfg.enabled,
                "priority": pcfg.priority,
                "type": pcfg.type,
                "account_tier": getattr(pcfg, "account_tier", None),
                "description": getattr(pcfg, "description", None),
            }
        )

    if json_mode:
        import json

        typer.echo(json.dumps(platform_list, indent=2))
    else:
        if not platform_list:
            typer.echo("No platforms configured.")
            return
        for p in platform_list:
            status = "enabled" if p["enabled"] else "disabled"
            line = f"  {p['name']:12s}  [{status:8s}]  {p['priority']:10s}  {p['type']}"
            if p.get("description"):
                line += f"  -- {p['description']}"
            typer.echo(line)


VALID_LOG_COMPONENTS = ("trigger", "scheduler", "bot")


@app.command()
def logs(
    component: str | None = typer.Argument(
        None, help=f"Component to tail ({', '.join(VALID_LOG_COMPONENTS)}, or omit for all)"
    ),
    level: str = typer.Option("info", "--level", "-l", help="Filter by log level"),
):
    """Tail log files. Optionally filter by component or level."""
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

    # Use tail to follow logs
    cmd = ["tail", "-f"] + [str(f) for f in existing]
    with contextlib.suppress(KeyboardInterrupt):
        subprocess.run(cmd)
