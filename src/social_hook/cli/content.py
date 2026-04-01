"""CLI commands for content suggestion management."""

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
def suggest(
    ctx: typer.Context,
    idea: str = typer.Option(..., "--idea", "-i", help="Content idea to suggest"),
    strategy: str | None = typer.Option(
        None,
        "--strategy",
        "-s",
        help="Strategy to suggest for (omit to let evaluator decide)",
    ),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Suggest content for the project.

    Creates a content suggestion. If --strategy is omitted, the evaluator
    will decide which strategy fits best. This is an LLM operation when
    the evaluator runs.

    Example: social-hook content suggest --idea "Show the new dashboard feature"
    Example: social-hook content suggest --strategy brand-primary --idea "Launch announcement"
    """
    from social_hook.db import operations as ops
    from social_hook.filesystem import generate_id
    from social_hook.models.content import ContentSuggestion

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)

        suggestion = ContentSuggestion(
            id=generate_id("suggestion"),
            project_id=proj.id,
            idea=idea,
            strategy=strategy,
            source="operator",
        )
        ops.insert_content_suggestion(conn, suggestion)
        ops.emit_data_event(conn, "suggestion", "created", suggestion.id, proj.id)

        if json_output:
            typer.echo(json_mod.dumps(suggestion.to_dict(), indent=2))
        else:
            if strategy:
                typer.echo(f"Suggestion created for strategy '{strategy}': {suggestion.id}")
            else:
                typer.echo(f"Suggestion created (evaluator will assign strategy): {suggestion.id}")
    finally:
        conn.close()


@app.command("list")
def list_cmd(
    ctx: typer.Context,
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List previous content suggestions with status.

    Shows all content suggestions for the project with their current status
    (pending, evaluated, drafted, dismissed).

    Example: social-hook content list
    """
    from social_hook.db import operations as ops

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)
        suggestions = ops.get_suggestions_by_project(conn, proj.id)

        if json_output:
            typer.echo(
                json_mod.dumps(
                    {"suggestions": [s.to_dict() for s in suggestions]},
                    indent=2,
                )
            )
            return

        if not suggestions:
            typer.echo("No content suggestions found.")
            typer.echo("Use 'social-hook content suggest --idea \"...\"' to create one.")
            return

        typer.echo(f"{'ID':<18} {'Strategy':<20} {'Status':<12} {'Idea'}")
        typer.echo("-" * 80)
        for s in suggestions:
            sid = s.id[:16]
            strat = (s.strategy or "auto")[:18]
            idea_preview = s.idea[:35]
            typer.echo(f"{sid:<18} {strat:<20} {s.status:<12} {idea_preview}")
    finally:
        conn.close()


@app.command()
def dismiss(
    ctx: typer.Context,
    suggestion_id: str = typer.Argument(..., help="Suggestion ID to dismiss"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Dismiss a content suggestion.

    Marks the suggestion as dismissed. This is a destructive operation.

    Example: social-hook content dismiss suggestion_abc123 --yes
    """
    from social_hook.db import operations as ops

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)

        # Look up suggestion
        rows = conn.execute(
            "SELECT * FROM content_suggestions WHERE id = ?", (suggestion_id,)
        ).fetchall()
        if not rows:
            msg = f"Suggestion not found: {suggestion_id}"
            if json_output:
                typer.echo(json_mod.dumps({"error": msg}))
            else:
                typer.echo(msg)
            raise typer.Exit(1)

        from social_hook.models.content import ContentSuggestion

        suggestion = ContentSuggestion.from_dict(dict(rows[0]))

        if suggestion.project_id != proj.id:
            msg = "Suggestion does not belong to this project"
            if json_output:
                typer.echo(json_mod.dumps({"error": msg}))
            else:
                typer.echo(msg)
            raise typer.Exit(1)

        if suggestion.status == "dismissed":
            typer.echo("Suggestion is already dismissed.")
            return

        if not yes:
            typer.echo(f"Suggestion: {suggestion.idea[:60]}")
            if not typer.confirm("Dismiss this suggestion?"):
                typer.echo("Cancelled.")
                return

        ops.update_suggestion_status(conn, suggestion_id, "dismissed")
        ops.emit_data_event(conn, "suggestion", "updated", suggestion_id, proj.id)

        if json_output:
            typer.echo(
                json_mod.dumps(
                    {
                        "dismissed": True,
                        "suggestion_id": suggestion_id,
                    },
                    indent=2,
                )
            )
        else:
            typer.echo(f"Suggestion {suggestion_id} dismissed.")
    finally:
        conn.close()


@app.command()
def combine(
    ctx: typer.Context,
    topics: list[str] = typer.Option(
        ..., "--topics", "-t", help="Topic IDs to combine (at least 2)"
    ),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Combine 2+ held brand-primary topics into one draft.

    Creates a single draft from multiple held topics. Topics must belong
    to the brand-primary strategy and be in 'holding' status.
    This is an LLM operation.

    Example: social-hook content combine --topics topic_abc --topics topic_def
    """
    from social_hook.content.operations import combine_candidates

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)

        if not json_output:
            typer.echo(f"Combining {len(topics)} topics...")

        try:
            from social_hook.config.yaml import load_full_config

            config_path = ctx.obj.get("config") if ctx.obj else None
            config = load_full_config(str(config_path) if config_path else None)
            draft_id = combine_candidates(conn, config, topics, proj.id)
        except ValueError as e:
            if json_output:
                typer.echo(json_mod.dumps({"error": str(e)}))
            else:
                typer.echo(f"Error: {e}")
            raise typer.Exit(1) from None

        from social_hook.db import operations as ops

        ops.emit_data_event(conn, "draft", "created", draft_id, proj.id)

        if json_output:
            typer.echo(
                json_mod.dumps(
                    {
                        "draft_id": draft_id,
                        "topic_ids": topics,
                    },
                    indent=2,
                )
            )
        else:
            typer.echo(f"Combined draft created: {draft_id}")
    finally:
        conn.close()


@app.command("hero-launch")
def hero_launch(
    ctx: typer.Context,
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Trigger a hero launch draft using full project context.

    Assembles the full project brief, all held brand-primary candidates,
    and all covered topics to create a comprehensive launch draft.
    This is an LLM operation.

    Example: social-hook content hero-launch --project /path/to/repo
    """
    from social_hook.content.operations import trigger_hero_launch
    from social_hook.db import operations as ops

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)

        if not json_output:
            typer.echo(f"Triggering hero launch for '{proj.name}'...")

        try:
            from social_hook.config.yaml import load_full_config

            config_path = ctx.obj.get("config") if ctx.obj else None
            config = load_full_config(str(config_path) if config_path else None)
            draft_id = trigger_hero_launch(conn, config, proj.id, proj.repo_path)
        except Exception as e:
            logger.error("Hero launch failed: %s", e, exc_info=True)
            if json_output:
                typer.echo(json_mod.dumps({"error": str(e)}))
            else:
                typer.echo(f"Error: {e}")
            raise typer.Exit(2) from None

        ops.emit_data_event(conn, "draft", "created", draft_id, proj.id)

        if json_output:
            typer.echo(
                json_mod.dumps(
                    {
                        "draft_id": draft_id,
                        "project": proj.name,
                    },
                    indent=2,
                )
            )
        else:
            typer.echo(f"Hero launch draft created: {draft_id}")
    finally:
        conn.close()
