"""CLI commands for draft lifecycle management."""

import json as json_mod
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import typer

app = typer.Typer(no_args_is_help=True)

TERMINAL_STATUSES = {"posted", "rejected", "cancelled", "superseded"}


def _get_conn():
    from social_hook.db.connection import init_database
    from social_hook.filesystem import get_db_path

    return init_database(get_db_path())


def _media_url(file_path: str, api_port: int = 8741) -> str | None:
    """Build a localhost URL for a media file path."""
    from social_hook.filesystem import get_base_path

    media_dir = get_base_path() / "media-cache"
    try:
        rel = Path(file_path).relative_to(media_dir)
        return f"http://localhost:{api_port}/api/media/{quote(str(rel))}"
    except ValueError:
        return None


def _get_draft_or_exit(conn, draft_id: str):
    from social_hook.db import operations as ops

    draft = ops.get_draft(conn, draft_id)
    if not draft:
        typer.echo(f"Draft not found: {draft_id}")
        raise typer.Exit(1)
    return draft


@app.command()
def approve(
    ctx: typer.Context,
    draft_id: str = typer.Argument(..., help="Draft ID to approve"),
):
    """Approve a draft for posting."""
    from social_hook.db import operations as ops

    conn = _get_conn()
    try:
        draft = _get_draft_or_exit(conn, draft_id)
        if draft.platform == "preview":
            typer.echo(
                "Preview drafts cannot be posted. Use 'social-hook draft promote "
                "<id> --platform <name>' to create a platform-specific draft."
            )
            raise typer.Exit(1)
        if draft.status in TERMINAL_STATUSES:
            typer.echo(f"Cannot approve: draft status is '{draft.status}'")
            raise typer.Exit(1)
        ops.update_draft(conn, draft_id, status="approved")
        ops.emit_data_event(conn, "draft", "approved", draft_id, draft.project_id)
        typer.echo(f"Draft {draft_id} approved.")
    finally:
        conn.close()


@app.command()
def reject(
    ctx: typer.Context,
    draft_id: str = typer.Argument(..., help="Draft ID to reject"),
    reason: str | None = typer.Option(None, "--reason", "-r", help="Rejection reason"),
):
    """Reject a draft (saves reason as voice memory when --reason provided).

    Example: social-hook draft reject draft-abc123 --reason "too technical for the audience"
    """
    from social_hook.db import operations as ops

    conn = _get_conn()
    try:
        draft = _get_draft_or_exit(conn, draft_id)
        if draft.status in TERMINAL_STATUSES:
            typer.echo(f"Cannot reject: draft status is '{draft.status}'")
            raise typer.Exit(1)
        kwargs = {"status": "rejected"}
        if reason:
            kwargs["last_error"] = f"Rejected: {reason}"
        ops.update_draft(conn, draft_id, **kwargs)  # type: ignore[arg-type]
        ops.emit_data_event(conn, "draft", "rejected", draft_id, draft.project_id)

        # Save rejection feedback as voice memory
        if reason:
            try:
                project = ops.get_project(conn, draft.project_id)
                if project:
                    from social_hook.config.project import save_memory

                    save_memory(
                        project.repo_path,
                        context=f"Rejected {draft.platform} draft",
                        feedback=reason,
                        draft_id=draft_id,
                    )
            except Exception:
                typer.echo("Warning: could not save rejection feedback as memory.", err=True)

        # Cascade re-draft if this was an intro draft
        from social_hook.intro_lifecycle import on_intro_rejected

        cascade_msg = on_intro_rejected(conn, draft, draft.project_id, verbose=False)

        typer.echo(f"Draft {draft_id} rejected.")
        if cascade_msg:
            typer.echo(cascade_msg)
    finally:
        conn.close()


