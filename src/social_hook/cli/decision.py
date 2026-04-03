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


@app.command("batch-evaluate")
def batch_evaluate(
    ctx: typer.Context,
    decision_ids: list[str] = typer.Argument(..., help="Decision IDs to evaluate as a batch"),
    project: str | None = typer.Option(None, "--project", "-p", help="Project path (default: cwd)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Evaluate multiple imported/deferred decisions as a single batch.

    Groups the decisions and runs a combined evaluation through the full
    pipeline (commit analysis, evaluation, drafting, notifications).
    All decisions must belong to the same project and have status
    'imported' or 'deferred_eval' (without an existing batch_id).

    Example: social-hook decision batch-evaluate dec_abc123 dec_def456
    """
    from social_hook.db import operations as ops

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)
    dry_run = ctx.obj.get("dry_run", False) if ctx.obj else False

    conn = _get_conn()
    try:
        # Validate all decisions exist
        decisions = []
        for did in decision_ids:
            d = ops.get_decision(conn, did)
            if not d:
                typer.echo(f"Decision not found: {did}", err=True)
                raise typer.Exit(1)
            decisions.append(d)

        # All must be same project
        project_ids = {d.project_id for d in decisions}
        if len(project_ids) > 1:
            typer.echo("All decisions must belong to the same project.", err=True)
            raise typer.Exit(1)

        # Validate statuses
        from social_hook.models.enums import DecisionType

        valid_statuses = {DecisionType.IMPORTED.value, DecisionType.DEFERRED_EVAL.value}
        for d in decisions:
            if d.decision not in valid_statuses:
                typer.echo(
                    f"Decision {d.id} has status '{d.decision}', "
                    "expected 'imported' or 'deferred_eval'.",
                    err=True,
                )
                raise typer.Exit(1)
            if d.decision == DecisionType.DEFERRED_EVAL.value and d.batch_id:
                typer.echo(
                    f"Decision {d.id} already belongs to batch {d.batch_id}.",
                    err=True,
                )
                raise typer.Exit(1)

        proj = ops.get_project(conn, decisions[0].project_id)
        if not proj:
            typer.echo(f"Project not found: {decisions[0].project_id}", err=True)
            raise typer.Exit(1)

        # Verify --project matches if provided
        if project:
            repo_path_check = _resolve_project(project)
            proj_check = ops.get_project_by_path(conn, repo_path_check)
            if not proj_check or proj_check.id != proj.id:
                typer.echo(
                    f"Decisions belong to project '{proj.name}', "
                    f"not the project at {repo_path_check}.",
                    err=True,
                )
                raise typer.Exit(1)

        if not yes:
            typer.echo(f"Batch evaluate {len(decisions)} decision(s):")
            for d in decisions:
                typer.echo(f"  {d.id[:14]}  {d.commit_hash[:7]}  {d.decision}")
            typer.echo()
            confirm = typer.confirm("Proceed?")
            if not confirm:
                typer.echo("Cancelled.")
                return

        # Save original statuses for error recovery
        original_statuses = {d.id: d.decision for d in decisions}

        # Clean up old drafts for each decision
        for did in decision_ids:
            ops.delete_drafts_for_decision(conn, did)

        # Pre-mark as processing
        for did in decision_ids:
            conn.execute(
                "UPDATE decisions SET decision = ? WHERE id = ?",
                (DecisionType.PROCESSING.value, did),
            )
        conn.commit()
        for did in decision_ids:
            ops.emit_data_event(conn, "decision", "updated", did, proj.id)

        repo_path = proj.repo_path
        project_id = proj.id
    finally:
        conn.close()

    # Run evaluation (synchronous, with spinner)
    from social_hook.cli._spinner import spinner

    try:
        with spinner(f"Evaluating batch of {len(decisions)} decision(s)..."):
            from social_hook.config.project import ProjectConfig, load_project_config
            from social_hook.config.yaml import load_full_config
            from social_hook.errors import ConfigError
            from social_hook.llm.dry_run import DryRunContext
            from social_hook.llm.factory import create_client
            from social_hook.llm.prompts import assemble_evaluator_context
            from social_hook.trigger import TriggerContext, evaluate_batch, parse_commit_info

            conn2 = _get_conn()
            db = DryRunContext(conn2, dry_run=dry_run)

            try:
                config = load_full_config()
                proj2 = ops.get_project(conn2, project_id)
                if not proj2:
                    raise RuntimeError(f"Project {project_id} not found")

                try:
                    project_config = load_project_config(repo_path)
                except ConfigError:
                    project_config = ProjectConfig(repo_path=repo_path)

                # Use last decision as trigger (evaluate_batch convention)
                last_decision = decisions[-1]
                trigger_hash = last_decision.commit_hash
                commit = parse_commit_info(trigger_hash, repo_path)
                context = assemble_evaluator_context(db, project_id, project_config)

                # Ensure project has a brief (runs discovery if missing)
                from social_hook.trigger import ensure_project_brief

                ensure_project_brief(
                    config=config,
                    project_config=project_config,
                    conn=conn2,
                    db=db,
                    project=proj2,
                    context=context,
                    entity_id=trigger_hash[:8],
                )

                evaluator_client = create_client(config.models.evaluator, config)

                tctx = TriggerContext(
                    config=config,
                    conn=conn2,
                    db=db,
                    project=proj2,
                    commit=commit,
                    project_config=project_config,
                    current_branch=last_decision.branch,
                    dry_run=dry_run,
                    verbose=False,
                    show_prompt=False,
                    existing_decision_id=last_decision.id,
                )

                # Re-fetch decisions from fresh connection
                batch_decisions = []
                for did in decision_ids:
                    d = ops.get_decision(conn2, did)
                    if d:
                        batch_decisions.append(d)

                # Separate trigger (last) from deferred (the rest)
                deferred_decisions = batch_decisions[:-1]

                result = evaluate_batch(
                    ctx=tctx,
                    deferred_commits=deferred_decisions,
                    trigger_commit_hash=trigger_hash,
                    context=context,
                    evaluator_client=evaluator_client,
                )

                if result != 0:
                    raise RuntimeError(f"evaluate_batch returned {result}")
            finally:
                conn2.close()
    except Exception as exc:
        # Error recovery: restore original statuses
        conn3 = _get_conn()
        try:
            for did, orig_status in original_statuses.items():
                conn3.execute(
                    "UPDATE decisions SET decision = ? WHERE id = ? AND decision = ?",
                    (orig_status, did, DecisionType.PROCESSING.value),
                )
            conn3.commit()
            for did in decision_ids:
                ops.emit_data_event(conn3, "decision", "updated", did, project_id)
        finally:
            conn3.close()

        if json_output:
            typer.echo(
                json_mod.dumps(
                    {"success": False, "error": str(exc), "count": len(decision_ids)},
                    indent=2,
                )
            )
        else:
            typer.echo(f"Batch evaluation failed: {exc}")
        raise typer.Exit(2) from None

    if json_output:
        typer.echo(
            json_mod.dumps(
                {"success": True, "count": len(decision_ids)},
                indent=2,
            )
        )
    else:
        typer.echo(f"Batch evaluation complete ({len(decision_ids)} decisions).")


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
            f"{'ID':<16} {'Commit':<9} {'Decision':<14} {'Media':<14} {'Angle':<30} {'Date'}"
        )
        typer.echo("-" * 103)

        # Group deferred_eval decisions with same batch_id for visual separators
        seen_batches: set[str] = set()
        for d in decisions:
            bid = d.batch_id
            if bid and bid not in seen_batches:
                seen_batches.add(bid)
                batch_members = [x for x in decisions if x.batch_id == bid]
                if len(batch_members) > 1:
                    typer.echo(f"  --- batch {bid[:14]} ({len(batch_members)} decisions) ---")

            did = d.id[:14]
            commit = d.commit_hash[:7]
            decision_str = d.decision
            if bid:
                decision_str = f"{d.decision}*"
            media = (d.media_tool or "—")[:12]
            angle = (d.angle or "")[:28]
            date = str(d.created_at)[:19] if d.created_at else ""
            typer.echo(f"{did:<16} {commit:<9} {decision_str:<14} {media:<14} {angle:<30} {date}")
    finally:
        conn.close()
