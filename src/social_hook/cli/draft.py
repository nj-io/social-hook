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

        from social_hook.vehicle import check_auto_postable, handle_advisory_approval

        if not check_auto_postable(draft):
            from social_hook.config.yaml import load_full_config

            config = load_full_config()
            handle_advisory_approval(conn, draft, config)
            typer.echo(f"Draft {draft_id} → advisory (requires manual posting).")
            return

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
        if draft.status in TERMINAL_STATUSES:
            typer.echo(f"Cannot schedule: draft status is '{draft.status}'")
            raise typer.Exit(1)

        from social_hook.vehicle import check_auto_postable, handle_advisory_approval

        if not check_auto_postable(draft):
            from social_hook.config.yaml import load_full_config

            config = load_full_config()
            handle_advisory_approval(conn, draft, config, scheduled_time=time)
            typer.echo(f"Draft {draft_id} → advisory (requires manual posting).")
            return

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

        from social_hook.vehicle import rematerialize_draft_parts

        rematerialize_draft_parts(conn, draft, content)
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

                from social_hook.vehicle import rematerialize_draft_parts

                rematerialize_draft_parts(conn, draft, result.refined_content)
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
                # Target the first media slot; create one if none exists.
                target_id: str | None = None
                if draft.media_specs and isinstance(draft.media_specs[0], dict):
                    target_id = draft.media_specs[0].get("id")
                if not target_id:
                    target_id = ops.append_draft_media(
                        conn,
                        draft_id,
                        {"tool": "nano_banana_pro", "spec": {}, "user_uploaded": False},
                    )
                if target_id:
                    d2 = ops.get_draft(conn, draft_id) or draft
                    current = next(
                        (
                            s
                            for s in (d2.media_specs or [])
                            if isinstance(s, dict) and s.get("id") == target_id
                        ),
                        {"id": target_id, "tool": "nano_banana_pro", "user_uploaded": False},
                    )
                    new_item = dict(current)
                    new_item["spec"] = result.refined_media_spec
                    ops.update_draft_media(conn, draft_id, target_id, spec=new_item)
                    ops.insert_draft_change(
                        conn,
                        DraftChange(
                            id=generate_id("change"),
                            draft_id=draft_id,
                            field=f"media_spec:{target_id}",
                            old_value="",
                            new_value=json_mod.dumps(result.refined_media_spec)[:200],
                            changed_by="expert",
                        ),
                    )

            ops.emit_data_event(conn, "draft", "edited", draft_id, draft.project_id)
            typer.echo(f"Draft {draft_id} redrafted.")
            if result.refined_content:
                typer.echo(f"\n{result.refined_content[:500]}")
            if result.refined_media_spec:
                typer.echo(
                    "Media spec updated. Run "
                    "`social-hook draft media regen --draft <id> --id <media_id>`."
                )
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

        from social_hook.vehicle import check_auto_postable, handle_advisory_approval

        if not check_auto_postable(draft):
            from social_hook.config.yaml import load_full_config

            config = load_full_config()
            handle_advisory_approval(conn, draft, config)
            if json_output:
                typer.echo(json_mod.dumps({"status": "advisory", "draft_id": draft_id}))
            else:
                typer.echo(f"Draft {draft_id} → advisory (requires manual posting).")
            return

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

        from social_hook.vehicle import check_auto_postable, handle_advisory_approval

        if not check_auto_postable(draft):
            handle_advisory_approval(conn, draft, config, scheduled_time=scheduled_str)
            typer.echo(f"Draft {draft_id} → advisory (due {scheduled_str}).")
            return

        ops.update_draft(conn, draft_id, status="scheduled", scheduled_time=scheduled_str)
        ops.emit_data_event(conn, "draft", "approved", draft_id, draft.project_id)
        typer.echo(f"Draft {draft_id} approved and scheduled for {scheduled_str}.")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Media subcommand group — `social-hook draft media {list,regen,edit,remove,add}`
# ID-only addressing (media_<12hex>); never accepts --index.
# ---------------------------------------------------------------------------


media_app = typer.Typer(
    name="media",
    no_args_is_help=True,
    help=(
        "Per-item media operations on a draft. All commands address items by "
        "stable media_id (media_<12hex>); --index is intentionally rejected. "
        "Every command supports --json and --project/-p."
    ),
)


def _merge_json_flag(ctx: typer.Context, json_output: bool) -> bool:
    """Allow `--json` before or after the subcommand via the global ctx.obj."""
    return json_output or (ctx.obj.get("json", False) if ctx.obj else False)