@app.command()
def schedule(
    ctx: typer.Context,
    draft_id: str = typer.Argument(..., help="Draft ID to schedule"),
    time: str | None = typer.Option(None, "--time", "-t", help="Schedule time (ISO format)"),
):
    """Schedule a draft for posting."""
    from social_hook.db import operations as ops

    conn = _get_conn()
    try:
        draft = _get_draft_or_exit(conn, draft_id)
        if draft.platform == "preview":
            typer.echo(
                "Preview drafts cannot be posted. Use 'social-hook draft promote "
                "<id> --platform <name>' to create a platform-specific draft."
            )
            raise typer.Exit(1)
        if draft.status not in ("draft", "approved", "scheduled", "deferred"):
            typer.echo(f"Cannot schedule: draft status is '{draft.status}'")
            raise typer.Exit(1)

        if time:
            try:
                datetime.fromisoformat(time)
            except ValueError:
                typer.echo(f"Invalid datetime format: {time}")
                raise typer.Exit(1) from None
            ops.update_draft(conn, draft_id, status="scheduled", scheduled_time=time)
            typer.echo(f"Draft {draft_id} scheduled for {time}.")
        else:
            from social_hook.config.yaml import load_full_config
            from social_hook.scheduling import calculate_optimal_time

            config_path = ctx.obj.get("config") if ctx.obj else None
            config = load_full_config(str(config_path) if config_path else None)
            result = calculate_optimal_time(
                conn,
                draft.project_id,
                platform=draft.platform,
                tz=config.scheduling.timezone if config else "UTC",
                max_posts_per_day=config.scheduling.max_posts_per_day if config else 3,
                min_gap_minutes=config.scheduling.min_gap_minutes if config else 30,
                optimal_days=config.scheduling.optimal_days if config else None,
                optimal_hours=config.scheduling.optimal_hours if config else None,
            )
            scheduled_str = result.datetime.isoformat()
            ops.update_draft(conn, draft_id, status="scheduled", scheduled_time=scheduled_str)
            typer.echo(f"Draft {draft_id} scheduled for {scheduled_str}.")

        ops.emit_data_event(conn, "draft", "scheduled", draft_id, draft.project_id)
    finally:
        conn.close()


@app.command()
def cancel(
    ctx: typer.Context,
    draft_id: str = typer.Argument(..., help="Draft ID to cancel"),
):
    """Cancel a draft."""
    from social_hook.db import operations as ops

    conn = _get_conn()
    try:
        draft = _get_draft_or_exit(conn, draft_id)
        if draft.status in TERMINAL_STATUSES:
            typer.echo(f"Cannot cancel: draft status is '{draft.status}'")
            raise typer.Exit(1)
        ops.update_draft(conn, draft_id, status="cancelled")
        ops.emit_data_event(conn, "draft", "cancelled", draft_id, draft.project_id)
        typer.echo(f"Draft {draft_id} cancelled.")
    finally:
        conn.close()


@app.command()
def retry(
    ctx: typer.Context,
    draft_id: str = typer.Argument(..., help="Draft ID to retry"),
):
    """Retry a failed draft."""
    from social_hook.db import operations as ops

    conn = _get_conn()
    try:
        draft = _get_draft_or_exit(conn, draft_id)
        if draft.status != "failed":
            typer.echo(f"Cannot retry: draft status is '{draft.status}' (must be 'failed')")
            raise typer.Exit(1)
        ops.update_draft(conn, draft_id, status="scheduled", retry_count=0)
        ops.emit_data_event(conn, "draft", "retried", draft_id, draft.project_id)
        typer.echo(f"Draft {draft_id} retried.")
    finally:
        conn.close()


@app.command()
def edit(
    ctx: typer.Context,
    draft_id: str = typer.Argument(..., help="Draft ID to edit"),
    content: str = typer.Option(..., "--content", "-c", help="New content"),
):
    """Edit draft content.

    Example: social-hook draft edit draft-abc123 --content "Updated post text here"
    """
    from social_hook.db import operations as ops
    from social_hook.filesystem import generate_id
    from social_hook.models import DraftChange

    conn = _get_conn()
    try:
        draft = _get_draft_or_exit(conn, draft_id)
        if not content.strip():
            typer.echo("Content cannot be empty.")
            raise typer.Exit(1)
        old_content = draft.content
        ops.update_draft(conn, draft_id, content=content)
        ops.insert_draft_change(
            conn,
            DraftChange(
                id=generate_id("change"),
                draft_id=draft_id,
                field="content",
                old_value=old_content,
                new_value=content,
                changed_by="human",
            ),
        )
        ops.emit_data_event(conn, "draft", "edited", draft_id, draft.project_id)
        typer.echo(f"Draft {draft_id} content updated.")
    finally:
        conn.close()


