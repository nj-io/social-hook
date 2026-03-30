"""CLI commands for evaluation cycle inspection."""

import json as json_mod
import logging

import typer

from social_hook.cli.utils import resolve_project
from social_hook.diagnostics import filter_actionable
from social_hook.parsing import safe_int, safe_json_loads

app = typer.Typer(no_args_is_help=True)
logger = logging.getLogger(__name__)


def _get_conn():
    from social_hook.db.connection import init_database
    from social_hook.filesystem import get_db_path

    return init_database(get_db_path())


def _resolve_proj(conn, project_path: str | None):
    """Resolve project from --project or cwd. Returns project or exits."""
    from social_hook.db import operations as ops

    repo_path = resolve_project(project_path)
    proj = ops.get_project_by_path(conn, repo_path)
    if not proj:
        typer.echo(f"No registered project at {repo_path}", err=True)
        raise typer.Exit(1)
    return proj


@app.command("list")
def list_cmd(
    ctx: typer.Context,
    limit: int = typer.Option(20, "--limit", "-n", help="Max cycles to show"),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List recent evaluation cycles.

    Shows the history of content evaluation cycles for the project,
    including trigger type and timing.

    Example: social-hook cycles list --limit 10
    """
    from social_hook.db import operations as ops

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)
    limit = safe_int(limit, 20, "limit")

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)
        cycles = ops.get_recent_cycles(conn, proj.id, limit=limit)

        if json_output:
            typer.echo(
                json_mod.dumps(
                    {"cycles": [c.to_dict() for c in cycles]},
                    indent=2,
                )
            )
            return

        if not cycles:
            typer.echo("No evaluation cycles found.")
            return

        typer.echo(f"{'ID':<16} {'Trigger':<14} {'Reference':<24} {'Created'}")
        typer.echo("-" * 75)
        for c in cycles:
            cid = c.id[:14]
            ref = (c.trigger_ref or "")[:22]
            created = (c.created_at or "")[:19]
            typer.echo(f"{cid:<16} {c.trigger_type:<14} {ref:<24} {created}")
    finally:
        conn.close()


@app.command()
def show(
    ctx: typer.Context,
    cycle_id: str = typer.Argument(..., help="Cycle ID to show"),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show evaluation cycle detail with per-strategy outcomes.

    Displays the full cycle including trigger information, related
    decisions, and drafts produced.

    Example: social-hook cycles show cycle_abc123
    """
    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)

        # Look up cycle
        row = conn.execute("SELECT * FROM evaluation_cycles WHERE id = ?", (cycle_id,)).fetchone()
        if not row:
            msg = f"Cycle not found: {cycle_id}"
            if json_output:
                typer.echo(json_mod.dumps({"error": msg}))
            else:
                typer.echo(msg)
            raise typer.Exit(1)

        from social_hook.models.content import EvaluationCycle

        cycle = EvaluationCycle.from_dict(dict(row))

        if cycle.project_id != proj.id:
            msg = "Cycle does not belong to this project"
            if json_output:
                typer.echo(json_mod.dumps({"error": msg}))
            else:
                typer.echo(msg)
            raise typer.Exit(1)

        # Get related drafts
        draft_rows = conn.execute(
            "SELECT id, status, platform, content FROM drafts WHERE evaluation_cycle_id = ?",
            (cycle_id,),
        ).fetchall()
        drafts = [dict(r) for r in draft_rows]

        # Get related decisions (via commit_hash pattern for synthetic decisions)
        decision_rows = conn.execute(
            """
            SELECT id, decision, reasoning, commit_hash
            FROM decisions
            WHERE project_id = ? AND (
                commit_hash LIKE 'combine:%' OR
                commit_hash LIKE 'hero_launch:%' OR
                commit_hash LIKE 'topic:%' OR
                id IN (SELECT decision_id FROM drafts WHERE evaluation_cycle_id = ?)
            )
            """,
            (proj.id, cycle_id),
        ).fetchall()
        decisions = [dict(r) for r in decision_rows]

        # Get batched decisions (deferred commits included in this cycle)
        batched_rows = conn.execute(
            "SELECT id, decision, commit_hash, commit_message FROM decisions WHERE batch_id = ?",
            (cycle_id,),
        ).fetchall()
        batched = [dict(r) for r in batched_rows]

        if json_output:
            typer.echo(
                json_mod.dumps(
                    {
                        "cycle": cycle.to_dict(),
                        "drafts": drafts,
                        "decisions": decisions,
                        "batched_commits": batched,
                    },
                    indent=2,
                    default=str,
                )
            )
            return

        typer.echo(f"Cycle: {cycle.id}")
        typer.echo(f"  Trigger:  {cycle.trigger_type}")
        if cycle.trigger_ref:
            typer.echo(f"  Ref:      {cycle.trigger_ref}")
        typer.echo(f"  Created:  {cycle.created_at}")

        if batched:
            typer.echo(f"\n  Batched commits ({len(batched)}):")
            for b in batched:
                msg = (
                    (b.get("commit_message") or "").splitlines()[0][:50]
                    if b.get("commit_message")
                    else ""
                )
                typer.echo(f"    {b['commit_hash'][:8]:<10} {msg}")

        if drafts:
            typer.echo(f"\n  Drafts ({len(drafts)}):")
            for d in drafts:
                content_preview = (d.get("content") or "")[:50].replace("\n", " ")
                typer.echo(
                    f"    {d['id'][:14]:<16} {d.get('platform', '?'):<10} "
                    f"{d.get('status', '?'):<10} {content_preview}"
                )
        else:
            typer.echo("\n  No drafts.")

        if decisions:
            typer.echo(f"\n  Decisions ({len(decisions)}):")
            for d in decisions:
                typer.echo(
                    f"    {d['id'][:14]:<16} {d['decision']:<10} {d.get('reasoning', '')[:40]}"
                )
        else:
            typer.echo("\n  No decisions.")

        # Parse and display diagnostics
        diag_raw = cycle.diagnostics
        diags = safe_json_loads(diag_raw, "cycle.diagnostics", default=[]) if diag_raw else []
        warnings = filter_actionable(diags)
        if warnings:
            typer.echo(
                f"\n  Diagnostics ({len(warnings)} warning{'s' if len(warnings) != 1 else ''}):"
            )
            for d in warnings:
                sev = d.get("severity", "?").upper()
                typer.echo(f"    [{sev}] {d.get('code', '?')}: {d.get('message', '')}")
                if d.get("suggestion"):
                    typer.echo(f"           → {d['suggestion']}")
        else:
            typer.echo("\n  No diagnostics.")
    finally:
        conn.close()
