"""CLI commands for project management."""

from pathlib import Path

import typer

from social_hook.constants import PROJECT_SLUG

app = typer.Typer()


@app.command()
def register(
    ctx: typer.Context,
    path: Path | None = typer.Argument(
        None, help="Path to repository (default: current directory)"
    ),
    name: str | None = typer.Option(None, "--name", "-n", help="Project name"),
    git_hook: bool = typer.Option(
        True, "--git-hook/--no-git-hook", help="Install git post-commit hook"
    ),
):
    """Register a project for social-hook."""
    from social_hook.config import load_full_config
    from social_hook.db import init_database
    from social_hook.db.operations import register_project
    from social_hook.filesystem import get_db_path
    from social_hook.setup.install import check_hook_installed, install_git_hook

    if path is None:
        path = Path.cwd()

    load_full_config(str(ctx.obj["config"]) if ctx.obj and ctx.obj.get("config") else None)
    conn = init_database(get_db_path())
    try:
        project, repo_origin = register_project(conn, str(path), name)

        typer.echo(f"Registered project: {project.name}")
        typer.echo(f"  ID: {project.id}")
        typer.echo(f"  Path: {project.repo_path}")
        if repo_origin:
            typer.echo(f"  Origin: {repo_origin}")

        if git_hook:
            success, msg = install_git_hook(project.repo_path)
            typer.echo(f"  {msg}")

        if not check_hook_installed():
            typer.echo()
            typer.echo("Note: Claude Code commit hook is not installed.")
            typer.echo(f"  Git hook is {'active' if git_hook else 'not installed'}.")
    except ValueError as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(1) from None
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
            confirm = typer.confirm(f"Delete project '{project.name}' and all its data?")
            if not confirm:
                typer.echo("Cancelled.")
                return

        from social_hook.setup.install import uninstall_git_hook

        uninstall_git_hook(project.repo_path)

        if delete_project(conn, project_id):
            typer.echo(f"Project '{project.name}' unregistered.")
        else:
            typer.echo("Failed to delete project.")
    finally:
        conn.close()


@app.command()
def pause(
    ctx: typer.Context,
    project_id: str | None = typer.Argument(
        None, help="Project ID (default: detect from current directory)"
    ),
):
    """Pause a project (skip commit evaluation)."""
    _set_paused(project_id, paused=True)


@app.command()
def unpause(
    ctx: typer.Context,
    project_id: str | None = typer.Argument(
        None, help="Project ID (default: detect from current directory)"
    ),
):
    """Unpause a project (resume commit evaluation)."""
    _set_paused(project_id, paused=False)


def _set_paused(project_id: str | None, paused: bool) -> None:
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
                    capture_output=True,
                    text=True,
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