@app.command()
def redraft(
    ctx: typer.Context,
    draft_id: str = typer.Argument(..., help="Draft ID to redraft"),
    angle: str = typer.Option(..., "--angle", "-a", help="New angle or direction for the draft"),
):
    """Redraft content using the Expert agent with a new angle.

    Example: social-hook draft redraft draft-abc123 --angle "focus on the performance gains"
    """
    from social_hook.config.yaml import load_full_config
    from social_hook.db import operations as ops
    from social_hook.errors import ConfigError
    from social_hook.filesystem import generate_id
    from social_hook.llm.expert import Expert
    from social_hook.llm.factory import create_client
    from social_hook.models import DraftChange

    conn = _get_conn()
    try:
        draft = _get_draft_or_exit(conn, draft_id)
        if draft.status in TERMINAL_STATUSES:
            typer.echo(f"Cannot redraft: draft status is '{draft.status}'")
            raise typer.Exit(1)

        config_path = ctx.obj.get("config") if ctx.obj else None
        config = load_full_config(str(config_path) if config_path else None)

        try:
            client = create_client(config.models.drafter, config)
        except ConfigError as e:
            typer.echo(f"Cannot redraft: {e}")
            raise typer.Exit(1) from None

        summary = ops.get_project_summary(conn, draft.project_id)

        expert = Expert(client)
        result = expert.handle(
            draft=draft,
            user_message=angle,
            escalation_reason="angle_change",
            project_summary=summary,
            project_id=draft.project_id,
            db=conn,
        )

        if result.refined_content or result.refined_media_spec:
            if result.refined_content:
                old_content = draft.content
                ops.update_draft(conn, draft_id, content=result.refined_content)
                ops.insert_draft_change(
                    conn,
                    DraftChange(
                        id=generate_id("change"),
                        draft_id=draft_id,
                        field="content",
                        old_value=old_content[:200],
                        new_value=result.refined_content[:200],
                        changed_by="expert",
                    ),
                )

            if result.refined_media_spec:
                ops.update_draft(conn, draft_id, media_spec=result.refined_media_spec)
                ops.insert_draft_change(
                    conn,
                    DraftChange(
                        id=generate_id("change"),
                        draft_id=draft_id,
                        field="media_spec",
                        old_value=json_mod.dumps(draft.media_spec)[:200]
                        if draft.media_spec
                        else "null",
                        new_value=json_mod.dumps(result.refined_media_spec)[:200],
                        changed_by="expert",
                    ),
                )

            ops.emit_data_event(conn, "draft", "edited", draft_id, draft.project_id)
            typer.echo(f"Draft {draft_id} redrafted.")
            if result.refined_content:
                typer.echo(f"\n{result.refined_content[:500]}")
            if result.refined_media_spec:
                typer.echo("Media spec updated. Run `social-hook draft media-regen` to regenerate.")
        else:
            typer.echo(f"Expert could not refine: {result.reasoning}")
            raise typer.Exit(1)
    finally:
        conn.close()


@app.command("quick-approve")
def quick_approve(
    ctx: typer.Context,
    draft_id: str = typer.Argument(..., help="Draft ID to approve and schedule"),
):
    """Approve and schedule at optimal time in one step."""
    from social_hook.config.yaml import load_full_config
    from social_hook.db import operations as ops
    from social_hook.scheduling import calculate_optimal_time

    conn = _get_conn()
    try:
        draft = _get_draft_or_exit(conn, draft_id)
        if draft.platform == "preview":
            typer.echo(
                "Preview drafts cannot be posted. Use 'social-hook draft promote "
                "<id> --platform <name>' to create a platform-specific draft."
            )
            raise typer.Exit(1)
        if draft.status not in ("draft", "approved", "deferred"):
            typer.echo(f"Cannot quick-approve: draft status is '{draft.status}'")
            raise typer.Exit(1)

        config_path = ctx.obj.get("config") if ctx.obj else None
        config = load_full_config(str(config_path) if config_path else None)
        result = calculate_optimal_time(
            conn,
            draft.project_id,
            platform=draft.platform,
            tz=config.scheduling.timezone if config else "UTC",
            max_posts_per_day=config.scheduling.max_posts_per_day if config else 3,
            min_gap_minutes=config.scheduling.min_gap_minutes if config else 30,
            optimal_days=config.scheduling.optimal_days if config else None,
            optimal_hours=config.scheduling.optimal_hours if config else None,
        )
        scheduled_str = result.datetime.isoformat()
        ops.update_draft(conn, draft_id, status="scheduled", scheduled_time=scheduled_str)
        ops.emit_data_event(conn, "draft", "approved", draft_id, draft.project_id)
        typer.echo(f"Draft {draft_id} approved and scheduled for {scheduled_str}.")
    finally:
        conn.close()


