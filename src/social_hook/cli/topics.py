"""CLI commands for content topic queue management."""

from __future__ import annotations

import json as json_mod
import logging
from typing import NoReturn

import typer

from social_hook.cli.utils import resolve_project
from social_hook.models.enums import TOPIC_STATUSES
from social_hook.parsing import safe_int

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


def _fail(msg: str, json_output: bool, exit_code: int = 1) -> NoReturn:
    """Print error (JSON or plain) and raise typer.Exit."""
    if json_output:
        typer.echo(json_mod.dumps({"error": msg}))
    else:
        typer.echo(msg)
    raise typer.Exit(exit_code)


@app.command("list")
def list_cmd(
    ctx: typer.Context,
    strategy: str | None = typer.Option(None, "--strategy", "-s", help="Filter by strategy name"),
    include_dismissed: bool = typer.Option(
        False, "--include-dismissed", help="Include dismissed topics in output"
    ),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List all topics, grouped by strategy.

    Shows the content topic queue with status, commit count, and priority.
    Use --strategy to filter by a specific strategy. Dismissed topics are
    hidden by default; use --include-dismissed to show them.

    Example: social-hook topics list --strategy building-public
    """
    from social_hook.db import operations as ops

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)

        if strategy:
            all_topics = ops.get_topics_by_strategy(conn, proj.id, strategy, include_dismissed=True)
        else:
            all_topics = ops.get_topics_by_project(conn, proj.id, include_dismissed=True)

        dismissed_count = sum(1 for t in all_topics if t.status == "dismissed")
        topics = (
            all_topics if include_dismissed else [t for t in all_topics if t.status != "dismissed"]
        )

        if json_output:
            typer.echo(
                json_mod.dumps(
                    {
                        "topics": [t.to_dict() for t in topics],
                        "dismissed_count": dismissed_count,
                    },
                    indent=2,
                )
            )
            return

        if not topics:
            filter_msg = f" for strategy '{strategy}'" if strategy else ""
            typer.echo(f"No topics found{filter_msg}.")
            if dismissed_count and not include_dismissed:
                typer.echo(
                    f"({dismissed_count} dismissed topic(s) hidden. Use --include-dismissed to show.)"
                )
            return

        # Group by strategy
        by_strategy: dict[str, list] = {}
        for t in topics:
            by_strategy.setdefault(t.strategy, []).append(t)

        for strat_name, strat_topics in sorted(by_strategy.items()):
            typer.echo(f"\n  {strat_name}:")
            typer.echo(
                f"  {'#':<4} {'ID':<16} {'Topic':<30} {'Status':<12} {'Commits':<9} {'Rank'}"
            )
            typer.echo("  " + "-" * 79)
            for idx, t in enumerate(strat_topics, start=1):
                tid = t.id[:14]
                topic_name = t.topic[:28]
                typer.echo(
                    f"  {f'#{idx}':<4} {tid:<16} {topic_name:<30} {t.status:<12} {t.commit_count:<9} {t.priority_rank}"
                )

        if dismissed_count and not include_dismissed:
            typer.echo(
                f"\n  ({dismissed_count} dismissed topic(s) hidden. Use --include-dismissed to show.)"
            )
    finally:
        conn.close()


@app.command()
def add(
    ctx: typer.Context,
    strategy: str = typer.Option(..., "--strategy", "-s", help="Strategy name"),
    topic: str = typer.Option(..., "--topic", "-t", help="Topic name"),
    description: str | None = typer.Option(None, "--description", "-d", help="Topic description"),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Add a new topic to the queue.

    Topics track areas of content to cover for a strategy.
    New topics start with 'uncovered' status and priority rank 0.

    Example: social-hook topics add --strategy technical --topic "evaluation pipeline" --description "How we built the evaluation system"
    """
    from social_hook.config.yaml import load_full_config
    from social_hook.db import operations as ops
    from social_hook.filesystem import generate_id
    from social_hook.models.content import ContentTopic

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)

        # Validate strategy exists in config (if config is available)
        try:
            config_path = ctx.obj.get("config") if ctx.obj else None
            config = load_full_config(str(config_path) if config_path else None)
            if config.content_strategies and strategy not in config.content_strategies:
                valid = ", ".join(sorted(config.content_strategies.keys()))
                _fail(f"Unknown strategy '{strategy}'. Available: {valid}", json_output)
        except typer.Exit:
            raise
        except Exception:
            logger.debug("Could not load config for strategy validation, skipping")

        new_topic = ContentTopic(
            id=generate_id("topic"),
            project_id=proj.id,
            strategy=strategy,
            topic=topic,
            description=description,
            created_by="user",
        )
        ops.insert_content_topic(conn, new_topic)
        ops.emit_data_event(conn, "topic", "created", new_topic.id, proj.id)

        if json_output:
            typer.echo(json_mod.dumps(new_topic.to_dict(), indent=2))
        else:
            typer.echo(f"Added topic '{topic}' to strategy '{strategy}' (ID: {new_topic.id})")
    finally:
        conn.close()


