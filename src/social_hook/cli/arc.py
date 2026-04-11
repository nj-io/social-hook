"""CLI commands for narrative arc management."""

import os

import typer

app = typer.Typer(no_args_is_help=True)


def _resolve_project(project: str | None = None) -> str:
    """Resolve project path, defaulting to cwd."""
    return os.path.realpath(project or os.getcwd())


@app.command("list")
def list_cmd(
    project: str | None = typer.Option(None, "--project", "-p", help="Project path (default: cwd)"),
    status: str | None = typer.Option(
        None, "--status", "-s", help="Filter by status: active, completed, abandoned, all"
    ),
):
    """List narrative arcs for a project.

    Shows ID, status, post count, and theme for each arc.
    Defaults to active arcs only; use --status to filter
    (active, completed, abandoned, all).

    Example: social-hook arc list
    Example: social-hook arc list --status all
    """
    from social_hook.db import operations as ops
    from social_hook.db.connection import init_database
    from social_hook.filesystem import get_db_path

    repo_path = _resolve_project(project)
    conn = init_database(get_db_path())
    try:
        proj = ops.get_project_by_path(conn, repo_path)
        if not proj:
            typer.echo(f"No registered project at {repo_path}", err=True)
            raise typer.Exit(1)

        filter_status = None if status == "all" else (status or "active")
        arcs = ops.get_arcs_by_project(conn, proj.id, status=filter_status)

        if not arcs:
            label = filter_status or "any"
            typer.echo(f"No {label} arcs found.")
            return

        typer.echo(f"{'ID':<16} {'Status':<12} {'Posts':>5}  {'Theme'}")
        typer.echo("-" * 65)
        for a in arcs:
            typer.echo(f"{a.id[:14]:<16} {a.status:<12} {a.post_count:>5}  {a.theme}")
    finally:
        conn.close()


@app.command()
def create(
    theme: str = typer.Argument(..., help="Theme/topic for the narrative arc"),
    project: str | None = typer.Option(None, "--project", "-p", help="Project path (default: cwd)"),
    notes: str | None = typer.Option(None, "--notes", "-n", help="Optional notes"),
):
    """Create a new narrative arc.

    Arcs give the LLM a thematic thread to weave through posts.
    A project can have at most 3 active arcs; complete or
    abandon an existing arc to make room.

    Example: social-hook arc create "WebSocket migration"
    Example: social-hook arc create "Performance sprint" --notes "Q2 focus"
    """
    from social_hook.db import operations as ops
    from social_hook.db.connection import init_database
    from social_hook.errors import MaxArcsError
    from social_hook.filesystem import get_db_path
    from social_hook.narrative.arcs import create_arc, update_arc

    repo_path = _resolve_project(project)
    conn = init_database(get_db_path())
    try:
        proj = ops.get_project_by_path(conn, repo_path)
        if not proj:
            typer.echo(f"No registered project at {repo_path}", err=True)
            raise typer.Exit(1)

        try:
            arc_id = create_arc(conn, proj.id, theme)
        except MaxArcsError:
            typer.echo("Maximum 3 active arcs. Complete or abandon one first.", err=True)
            raise typer.Exit(1) from None

        if notes:
            update_arc(conn, arc_id, notes=notes)

        typer.echo(f"Created arc: {arc_id}")
        typer.echo(f"  Theme: {theme}")
    finally:
        conn.close()


@app.command()
def complete(
    arc_id: str = typer.Argument(..., help="Arc ID to complete"),
    notes: str | None = typer.Option(None, "--notes", "-n", help="Optional completion notes"),
):
    """Mark a narrative arc as completed.

    Completed arcs are no longer included in the LLM evaluation
    context. The post count is preserved. Use 'arc resume' to
    reactivate a completed arc later (subject to the 3-arc limit).

    Example: social-hook arc complete arc_abc123
    """
    from social_hook.db import operations as ops
    from social_hook.db.connection import init_database
    from social_hook.filesystem import get_db_path
    from social_hook.narrative.arcs import update_arc

    conn = init_database(get_db_path())
    try:
        arc = ops.get_arc(conn, arc_id)
        if not arc:
            typer.echo(f"Arc not found: {arc_id}", err=True)
            raise typer.Exit(1)

        if arc.status != "active":
            typer.echo(f"Arc is already {arc.status}.", err=True)
            raise typer.Exit(1)

        update_arc(conn, arc_id, status="completed", notes=notes)
        typer.echo(f"Completed arc: {arc.theme}")
    finally:
        conn.close()


@app.command()
def resume(
    arc_id: str = typer.Argument(..., help="Arc ID to resume"),
):
    """Resume a completed or abandoned arc.

    Moves the arc back to active status so it is included in
    future LLM evaluations. Fails if 3 arcs are already active.

    Example: social-hook arc resume arc_abc123
    """
    from social_hook.db import operations as ops
    from social_hook.db.connection import init_database
    from social_hook.errors import MaxArcsError
    from social_hook.filesystem import get_db_path
    from social_hook.narrative.arcs import resume_arc

    conn = init_database(get_db_path())
    try:
        arc = ops.get_arc(conn, arc_id)
        if not arc:
            typer.echo(f"Arc not found: {arc_id}", err=True)
            raise typer.Exit(1) from None

        try:
            resume_arc(conn, arc_id, arc.project_id)
        except MaxArcsError:
            typer.echo("Maximum 3 active arcs. Complete or abandon one first.", err=True)
            raise typer.Exit(1) from None
        except ValueError as e:
            typer.echo(str(e), err=True)
            raise typer.Exit(1) from None

        typer.echo(f"Resumed arc: {arc.theme}")
    finally:
        conn.close()


@app.command()
def abandon(
    arc_id: str = typer.Argument(..., help="Arc ID to abandon"),
    notes: str | None = typer.Option(None, "--notes", "-n", help="Optional notes"),
):
    """Mark a narrative arc as abandoned.

    Abandoned arcs are removed from the LLM evaluation context.
    Unlike completed arcs, abandonment signals the theme was
    dropped rather than concluded. Use 'arc resume' to reactivate.

    Example: social-hook arc abandon arc_abc123
    """
    from social_hook.db import operations as ops
    from social_hook.db.connection import init_database
    from social_hook.filesystem import get_db_path
    from social_hook.narrative.arcs import update_arc

    conn = init_database(get_db_path())
    try:
        arc = ops.get_arc(conn, arc_id)
        if not arc:
            typer.echo(f"Arc not found: {arc_id}", err=True)
            raise typer.Exit(1)

        if arc.status != "active":
            typer.echo(f"Arc is already {arc.status}.", err=True)
            raise typer.Exit(1)

        update_arc(conn, arc_id, status="abandoned", notes=notes)
        typer.echo(f"Abandoned arc: {arc.theme}")
    finally:
        conn.close()
