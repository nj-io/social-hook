"""CLI commands for project management."""

import subprocess
from pathlib import Path
from typing import Optional

import typer

from social_hook.constants import PROJECT_SLUG

app = typer.Typer()


@app.command()
def register(
    ctx: typer.Context,
    path: Optional[Path] = typer.Argument(None, help="Path to repository (default: current directory)"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Project name"),
):
    """Register a project for social-hook."""
    from social_hook.config import load_full_config
    from social_hook.db import (
        get_project_by_origin,
        get_project_by_path,
        init_database,
        insert_project,
    )
    from social_hook.filesystem import generate_id, get_db_path

    if path is None:
        path = Path.cwd()
    path = path.resolve()

    # Validate git repo
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--git-dir"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        typer.echo(f"Error: {path} is not a git repository")
        raise typer.Exit(1)

    # Extract remote origin
    origin_result = subprocess.run(
        ["git", "-C", str(path), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
    )
    repo_origin = origin_result.stdout.strip() if origin_result.returncode == 0 else None

    # Default name from directory
    if not name:
        name = path.name

    # Check duplicates
    config = load_full_config(
        str(ctx.obj["config"]) if ctx.obj and ctx.obj.get("config") else None
    )
    conn = init_database(get_db_path())

    try:
        existing = get_project_by_path(conn, str(path))
        if existing:
            typer.echo(f"Project already registered: {existing.name} ({existing.id})")
            raise typer.Exit(1)

        if repo_origin:
            matches = get_project_by_origin(conn, repo_origin)
            if matches:
                typer.echo(f"Repository origin already registered as: {matches[0].name}")
                raise typer.Exit(1)

        from social_hook.models import Project

        project = Project(
            id=generate_id("project"),
            name=name,
            repo_path=str(path),
            repo_origin=repo_origin,
        )
        insert_project(conn, project)

        # Initialize lifecycle and narrative debt
        from social_hook.db import insert_lifecycle, insert_narrative_debt
        from social_hook.models import Lifecycle, NarrativeDebt

        lifecycle = Lifecycle(
            project_id=project.id,
            phase="research",
            confidence=0.3,
        )
        insert_lifecycle(conn, lifecycle)

        debt = NarrativeDebt(
            project_id=project.id,
            debt_counter=0,
        )
        insert_narrative_debt(conn, debt)

        typer.echo(f"Registered project: {name}")
        typer.echo(f"  ID: {project.id}")
        typer.echo(f"  Path: {path}")
        if repo_origin:
            typer.echo(f"  Origin: {repo_origin}")

        from social_hook.setup.install import check_hook_installed
        if not check_hook_installed():
            typer.echo()
            typer.echo("Warning: Claude Code commit hook is not installed.")
            typer.echo(f"  Run '{PROJECT_SLUG} setup' or install from the web dashboard.")
    finally:
        conn.close()


@app.command()
def unregister(
    ctx: typer.Context,
    project_id: str = typer.Argument(..., help="Project ID to unregister"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Unregister a project."""
    from social_hook.db import delete_project, get_project, init_database
    from social_hook.filesystem import get_db_path

    conn = init_database(get_db_path())
    try:
        project = get_project(conn, project_id)
        if not project:
            typer.echo(f"Project not found: {project_id}")
            raise typer.Exit(1)

        if not force:
            confirm = typer.confirm(
                f"Delete project '{project.name}' and all its data?"
            )
            if not confirm:
                typer.echo("Cancelled.")
                return

        if delete_project(conn, project_id):
            typer.echo(f"Project '{project.name}' unregistered.")
        else:
            typer.echo("Failed to delete project.")
    finally:
        conn.close()


@app.command()
def pause(
    ctx: typer.Context,
    project_id: Optional[str] = typer.Argument(None, help="Project ID (default: detect from current directory)"),
):
    """Pause a project (skip commit evaluation)."""
    _set_paused(project_id, paused=True)


@app.command()
def unpause(
    ctx: typer.Context,
    project_id: Optional[str] = typer.Argument(None, help="Project ID (default: detect from current directory)"),
):
    """Unpause a project (resume commit evaluation)."""
    _set_paused(project_id, paused=False)


def _set_paused(project_id: Optional[str], paused: bool) -> None:
    """Shared implementation for pause/unpause."""
    import subprocess as sp

    from social_hook.db import (
        get_project,
        get_project_by_origin,
        get_project_by_path,
        init_database,
        set_project_paused,
    )
    from social_hook.db.operations import emit_data_event
    from social_hook.filesystem import get_db_path

    conn = init_database(get_db_path())
    try:
        project = None

        if project_id:
            project = get_project(conn, project_id)
            if not project:
                # Try prefix match
                from social_hook.db import get_all_projects
                for p in get_all_projects(conn):
                    if p.id.startswith(project_id):
                        project = p
                        break

        if not project:
            # Auto-detect from current directory
            cwd = str(Path.cwd().resolve())
            project = get_project_by_path(conn, cwd)

            if not project:
                origin_result = sp.run(
                    ["git", "-C", cwd, "remote", "get-url", "origin"],
                    capture_output=True, text=True,
                )
                if origin_result.returncode == 0:
                    matches = get_project_by_origin(conn, origin_result.stdout.strip())
                    if matches:
                        project = matches[0]

        if not project:
            typer.echo("No project found. Provide a project ID or run from a registered repo.")
            raise typer.Exit(1)

        if project.paused == paused:
            state = "paused" if paused else "active"
            typer.echo(f"Project '{project.name}' is already {state}.")
            return

        set_project_paused(conn, project.id, paused)
        emit_data_event(conn, "project", "updated", project.id, project.id)

        action = "Paused" if paused else "Unpaused"
        typer.echo(f"{action} project '{project.name}'.")
    finally:
        conn.close()


@app.command("list")
def list_projects(ctx: typer.Context):
    """List all registered projects."""
    from social_hook.db import get_all_projects, init_database
    from social_hook.filesystem import get_db_path

    conn = init_database(get_db_path())
    try:
        projects = get_all_projects(conn)
        if not projects:
            typer.echo("No registered projects.")
            return

        for p in projects:
            status = "paused" if p.paused else "active"
            typer.echo(f"  {p.id[:12]}  {p.name:20s}  [{status}]  {p.repo_path}")

        from social_hook.setup.install import check_hook_installed
        if projects and not check_hook_installed():
            typer.echo()
            typer.echo("Warning: Claude Code commit hook is not installed.")
            typer.echo(f"  Run '{PROJECT_SLUG} setup' or install from the web dashboard.")
    finally:
        conn.close()
