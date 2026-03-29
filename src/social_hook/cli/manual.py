"""CLI commands for manual operations (evaluate, draft, consolidate, post)."""

import typer

from social_hook.models.enums import PENDING_STATUSES

app = typer.Typer()


@app.command()
def evaluate(
    ctx: typer.Context,
    commit: str = typer.Argument(..., help="Commit hash to evaluate"),
    repo: str | None = typer.Option(None, "--repo", help="Repository path"),
):
    """Manually evaluate a commit through the full pipeline.

    Runs the same evaluation and drafting pipeline as the automatic hook trigger.

    Example: social-hook manual evaluate abc1234 --repo /path/to/repo
    """
    from social_hook.trigger import run_trigger

    dry_run = ctx.obj.get("dry_run", False) if ctx.obj else False
    verbose = ctx.obj.get("verbose", False) if ctx.obj else False
    config_path = ctx.obj.get("config") if ctx.obj else None

    if not repo:
        import os

        repo = os.getcwd()

    from social_hook.cli._spinner import spinner

    with spinner("Evaluating commit..."):
        exit_code = run_trigger(
            commit_hash=commit,
            repo_path=repo,
            dry_run=dry_run,
            config_path=str(config_path) if config_path else None,
            verbose=verbose,
            trigger_source="manual",
        )
    raise SystemExit(exit_code)


@app.command()
def draft(
    ctx: typer.Context,
    decision_id: str = typer.Argument(..., help="Decision ID to create draft for"),
    platform: str | None = typer.Option(
        None, "--platform", help="Target platform (default: all enabled)"
    ),
):
    """Manually create drafts from an existing decision."""
    from social_hook.config import load_full_config
    from social_hook.db import get_decision, get_project, init_database
    from social_hook.filesystem import get_db_path

    config_path = ctx.obj.get("config") if ctx.obj else None
    dry_run = ctx.obj.get("dry_run", False) if ctx.obj else False
    verbose = ctx.obj.get("verbose", False) if ctx.obj else False
    config = load_full_config(str(config_path) if config_path else None)

    # Validate platform is enabled if specified
    if platform:
        pcfg = config.platforms.get(platform)
        if not pcfg or not pcfg.enabled:
            typer.echo(f"Platform '{platform}' is not enabled.")
            raise typer.Exit(1)

    conn = init_database(get_db_path())
    try:
        decision = get_decision(conn, decision_id)
        if not decision:
            typer.echo(f"Decision not found: {decision_id}")
            raise typer.Exit(1)

        typer.echo(f"Decision: {decision.decision}")
        typer.echo(f"Reasoning: {decision.reasoning}")

        project = get_project(conn, decision.project_id)
        if not project:
            typer.echo(f"Project not found: {decision.project_id}")
            raise typer.Exit(1)

        # Parse commit info
        from social_hook.trigger import parse_commit_info

        commit_info = parse_commit_info(decision.commit_hash, project.repo_path)

        # Assemble context
        from social_hook.config.project import ProjectConfig, load_project_config
        from social_hook.errors import ConfigError
        from social_hook.llm.dry_run import DryRunContext
        from social_hook.llm.prompts import assemble_evaluator_context

        db = DryRunContext(conn, dry_run=dry_run)
        try:
            project_config = load_project_config(project.repo_path)
        except ConfigError:
            project_config = ProjectConfig(repo_path=project.repo_path)

        context = assemble_evaluator_context(
            db,
            project.id,
            project_config,
            commit_timestamp=commit_info.timestamp,
            parent_timestamp=commit_info.parent_timestamp,
        )

        # Build evaluation from stored decision, forcing draft for override
        from social_hook.compat import evaluation_from_decision

        evaluation = evaluation_from_decision(decision, "draft")

        # Draft for platforms
        from social_hook.cli._spinner import spinner
        from social_hook.drafting import draft_for_platforms

        target_platform_names = [platform] if platform else None
        with spinner("Creating draft..."):
            results = draft_for_platforms(
                config,
                conn,
                db,
                project,
                decision_id=decision.id,
                evaluation=evaluation,
                context=context,
                commit=commit_info,
                project_config=project_config,
                target_platform_names=target_platform_names,
                dry_run=dry_run,
                verbose=verbose,
            )

        if not results:
            typer.echo("\nNo drafts created (platforms may have been filtered or deferred).")
        else:
            typer.echo(f"\n{len(results)} draft(s) created:")
            for r in results:
                typer.echo(f"  {r.draft.platform}: {r.draft.id}")
                typer.echo(f"    Content: {r.draft.content[:100]}...")
    finally:
        conn.close()


