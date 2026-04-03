"""CLI commands for target management."""

import json as json_mod
import logging

import typer

from social_hook.cli.utils import resolve_project
from social_hook.models.enums import PENDING_STATUSES

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
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List targets with account, destination, and strategy.

    Shows all content distribution targets for the project.
    Each target maps an account + destination to a content strategy.

    Example: social-hook target list
    """
    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)

        # Targets are stored in project's content-config.yaml
        from social_hook.config.project import load_project_config

        project_config = load_project_config(proj.repo_path)
        targets = project_config.content_config.get("targets", [])

        if json_output:
            typer.echo(json_mod.dumps({"targets": targets, "project": proj.name}, indent=2))
            return

        if not targets:
            typer.echo(f"No targets configured for '{proj.name}'.")
            typer.echo("Use 'social-hook target add' to create one.")
            return

        typer.echo(f"Targets for '{proj.name}':")
        typer.echo(f"{'Account':<18} {'Destination':<14} {'Strategy':<20} {'Status'}")
        typer.echo("-" * 65)
        for t in targets:
            account = t.get("account", "—")
            dest = t.get("destination", "—")
            strategy = t.get("strategy", "—")
            status = t.get("status", "active")
            typer.echo(f"{account:<18} {dest:<14} {strategy:<20} {status}")
    finally:
        conn.close()


@app.command()
def add(
    ctx: typer.Context,
    account: str = typer.Option(..., "--account", help="Account name"),
    destination: str = typer.Option(
        "timeline", "--destination", help="Destination (timeline, etc.)"
    ),
    strategy: str = typer.Option(..., "--strategy", help="Content strategy name"),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Add a content distribution target.

    Maps an account + destination to a content strategy.
    Max targets per project is configurable (default: 10).

    Example: social-hook target add --account product --destination timeline --strategy product-news
    """
    import yaml

    from social_hook.constants import CONFIG_DIR_NAME

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)

        from pathlib import Path

        config_path = Path(proj.repo_path) / CONFIG_DIR_NAME / "content-config.yaml"

        # Load existing config
        if config_path.exists():
            content = config_path.read_text(encoding="utf-8")
            config_data = yaml.safe_load(content) or {}
        else:
            config_data = {}

        targets = config_data.get("targets", [])

        # Check for duplicate
        for t in targets:
            if t.get("account") == account and t.get("destination") == destination:
                msg = f"Target already exists: {account}/{destination}"
                if json_output:
                    typer.echo(json_mod.dumps({"error": msg}))
                else:
                    typer.echo(msg)
                raise typer.Exit(1)

        new_target = {
            "account": account,
            "destination": destination,
            "strategy": strategy,
            "status": "active",
        }
        targets.append(new_target)
        config_data["targets"] = targets

        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(yaml.dump(config_data, default_flow_style=False), encoding="utf-8")

        if json_output:
            typer.echo(json_mod.dumps({"added": True, "target": new_target}, indent=2))
        else:
            typer.echo(f"Added target: {account}/{destination} -> {strategy}")
    finally:
        conn.close()