def _reject_index(index: int | None) -> None:
    """Force ID-only addressing. --index is reserved at the Typer level; this
    is a belt-and-braces check for programmatic callers / tests."""
    if index is not None:
        typer.echo(
            "--index is not supported. Use --id media_<12hex> — media items are "
            "addressed by stable id, not array position.",
            err=True,
        )
        raise typer.Exit(1)


def _find_draft_media_spec(draft, media_id: str) -> tuple[int, dict] | tuple[None, None]:
    """Return (index, spec) for the media_id on the draft, or (None, None)."""
    for i, spec in enumerate(draft.media_specs or []):
        if isinstance(spec, dict) and spec.get("id") == media_id:
            return i, spec
    return None, None


@media_app.command("list")
def media_list(
    ctx: typer.Context,
    draft_id: str = typer.Option(..., "--draft", help="Draft ID to list media for"),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    index: int | None = typer.Option(
        None, "--index", hidden=True, help="Rejected — addressing is by media_id."
    ),
):
    """List all media items on a draft with their ids, tools, paths, and errors.

    Example: social-hook draft media list --draft draft_abc123 --json
    """
    _reject_index(index)
    from social_hook.cli.utils import resolve_project
    from social_hook.db import operations as ops

    json_output = _merge_json_flag(ctx, json_output)
    conn = _get_conn()
    try:
        draft = _get_draft_or_exit(conn, draft_id)
        # Project scope check: --project resolves to a repo; if provided, the
        # draft's project must match. Non-match is user error (exit 1).
        if project_path:
            repo = resolve_project(project_path)
            proj = ops.get_project_by_path(conn, repo)
            if proj and proj.id != draft.project_id:
                typer.echo(f"Draft {draft_id} does not belong to project at {repo}.", err=True)
                raise typer.Exit(1)

        specs = draft.media_specs or []
        paths = draft.media_paths or []
        errors = draft.media_errors or []
        used = draft.media_specs_used or []

        items: list[dict] = []
        for i, spec in enumerate(specs):
            items.append(
                {
                    "id": spec.get("id") if isinstance(spec, dict) else None,
                    "tool": spec.get("tool") if isinstance(spec, dict) else None,
                    "user_uploaded": bool(spec.get("user_uploaded"))
                    if isinstance(spec, dict)
                    else False,
                    "spec": spec.get("spec") if isinstance(spec, dict) else None,
                    "caption": spec.get("caption") if isinstance(spec, dict) else None,
                    "path": paths[i] if i < len(paths) else "",
                    "error": errors[i] if i < len(errors) else None,
                    "spec_unchanged": (
                        isinstance(spec, dict)
                        and i < len(used)
                        and spec.get("spec") == (used[i] or {}).get("spec")
                    ),
                }
            )

        if json_output:
            typer.echo(json_mod.dumps({"draft_id": draft_id, "media": items}, indent=2))
            return

        if not items:
            typer.echo(f"No media on draft {draft_id}.")
            return
        typer.echo(f"{'#':<3} {'ID':<20} {'Tool':<16} {'Err':<4} {'Path'}")
        typer.echo("-" * 80)
        for i, item in enumerate(items):
            err_mark = "!" if item["error"] else ("U" if item["user_uploaded"] else "")
            typer.echo(
                f"{i:<3} {(item['id'] or '-'):<20} {(item['tool'] or '-'):<16} {err_mark:<4} {item['path']}"
            )
    finally:
        conn.close()


