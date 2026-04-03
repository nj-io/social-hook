"""CLI commands for draft lifecycle management."""

import json as json_mod
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import typer

from social_hook.models.enums import PENDING_STATUSES, TERMINAL_STATUSES

app = typer.Typer(no_args_is_help=True)


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


def _resync_thread_tweets(conn, draft_id: str, new_content: str) -> None:
    """Re-split content into draft_tweets if the draft has an existing thread."""
    from social_hook.db import operations as ops
    from social_hook.drafting import _parse_thread_tweets
    from social_hook.filesystem import generate_id
    from social_hook.models.core import DraftTweet

    existing = ops.get_draft_tweets(conn, draft_id)
    if not existing:
        return

    parts = _parse_thread_tweets(new_content, thread_min=1)
    new_tweets = [
        DraftTweet(
            id=generate_id("tweet"),
            draft_id=draft_id,
            position=i,
            content=part,
        )
        for i, part in enumerate(parts)
    ]
    ops.replace_draft_tweets(conn, draft_id, new_tweets)


@app.command()
def approve(
    ctx: typer.Context,
    draft_id: str = typer.Argument(..., help="Draft ID to approve"),
):
    """Mark a draft as approved for posting.

    The scheduler will post it when its scheduled time arrives.
    Preview drafts must be promoted to a platform first.

    Example: social-hook draft approve draft_abc123
    """
    from social_hook.db import operations as ops

    conn = _get_conn()
    try:
        draft = _get_draft_or_exit(conn, draft_id)
        if draft.preview_mode:
            typer.echo(
                "No account connected. Run 'social-hook account add' to connect and enable posting."
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
    """Reject a draft and optionally record feedback as voice memory.

    When --reason is provided, the feedback is saved to voice memory so the
    drafter learns from it in future runs. If the draft is an intro draft,
    rejection cascades to re-draft the introduction for that platform.

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
    """Schedule a draft for posting at a specific or optimal time.

    With --time, posts at that exact ISO datetime. Without --time,
    automatically picks the next optimal slot based on your configured
    posting limits, time windows, and minimum gap between posts.

    Example: social-hook draft schedule draft_abc123
    Example: social-hook draft schedule draft_abc123 --time 2026-03-25T10:00:00
    """
    from social_hook.db import operations as ops

    conn = _get_conn()
    try:
        draft = _get_draft_or_exit(conn, draft_id)
        if draft.preview_mode:
            typer.echo(
                "No account connected. Run 'social-hook account add' to connect and enable posting."
            )
            raise typer.Exit(1)
        if draft.status not in PENDING_STATUSES:
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
    """Cancel a pending draft, removing it from the posting queue.

    Example: social-hook draft cancel draft_abc123
    """
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
def reopen(
    ctx: typer.Context,
    draft_id: str = typer.Argument(..., help="Draft ID to reopen"),
):
    """Reopen a cancelled or rejected draft, returning it to 'draft' status.

    Intro drafts cannot be reopened -- create a new draft instead.
    Clears any previous error message on the draft.

    Example: social-hook draft reopen draft-abc123
    """
    from social_hook.db import operations as ops

    conn = _get_conn()
    try:
        draft = _get_draft_or_exit(conn, draft_id)
        if draft.status not in ("cancelled", "rejected"):
            typer.echo(
                f"Cannot reopen: draft status is '{draft.status}' (must be 'cancelled' or 'rejected')"
            )
            raise typer.Exit(1)
        if getattr(draft, "is_intro", False):
            typer.echo("Intro drafts cannot be reopened — create a new draft instead.")
            raise typer.Exit(1)
        ops.update_draft(conn, draft_id, status="draft", last_error="")
        ops.emit_data_event(conn, "draft", "reopened", draft_id, draft.project_id)
        typer.echo(f"Draft {draft_id} reopened.")
    finally:
        conn.close()


@app.command()
def unapprove(
    ctx: typer.Context,
    draft_id: str = typer.Argument(..., help="Draft ID to unapprove"),
):
    """Revert approval on a draft, returning it to 'draft' status.

    Use when you approved a draft prematurely and want to make further
    edits before scheduling or posting.

    Example: social-hook draft unapprove draft-abc123
    """
    from social_hook.db import operations as ops

    conn = _get_conn()
    try:
        draft = _get_draft_or_exit(conn, draft_id)
        if draft.status != "approved":
            typer.echo(f"Cannot unapprove: draft status is '{draft.status}' (must be 'approved')")
            raise typer.Exit(1)
        ops.update_draft(conn, draft_id, status="draft")
        ops.emit_data_event(conn, "draft", "unapproved", draft_id, draft.project_id)
        typer.echo(f"Draft {draft_id} unapproved.")
    finally:
        conn.close()


@app.command()
def unschedule(
    ctx: typer.Context,
    draft_id: str = typer.Argument(..., help="Draft ID to unschedule"),
):
    """Revert scheduling on a draft, returning it to 'draft' status.

    Clears the scheduled time. Use when you need to edit or reschedule
    a draft that was already queued for posting.

    Example: social-hook draft unschedule draft-abc123
    """
    from social_hook.db import operations as ops

    conn = _get_conn()
    try:
        draft = _get_draft_or_exit(conn, draft_id)
        if draft.status != "scheduled":
            typer.echo(f"Cannot unschedule: draft status is '{draft.status}' (must be 'scheduled')")
            raise typer.Exit(1)
        ops.update_draft(conn, draft_id, status="draft", scheduled_time="")
        ops.emit_data_event(conn, "draft", "unscheduled", draft_id, draft.project_id)
        typer.echo(f"Draft {draft_id} unscheduled.")
    finally:
        conn.close()


@app.command()
def retry(
    ctx: typer.Context,
    draft_id: str = typer.Argument(..., help="Draft ID to retry"),
):
    """Re-queue a failed draft for another posting attempt.

    Resets the retry counter and sets status back to scheduled so
    the scheduler will try posting it again.

    Example: social-hook draft retry draft_abc123
    """
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

    Records the change in the draft's change history (visible in draft show).
    If the draft is a thread, tweet boundaries are automatically re-split.

    Example: social-hook draft edit draft-abc123 --content "Updated post text here"
    """
    from social_hook.db import operations as ops
    from social_hook.filesystem import generate_id
    from social_hook.models.core import DraftChange

    conn = _get_conn()
    try:
        draft = _get_draft_or_exit(conn, draft_id)
        if not content.strip():
            typer.echo("Content cannot be empty.")
            raise typer.Exit(1)
        old_content = draft.content
        ops.update_draft(conn, draft_id, content=content)
        _resync_thread_tweets(conn, draft_id, content)
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

    Calls the Expert LLM agent to rewrite the draft with a different
    direction. May also update the media spec. Changes are recorded
    in the draft's change history.

    Example: social-hook draft redraft draft-abc123 --angle "focus on the performance gains"
    """
    from social_hook.config.yaml import load_full_config
    from social_hook.db import operations as ops
    from social_hook.errors import ConfigError
    from social_hook.filesystem import generate_id
    from social_hook.llm.expert import Expert
    from social_hook.llm.factory import create_client
    from social_hook.models.core import DraftChange

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

        from social_hook.cli._spinner import spinner

        # Load social context and identity for voice consistency
        social_context = None
        identity = None
        project = ops.get_project(conn, draft.project_id)
        if project and project.repo_path:
            try:
                from social_hook.config.project import load_project_config

                pc = load_project_config(project.repo_path)
                social_context = pc.social_context
            except Exception:
                pass
        try:
            from social_hook.config.yaml import resolve_identity

            identity = resolve_identity(config, draft.platform)
        except Exception:
            pass

        expert = Expert(client)
        with spinner("Redrafting with new angle..."):
            result = expert.handle(
                draft=draft,
                user_message=angle,
                escalation_reason="angle_change",
                project_summary=summary,
                project_id=draft.project_id,
                db=conn,
                social_context=social_context,
                identity=identity,
            )

        if result.refined_content or result.refined_media_spec:
            if result.refined_content:
                old_content = draft.content
                ops.update_draft(conn, draft_id, content=result.refined_content)
                _resync_thread_tweets(conn, draft_id, result.refined_content)
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


@app.command("post-now")
def post_now(
    ctx: typer.Context,
    draft_id: str = typer.Argument(..., help="Draft ID to post immediately"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Post a draft immediately to its platform.

    Requires platform credentials in ~/.social-hook/.env.

    Example: social-hook draft post-now draft_abc123
    Example: social-hook draft post-now draft_abc123 --yes  (skip confirmation)
    """
    from social_hook.db import operations as ops

    # Merge with global --json flag
    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)
    dry_run = ctx.obj.get("dry_run", False) if ctx.obj else False

    conn = _get_conn()
    try:
        draft = _get_draft_or_exit(conn, draft_id)

        if draft.status in TERMINAL_STATUSES:
            msg = f"Cannot post: draft status is '{draft.status}'"
            if json_output:
                typer.echo(json_mod.dumps({"error": msg, "draft_id": draft_id}))
            else:
                typer.echo(msg)
            raise typer.Exit(1)

        if draft.preview_mode:
            msg = (
                "No account connected. Run 'social-hook account add' to connect and enable posting."
            )
            if json_output:
                typer.echo(json_mod.dumps({"error": msg, "draft_id": draft_id}))
            else:
                typer.echo(msg)
            raise typer.Exit(1)

        if dry_run:
            if json_output:
                typer.echo(
                    json_mod.dumps(
                        {"status": "dry_run", "draft_id": draft_id, "platform": draft.platform}
                    )
                )
            else:
                typer.echo(f"Dry run: would post draft {draft_id} to {draft.platform}")
            return

        if not yes:
            confirm = typer.confirm(f"Post draft {draft_id} to {draft.platform} now?")
            if not confirm:
                raise typer.Exit(0)

        from datetime import datetime as dt_cls
        from datetime import timezone

        now_str = dt_cls.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        ops.update_draft(conn, draft_id, status="scheduled", scheduled_time=now_str)
        ops.emit_data_event(conn, "draft", "updated", draft_id, draft.project_id)
    finally:
        conn.close()

    from social_hook.scheduler import scheduler_tick

    scheduler_tick(draft_id=draft_id, dry_run=False)

    conn = _get_conn()
    try:
        draft_after = ops.get_draft(conn, draft_id)
        if draft_after and draft_after.status == "posted":
            post = conn.execute(
                "SELECT external_id, external_url FROM posts WHERE draft_id = ? ORDER BY posted_at DESC LIMIT 1",
                (draft_id,),
            ).fetchone()

            if json_output:
                typer.echo(
                    json_mod.dumps(
                        {
                            "status": "posted",
                            "draft_id": draft_id,
                            "platform": draft_after.platform,
                            "external_id": post[0] if post else None,
                            "external_url": post[1] if post else None,
                        }
                    )
                )
            else:
                typer.echo(f"Posted draft {draft_id} to {draft_after.platform}.")
                if post and post[1]:
                    typer.echo(f"URL: {post[1]}")
        else:
            status = draft_after.status if draft_after else "unknown"
            error = draft_after.last_error if draft_after else None
            msg = f"Post failed: draft status is '{status}'"
            if error:
                msg += f" ({error})"
            if json_output:
                typer.echo(json_mod.dumps({"error": msg, "draft_id": draft_id}))
            else:
                typer.echo(msg)
            raise typer.Exit(2)
    finally:
        conn.close()


