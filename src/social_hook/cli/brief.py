"""CLI commands for project brief management."""

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


@app.command()
def show(
    ctx: typer.Context,
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """View the project brief.

    Shows the structured project summary used by the evaluator and drafter
    for context. Sections: What It Does, Key Capabilities, Technical
    Architecture, Current State.

    Example: social-hook brief show
    """
    from social_hook.db import operations as ops

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)
        summary = ops.get_project_summary(conn, proj.id)

        if json_output:
            typer.echo(
                json_mod.dumps(
                    {
                        "project": proj.name,
                        "brief": summary,
                        "has_brief": summary is not None,
                    },
                    indent=2,
                )
            )
            return

        if not summary:
            typer.echo(f"No brief found for '{proj.name}'.")
            typer.echo("Run 'social-hook discover <project-id>' to generate one,")
            typer.echo("or 'social-hook brief edit' to write one manually.")
            return

        typer.echo(f"Brief for '{proj.name}':\n")
        typer.echo(summary)
    finally:
        conn.close()


@app.command()
def edit(
    ctx: typer.Context,
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Open the project brief in $EDITOR.

    Loads the current brief into a temporary file, opens in your editor
    (VISUAL -> EDITOR -> vi), and saves changes back to the database.

    Example: social-hook brief edit
    """
    import os
    import subprocess
    import tempfile

    from social_hook.db import operations as ops

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)
        summary = ops.get_project_summary(conn, proj.id) or ""

        # Find editor: VISUAL -> EDITOR -> vi
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", prefix="brief-", delete=False
        ) as tmp:
            tmp.write(summary)
            tmp_path = tmp.name

        try:
            result = subprocess.run([editor, tmp_path])
            if result.returncode != 0:
                msg = f"Editor exited with code {result.returncode}"
                if json_output:
                    typer.echo(json_mod.dumps({"error": msg}))
                else:
                    typer.echo(msg)
                raise typer.Exit(1)

            with open(tmp_path, encoding="utf-8") as f:
                new_content = f.read()

            if new_content == summary:
                typer.echo("No changes.")
                return
        finally:
            os.unlink(tmp_path)

        ops.update_project_summary(conn, proj.id, new_content)
        ops.emit_data_event(conn, "project", "updated", proj.id, proj.id)

        if json_output:
            typer.echo(json_mod.dumps({"edited": True, "project": proj.name}, indent=2))
        else:
            typer.echo(f"Brief updated for '{proj.name}'.")
    finally:
        conn.close()