@media_app.command("regen")
def media_regen(
    ctx: typer.Context,
    media_id: str | None = typer.Option(None, "--id", help="Media id to regenerate"),
    all_items: bool = typer.Option(False, "--all", help="Regenerate every media item on the draft"),
    draft_id: str = typer.Option(..., "--draft", help="Draft ID"),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    index: int | None = typer.Option(
        None, "--index", hidden=True, help="Rejected — addressing is by media_id."
    ),
):
    """Regenerate media for a single item (--id) or all items (--all).

    Media addressing is by stable id. Pass --all to regenerate every item on
    the draft (equivalent to the web Regen All button). LLM-bearing — runs
    adapter generation synchronously in CLI context.

    Example: social-hook draft media regen --draft draft_abc123 --id media_a1b2c3d4e5f6
    Example: social-hook draft media regen --draft draft_abc123 --all --json
    """
    _reject_index(index)
    if bool(media_id) == bool(all_items):
        typer.echo("Provide exactly one of --id MEDIA_ID or --all.", err=True)
        raise typer.Exit(1)

    from social_hook.adapters.registry import get_media_adapter
    from social_hook.config.yaml import load_full_config
    from social_hook.db import operations as ops
    from social_hook.filesystem import generate_id, get_base_path
    from social_hook.models.core import DraftChange

    json_output = _merge_json_flag(ctx, json_output)
    conn = _get_conn()
    try:
        draft = _get_draft_or_exit(conn, draft_id)
        specs = list(draft.media_specs or [])
        if not specs:
            typer.echo("Draft has no media items.", err=True)
            raise typer.Exit(1)

        if media_id:
            idx, spec = _find_draft_media_spec(draft, media_id)
            if idx is None or spec is None:
                typer.echo(f"Media id {media_id!r} not found on draft {draft_id}.", err=True)
                raise typer.Exit(1)
            targets = [(idx, spec)]
        else:
            targets = list(enumerate(specs))

        config_path = ctx.obj.get("config") if ctx.obj else None
        config = load_full_config(str(config_path) if config_path else None)

        results: list[dict] = []
        for _idx, spec in targets:
            if not isinstance(spec, dict):
                continue
            if spec.get("user_uploaded"):
                # Skip uploads — they are not generated.
                results.append({"id": spec.get("id"), "skipped": "user_uploaded"})
                continue
            tool_name = spec.get("tool")
            if not tool_name or tool_name == "legacy_upload":
                results.append({"id": spec.get("id"), "skipped": "no_generator"})
                continue

            api_key = None
            if tool_name == "nano_banana_pro":
                api_key = config.env.get("GEMINI_API_KEY") if config else None
                if not api_key:
                    msg = "GEMINI_API_KEY not configured"
                    ops.update_draft_media(conn, draft_id, spec["id"], error=msg)
                    results.append({"id": spec["id"], "error": msg})
                    continue

            try:
                adapter = get_media_adapter(tool_name, api_key=api_key)
            except ValueError as e:
                ops.update_draft_media(conn, draft_id, spec["id"], error=str(e))
                results.append({"id": spec["id"], "error": str(e)})
                continue
            if adapter is None:
                msg = f"Media adapter '{tool_name}' not available"
                ops.update_draft_media(conn, draft_id, spec["id"], error=msg)
                results.append({"id": spec["id"], "error": msg})
                continue

            output_dir = str(get_base_path() / "media-cache" / spec["id"])
            result = adapter.generate(spec=spec.get("spec", {}), output_dir=output_dir)

            if result.success and result.file_path:
                old_paths = draft.media_paths
                ops.update_draft_media(
                    conn,
                    draft_id,
                    spec["id"],
                    path=result.file_path,
                    spec_used=spec,
                    error="",
                )
                ops.insert_draft_change(
                    conn,
                    DraftChange(
                        id=generate_id("change"),
                        draft_id=draft_id,
                        field=f"media_spec:{spec['id']}",
                        old_value=json_mod.dumps(old_paths),
                        new_value=json_mod.dumps(result.file_path),
                        changed_by="human",
                    ),
                )
                results.append({"id": spec["id"], "path": result.file_path})
            else:
                msg = result.error or "unknown generation failure"
                ops.update_draft_media(conn, draft_id, spec["id"], error=msg)
                results.append({"id": spec["id"], "error": msg})

        ops.emit_data_event(conn, "draft", "updated", draft_id, draft.project_id)

        if json_output:
            typer.echo(
                json_mod.dumps(
                    {"draft_id": draft_id, "regenerated": results, "count": len(results)}, indent=2
                )
            )
        else:
            typer.echo(f"Regenerated {len(results)} media item(s) on draft {draft_id}.")
            for r in results:
                mark = r.get("error") or r.get("skipped") or r.get("path")
                typer.echo(f"  {r.get('id')}: {mark}")
    finally:
        conn.close()


