"""CLI commands for decision management."""

import json as json_mod
import os
import shutil
import sqlite3

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
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Delete a decision and its associated drafts.

    A decision is the evaluator's verdict on a commit (draft, skip, or defer).
    This permanently removes the decision and all linked drafts from the
    database. This action cannot be undone.

    Example: social-hook decision delete decision-abc123
    Example: social-hook decision delete decision-abc123 --yes  (skip confirmation)
    """
    from social_hook.db import operations as ops

    conn = _get_conn()
    try:
        decision = ops.get_decision(conn, decision_id)
        if not decision:
            typer.echo(f"Decision not found: {decision_id}")
            raise typer.Exit(1)

        json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

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
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Delete a decision and re-evaluate the commit from scratch.

    This re-runs the evaluator LLM, which may produce a different angle,
    episode type, or even skip the commit entirely.

    Example: social-hook decision retrigger decision-abc123
    Example: social-hook decision retrigger decision-abc123 --yes  (skip confirmation)
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

        json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

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

    from social_hook.cli._spinner import spinner

    with spinner(f"Re-evaluating commit {commit_hash[:7]}..."):
        exit_code = run_trigger(
            commit_hash=commit_hash,
            repo_path=repo_path,
            dry_run=dry_run,
            config_path=str(config_path) if config_path else None,
            verbose=verbose,
            trigger_source="manual",
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


@app.command()
def rewind(
    ctx: typer.Context,
    identifier: str = typer.Argument(..., help="Decision ID or commit hash (full or short prefix)"),
    project: str | None = typer.Option(None, "--project", "-p", help="Project path (default: cwd)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    force: bool = typer.Option(False, "--force", "-f", help="Allow rewind even with posted drafts"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Rewind a decision to its evaluation point, removing all downstream artifacts.

    Keeps the evaluator's decision but deletes drafts, posts, and draft metadata.
    Resets the decision to unprocessed so it can be re-drafted.

    Accepts either a decision ID (e.g. decision_abc123) or a commit hash.
    When non-commit trigger sources exist (plugins, external events), use
    the decision ID directly.

    Example: social-hook decision rewind abc1234
    Example: social-hook decision rewind decision_abc123
    Example: social-hook decision rewind abc1234 --yes  (skip confirmation)
    """
    from social_hook.db import operations as ops
    from social_hook.filesystem import get_db_path

    conn = _get_conn()
    try:
        json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

        # Resolve project
        repo_path = _resolve_project(project)
        proj = ops.get_project_by_path(conn, repo_path)
        if not proj:
            typer.echo(f"No registered project at {repo_path}", err=True)
            raise typer.Exit(1)

        # Look up decision — auto-detect identifier type
        decision = None
        if identifier.startswith("decision_"):
            decision = ops.get_decision(conn, identifier)
        else:
            decision = ops.get_decision_by_commit(conn, proj.id, identifier)
            if not decision and len(identifier) < 40:
                # Try short prefix match (escape LIKE metacharacters)
                escaped = identifier.replace("%", r"\%").replace("_", r"\_")
                rows = conn.execute(
                    "SELECT * FROM decisions WHERE project_id = ? AND commit_hash LIKE ? ESCAPE '\\'",
                    (proj.id, escaped + "%"),
                ).fetchall()
                if len(rows) == 1:
                    from social_hook.models.core import Decision

                    decision = Decision.from_dict(dict(rows[0]))
                elif len(rows) > 1:
                    typer.echo(f"Ambiguous commit prefix '{identifier}'. Matches:")
                    for r in rows:
                        typer.echo(f"  {r['commit_hash'][:12]}")
                    raise typer.Exit(1)

        if not decision:
            typer.echo(f"No decision found for: {identifier}")
            raise typer.Exit(1)

        # Show decision details and draft summary
        if not yes:
            typer.echo(f"Decision: {decision.id}")
            typer.echo(f"  Commit:   {decision.commit_hash[:7]}")
            typer.echo(f"  Type:     {decision.decision}")
            if decision.angle:
                typer.echo(f"  Angle:    {decision.angle}")
            if decision.media_tool:
                typer.echo(f"  Media:    {decision.media_tool}")

            # Draft status summary
            status_rows = conn.execute(
                "SELECT status, COUNT(*) FROM drafts WHERE decision_id = ? GROUP BY status",
                (decision.id,),
            ).fetchall()
            if status_rows:
                typer.echo("  Drafts:")
                for sr in status_rows:
                    marker = "  ⚠ " if sr[0] == "posted" else "    "
                    typer.echo(f"{marker}{sr[0]}: {sr[1]}")
                if any(sr[0] == "posted" for sr in status_rows):
                    typer.echo()
                    typer.echo("WARNING: Posted drafts exist. Content remains live on platform.")
            else:
                typer.echo("  Drafts:   (none)")

            typer.echo()
            confirm = typer.confirm(
                "Rewind this decision? Drafts and posts will be permanently deleted."
            )
            if not confirm:
                typer.echo("Cancelled.")
                return

        # Auto-snapshot before rewind (safety net — rewind is irreversible)
        db_path = get_db_path()
        try:
            from social_hook.filesystem import get_base_path

            snap_dir = get_base_path() / "snapshots"
            snap_dir.mkdir(parents=True, exist_ok=True)
            backup = snap_dir / "_pre_rewind.db"
            snap_conn = sqlite3.connect(str(db_path))
            snap_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            snap_conn.close()
            shutil.copy2(str(db_path), str(backup))
        except Exception:
            pass  # Best-effort; don't block rewind on snapshot failure

        # Execute rewind
        try:
            result = ops.rewind_decision(conn, decision.id, force=force)
        except ValueError as exc:
            typer.echo(f"Error: {exc}")
            raise typer.Exit(1) from None

        if result is None:
            typer.echo("Rewind failed.")
            raise typer.Exit(1)

        ops.emit_data_event(conn, "decision", "rewound", decision.id, proj.id)

        if json_output:
            result["backup"] = "_pre_rewind"
            typer.echo(json_mod.dumps(result, indent=2))
        else:
            typer.echo(
                f"Rewound decision {decision.id}: "
                f"deleted {result['drafts_deleted']} draft(s), "
                f"{result['posts_deleted']} post(s)."
            )
            if result["arc_decremented"]:
                typer.echo(f"  Arc post count decremented for: {decision.arc_id}")
            if result["audience_reset"]:
                typer.echo("  platform_introduced reset for affected platforms.")
            typer.echo(
                "  Pre-rewind snapshot saved. Restore with: social-hook snapshot restore _pre_rewind"
            )
    finally:
        conn.close()


@app.command("list")
def list_cmd(
    ctx: typer.Context,
    project: str | None = typer.Option(None, "--project", "-p", help="Project path (default: cwd)"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max decisions to show"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List decisions for a project.

    Decisions are evaluator outcomes for commits (draft, skip, or defer).
    Each row shows the decision ID, commit hash, type, media tool, content
    angle, and date.

    Examples:
        social-hook decision list --project .
        social-hook decision list --limit 50 --json
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
        json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

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
