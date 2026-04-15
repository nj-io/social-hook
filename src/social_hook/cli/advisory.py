"""CLI commands for advisory item management."""

import json as json_mod
import logging

import typer

from social_hook.cli.utils import resolve_project

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
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    status: str | None = typer.Option(
        None, "--status", "-s", help="Filter by status: pending, completed, dismissed"
    ),
    category: str | None = typer.Option(None, "--category", help="Filter by category"),
    urgency: str | None = typer.Option(
        None, "--urgency", help="Filter by urgency: blocking, normal"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List advisory items for a project.

    Shows action items that need operator attention — article posts,
    platform setup, infrastructure tasks, etc.

    Example: social-hook advisory list
    Example: social-hook advisory list --status pending --urgency blocking
    """
    from social_hook.db import operations as ops

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)
        items = ops.get_advisory_items(
            conn,
            project_id=proj.id,
            status=status,
            category=category,
            urgency=urgency,
        )

        if json_output:
            typer.echo(
                json_mod.dumps(
                    {"advisory_items": [i.to_dict() for i in items]},
                    indent=2,
                )
            )
            return

        if not items:
            typer.echo("No advisory items found.")
            return

        typer.echo(f"{'ID':<18} {'Status':<12} {'Urgency':<10} {'Category':<22} {'Title'}")
        typer.echo("-" * 90)
        for item in items:
            iid = item.id[:16]
            title_preview = item.title[:30]
            typer.echo(
                f"{iid:<18} {item.status:<12} {item.urgency:<10} {item.category:<22} {title_preview}"
            )
    finally:
        conn.close()


@app.command()
def complete(
    ctx: typer.Context,
    item_id: str = typer.Argument(..., help="Advisory item ID to mark as completed"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Mark an advisory item as completed.

    Use after you've taken the recommended action (e.g., posted an article
    manually, set up a platform account).

    Example: social-hook advisory complete advisory_abc123
    """
    from datetime import datetime, timezone

    from social_hook.db import operations as ops

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        item = ops.get_advisory_item(conn, item_id)
        if not item:
            msg = f"Advisory item not found: {item_id}"
            if json_output:
                typer.echo(json_mod.dumps({"error": msg}))
            else:
                typer.echo(msg, err=True)
            raise typer.Exit(1)

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        ops.update_advisory_item(conn, item_id, status="completed", completed_at=now)
        ops.emit_data_event(
            conn, "advisory", "updated", item_id, item.project_id, extra={"title": item.title}
        )

        if json_output:
            typer.echo(json_mod.dumps({"completed": True, "advisory_id": item_id}, indent=2))
        else:
            typer.echo(f"Advisory item {item_id} marked as completed.")
    finally:
        conn.close()


@app.command()
def dismiss(
    ctx: typer.Context,
    item_id: str = typer.Argument(..., help="Advisory item ID to dismiss"),
    reason: str | None = typer.Option(None, "--reason", "-r", help="Reason for dismissing"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Dismiss an advisory item.

    Marks the item as dismissed with an optional reason. This is a
    destructive operation — dismissed items are hidden from the active list.

    Example: social-hook advisory dismiss advisory_abc123 --reason "Not applicable"
    """
    from social_hook.db import operations as ops

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        item = ops.get_advisory_item(conn, item_id)
        if not item:
            msg = f"Advisory item not found: {item_id}"
            if json_output:
                typer.echo(json_mod.dumps({"error": msg}))
            else:
                typer.echo(msg, err=True)
            raise typer.Exit(1)

        if item.status == "dismissed":
            typer.echo("Advisory item is already dismissed.")
            return

        if not yes:
            typer.echo(f"Advisory: {item.title}")
            if not typer.confirm("Dismiss this advisory item?"):
                typer.echo("Cancelled.")
                return

        updates: dict = {"status": "dismissed"}
        if reason:
            updates["dismissed_reason"] = reason
        ops.update_advisory_item(conn, item_id, **updates)
        ops.emit_data_event(
            conn, "advisory", "updated", item_id, item.project_id, extra={"title": item.title}
        )

        if json_output:
            typer.echo(
                json_mod.dumps(
                    {"dismissed": True, "advisory_id": item_id},
                    indent=2,
                )
            )
        else:
            typer.echo(f"Advisory item {item_id} dismissed.")
    finally:
        conn.close()


@app.command()
def create(
    ctx: typer.Context,
    title: str = typer.Option(..., "--title", "-t", help="Advisory item title"),
    category: str = typer.Option(
        ...,
        "--category",
        "-c",
        help="Category: platform_presence, product_infrastructure, content_asset, code_change, external_action, outreach",
    ),
    description: str | None = typer.Option(
        None, "--description", "-d", help="Detailed description"
    ),
    urgency: str = typer.Option(
        "normal", "--urgency", "-u", help="Urgency: blocking or normal (default: normal)"
    ),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Create an advisory item manually.

    Advisory items track actions that need operator attention — posting
    articles, setting up accounts, infrastructure changes, etc.

    Example: social-hook advisory create --title "Set up LinkedIn" --category platform_presence
    Example: social-hook advisory create -t "Post article draft" -c content_asset -u blocking
    """
    from social_hook.db import operations as ops
    from social_hook.filesystem import generate_id
    from social_hook.models.infra import AdvisoryItem

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    valid_categories = {
        "platform_presence",
        "product_infrastructure",
        "content_asset",
        "code_change",
        "external_action",
        "outreach",
    }
    if category not in valid_categories:
        msg = f"Invalid category '{category}'. Must be one of: {sorted(valid_categories)}"
        if json_output:
            typer.echo(json_mod.dumps({"error": msg}))
        else:
            typer.echo(msg, err=True)
        raise typer.Exit(1)

    if urgency not in ("blocking", "normal"):
        msg = f"Invalid urgency '{urgency}'. Must be 'blocking' or 'normal'."
        if json_output:
            typer.echo(json_mod.dumps({"error": msg}))
        else:
            typer.echo(msg, err=True)
        raise typer.Exit(1)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)

        item = AdvisoryItem(
            id=generate_id("advisory"),
            project_id=proj.id,
            category=category,
            title=title,
            description=description,
            urgency=urgency,
            created_by="operator",
        )
        ops.insert_advisory_item(conn, item)
        ops.emit_data_event(
            conn, "advisory", "created", item.id, proj.id, extra={"title": item.title}
        )

        if json_output:
            typer.echo(json_mod.dumps(item.to_dict(), indent=2))
        else:
            typer.echo(f"Advisory item created: {item.id}")
    finally:
        conn.close()