@app.command()
def reorder(
    ctx: typer.Context,
    strategy: str = typer.Option(..., "--strategy", "-s", help="Strategy name"),
    id: str = typer.Option(..., "--id", help="Topic ID"),
    rank: int = typer.Option(
        ..., "--rank", "-r", help="New priority rank (higher = more priority)"
    ),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Reorder a topic within its strategy by setting its priority rank.

    Higher rank = higher priority. Inserts topic at rank, shifts others down.

    Example: social-hook topics reorder --strategy technical --id topic_abc123 --rank 1
    """
    from social_hook.db import operations as ops

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)
    rank = safe_int(rank, 0, "rank")

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)

        topic = ops.get_topic(conn, id)
        if not topic:
            _fail(f"Topic not found: {id}", json_output)
        if topic.project_id != proj.id:
            _fail("Topic does not belong to this project", json_output)
        if topic.strategy != strategy:
            _fail(f"Topic belongs to strategy '{topic.strategy}', not '{strategy}'", json_output)

        ops.update_topic_priority(conn, id, rank)
        ops.emit_data_event(conn, "topic", "updated", id, proj.id)

        if json_output:
            updated = ops.get_topic(conn, id)
            typer.echo(
                json_mod.dumps(updated.to_dict() if updated else {"id": id, "rank": rank}, indent=2)
            )
        else:
            typer.echo(f"Topic '{topic.topic}' moved to rank {rank}.")
    finally:
        conn.close()


@app.command()
def status(
    ctx: typer.Context,
    topic_id: str = typer.Argument(..., help="Topic ID"),
    new_status: str = typer.Argument(
        ..., help="New status (uncovered, holding, partial, covered, dismissed)"
    ),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Set a topic's status.

    Valid statuses: uncovered, holding, partial, covered, dismissed.

    Example: social-hook topics status topic_abc123 covered
    """
    from social_hook.db import operations as ops

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    if new_status not in TOPIC_STATUSES:
        valid = ", ".join(sorted(TOPIC_STATUSES))
        _fail(f"Invalid status: {new_status}. Valid: {valid}", json_output)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)

        topic = ops.get_topic(conn, topic_id)
        if not topic:
            _fail(f"Topic not found: {topic_id}", json_output)
        if topic.project_id != proj.id:
            _fail("Topic does not belong to this project", json_output)

        ops.update_topic_status(conn, topic_id, new_status)
        ops.emit_data_event(conn, "topic", "updated", topic_id, proj.id)

        if json_output:
            updated = ops.get_topic(conn, topic_id)
            typer.echo(
                json_mod.dumps(
                    updated.to_dict() if updated else {"id": topic_id, "status": new_status},
                    indent=2,
                )
            )
        else:
            typer.echo(f"Topic '{topic.topic}' status set to '{new_status}'.")
    finally:
        conn.close()


@app.command()
def dismiss(
    ctx: typer.Context,
    topic_id: str = typer.Argument(..., help="Topic ID to dismiss"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Dismiss a topic so no posts are created about it.

    Dismissed topics are hidden from the queue and will not be recreated
    by auto-seeding. Use 'topics list --include-dismissed' to see them.

    Example: social-hook topics dismiss topic_abc123
    Example: social-hook topics dismiss topic_abc123 --yes  (skip confirmation)
    """
    from social_hook.db import operations as ops

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)

        topic = ops.get_topic(conn, topic_id)
        if not topic:
            _fail(f"Topic not found: {topic_id}", json_output)
        if topic.project_id != proj.id:
            _fail("Topic does not belong to this project", json_output)
        if topic.status == "dismissed":
            _fail(f"Topic '{topic.topic}' is already dismissed.", json_output)

        if not yes and not typer.confirm(f"Dismiss topic '{topic.topic}'?"):
            typer.echo("Cancelled.")
            return

        ops.update_topic_status(conn, topic_id, "dismissed")
        ops.emit_data_event(conn, "topic", "updated", topic_id, proj.id)

        if json_output:
            typer.echo(json_mod.dumps({"dismissed": True, "topic_id": topic_id}, indent=2))
        else:
            typer.echo(f"Topic '{topic.topic}' dismissed.")
    finally:
        conn.close()


@app.command("draft-now")
def draft_now(
    ctx: typer.Context,
    topic_id: str = typer.Argument(..., help="Topic ID to draft"),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Force-draft a held or uncovered topic via LLM evaluation and drafting.

    Topics with status 'holding' or 'uncovered' can be force-drafted. Runs the
    full evaluation and drafting pipeline (same as the web UI "Draft Now" button).
    This is an LLM operation — may take a moment.

    Example: social-hook topics draft-now topic_abc123
    """
    from social_hook.config.yaml import load_full_config
    from social_hook.db import operations as ops
    from social_hook.topics import force_draft_topic

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)

        topic = ops.get_topic(conn, topic_id)
        if not topic:
            _fail(f"Topic not found: {topic_id}", json_output)
        if topic.project_id != proj.id:
            _fail("Topic does not belong to this project", json_output)
        if topic.status not in ("holding", "uncovered"):
            _fail(
                f"Topic has status '{topic.status}'. Only held or uncovered topics can be force-drafted.",
                json_output,
            )

        # Resolve strategy: topic.strategy, then config.content_strategy fallback
        strategy = topic.strategy
        config_path = ctx.obj.get("config") if ctx.obj else None
        config = load_full_config(str(config_path) if config_path else None)

        if not strategy:
            strategy = getattr(config, "content_strategy", None) or ""
        if not strategy:
            _fail(
                "Topic has no strategy and no content_strategy configured. Set a strategy first.",
                json_output,
            )

        if not json_output:
            typer.echo(f"Creating draft for topic '{topic.topic}'...")

        cycle_id = force_draft_topic(conn, config, proj.id, topic_id, strategy)

        if cycle_id is None:
            _fail("Failed to create draft. Check logs for details.", json_output, exit_code=2)

        if json_output:
            typer.echo(
                json_mod.dumps(
                    {
                        "topic_id": topic_id,
                        "cycle_id": cycle_id,
                    },
                    indent=2,
                )
            )
        else:
            typer.echo(f"Evaluation cycle created: {cycle_id}")
    finally:
        conn.close()