@app.command()
def consolidate(
    ctx: typer.Context,
    decision_ids: list[str] = typer.Argument(..., help="Decision IDs to consolidate (at least 2)"),
):
    """Consolidate multiple decisions into a single draft."""
    if len(decision_ids) < 2:
        typer.echo("At least 2 decision IDs are required for consolidation.")
        raise typer.Exit(1)

    from social_hook.config import load_full_config
    from social_hook.db import get_decision, get_project, init_database
    from social_hook.filesystem import get_db_path

    config_path = ctx.obj.get("config") if ctx.obj else None
    dry_run = ctx.obj.get("dry_run", False) if ctx.obj else False
    verbose = ctx.obj.get("verbose", False) if ctx.obj else False
    config = load_full_config(str(config_path) if config_path else None)

    conn = init_database(get_db_path())
    try:
        # Fetch and validate all decisions
        decisions = []
        for did in decision_ids:
            decision = get_decision(conn, did)
            if not decision:
                typer.echo(f"Decision not found: {did}")
                raise typer.Exit(1)
            decisions.append(decision)

        # Verify all belong to same project
        project_ids = {d.project_id for d in decisions}
        if len(project_ids) > 1:
            typer.echo("All decisions must belong to the same project.")
            raise typer.Exit(1)

        project_id = decisions[0].project_id
        project = get_project(conn, project_id)
        if not project:
            typer.echo(f"Project not found: {project_id}")
            raise typer.Exit(1)

        # Build synthetic CommitInfo combining commit messages
        from social_hook.models.core import CommitInfo

        combined_summary = "\n".join(
            f"- {d.commit_summary or d.commit_message or d.commit_hash[:8]}" for d in decisions
        )
        commit = CommitInfo(
            hash=f"consolidate-{decisions[-1].commit_hash[:8]}",
            message=f"Consolidation of {len(decisions)} commits:\n{combined_summary}",
            diff="",
            files_changed=[],
        )

        # Assemble context
        from social_hook.compat import evaluation_from_decision
        from social_hook.config.project import ProjectConfig, load_project_config
        from social_hook.errors import ConfigError
        from social_hook.llm.dry_run import DryRunContext
        from social_hook.llm.prompts import assemble_evaluator_context

        db = DryRunContext(conn, dry_run=dry_run)
        try:
            project_config = load_project_config(project.repo_path)
        except ConfigError:
            project_config = ProjectConfig(repo_path=project.repo_path)

        context = assemble_evaluator_context(
            db,
            project.id,
            project_config,
        )

        # Use most recent decision as anchor
        anchor = decisions[-1]
        evaluation = evaluation_from_decision(anchor, "draft")

        # Draft for platforms
        from social_hook.cli._spinner import spinner
        from social_hook.drafting import draft_for_platforms

        with spinner("Consolidating and drafting..."):
            results = draft_for_platforms(
                config,
                conn,
                db,
                project,
                decision_id=anchor.id,
                evaluation=evaluation,
                context=context,
                commit=commit,
                project_config=project_config,
                dry_run=dry_run,
                verbose=verbose,
            )

        if not results:
            typer.echo("\nNo drafts created (platforms may have been filtered or deferred).")
        else:
            typer.echo(
                f"\n{len(results)} draft(s) created from {len(decisions)} consolidated decisions:"
            )
            for r in results:
                typer.echo(f"  {r.draft.platform}: {r.draft.id}")
    finally:
        conn.close()


@app.command()
def post(
    ctx: typer.Context,
    draft_id: str = typer.Argument(..., help="Draft ID to post"),
):
    """Manually post an approved draft."""
    from social_hook.config import load_full_config
    from social_hook.db import get_draft, init_database
    from social_hook.db import operations as ops
    from social_hook.filesystem import get_db_path

    config_path = ctx.obj.get("config") if ctx.obj else None
    config = load_full_config(str(config_path) if config_path else None)

    conn = init_database(get_db_path())
    try:
        draft_obj = get_draft(conn, draft_id)
        if not draft_obj:
            typer.echo(f"Draft not found: {draft_id}")
            raise typer.Exit(1)

        if draft_obj.preview_mode:
            typer.echo(
                "No account connected. Run 'social-hook account add' to connect and enable posting."
            )
            raise typer.Exit(1)

        if draft_obj.status not in PENDING_STATUSES:
            typer.echo(
                f"Draft status is '{draft_obj.status}'. Must be 'draft', 'approved', 'scheduled', or 'deferred' to post."
            )
            raise typer.Exit(1)

        typer.echo(f"Platform: {draft_obj.platform}")
        typer.echo(f"Content: {draft_obj.content[:200]}...")

        dry_run = ctx.obj.get("dry_run", False) if ctx.obj else False

        if dry_run:
            typer.echo("\n[dry-run] Would post this draft.")
            return

        from social_hook.cli._spinner import spinner
        from social_hook.scheduler import _handle_post_failure, _post_draft, record_post_success

        project = ops.get_project(conn, draft_obj.project_id)
        project_name = project.name if project else "Unknown"

        db_path = get_db_path()
        with spinner(f"Posting to {draft_obj.platform}..."):
            result = _post_draft(conn, draft_obj, config, db_path=db_path)
        if result.success:
            record_post_success(conn, draft_obj, result, config, project_name, dry_run=dry_run)
            typer.echo("\nPosted successfully!")
            if result.external_url:
                typer.echo(f"URL: {result.external_url}")
            if result.external_id:
                typer.echo(f"External ID: {result.external_id}")
        else:
            _handle_post_failure(conn, draft_obj, result.error or "Unknown error", config, dry_run)
            typer.echo(f"\nPost failed: {result.error}")
            raise typer.Exit(1)
    finally:
        conn.close()