@media_app.command("edit")
def media_edit(
    ctx: typer.Context,
    media_id: str = typer.Option(..., "--id", help="Media id to edit"),
    spec_json: str = typer.Option(
        ..., "--spec", "-s", help="New spec payload (JSON) for this media item"
    ),
    draft_id: str = typer.Option(..., "--draft", help="Draft ID"),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    index: int | None = typer.Option(
        None, "--index", hidden=True, help="Rejected — addressing is by media_id."
    ),
):
    """Edit the spec payload of a single media item on a draft.

    Stores the new spec only; does not regenerate. Run `media regen --id`
    next to produce a file from the updated spec.

    Example: social-hook draft media edit --draft draft_abc --id media_a1b2c3d4e5f6 --spec '{"code": "print(1)", "language": "python"}'
    """
    _reject_index(index)
    from social_hook.db import operations as ops
    from social_hook.filesystem import generate_id
    from social_hook.models.core import DraftChange

    json_output = _merge_json_flag(ctx, json_output)
    try:
        new_spec_payload = json_mod.loads(spec_json)
    except json_mod.JSONDecodeError as e:
        typer.echo(f"Invalid JSON for --spec: {e}", err=True)
        raise typer.Exit(1) from None
    if not isinstance(new_spec_payload, dict):
        typer.echo("--spec must be a JSON object.", err=True)
        raise typer.Exit(1)

    conn = _get_conn()
    try:
        draft = _get_draft_or_exit(conn, draft_id)
        idx, spec = _find_draft_media_spec(draft, media_id)
        if idx is None or spec is None:
            typer.echo(f"Media id {media_id!r} not found on draft {draft_id}.", err=True)
            raise typer.Exit(1)

        updated = dict(spec)
        updated["spec"] = new_spec_payload

        ops.update_draft_media(conn, draft_id, media_id, spec=updated)
        ops.insert_draft_change(
            conn,
            DraftChange(
                id=generate_id("change"),
                draft_id=draft_id,
                field=f"media_spec:{media_id}",
                old_value=json_mod.dumps(spec.get("spec"))[:200],
                new_value=json_mod.dumps(new_spec_payload)[:200],
                changed_by="human",
            ),
        )
        ops.emit_data_event(conn, "draft", "updated", draft_id, draft.project_id)

        if json_output:
            typer.echo(
                json_mod.dumps(
                    {"draft_id": draft_id, "media_id": media_id, "spec": new_spec_payload},
                    indent=2,
                )
            )
        else:
            typer.echo(f"Updated spec for {media_id} on draft {draft_id}.")
    finally:
        conn.close()


@media_app.command("remove")
def media_remove(
    ctx: typer.Context,
    media_id: str = typer.Option(..., "--id", help="Media id to remove"),
    draft_id: str = typer.Option(..., "--draft", help="Draft ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    index: int | None = typer.Option(
        None, "--index", hidden=True, help="Rejected — addressing is by media_id."
    ),
):
    """Remove a single media item from a draft by id.

    Destructive — splices the item out of all four parallel arrays
    (media_specs, media_paths, media_errors, media_specs_used). --yes
    skips confirmation and is required for non-interactive use.

    Example: social-hook draft media remove --draft draft_abc --id media_a1b2c3d4e5f6 --yes
    """
    _reject_index(index)
    from social_hook.db import operations as ops
    from social_hook.filesystem import generate_id
    from social_hook.models.core import DraftChange

    json_output = _merge_json_flag(ctx, json_output)
    conn = _get_conn()
    try:
        draft = _get_draft_or_exit(conn, draft_id)
        idx, spec = _find_draft_media_spec(draft, media_id)
        if idx is None or spec is None:
            typer.echo(f"Media id {media_id!r} not found on draft {draft_id}.", err=True)
            raise typer.Exit(1)

        if not yes:
            typer.confirm(
                f"Remove media {media_id} (tool={spec.get('tool')}) from draft {draft_id[:12]}?",
                abort=True,
            )

        if not ops.remove_draft_media(conn, draft_id, media_id):
            typer.echo(f"Failed to remove {media_id} from draft {draft_id}.", err=True)
            raise typer.Exit(2)

        ops.insert_draft_change(
            conn,
            DraftChange(
                id=generate_id("change"),
                draft_id=draft_id,
                field=f"media_spec:{media_id}",
                old_value=json_mod.dumps(spec)[:200],
                new_value="null",
                changed_by="human",
            ),
        )
        ops.emit_data_event(conn, "draft", "updated", draft_id, draft.project_id)

        if json_output:
            typer.echo(
                json_mod.dumps({"draft_id": draft_id, "removed_media_id": media_id}, indent=2)
            )
        else:
            typer.echo(f"Removed {media_id} from draft {draft_id}.")
    finally:
        conn.close()


