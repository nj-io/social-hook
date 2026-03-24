"""CLI commands for content topic queue management."""

import json as json_mod
import logging

import typer

from social_hook.cli.utils import resolve_project
from social_hook.models import TOPIC_STATUSES
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


@app.command("list")
def list_cmd(
    ctx: typer.Context,
    strategy: str | None = typer.Option(None, "--strategy", "-s", help="Filter by strategy name"),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List all topics, grouped by strategy.

    Shows the content topic queue with status, commit count, and priority.
    Use --strategy to filter by a specific strategy.

    Example: social-hook topics list --strategy building-public
    """
    from social_hook.db import operations as ops

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)

        if strategy:
            topics = ops.get_topics_by_strategy(conn, proj.id, strategy)
        else:
            # Get all topics for the project
            rows = conn.execute(
                """
                SELECT * FROM content_topics
                WHERE project_id = ?
                ORDER BY strategy, priority_rank DESC, created_at ASC
                """,
                (proj.id,),
            ).fetchall()
            from social_hook.models import ContentTopic

            topics = [ContentTopic.from_dict(dict(r)) for r in rows]

        if json_output:
            typer.echo(
                json_mod.dumps(
                    {"topics": [t.to_dict() for t in topics]},
                    indent=2,
                )
            )
            return

        if not topics:
            filter_msg = f" for strategy '{strategy}'" if strategy else ""
            typer.echo(f"No topics found{filter_msg}.")
            return

        # Group by strategy
        by_strategy: dict[str, list] = {}
        for t in topics:
            by_strategy.setdefault(t.strategy, []).append(t)

        for strat_name, strat_topics in sorted(by_strategy.items()):
            typer.echo(f"\n  {strat_name}:")
            typer.echo(f"  {'ID':<16} {'Topic':<30} {'Status':<12} {'Commits':<9} {'Rank'}")
            typer.echo("  " + "-" * 75)
            for t in strat_topics:
                tid = t.id[:14]
                topic_name = t.topic[:28]
                typer.echo(
                    f"  {tid:<16} {topic_name:<30} {t.status:<12} {t.commit_count:<9} {t.priority_rank}"
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
    from social_hook.db import operations as ops
    from social_hook.filesystem import generate_id
    from social_hook.models import ContentTopic

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)

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
            msg = f"Topic not found: {id}"
            if json_output:
                typer.echo(json_mod.dumps({"error": msg}))
            else:
                typer.echo(msg)
            raise typer.Exit(1)

        if topic.project_id != proj.id:
            msg = "Topic does not belong to this project"
            if json_output:
                typer.echo(json_mod.dumps({"error": msg}))
            else:
                typer.echo(msg)
            raise typer.Exit(1)

        if topic.strategy != strategy:
            msg = f"Topic belongs to strategy '{topic.strategy}', not '{strategy}'"
            if json_output:
                typer.echo(json_mod.dumps({"error": msg}))
            else:
                typer.echo(msg)
            raise typer.Exit(1)

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
    new_status: str = typer.Argument(..., help="New status (uncovered, holding, partial, covered)"),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Set a topic's status.

    Valid statuses: uncovered, holding, partial, covered.

    Example: social-hook topics status topic_abc123 covered
    """
    from social_hook.db import operations as ops

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    if new_status not in TOPIC_STATUSES:
        valid = ", ".join(sorted(TOPIC_STATUSES))
        msg = f"Invalid status: {new_status}. Valid: {valid}"
        if json_output:
            typer.echo(json_mod.dumps({"error": msg}))
        else:
            typer.echo(msg)
        raise typer.Exit(1)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)

        topic = ops.get_topic(conn, topic_id)
        if not topic:
            msg = f"Topic not found: {topic_id}"
            if json_output:
                typer.echo(json_mod.dumps({"error": msg}))
            else:
                typer.echo(msg)
            raise typer.Exit(1)

        if topic.project_id != proj.id:
            msg = "Topic does not belong to this project"
            if json_output:
                typer.echo(json_mod.dumps({"error": msg}))
            else:
                typer.echo(msg)
            raise typer.Exit(1)

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


@app.command("draft-now")
def draft_now(
    ctx: typer.Context,
    topic_id: str = typer.Argument(..., help="Topic ID to draft"),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Force a draft on a held topic.

    Creates a draft from the topic's content, bypassing normal scheduling.
    This is an LLM operation — may take a moment.

    Example: social-hook topics draft-now topic_abc123
    """
    from social_hook.db import operations as ops
    from social_hook.filesystem import generate_id
    from social_hook.models import Decision, Draft, EvaluationCycle

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)

        topic = ops.get_topic(conn, topic_id)
        if not topic:
            msg = f"Topic not found: {topic_id}"
            if json_output:
                typer.echo(json_mod.dumps({"error": msg}))
            else:
                typer.echo(msg)
            raise typer.Exit(1)

        if topic.project_id != proj.id:
            msg = "Topic does not belong to this project"
            if json_output:
                typer.echo(json_mod.dumps({"error": msg}))
            else:
                typer.echo(msg)
            raise typer.Exit(1)

        if not json_output:
            typer.echo(f"Creating draft for topic '{topic.topic}'...")

        # Create evaluation cycle
        cycle_id = generate_id("cycle")
        cycle = EvaluationCycle(
            id=cycle_id,
            project_id=proj.id,
            trigger_type="draft_now",
            trigger_ref=topic_id,
        )
        ops.insert_evaluation_cycle(conn, cycle)

        # Create decision
        decision_id = generate_id("decision")
        context = f"Topic: {topic.topic}"
        if topic.description:
            context += f"\nDescription: {topic.description}"
        decision = Decision(
            id=decision_id,
            project_id=proj.id,
            commit_hash=f"topic:{topic_id}",
            decision="draft",
            reasoning=f"Forced draft for topic: {topic.topic}",
            commit_message=context,
            trigger_source="draft_now",
        )
        ops.insert_decision(conn, decision)

        # Create draft
        draft_id = generate_id("draft")
        draft = Draft(
            id=draft_id,
            project_id=proj.id,
            decision_id=decision_id,
            platform="preview",
            content=context,
            status="draft",
            evaluation_cycle_id=cycle_id,
        )
        ops.insert_draft(conn, draft)

        ops.emit_data_event(conn, "draft", "created", draft_id, proj.id)

        if json_output:
            typer.echo(
                json_mod.dumps(
                    {
                        "draft_id": draft_id,
                        "topic_id": topic_id,
                        "cycle_id": cycle_id,
                    },
                    indent=2,
                )
            )
        else:
            typer.echo(f"Draft created: {draft_id}")
    finally:
        conn.close()