@app.command("set-branch")
def set_branch(
    ctx: typer.Context,
    branch: str | None = typer.Argument(None, help="Branch name to filter on"),
    project_id: str | None = typer.Option(None, "--id", "-p", help="Project ID"),
    all_branches: bool = typer.Option(
        False, "--all", help="Clear filter (trigger on all branches)"
    ),
):
    """Set which branch triggers the pipeline for a project."""
    import subprocess as sp

    from social_hook.db import (
        get_project,
        get_project_by_origin,
        get_project_by_path,
        init_database,
        set_project_trigger_branch,
    )
    from social_hook.db.operations import emit_data_event
    from social_hook.filesystem import get_db_path

    if branch is None and not all_branches:
        typer.echo("Error: provide a branch name or use --all to clear the filter.")
        raise typer.Exit(1)

    target_branch = None if all_branches else branch

    conn = init_database(get_db_path())
    try:
        project = None

        if project_id:
            project = get_project(conn, project_id)
            if not project:
                from social_hook.db import get_all_projects

                for p in get_all_projects(conn):
                    if p.id.startswith(project_id):
                        project = p
                        break

        if not project:
            cwd = str(Path.cwd().resolve())
            project = get_project_by_path(conn, cwd)

            if not project:
                origin_result = sp.run(
                    ["git", "-C", cwd, "remote", "get-url", "origin"],
                    capture_output=True,
                    text=True,
                )
                if origin_result.returncode == 0:
                    matches = get_project_by_origin(conn, origin_result.stdout.strip())
                    if matches:
                        project = matches[0]

        if not project:
            typer.echo("No project found. Provide a project ID or run from a registered repo.")
            raise typer.Exit(1)

        # Warn if branch doesn't exist locally
        if target_branch:
            try:
                sp.run(
                    [
                        "git",
                        "-C",
                        project.repo_path,
                        "rev-parse",
                        "--verify",
                        f"refs/heads/{target_branch}",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
            except (sp.CalledProcessError, OSError):
                typer.echo(f"Warning: branch '{target_branch}' not found in {project.repo_path}")

        set_project_trigger_branch(conn, project.id, target_branch)
        emit_data_event(conn, "project", "updated", project.id, project.id)

        if target_branch:
            typer.echo(f"Set trigger branch to '{target_branch}' for project '{project.name}'.")
        else:
            typer.echo(
                f"Cleared trigger branch filter for project '{project.name}' (all branches)."
            )
    finally:
        conn.close()


@app.command("import-commits")
def import_commits(
    ctx: typer.Context,
    branch: str | None = typer.Option(None, "--branch", "-b", help="Import only this branch"),
    project_id: str | None = typer.Option(None, "--id", "-p", help="Project ID"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Import historical git commits as imported decisions.

    Imports all past commits so the dashboard shows the full project timeline.
    Imported commits are NOT evaluated — use retrigger to evaluate them later.

    Examples:
        social-hook project import-commits
        social-hook project import-commits --branch main
        social-hook project import-commits --id project_abc123
    """
    import json
    import subprocess as sp

    from social_hook.db import (
        get_all_projects,
        get_project,
        get_project_by_origin,
        get_project_by_path,
        init_database,
    )
    from social_hook.db.operations import emit_data_event
    from social_hook.filesystem import get_db_path
    from social_hook.import_commits import import_project_commits

    conn = init_database(get_db_path())
    try:
        project = None

        if project_id:
            project = get_project(conn, project_id)
            if not project:
                for p in get_all_projects(conn):
                    if p.id.startswith(project_id):
                        project = p
                        break

        if not project:
            cwd = str(Path.cwd().resolve())
            project = get_project_by_path(conn, cwd)

            if not project:
                origin_result = sp.run(
                    ["git", "-C", cwd, "remote", "get-url", "origin"],
                    capture_output=True,
                    text=True,
                )
                if origin_result.returncode == 0:
                    matches = get_project_by_origin(conn, origin_result.stdout.strip())
                    if matches:
                        project = matches[0]

        if not project:
            typer.echo("No project found. Provide a project ID or run from a registered repo.")
            raise typer.Exit(1)

        from social_hook.cli._spinner import spinner

        branch_desc = f" (branch: {branch})" if branch else " (all branches)"
        with spinner(f"Importing commits for '{project.name}'{branch_desc}..."):
            result = import_project_commits(conn, project.id, project.repo_path, branch)
        emit_data_event(conn, "decision", "created", project.id, project.id)

        if json_output:
            typer.echo(json.dumps(result))
        else:
            typer.echo(
                f"Done: {result['imported']} imported, "
                f"{result['skipped']} already tracked, "
                f"{result['total']} total commits."
            )
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
            branch_info = f"  [{p.trigger_branch} only]" if p.trigger_branch else ""
            typer.echo(f"  {p.id[:12]}  {p.name:20s}  [{status}]{branch_info}  {p.repo_path}")

        from social_hook.setup.install import check_hook_installed

        if projects and not check_hook_installed():
            typer.echo()
            typer.echo("Warning: Claude Code commit hook is not installed.")
            typer.echo(f"  Run '{PROJECT_SLUG} setup' or install from the web dashboard.")
    finally:
        conn.close()


@app.command("install-hook")
def install_hook_cmd(
    ctx: typer.Context,
    path: Path | None = typer.Argument(
        None, help="Path to repository (default: current directory)"
    ),
):
    """Install git post-commit hook for a project.
    Example: social-hook project install-hook /path/to/repo"""
    from social_hook.setup.install import install_git_hook

    if path is None:
        path = Path.cwd()
    path = path.resolve()

    json_mode = ctx.obj.get("json", False) if ctx.obj else False
    success, msg = install_git_hook(str(path))

    if json_mode:
        import json

        typer.echo(json.dumps({"success": success, "message": msg}, indent=2))
    else:
        typer.echo(msg)

    if not success:
        raise typer.Exit(1)


@app.command("uninstall-hook")
def uninstall_hook_cmd(
    ctx: typer.Context,
    path: Path | None = typer.Argument(
        None, help="Path to repository (default: current directory)"
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Remove git post-commit hook from a project.
    Example: social-hook project uninstall-hook /path/to/repo"""
    from social_hook.setup.install import check_git_hook_installed, uninstall_git_hook

    if path is None:
        path = Path.cwd()
    path = path.resolve()

    json_mode = ctx.obj.get("json", False) if ctx.obj else False

    if not check_git_hook_installed(str(path)):
        msg = "Git hook is not installed"
        if json_mode:
            import json

            typer.echo(json.dumps({"success": True, "message": msg}, indent=2))
        else:
            typer.echo(msg)
        return

    if not force and not json_mode and not typer.confirm("Remove git post-commit hook?"):
        typer.echo("Cancelled.")
        return

    success, msg = uninstall_git_hook(str(path))

    if json_mode:
        import json

        typer.echo(json.dumps({"success": success, "message": msg}, indent=2))
    else:
        typer.echo(msg)

    if not success:
        raise typer.Exit(1)