@media_app.command("add")
def media_add(
    ctx: typer.Context,
    tool: str = typer.Option(
        ..., "--tool", help="Generator tool (nano_banana_pro, mermaid, ray_so, legacy_upload)"
    ),
    spec_json: str = typer.Option(
        ..., "--spec", "-s", help="Spec payload (JSON) for the new media item"
    ),
    draft_id: str = typer.Option(..., "--draft", help="Draft ID"),
    caption: str | None = typer.Option(None, "--caption", help="Optional caption text"),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    index: int | None = typer.Option(
        None, "--index", hidden=True, help="Rejected — addressing is by media_id."
    ),
):
    """Append a new media slot to a draft and print its fresh media_id.

    Does not generate. Run `media regen --id <new_id>` afterwards to produce
    the file. Useful for adding a slot the drafter missed before an article
    is ready for review.

    Example: social-hook draft media add --draft draft_abc --tool mermaid --spec '{"diagram": "graph TD; A-->B"}'
    """
    _reject_index(index)
    from social_hook.db import operations as ops
    from social_hook.filesystem import generate_id
    from social_hook.models.core import DraftChange

    json_output = _merge_json_flag(ctx, json_output)
    try:
        new_spec_payload = json_mod.loads(spec_json)
    except json_mod.JSONDecodeError as e:
        typer.echo(f"Invalid JSON for --spec: {e}", err=True)
        raise typer.Exit(1) from None
    if not isinstance(new_spec_payload, dict):
        typer.echo("--spec must be a JSON object.", err=True)
        raise typer.Exit(1)

    conn = _get_conn()
    try:
        draft = _get_draft_or_exit(conn, draft_id)
        new_spec = {
            "tool": tool,
            "spec": new_spec_payload,
            "caption": caption,
            "user_uploaded": tool == "legacy_upload",
        }
        new_id = ops.append_draft_media(conn, draft_id, new_spec)
        if new_id is None:
            typer.echo(f"Failed to append media to draft {draft_id}.", err=True)
            raise typer.Exit(2)

        ops.insert_draft_change(
            conn,
            DraftChange(
                id=generate_id("change"),
                draft_id=draft_id,
                field=f"media_spec:{new_id}",
                old_value="null",
                new_value=json_mod.dumps({"tool": tool})[:200],
                changed_by="human",
            ),
        )
        ops.emit_data_event(conn, "draft", "updated", draft_id, draft.project_id)

        if json_output:
            typer.echo(
                json_mod.dumps({"draft_id": draft_id, "media_id": new_id, "tool": tool}, indent=2)
            )
        else:
            typer.echo(f"Added media slot {new_id} ({tool}) to draft {draft_id}.")
    finally:
        conn.close()


app.add_typer(media_app, name="media")


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
            fmt = getattr(d, "vehicle", "single") or "single"
            media_count = len(d.media_specs or [])
            media = str(media_count) if media_count else "-"

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
        tweets = ops.get_draft_parts(conn, draft_id)

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
        specs = draft.media_specs or []
        paths = draft.media_paths or []
        errors = draft.media_errors or []
        if specs:
            typer.echo(f"Media:      {len(specs)} item(s)")
            for i, spec in enumerate(specs):
                sid = spec.get("id") if isinstance(spec, dict) else "?"
                tool = spec.get("tool") if isinstance(spec, dict) else "?"
                marker = "U" if isinstance(spec, dict) and spec.get("user_uploaded") else ""
                path = paths[i] if i < len(paths) else ""
                err = errors[i] if i < len(errors) else None
                status = err if err else (path or "(pending)")
                typer.echo(f"  [{i}] {sid} {tool}{marker}: {status}")
                url = _media_url(path) if path else None
                if url:
                    typer.echo(f"       View: {url}")
            if open_media:
                import platform as plat
                import subprocess

                for mp in paths:
                    if mp and Path(mp).exists():
                        cmd = "open" if plat.system() == "Darwin" else "xdg-open"
                        subprocess.Popen(
                            [cmd, mp], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                        )
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
    from social_hook.config.project import ProjectConfig, load_project_config
    from social_hook.config.yaml import load_full_config
    from social_hook.db import operations as ops
    from social_hook.drafting import draft as run_draft
    from social_hook.drafting_intents import intent_from_decision
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

        intent = intent_from_decision(decision, config, conn, target_platform=platform)

        from social_hook.cli._spinner import spinner

        with spinner(f"Redrafting for {platform}..."):
            results = run_draft(
                intent,
                config,
                conn,
                db,
                project,
                context,
                commit,
                project_config=project_config,
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