@app.command()
def delete(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Target name to delete"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Delete a target and cancel its pending drafts.

    Permanently removes the target from config. Pending drafts for
    this target will be cancelled. This cannot be undone.

    Example: social-hook target delete x-lead-timeline --yes
    """
    from social_hook.config.yaml import load_full_config
    from social_hook.db import operations as ops
    from social_hook.filesystem import get_config_path

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)

        config = load_full_config()
        if name not in config.targets:
            msg = f"Target not found: {name}"
            if json_output:
                typer.echo(json_mod.dumps({"error": msg}))
            else:
                typer.echo(msg)
            raise typer.Exit(1)

        if not yes and not typer.confirm(
            f"Delete target '{name}'? Pending drafts will be cancelled."
        ):
            typer.echo("Cancelled.")
            return

        # Cancel pending drafts
        placeholders = ",".join("?" for _ in PENDING_STATUSES)
        pending = conn.execute(
            f"SELECT id FROM drafts WHERE project_id = ? AND target_id = ? AND status IN ({placeholders})",
            (proj.id, name, *PENDING_STATUSES),
        ).fetchall()
        for row in pending:
            ops.update_draft(conn, row["id"], status="cancelled")

        # Remove from config
        from social_hook.config.yaml import delete_config_key

        delete_config_key(get_config_path(), "targets", name)

        if json_output:
            typer.echo(
                json_mod.dumps(
                    {"deleted": True, "target": name, "cancelled_drafts": len(pending)},
                    indent=2,
                )
            )
        else:
            typer.echo(f"Target '{name}' deleted. {len(pending)} draft(s) cancelled.")
    finally:
        conn.close()


@app.command()
def disable(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Target name (account/destination)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Disable a target and archive its pending drafts.

    Sets the target status to 'disabled' and cancels any pending drafts.
    The target remains in the system and can be re-enabled.

    Example: social-hook target disable product/timeline --yes
    """
    import yaml

    from social_hook.constants import CONFIG_DIR_NAME

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)

        from pathlib import Path

        config_path = Path(proj.repo_path) / CONFIG_DIR_NAME / "content-config.yaml"
        if not config_path.exists():
            typer.echo("No targets configured.")
            raise typer.Exit(1)

        config_data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        targets = config_data.get("targets", [])

        # Parse name as account/destination or just account
        parts = name.split("/", 1)
        account = parts[0]
        destination = parts[1] if len(parts) > 1 else None

        found = None
        for t in targets:
            if t.get("account") == account and (
                destination is None or t.get("destination") == destination
            ):
                found = t
                break

        if not found:
            msg = f"Target not found: {name}"
            if json_output:
                typer.echo(json_mod.dumps({"error": msg}))
            else:
                typer.echo(msg)
            raise typer.Exit(1)

        if found.get("status") == "disabled":
            typer.echo(f"Target '{name}' is already disabled.")
            return

        if not yes and not typer.confirm(
            f"Disable target '{name}'? Pending drafts will be cancelled."
        ):
            typer.echo("Cancelled.")
            return

        found["status"] = "disabled"
        config_path.write_text(yaml.dump(config_data, default_flow_style=False), encoding="utf-8")

        if json_output:
            typer.echo(json_mod.dumps({"disabled": True, "target": found}, indent=2))
        else:
            typer.echo(f"Target '{name}' disabled.")
    finally:
        conn.close()


@app.command()
def enable(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Target name (account/destination)"),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Re-enable a disabled target.

    Sets the target status back to 'active'. Previously cancelled drafts
    are not restored -- new drafts will be created on the next trigger.

    Example: social-hook target enable product/timeline
    """
    import yaml

    from social_hook.constants import CONFIG_DIR_NAME

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)

        from pathlib import Path

        config_path = Path(proj.repo_path) / CONFIG_DIR_NAME / "content-config.yaml"
        if not config_path.exists():
            typer.echo("No targets configured.")
            raise typer.Exit(1)

        config_data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        targets = config_data.get("targets", [])

        parts = name.split("/", 1)
        account = parts[0]
        destination = parts[1] if len(parts) > 1 else None

        found = None
        for t in targets:
            if t.get("account") == account and (
                destination is None or t.get("destination") == destination
            ):
                found = t
                break

        if not found:
            msg = f"Target not found: {name}"
            if json_output:
                typer.echo(json_mod.dumps({"error": msg}))
            else:
                typer.echo(msg)
            raise typer.Exit(1)

        if found.get("status", "active") == "active":
            typer.echo(f"Target '{name}' is already active.")
            return

        found["status"] = "active"
        config_path.write_text(yaml.dump(config_data, default_flow_style=False), encoding="utf-8")

        if json_output:
            typer.echo(json_mod.dumps({"enabled": True, "target": found}, indent=2))
        else:
            typer.echo(f"Target '{name}' enabled.")
    finally:
        conn.close()