@app.command("media-regen")
def media_regen(
    ctx: typer.Context,
    draft_id: str = typer.Argument(..., help="Draft ID to regenerate media for"),
):
    """Regenerate media for a draft using its stored media spec.

    Example: social-hook draft media-regen draft-abc123
    """
    from social_hook.adapters.registry import get_media_adapter
    from social_hook.config.yaml import load_full_config
    from social_hook.db import operations as ops
    from social_hook.filesystem import generate_id, get_base_path
    from social_hook.models import DraftChange

    conn = _get_conn()
    try:
        draft = _get_draft_or_exit(conn, draft_id)
        if draft.media_spec and draft.media_spec == draft.media_spec_used:
            typer.echo("Media spec unchanged — edit the spec first (social-hook draft media-edit).")
            raise typer.Exit(1)
        if not draft.media_type or not draft.media_spec:
            typer.echo("No media spec available for regeneration.")
            raise typer.Exit(1)

        config_path = ctx.obj.get("config") if ctx.obj else None
        config = load_full_config(str(config_path) if config_path else None)

        api_key = None
        if draft.media_type == "nano_banana_pro":
            api_key = config.env.get("GEMINI_API_KEY") if config else None
            if not api_key:
                typer.echo("Cannot regenerate: GEMINI_API_KEY not configured.")
                raise typer.Exit(1)

        media_adapter = get_media_adapter(draft.media_type, api_key=api_key)
        if not media_adapter:
            typer.echo(f"Media adapter '{draft.media_type}' not available.")
            raise typer.Exit(1)

        output_dir = str(get_base_path() / "media-cache" / draft_id)
        result = media_adapter.generate(spec=draft.media_spec, output_dir=output_dir)

        if result.success and result.file_path:
            old_paths = draft.media_paths
            ops.update_draft(
                conn, draft_id, media_paths=[result.file_path], media_spec_used=draft.media_spec
            )
            ops.insert_draft_change(
                conn,
                DraftChange(
                    id=generate_id("change"),
                    draft_id=draft_id,
                    field="media_paths",
                    old_value=json_mod.dumps(old_paths),
                    new_value=json_mod.dumps([result.file_path]),
                    changed_by="human",
                ),
            )
            ops.emit_data_event(conn, "draft", "media_regenerated", draft_id, draft.project_id)
            typer.echo(f"Media regenerated for draft {draft_id}.")
        else:
            typer.echo(f"Regeneration failed: {result.error}")
            raise typer.Exit(1)
    finally:
        conn.close()


@app.command("media-remove")
def media_remove(
    ctx: typer.Context,
    draft_id: str = typer.Argument(..., help="Draft ID to remove media from"),
):
    """Remove media from a draft.

    Example: social-hook draft media-remove draft-abc123
    """
    from social_hook.db import operations as ops
    from social_hook.filesystem import generate_id
    from social_hook.models import DraftChange

    conn = _get_conn()
    try:
        draft = _get_draft_or_exit(conn, draft_id)
        old_paths = draft.media_paths
        ops.update_draft(conn, draft_id, media_paths=[])
        ops.insert_draft_change(
            conn,
            DraftChange(
                id=generate_id("change"),
                draft_id=draft_id,
                field="media_paths",
                old_value=json_mod.dumps(old_paths),
                new_value="[]",
                changed_by="human",
            ),
        )
        ops.emit_data_event(conn, "draft", "media_removed", draft_id, draft.project_id)
        typer.echo(f"Media removed from draft {draft_id}.")
    finally:
        conn.close()