@app.command("quick-approve")
def quick_approve(
    ctx: typer.Context,
    draft_id: str = typer.Argument(..., help="Draft ID to approve and schedule"),
):
    """Approve and schedule a draft for the next optimal posting time in one step.

    Combines approve + schedule. Considers your configured posting limits,
    preferred time windows, and minimum gap between posts to pick the best slot.

    Example: social-hook draft quick-approve draft_abc123
    """
    from social_hook.config.yaml import load_full_config
    from social_hook.db import operations as ops
    from social_hook.scheduling import calculate_optimal_time

    conn = _get_conn()
    try:
        draft = _get_draft_or_exit(conn, draft_id)
        if draft.preview_mode:
            typer.echo(
                "No account connected. Run 'social-hook account add' to connect and enable posting."
            )
            raise typer.Exit(1)
        # Scheduled drafts go through the scheduler; use unschedule first
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

    The media spec is a JSON object describing what to generate (e.g., code
    snippet image, diagram). Edit the spec first with media-edit, then run
    this command to produce a new file from the updated spec.

    Example: social-hook draft media-regen draft-abc123
    """
    from social_hook.adapters.registry import get_media_adapter
    from social_hook.config.yaml import load_full_config
    from social_hook.db import operations as ops
    from social_hook.filesystem import generate_id, get_base_path
    from social_hook.models.core import DraftChange

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

        from social_hook.cli._spinner import spinner

        output_dir = str(get_base_path() / "media-cache" / draft_id)
        with spinner("Generating media..."):
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
    from social_hook.models.core import DraftChange

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

    The media spec is a JSON object that controls media generation (e.g.,
    code snippet, language, theme). After editing, run media-regen to
    produce a new media file from the updated spec.

    Example: social-hook draft media-edit draft-abc123 --spec '{"code": "print(42)", "language": "python"}'
    """
    from social_hook.db import operations as ops
    from social_hook.filesystem import generate_id
    from social_hook.models.core import DraftChange

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
    project: str | None = typer.Option(None, "--project", "-i", help="Filter by project ID"),
    decision: str | None = typer.Option(None, "--decision", "-d", help="Filter by decision ID"),
    commit: str | None = typer.Option(None, "--commit", "-c", help="Filter by commit hash"),
    tag: str | None = typer.Option(
        None, "--tag", "-t", help="Filter by episode tag (matches decision episode_tags)"
    ),
    pending: bool = typer.Option(
        False, "--pending", help="Show only actionable drafts (draft/approved/scheduled)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List drafts with optional filters.

    Example: social-hook draft list --pending --json
    Example: social-hook draft list --decision decision-abc123
    Example: social-hook draft list --commit 47a5191
    Example: social-hook draft list --tag auth
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
            tag=tag,
        )
        if pending:
            drafts = [d for d in drafts if d.status in PENDING_STATUSES]
        json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

        if json_output:
            typer.echo(json_mod.dumps([d.to_dict() for d in drafts], indent=2, default=str))
            return

        if not drafts:
            typer.echo("No drafts found.")
            return

        typer.echo(
            f"{'ID':<16} {'Status':<12} {'Platform':<10} {'Fmt':<8} {'Media':<7} {'Tags':<20} {'Content'}"
        )
        typer.echo("-" * 107)
        for d in drafts:
            content_preview = d.content[:35].replace("\n", " ") if d.content else ""
            intro = "[INTRO]" if getattr(d, "is_intro", False) else ""
            fmt = d.post_format or "single"
            media = d.media_type[:5] if d.media_type else "-"

            # Build tags from linked decision
            tags = []
            if intro:
                tags.append(intro)
            try:
                dec = ops.get_decision(conn, d.decision_id)
                if dec:
                    if dec.post_category:
                        tags.append(f"[{dec.post_category}]")
                    if dec.episode_tags:
                        for t in dec.episode_tags:
                            tags.append(f"[{t}]")
            except Exception:
                pass
            tag_str = " ".join(tags)[:18] if tags else "-"

            typer.echo(
                f"{d.id[:14]:<16} {d.status:<12} {d.platform:<10} {fmt:<8} {media:<7} {tag_str:<20} {content_preview}"
            )
    finally:
        conn.close()


