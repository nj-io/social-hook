"""CLI commands for draft lifecycle management."""

import json as json_mod
from datetime import datetime

import typer

app = typer.Typer(no_args_is_help=True)

TERMINAL_STATUSES = {"posted", "rejected", "cancelled", "superseded"}


def _get_conn():
    from social_hook.db.connection import init_database
    from social_hook.filesystem import get_db_path

    return init_database(get_db_path())


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
    """Reject a draft."""
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
        if draft.status not in ("draft", "approved", "scheduled"):
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
        if draft.status not in ("draft", "approved"):
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
    pending: bool = typer.Option(
        False, "--pending", help="Show only actionable drafts (draft/approved/scheduled)"
    ),
):
    """List drafts with optional filters.

    Example: social-hook draft list --pending --json
    """
    from social_hook.db import operations as ops

    conn = _get_conn()
    try:
        drafts = ops.get_drafts_filtered(conn, status=status, project_id=project)
        if pending:
            drafts = [d for d in drafts if d.status in ("draft", "approved", "scheduled")]
        json_output = ctx.obj.get("json", False) if ctx.obj else False

        if json_output:
            typer.echo(json_mod.dumps([d.to_dict() for d in drafts], indent=2, default=str))
            return

        if not drafts:
            typer.echo("No drafts found.")
            return

        typer.echo(f"{'ID':<16} {'Status':<12} {'Platform':<10} {'Fmt':<8} {'Content'}")
        typer.echo("-" * 80)
        for d in drafts:
            content_preview = d.content[:40].replace("\n", " ") if d.content else ""
            intro = " [INTRO]" if getattr(d, "is_intro", False) else ""
            fmt = d.post_format or "single"
            typer.echo(
                f"{d.id[:14]:<16} {d.status:<12} {d.platform:<10} {fmt:<8} {content_preview}{intro}"
            )
    finally:
        conn.close()


@app.command("show")
def show(
    ctx: typer.Context,
    draft_id: str = typer.Argument(..., help="Draft ID to show"),
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