@app.command("media-edit")
def media_edit(
    ctx: typer.Context,
    draft_id: str = typer.Argument(..., help="Draft ID to edit media spec for"),
    spec: str = typer.Option(..., "--spec", "-s", help="New media spec as JSON string"),
):
    """Edit the media spec for a draft.

    Example: social-hook draft media-edit draft-abc123 --spec '{"code": "print(42)", "language": "python"}'
    """
    from social_hook.db import operations as ops
    from social_hook.filesystem import generate_id
    from social_hook.models import DraftChange

    conn = _get_conn()
    try:
        draft = _get_draft_or_exit(conn, draft_id)

        try:
            parsed_spec = json_mod.loads(spec)
        except json_mod.JSONDecodeError as e:
            typer.echo(f"Invalid JSON: {e}")
            raise typer.Exit(1) from None

        old_spec = draft.media_spec
        ops.update_draft(conn, draft_id, media_spec=parsed_spec)
        ops.insert_draft_change(
            conn,
            DraftChange(
                id=generate_id("change"),
                draft_id=draft_id,
                field="media_spec",
                old_value=json_mod.dumps(old_spec)[:200] if old_spec else "null",
                new_value=json_mod.dumps(parsed_spec)[:200],
                changed_by="human",
            ),
        )
        ops.emit_data_event(conn, "draft", "edited", draft_id, draft.project_id)
        typer.echo(f"Draft {draft_id} media spec updated.")
    finally:
        conn.close()


@app.command("list")
def list_cmd(
    ctx: typer.Context,
    status: str | None = typer.Option(None, "--status", "-s", help="Filter by status"),
    project: str | None = typer.Option(None, "--project", "-p", help="Filter by project ID"),
    decision: str | None = typer.Option(None, "--decision", "-d", help="Filter by decision ID"),
    commit: str | None = typer.Option(None, "--commit", "-c", help="Filter by commit hash"),
    pending: bool = typer.Option(
        False, "--pending", help="Show only actionable drafts (draft/approved/scheduled)"
    ),
):
    """List drafts with optional filters.

    Example: social-hook draft list --pending --json
    Example: social-hook draft list --decision decision-abc123
    Example: social-hook draft list --commit 47a5191
    """
    from social_hook.db import operations as ops

    conn = _get_conn()
    try:
        drafts = ops.get_drafts_filtered(
            conn,
            status=status,
            project_id=project,
            decision_id=decision,
            commit_hash=commit,
        )
        if pending:
            drafts = [
                d for d in drafts if d.status in ("draft", "approved", "scheduled", "deferred")
            ]
        json_output = ctx.obj.get("json", False) if ctx.obj else False

        if json_output:
            typer.echo(json_mod.dumps([d.to_dict() for d in drafts], indent=2, default=str))
            return

        if not drafts:
            typer.echo("No drafts found.")
            return

        typer.echo(
            f"{'ID':<16} {'Status':<12} {'Platform':<10} {'Fmt':<8} {'Media':<7} {'Content'}"
        )
        typer.echo("-" * 87)
        for d in drafts:
            content_preview = d.content[:40].replace("\n", " ") if d.content else ""
            intro = " [INTRO]" if getattr(d, "is_intro", False) else ""
            fmt = d.post_format or "single"
            media = d.media_type[:5] if d.media_type else "-"
            typer.echo(
                f"{d.id[:14]:<16} {d.status:<12} {d.platform:<10} {fmt:<8} {media:<7} {content_preview}{intro}"
            )
    finally:
        conn.close()


