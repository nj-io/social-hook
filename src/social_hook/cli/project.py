"""CLI commands for project management."""

from pathlib import Path

import typer

from social_hook.constants import PROJECT_SLUG

app = typer.Typer()
intro_app = typer.Typer(help="Manage per-platform introduction status.")
app.add_typer(intro_app, name="intro")
prompt_docs_app = typer.Typer(help="Manage project prompt documentation files.")
app.add_typer(prompt_docs_app, name="prompt-docs")


@app.command()
def register(
    ctx: typer.Context,
    path: Path | None = typer.Argument(
        None, help="Path to repository or directory (default: current directory)"
    ),
    name: str | None = typer.Option(None, "--name", "-n", help="Project name"),
    git_hook: bool = typer.Option(
        True, "--git-hook/--no-git-hook", help="Install git post-commit hook"
    ),
    docs: list[str] | None = typer.Option(
        None, "--docs", "-d", help="Documentation files to add as project context"
    ),
):
    """Register a project for social-hook.

    Supports both git repos and plain directories. For non-git projects,
    provide --docs to seed project context.

    Example: social-hook project register /path/to/project --docs README.md --docs guide.md
    """
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

        # Only install git hook if this is a git repo
        from social_hook.trigger_git import is_git_repo

        if git_hook and is_git_repo(project.repo_path):
            success, msg = install_git_hook(project.repo_path)
            typer.echo(f"  {msg}")

            if not check_hook_installed():
                typer.echo()
                typer.echo("Note: Claude Code commit hook is not installed.")
                typer.echo(f"  Git hook is {'active' if git_hook else 'not installed'}.")
        elif not is_git_repo(project.repo_path):
            typer.echo("  Non-git project — git hook skipped.")

        # Handle --docs flag: copy files and generate brief
        if docs:
            import shutil

            docs_dir = Path(project.repo_path) / ".social-hook" / "docs"
            docs_dir.mkdir(parents=True, exist_ok=True)
            prompt_doc_paths = []
            for doc_path in docs:
                src = Path(doc_path).resolve()
                if not src.is_file():
                    typer.echo(f"  Warning: {doc_path} not found, skipping.")
                    continue
                dest = docs_dir / src.name
                shutil.copy2(str(src), str(dest))
                rel = f".social-hook/docs/{src.name}"
                prompt_doc_paths.append(rel)
                typer.echo(f"  Copied: {src.name}")

            if prompt_doc_paths:
                from social_hook.db.operations import update_prompt_docs

                update_prompt_docs(conn, project.id, prompt_doc_paths)
                typer.echo(f"  Added {len(prompt_doc_paths)} doc(s) to prompt_docs.")

                # Generate brief from docs
                try:
                    from social_hook.llm.brief import generate_brief_from_docs
                    from social_hook.llm.factory import create_client

                    _cfg = load_full_config(
                        str(ctx.obj["config"]) if ctx.obj and ctx.obj.get("config") else None
                    )
                    client = create_client(_cfg.models.drafter, _cfg)
                    brief = generate_brief_from_docs(
                        prompt_doc_paths,
                        project.repo_path,
                        client,
                        project_id=project.id,
                    )
                    if brief:
                        from social_hook.db.operations import update_project_summary

                        update_project_summary(conn, project.id, brief)
                        typer.echo("  Brief generated from docs.")
                except Exception as e:
                    typer.echo(f"  Note: Brief generation skipped ({e})")
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

        from social_hook.trigger_git import is_git_repo

        if is_git_repo(project.repo_path):
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
    project_id: str | None = typer.Option(None, "--id", "-i", help="Project ID"),
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
    limit: int | None = typer.Option(
        None, "--limit", "-n", help="Import only the N most recent commits"
    ),
    project_id: str | None = typer.Option(None, "--id", "-i", help="Project ID"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Import historical git commits as imported decisions.

    Imports past commits so the dashboard shows the project timeline.
    Imported commits are NOT evaluated — use retrigger to evaluate them later.

    Examples:
        social-hook project import-commits
        social-hook project import-commits --branch main
        social-hook project import-commits --limit 50
        social-hook project import-commits --branch main --limit 100
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
        limit_desc = f", limit: {limit}" if limit else ""
        with spinner(f"Importing commits for '{project.name}'{branch_desc}{limit_desc}..."):
            result = import_project_commits(
                conn, project.id, project.repo_path, branch, limit=limit
            )
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
    json_mode: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Install git post-commit hook for a project.
    Example: social-hook project install-hook /path/to/repo"""
    from social_hook.setup.install import install_git_hook

    if path is None:
        path = Path.cwd()
    path = path.resolve()

    json_mode = json_mode or (ctx.obj.get("json", False) if ctx.obj else False)
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
    json_mode: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Remove git post-commit hook from a project.
    Example: social-hook project uninstall-hook /path/to/repo"""
    from social_hook.setup.install import check_git_hook_installed, uninstall_git_hook

    if path is None:
        path = Path.cwd()
    path = path.resolve()

    json_mode = json_mode or (ctx.obj.get("json", False) if ctx.obj else False)

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


@app.command("evaluate-recent")
def evaluate_recent(
    ctx: typer.Context,
    last: int = typer.Option(
        5,
        "--last",
        "-n",
        help="Number of recent un-evaluated commits to evaluate (max 5)",
    ),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: current directory)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Evaluate recent un-evaluated commits through the full pipeline.

    Finds commits with 'imported' or 'deferred_eval' decisions and runs each
    through the evaluator + drafter pipeline. Makes LLM calls. Writes decisions
    and drafts to the database. Max 5 commits per invocation.

    Examples:
        social-hook project evaluate-recent
        social-hook project evaluate-recent --last 3
        social-hook project evaluate-recent -p /path/to/repo --json
    """
    import json as json_mod

    from social_hook.cli.utils import resolve_project

    is_json = json_output or (ctx.obj or {}).get("json", False)
    dry_run = (ctx.obj or {}).get("dry_run", False)
    verbose = (ctx.obj or {}).get("verbose", False)

    last = min(max(last, 1), 5)
    repo_path = resolve_project(project_path)
    config_path_opt = (ctx.obj or {}).get("config")

    from social_hook.db.connection import init_database
    from social_hook.filesystem import get_db_path

    conn = init_database(get_db_path())
    try:
        from social_hook.db.operations import get_project_by_path

        project = get_project_by_path(conn, repo_path)
        if project is None:
            msg = f"No project registered at {repo_path}"
            if is_json:
                typer.echo(json_mod.dumps({"error": msg}))
            else:
                typer.echo(msg, err=True)
            raise typer.Exit(1)

        # Find unevaluated commits
        rows = conn.execute(
            """
            SELECT commit_hash FROM decisions
            WHERE project_id = ? AND decision IN ('imported', 'deferred_eval')
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (project.id, last),
        ).fetchall()

        hashes = [row["commit_hash"] for row in rows]
        if not hashes:
            if is_json:
                typer.echo(json_mod.dumps({"evaluated": 0, "results": []}))
            else:
                typer.echo("No unevaluated commits found.")
            return

        if not is_json:
            typer.echo(f"Evaluating {len(hashes)} commit(s)...")

        from social_hook.trigger import run_trigger

        results = []
        for commit_hash in hashes:
            try:
                exit_code = run_trigger(
                    commit_hash=commit_hash,
                    repo_path=repo_path,
                    dry_run=dry_run,
                    config_path=str(config_path_opt) if config_path_opt else None,
                    verbose=verbose,
                    trigger_source="manual",
                )
                results.append(
                    {
                        "commit_hash": commit_hash,
                        "exit_code": exit_code,
                        "status": "ok" if exit_code == 0 else "error",
                    }
                )
            except Exception as e:
                results.append(
                    {
                        "commit_hash": commit_hash,
                        "exit_code": 2,
                        "status": "error",
                        "error": str(e),
                    }
                )

        if is_json:
            typer.echo(
                json_mod.dumps(
                    {
                        "evaluated": len(results),
                        "results": results,
                    },
                    indent=2,
                )
            )
        else:
            ok_count = sum(1 for r in results if r["status"] == "ok")
            typer.echo(f"Evaluated {ok_count}/{len(results)} commits successfully.")
    finally:
        conn.close()