@app.command("show")
def show(
    ctx: typer.Context,
    draft_id: str = typer.Argument(..., help="Draft ID to show"),
    open_media: bool = typer.Option(False, "--open", help="Open media files in default viewer"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
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

        json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

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
    from social_hook.models.core import CommitInfo

    use_json = json or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        draft = _get_draft_or_exit(conn, draft_id)
        if not draft.preview_mode:
            typer.echo(f"Draft is not in preview mode (platform: {draft.platform}).")
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

        from social_hook.cli._spinner import spinner

        with spinner(f"Redrafting for {platform}..."):
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
            typer.echo(f"Content: {new_draft.content}")
    finally:
        conn.close()


@app.command()
def connect(
    ctx: typer.Context,
    draft_id: str = typer.Argument(..., help="Preview-mode draft ID to connect"),
    account: str = typer.Option(
        ..., "--account", "-a", help="Account name to connect (must match draft platform)"
    ),
    json: bool = typer.Option(False, "--json", help="Output as JSON"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Connect a preview-mode draft to an account.

    Links the draft's target to an existing OAuth account, clearing preview mode.
    The account's platform must match the draft's platform.

    Example: social-hook draft connect draft-abc123 --account my-x-account
    Example: social-hook draft connect draft-abc123 --account my-x-account --yes  (skip confirmation)
    """
    from social_hook.config.yaml import load_full_config, save_config
    from social_hook.db import operations as ops

    use_json = json or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        draft = _get_draft_or_exit(conn, draft_id)
        if not draft.preview_mode:
            msg = f"Draft is not in preview mode (platform: {draft.platform})."
            if use_json:
                typer.echo(json_mod.dumps({"error": msg, "draft_id": draft_id}))
            else:
                typer.echo(msg)
            raise typer.Exit(1)
        if draft.status in TERMINAL_STATUSES:
            msg = f"Cannot connect: draft status is '{draft.status}'"
            if use_json:
                typer.echo(json_mod.dumps({"error": msg, "draft_id": draft_id}))
            else:
                typer.echo(msg)
            raise typer.Exit(1)

        config_path = ctx.obj.get("config") if ctx.obj else None
        config = load_full_config(str(config_path) if config_path else None)

        acct = config.accounts.get(account)
        if not acct:
            msg = f"Account '{account}' not found."
            if use_json:
                typer.echo(json_mod.dumps({"error": msg}))
            else:
                typer.echo(msg)
            raise typer.Exit(1)

        if acct.platform != draft.platform:
            msg = (
                f"Account platform '{acct.platform}' does not match "
                f"draft platform '{draft.platform}'."
            )
            if use_json:
                typer.echo(json_mod.dumps({"error": msg}))
            else:
                typer.echo(msg)
            raise typer.Exit(1)

        if not yes:
            typer.confirm(
                f"Connect draft {draft_id[:12]} to account '{account}' ({acct.platform})?",
                abort=True,
            )

        # Clear preview_mode on the draft
        ops.clear_draft_preview_mode(conn, draft_id)

        # Persist target -> account link in config
        target_name = draft.target_id
        if target_name and target_name in config.targets:
            from social_hook.filesystem import get_config_path

            effective_path = str(config_path) if config_path else str(get_config_path())
            save_config(
                {"targets": {target_name: {"account": account}}},
                effective_path,
                deep_merge=True,
            )

        ops.emit_data_event(conn, "draft", "connected", draft_id, draft.project_id)

        if use_json:
            typer.echo(
                json_mod.dumps(
                    {
                        "draft_id": draft_id,
                        "account": account,
                        "platform": draft.platform,
                        "status": "connected",
                    },
                    indent=2,
                )
            )
        else:
            typer.echo(f"Draft {draft_id[:12]} connected to account '{account}'.")
            typer.echo("Preview mode cleared. Draft is now eligible for posting.")
    finally:
        conn.close()