@app.command("show")
def show(
    ctx: typer.Context,
    draft_id: str = typer.Argument(..., help="Draft ID to show"),
    open_media: bool = typer.Option(False, "--open", help="Open media files in default viewer"),
):
    """Show full detail for a draft including media spec and change history.

    Example: social-hook draft show draft-abc123
    """
    from social_hook.db import operations as ops

    conn = _get_conn()
    try:
        draft = _get_draft_or_exit(conn, draft_id)
        changes = ops.get_draft_changes(conn, draft_id)
        tweets = ops.get_draft_tweets(conn, draft_id)

        json_output = ctx.obj.get("json", False) if ctx.obj else False

        if json_output:
            data = draft.to_dict()
            data["changes"] = [c.to_dict() for c in changes]
            data["tweets"] = [t.to_dict() for t in tweets]
            typer.echo(json_mod.dumps(data, indent=2, default=str))
            return

        typer.echo(f"ID:         {draft.id}")
        typer.echo(f"Project:    {draft.project_id}")
        typer.echo(f"Decision:   {draft.decision_id}")
        typer.echo(f"Platform:   {draft.platform}")
        typer.echo(f"Status:     {draft.status}")
        typer.echo(f"Created:    {draft.created_at}")
        typer.echo(f"Updated:    {draft.updated_at}")
        if draft.scheduled_time:
            typer.echo(f"Scheduled:  {draft.scheduled_time}")
        if draft.media_type:
            typer.echo(f"Media type: {draft.media_type}")
        if draft.media_paths:
            typer.echo(f"Media:      {', '.join(draft.media_paths)}")
            for mp in draft.media_paths:
                url = _media_url(mp)
                if url:
                    typer.echo(f"  View:     {url}")
            if open_media:
                import platform as plat
                import subprocess

                for mp in draft.media_paths:
                    if Path(mp).exists():
                        cmd = "open" if plat.system() == "Darwin" else "xdg-open"
                        subprocess.Popen(
                            [cmd, mp], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                        )
        if draft.media_spec:
            typer.echo(f"Media spec: {json_mod.dumps(draft.media_spec, indent=2)}")
        if draft.last_error:
            typer.echo(f"Error:      {draft.last_error}")
        typer.echo(f"\nContent:\n{draft.content}")

        if tweets:
            typer.echo(f"\nThread ({len(tweets)} tweets):")
            for t in tweets:
                typer.echo(f"  [{t.position}] {t.content[:80]}")

        if changes:
            typer.echo(f"\nChanges ({len(changes)}):")
            for c in changes:
                typer.echo(f"  {c.changed_at} [{c.changed_by}] {c.field}")
    finally:
        conn.close()


