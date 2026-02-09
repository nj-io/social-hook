"""CLI commands for manual operations (evaluate, draft, post)."""

from typing import Optional

import typer

app = typer.Typer()


@app.command()
def evaluate(
    ctx: typer.Context,
    commit: str = typer.Argument(..., help="Commit hash to evaluate"),
    repo: Optional[str] = typer.Option(None, "--repo", help="Repository path"),
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Project ID"),
):
    """Manually evaluate a commit (without triggering draft creation)."""
    from social_hook.trigger import parse_commit_info, run_trigger

    dry_run = ctx.obj.get("dry_run", False) if ctx.obj else False
    verbose = ctx.obj.get("verbose", False) if ctx.obj else False
    config_path = ctx.obj.get("config") if ctx.obj else None

    if not repo:
        import os
        repo = os.getcwd()

    exit_code = run_trigger(
        commit_hash=commit,
        repo_path=repo,
        dry_run=dry_run,
        config_path=str(config_path) if config_path else None,
        verbose=verbose,
    )
    raise SystemExit(exit_code)


@app.command()
def draft(
    ctx: typer.Context,
    decision_id: str = typer.Argument(..., help="Decision ID to create draft for"),
):
    """Manually create a draft from an existing decision."""
    from social_hook.config import load_full_config
    from social_hook.db import get_decision, get_project, init_database, insert_draft
    from social_hook.filesystem import generate_id, get_db_path
    from social_hook.models import Draft

    config_path = ctx.obj.get("config") if ctx.obj else None
    dry_run = ctx.obj.get("dry_run", False) if ctx.obj else False
    config = load_full_config(str(config_path) if config_path else None)

    conn = init_database(get_db_path())
    try:
        decision = get_decision(conn, decision_id)
        if not decision:
            typer.echo(f"Decision not found: {decision_id}")
            raise typer.Exit(1)

        typer.echo(f"Decision: {decision.decision}")
        typer.echo(f"Reasoning: {decision.reasoning}")

        if decision.decision != "post_worthy":
            typer.echo("Decision is not post_worthy. Cannot create draft.")
            raise typer.Exit(1)

        project = get_project(conn, decision.project_id)
        if not project:
            typer.echo(f"Project not found: {decision.project_id}")
            raise typer.Exit(1)

        # Parse commit info
        from social_hook.trigger import parse_commit_info

        commit = parse_commit_info(decision.commit_hash, project.repo_path)

        # Assemble context
        from social_hook.config.project import load_project_config
        from social_hook.llm.dry_run import DryRunContext
        from social_hook.llm.prompts import assemble_evaluator_context

        db = DryRunContext(conn, dry_run=dry_run)
        project_config = load_project_config(project.repo_path)
        context = assemble_evaluator_context(db, project.id, project_config)

        # Create draft via LLM
        from social_hook.llm.client import ClaudeClient
        from social_hook.llm.drafter import Drafter
        from social_hook.llm.evaluator import EvaluationResult

        api_key = config.env.get("ANTHROPIC_API_KEY", "")
        if dry_run:
            api_key = "dry-run-key"

        client = ClaudeClient(
            api_key=api_key,
            model=config.models.drafter,
            dry_run=dry_run,
        )
        drafter = Drafter(client)

        # Build a minimal evaluation result
        evaluation = EvaluationResult(
            decision=decision.decision,
            reasoning=decision.reasoning,
            angle=decision.angle,
            episode_type=decision.episode_type,
            post_category=decision.post_category,
            arc_id=decision.arc_id,
            media_tool=decision.media_tool,
        )

        platform = "x"
        tier = "free"
        if config.platforms.x.enabled:
            tier = config.platforms.x.account_tier or "free"
        elif config.platforms.linkedin.enabled:
            platform = "linkedin"

        draft_result = drafter.create_draft(
            evaluation, context, commit, db,
            platform=platform, tier=tier,
        )

        draft_obj = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform=platform,
            content=draft_result.content,
            reasoning=draft_result.reasoning,
        )

        if not dry_run:
            insert_draft(conn, draft_obj)

        typer.echo(f"\nDraft created: {draft_obj.id}")
        typer.echo(f"Platform: {platform}")
        typer.echo(f"Content:\n{draft_result.content}")
    finally:
        conn.close()


@app.command()
def post(
    ctx: typer.Context,
    draft_id: str = typer.Argument(..., help="Draft ID to post"),
):
    """Manually post an approved draft."""
    from social_hook.config import load_full_config
    from social_hook.db import get_draft, init_database, update_draft
    from social_hook.filesystem import get_db_path

    config_path = ctx.obj.get("config") if ctx.obj else None
    config = load_full_config(str(config_path) if config_path else None)

    conn = init_database(get_db_path())
    try:
        draft_obj = get_draft(conn, draft_id)
        if not draft_obj:
            typer.echo(f"Draft not found: {draft_id}")
            raise typer.Exit(1)

        if draft_obj.status not in ("approved", "scheduled"):
            typer.echo(f"Draft status is '{draft_obj.status}'. Must be 'approved' or 'scheduled' to post.")
            raise typer.Exit(1)

        typer.echo(f"Platform: {draft_obj.platform}")
        typer.echo(f"Content: {draft_obj.content[:200]}...")

        dry_run = ctx.obj.get("dry_run", False) if ctx.obj else False

        if dry_run:
            typer.echo("\n[dry-run] Would post this draft.")
            update_draft(conn, draft_id, status="posted")
            return

        from social_hook.scheduler import _post_draft

        result = _post_draft(conn, draft_obj, config)
        if result.success:
            update_draft(conn, draft_id, status="posted")
            typer.echo(f"\nPosted successfully!")
            if result.external_id:
                typer.echo(f"External ID: {result.external_id}")
        else:
            typer.echo(f"\nPost failed: {result.error}")
            raise typer.Exit(1)
    finally:
        conn.close()
