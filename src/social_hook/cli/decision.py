"""CLI commands for decision management."""

import json as json_mod
import os

import typer

app = typer.Typer(no_args_is_help=True)


def _get_conn():
    from social_hook.db.connection import init_database
    from social_hook.filesystem import get_db_path

    return init_database(get_db_path())


def _resolve_project(project: str | None = None) -> str:
    """Resolve project path, defaulting to cwd."""
    return os.path.realpath(project or os.getcwd())


@app.command()
def delete(
    ctx: typer.Context,
    decision_id: str = typer.Argument(..., help="Decision ID to delete"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Delete a decision and its associated drafts.

    Example: social-hook decision delete decision-abc123
    """
    from social_hook.db import operations as ops

    conn = _get_conn()
    try:
        decision = ops.get_decision(conn, decision_id)
        if not decision:
            typer.echo(f"Decision not found: {decision_id}")
            raise typer.Exit(1)

        json_output = ctx.obj.get("json", False) if ctx.obj else False

        if not yes:
            typer.echo(f"Decision: {decision.id}")
            typer.echo(f"  Commit:   {decision.commit_hash[:7]}")
            typer.echo(f"  Type:     {decision.decision}")
            if decision.angle:
                typer.echo(f"  Angle:    {decision.angle}")
            if decision.media_tool:
                typer.echo(f"  Media:    {decision.media_tool}")
            confirm = typer.confirm("Delete this decision and all associated data?")
            if not confirm:
                typer.echo("Cancelled.")
                return

        deleted = ops.delete_decision(conn, decision_id)
        if deleted:
            ops.emit_data_event(conn, "decision", "deleted", decision_id, decision.project_id)
            if json_output:
                typer.echo(json_mod.dumps({"deleted": True, "decision_id": decision_id}, indent=2))
            else:
                typer.echo(f"Decision {decision_id} deleted.")
        else:
            typer.echo("Failed to delete decision.")
            raise typer.Exit(1)
    finally:
        conn.close()


@app.command()
def retrigger(
    ctx: typer.Context,
    decision_id: str = typer.Argument(..., help="Decision ID to re-evaluate"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Delete a decision and re-evaluate the commit from scratch.

    This re-runs the evaluator LLM, which may produce a different angle,
    episode type, or even skip the commit entirely.

    Example: social-hook decision retrigger decision-abc123
    """
    from social_hook.db import operations as ops

    conn = _get_conn()
    try:
        decision = ops.get_decision(conn, decision_id)
        if not decision:
            typer.echo(f"Decision not found: {decision_id}")
            raise typer.Exit(1)

        project = ops.get_project(conn, decision.project_id)
        if not project:
            typer.echo(f"Project not found: {decision.project_id}")
            raise typer.Exit(1)

        json_output = ctx.obj.get("json", False) if ctx.obj else False

        if not yes:
            typer.echo(f"Decision: {decision.id}")
            typer.echo(f"  Commit:   {decision.commit_hash[:7]}")
            typer.echo(f"  Type:     {decision.decision}")
            if decision.angle:
                typer.echo(f"  Angle:    {decision.angle}")
            if decision.media_tool:
                typer.echo(f"  Media:    {decision.media_tool}")
            typer.echo()
            typer.echo("This will delete the decision and re-run the evaluator.")
            confirm = typer.confirm("Proceed?")
            if not confirm:
                typer.echo("Cancelled.")
                return

        commit_hash = decision.commit_hash
        repo_path = project.repo_path

        ops.delete_decision(conn, decision_id)
        ops.emit_data_event(conn, "decision", "deleted", decision_id, decision.project_id)
    finally:
        conn.close()

    from social_hook.trigger import run_trigger

    config_path = ctx.obj.get("config") if ctx.obj else None
    verbose = ctx.obj.get("verbose", False) if ctx.obj else False
    dry_run = ctx.obj.get("dry_run", False) if ctx.obj else False

    if not json_output:
        typer.echo(f"Re-evaluating commit {commit_hash[:7]}...")

    exit_code = run_trigger(
        commit_hash=commit_hash,
        repo_path=repo_path,
        dry_run=dry_run,
        config_path=str(config_path) if config_path else None,
        verbose=verbose,
    )

    if json_output:
        typer.echo(
            json_mod.dumps(
                {"retriggered": exit_code == 0, "commit_hash": commit_hash, "exit_code": exit_code},
                indent=2,
            )
        )
    elif exit_code == 0:
        typer.echo("Re-evaluation complete.")
    else:
        typer.echo(f"Re-evaluation failed (exit code {exit_code}).")
        raise typer.Exit(exit_code)


@app.command("list")
def list_cmd(
    ctx: typer.Context,
    project: str | None = typer.Option(None, "--project", "-p", help="Project path (default: cwd)"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max decisions to show"),
):
    """List decisions for a project.

    Example: social-hook decision list --project .
    """
    from social_hook.db import operations as ops

    conn = _get_conn()
    try:
        repo_path = _resolve_project(project)
        proj = ops.get_project_by_path(conn, repo_path)
        if not proj:
            typer.echo(f"No registered project at {repo_path}", err=True)
            raise typer.Exit(1)

        decisions = ops.get_recent_decisions(conn, proj.id, limit=limit)
        json_output = ctx.obj.get("json", False) if ctx.obj else False

        if json_output:
            typer.echo(json_mod.dumps([d.to_dict() for d in decisions], indent=2, default=str))
            return

        if not decisions:
            typer.echo("No decisions found.")
            return

        typer.echo(
            f"{'ID':<16} {'Commit':<9} {'Decision':<10} {'Media':<14} {'Angle':<30} {'Date'}"
        )
        typer.echo("-" * 99)
        for d in decisions:
            did = d.id[:14]
            commit = d.commit_hash[:7]
            media = (d.media_tool or "—")[:12]
            angle = (d.angle or "")[:28]
            date = str(d.created_at)[:19] if d.created_at else ""
            typer.echo(f"{did:<16} {commit:<9} {d.decision:<10} {media:<14} {angle:<30} {date}")
    finally:
        conn.close()