@app.command()
def promote(
    ctx: typer.Context,
    draft_id: str = typer.Argument(..., help="Preview draft ID to promote"),
    platform: str = typer.Option(
        ..., "--platform", "-p", help="Target platform (e.g., x, linkedin)"
    ),
    json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Promote a preview draft to a real platform.

    Creates a new draft for the target platform using the LLM drafter,
    then marks the preview draft as superseded.

    Example: social-hook draft promote draft-abc123 --platform x
    """
    from social_hook.compat import evaluation_from_decision
    from social_hook.config.project import ProjectConfig, load_project_config
    from social_hook.config.yaml import load_full_config
    from social_hook.db import operations as ops
    from social_hook.drafting import draft_for_platforms
    from social_hook.errors import ConfigError
    from social_hook.llm.dry_run import DryRunContext
    from social_hook.llm.prompts import assemble_evaluator_context
    from social_hook.models import CommitInfo

    use_json = json or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        draft = _get_draft_or_exit(conn, draft_id)
        if draft.platform != "preview":
            typer.echo(f"Draft is not a preview draft (platform: {draft.platform}).")
            raise typer.Exit(1)
        if draft.status in TERMINAL_STATUSES:
            typer.echo(f"Cannot promote: draft status is '{draft.status}'")
            raise typer.Exit(1)

        config_path = ctx.obj.get("config") if ctx.obj else None
        config = load_full_config(str(config_path) if config_path else None)

        pcfg = config.platforms.get(platform)
        if not pcfg or not pcfg.enabled:
            typer.echo(f"Platform '{platform}' is not enabled.")
            raise typer.Exit(1)

        decision = ops.get_decision(conn, draft.decision_id)
        if not decision:
            typer.echo(f"Decision not found: {draft.decision_id}")
            raise typer.Exit(1)

        project = ops.get_project(conn, decision.project_id)
        if not project:
            typer.echo(f"Project not found: {decision.project_id}")
            raise typer.Exit(1)

        try:
            project_config = load_project_config(project.repo_path)
        except ConfigError:
            project_config = ProjectConfig(repo_path=project.repo_path)

        from social_hook.trigger import parse_commit_info

        try:
            commit = parse_commit_info(decision.commit_hash, project.repo_path)
        except Exception:
            commit = CommitInfo(
                hash=decision.commit_hash,
                message=decision.commit_message or "",
                diff="",
                files_changed=[],
            )

        dry_run = ctx.obj.get("dry_run", False) if ctx.obj else False
        db = DryRunContext(conn, dry_run=dry_run)

        context = assemble_evaluator_context(
            db,
            project.id,
            project_config,
            commit_timestamp=getattr(commit, "timestamp", None),
            parent_timestamp=getattr(commit, "parent_timestamp", None),
        )

        evaluation = evaluation_from_decision(decision, "draft")

        results = draft_for_platforms(
            config,
            conn,
            db,
            project,
            decision_id=decision.id,
            evaluation=evaluation,
            context=context,
            commit=commit,
            project_config=project_config,
            target_platform_names=[platform],
            skip_content_filter=True,
        )

        if not results:
            typer.echo("No draft created.")
            raise typer.Exit(1)

        new_draft = results[0].draft
        ops.supersede_draft(conn, draft_id, new_draft.id)
        ops.emit_data_event(conn, "draft", "updated", draft_id, draft.project_id)

        if use_json:
            typer.echo(
                json_mod.dumps(
                    {
                        "old_draft_id": draft_id,
                        "new_draft_id": new_draft.id,
                        "platform": new_draft.platform,
                        "status": "promoted",
                    },
                    indent=2,
                )
            )
        else:
            typer.echo(f"Preview draft {draft_id} promoted to {platform}.")
            typer.echo(f"New draft: {new_draft.id}")
            typer.echo(f"Content: {new_draft.content[:200]}...")
    finally:
        conn.close()


@app.command(name="post-now")
def post_now(
    ctx: typer.Context,
    draft_id: str = typer.Argument(..., help="Draft ID to post immediately"),
    json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Post a draft immediately to its platform.

    Approves and posts the draft in one step, bypassing the scheduler queue.
    The draft must be in draft, approved, or deferred status.

    Example: social-hook draft post-now draft-abc123
    """
    from social_hook.config.yaml import load_full_config
    from social_hook.db import operations as ops
    from social_hook.scheduler import _handle_post_failure, _post_draft, record_post_success

    use_json = json or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        draft = _get_draft_or_exit(conn, draft_id)

        if draft.platform == "preview":
            typer.echo(
                "Preview drafts cannot be posted. Use 'social-hook draft promote "
                "<id> --platform <name>' to create a platform-specific draft."
            )
            raise typer.Exit(1)

        if draft.status not in ("draft", "approved", "deferred"):
            typer.echo(f"Cannot post: draft status is '{draft.status}'")
            raise typer.Exit(1)

        config_path = ctx.obj.get("config") if ctx.obj else None
        config = load_full_config(str(config_path) if config_path else None)
        dry_run = ctx.obj.get("dry_run", False) if ctx.obj else False

        project = ops.get_project(conn, draft.project_id)
        project_name = project.name if project else "Unknown"

        # Mark as scheduled so the posting pipeline sees it correctly
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        ops.update_draft(conn, draft_id, status="scheduled", scheduled_time=now)

        if dry_run:
            from social_hook.adapters.dry_run import dry_run_post_result

            result = dry_run_post_result()
        else:
            result = _post_draft(conn, draft, config)

        if result.success:
            post = record_post_success(conn, draft, result, config, project_name, dry_run=dry_run)
            if use_json:
                typer.echo(
                    json_mod.dumps(
                        {
                            "draft_id": draft_id,
                            "post_id": post.id,
                            "status": "posted",
                            "external_url": result.external_url,
                        },
                        indent=2,
                        default=str,
                    )
                )
            else:
                typer.echo(f"Draft {draft_id} posted successfully!")
                if result.external_url:
                    typer.echo(f"URL: {result.external_url}")
        else:
            _handle_post_failure(conn, draft, result.error or "Unknown error", config, dry_run)
            typer.echo(f"Post failed: {result.error}")
            raise typer.Exit(1)
    finally:
        conn.close()