def _resolve_project_for_intro(project_path: str | None) -> tuple:
    """Resolve project from path or cwd. Returns (conn, project)."""
    import subprocess as sp

    from social_hook.db import (
        get_all_projects,
        get_project,
        get_project_by_origin,
        get_project_by_path,
        init_database,
    )
    from social_hook.filesystem import get_db_path

    conn = init_database(get_db_path())
    project = None

    if project_path:
        project = get_project(conn, project_path)
        if not project:
            for p in get_all_projects(conn):
                if p.id.startswith(project_path):
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
        conn.close()
        typer.echo("No project found. Provide a project ID or run from a registered repo.")
        raise typer.Exit(1)

    return conn, project


@intro_app.callback(invoke_without_command=True)
def intro_status(
    ctx: typer.Context,
    project: str | None = typer.Option(None, "--project", "-p", help="Project ID or path"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show per-platform introduction status.

    Examples:
        social-hook project intro
        social-hook project intro --json
    """
    if ctx.invoked_subcommand is not None:
        return

    import json as json_mod

    from social_hook.db.operations import get_all_platform_introduced

    conn, proj = _resolve_project_for_intro(project)
    try:
        introduced = get_all_platform_introduced(conn, proj.id)

        if json_output:
            rows = conn.execute(
                "SELECT platform, introduced, introduced_at FROM platform_introduced WHERE project_id = ?",
                (proj.id,),
            ).fetchall()
            platforms_data = {}
            for row in rows:
                platforms_data[row[0]] = {
                    "introduced": bool(row[1]),
                    "introduced_at": row[2],
                }
            typer.echo(
                json_mod.dumps({"project": proj.name, "platforms": platforms_data}, indent=2)
            )
        else:
            typer.echo(f"Introduction status for '{proj.name}':")
            if not introduced:
                typer.echo("  No platforms tracked yet.")
            else:
                for plat, is_intro in sorted(introduced.items()):
                    status = "Introduced" if is_intro else "Not introduced"
                    typer.echo(f"  {plat:15s}  {status}")
    finally:
        conn.close()


@intro_app.command("reset")
def intro_reset(
    platform: str | None = typer.Option(None, "--platform", help="Reset a specific platform"),
    project: str | None = typer.Option(None, "--project", "-p", help="Project ID or path"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Reset introduction status (next draft will be an intro post).

    Examples:
        social-hook project intro reset
        social-hook project intro reset --platform x
        social-hook project intro reset --yes
    """
    import json as json_mod

    from social_hook.db.operations import emit_data_event, reset_platform_introduced

    conn, proj = _resolve_project_for_intro(project)
    try:
        target = platform or "all platforms"
        if not yes and not typer.confirm(f"Reset introduction for {target} on '{proj.name}'?"):
            typer.echo("Cancelled.")
            return

        count = reset_platform_introduced(conn, proj.id, platform)
        emit_data_event(conn, "project", "updated", proj.id, proj.id)

        if json_output:
            typer.echo(json_mod.dumps({"reset": count, "platform": platform or "all"}))
        else:
            typer.echo(f"Reset {count} platform(s) for '{proj.name}'.")
    finally:
        conn.close()


@intro_app.command("set")
def intro_set(
    platform: str = typer.Option(..., "--platform", help="Platform to mark as introduced"),
    project: str | None = typer.Option(None, "--project", "-p", help="Project ID or path"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Mark a platform as introduced (skip intro post).

    Examples:
        social-hook project intro set --platform x
    """
    import json as json_mod

    from social_hook.db.operations import emit_data_event, set_platform_introduced

    conn, proj = _resolve_project_for_intro(project)
    try:
        set_platform_introduced(conn, proj.id, platform, True)
        emit_data_event(conn, "project", "updated", proj.id, proj.id)

        if json_output:
            typer.echo(json_mod.dumps({"platform": platform, "introduced": True}))
        else:
            typer.echo(f"Marked '{platform}' as introduced for '{proj.name}'.")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# prompt-docs subcommands
# ---------------------------------------------------------------------------


@prompt_docs_app.callback(invoke_without_command=True)
def prompt_docs_list(
    ctx: typer.Context,
    project: str | None = typer.Option(None, "--project", "-p", help="Project ID or path"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List prompt documentation files for a project.

    Examples:
        social-hook project prompt-docs
        social-hook project prompt-docs --json
        social-hook project prompt-docs -p my-project
    """
    if ctx.invoked_subcommand is not None:
        return

    import json as json_mod

    from social_hook.parsing import safe_json_loads

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn, proj = _resolve_project_for_intro(project)
    try:
        doc_paths = safe_json_loads(proj.prompt_docs, "project.prompt_docs", default=[])

        if json_output:
            typer.echo(json_mod.dumps({"project": proj.name, "prompt_docs": doc_paths}, indent=2))
        else:
            typer.echo(f"Prompt docs for '{proj.name}':")
            if not doc_paths:
                typer.echo("  (none)")
            else:
                for p in doc_paths:
                    typer.echo(f"  {p}")
    finally:
        conn.close()


@prompt_docs_app.command("add")
def prompt_docs_add(
    paths: list[str] = typer.Argument(..., help="File paths to add (relative to project root)"),
    project: str | None = typer.Option(None, "--project", "-p", help="Project ID or path"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Add files to the project's prompt documentation list.

    Examples:
        social-hook project prompt-docs add README.md docs/API.md
        social-hook project prompt-docs add --project my-proj guide.md
    """
    import json as json_mod

    from social_hook.db.operations import update_prompt_docs
    from social_hook.parsing import safe_json_loads

    conn, proj = _resolve_project_for_intro(project)
    try:
        existing = safe_json_loads(proj.prompt_docs, "project.prompt_docs", default=[])
        added = []
        for p in paths:
            if p not in existing:
                existing.append(p)
                added.append(p)

        update_prompt_docs(conn, proj.id, existing)

        if json_output:
            typer.echo(json_mod.dumps({"added": added, "prompt_docs": existing}, indent=2))
        else:
            if added:
                typer.echo(f"Added {len(added)} file(s) to prompt docs for '{proj.name}':")
                for a in added:
                    typer.echo(f"  + {a}")
            else:
                typer.echo("All paths already in prompt docs.")
    finally:
        conn.close()


@prompt_docs_app.command("remove")
def prompt_docs_remove(
    paths: list[str] = typer.Argument(..., help="File paths to remove"),
    project: str | None = typer.Option(None, "--project", "-p", help="Project ID or path"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Remove files from the project's prompt documentation list.

    Examples:
        social-hook project prompt-docs remove old-docs.md
        social-hook project prompt-docs remove --json README.md
    """
    import json as json_mod

    from social_hook.db.operations import update_prompt_docs
    from social_hook.parsing import safe_json_loads

    conn, proj = _resolve_project_for_intro(project)
    try:
        existing = safe_json_loads(proj.prompt_docs, "project.prompt_docs", default=[])
        removed = []
        for p in paths:
            if p in existing:
                existing.remove(p)
                removed.append(p)

        update_prompt_docs(conn, proj.id, existing)

        if json_output:
            typer.echo(json_mod.dumps({"removed": removed, "prompt_docs": existing}, indent=2))
        else:
            if removed:
                typer.echo(f"Removed {len(removed)} file(s) from prompt docs for '{proj.name}':")
                for r in removed:
                    typer.echo(f"  - {r}")
            else:
                typer.echo("None of the specified paths were in prompt docs.")
    finally:
        conn.close()
