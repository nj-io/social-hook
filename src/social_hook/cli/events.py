"""CLI command for monitoring live pipeline events."""

import contextlib
import json as json_mod
import sqlite3
import time
from datetime import datetime, timezone

import typer


def events(
    ctx: typer.Context,
    since: int = typer.Option(
        -1,
        "--since",
        help="Start from event ID (0=all history, -1=current, default: current)",
    ),
    entity: str | None = typer.Option(
        None, "--entity", "-e", help="Filter by entity type (pipeline, decision, draft)"
    ),
    follow: bool = typer.Option(
        True,
        "--follow/--no-follow",
        "-f",
        help="Follow new events in real time",
    ),
    json_mode: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Watch live pipeline events (commits, decisions, drafts).

    Example: social-hook events --json
    """
    from social_hook.db.connection import ResilientConnection, init_database
    from social_hook.filesystem import get_db_path

    json_mode = json_mode or (ctx.obj.get("json", False) if ctx.obj else False)
    db_path = get_db_path()
    init_database(db_path)  # ensure schema exists

    rc = ResilientConnection(db_path)
    conn = rc.conn

    try:
        if since == -1:
            row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM web_events").fetchone()
            last_id = row[0]
        else:
            last_id = since

        if not follow:
            last_id = _print_events(conn, last_id, entity, json_mode)
            return

        if not json_mode:
            typer.echo("Watching for events... (Ctrl+C to stop)\n")

        with contextlib.suppress(KeyboardInterrupt):
            while True:
                conn = rc.check()
                # If MAX(id) went backwards, DB was replaced — reset cursor
                row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM web_events").fetchone()
                max_id = row[0]
                if max_id < last_id:
                    last_id = max_id
                last_id = _print_events(conn, last_id, entity, json_mode)
                time.sleep(1)
    finally:
        rc.close()


def _print_events(
    conn: sqlite3.Connection,
    last_id: int,
    entity_filter: str | None,
    json_mode: bool,
) -> int:
    """Print new events since last_id. Returns the new last_id."""
    rows = conn.execute(
        "SELECT id, type, data, created_at FROM web_events WHERE id > ? ORDER BY id",
        (last_id,),
    ).fetchall()

    for row in rows:
        event_id, event_type, data_str, created_at = row
        last_id = event_id

        if event_type != "data_change":
            continue

        try:
            data = json_mod.loads(data_str)
        except json_mod.JSONDecodeError:
            continue

        ent = data.get("entity", "")
        if entity_filter and ent != entity_filter:
            continue

        # Suppress noisy internal events in human mode
        if not json_mode and ent in ("task",):
            continue

        if json_mode:
            typer.echo(json_mod.dumps(data))
        else:
            _print_human(data, created_at)

    return last_id


def _print_human(data: dict, created_at: str | None) -> None:
    """Print a single event in human-readable format."""
    entity = data.get("entity", "?")
    action = data.get("action", "?")
    entity_id = data.get("entity_id", "")
    content = data.get("content", "")
    platform = data.get("platform", "")

    # Format timestamp
    ts = ""
    if created_at:
        try:
            dt = datetime.fromisoformat(created_at)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            ts = dt.strftime("%H:%M:%S")
        except (ValueError, TypeError):
            ts = ""

    # Entity-specific formatting
    if entity == "pipeline":
        label = "evaluating" if action == "evaluating" else "drafting"
        typer.echo(f"[{ts}] [{entity:<8}] {label:<12} {entity_id}")
    elif entity == "draft" and action == "created":
        preview = f'  "{content[:60]}..."' if content else ""
        plat = f"  ({platform})" if platform else ""
        typer.echo(f"[{ts}] [{entity:<8}] {action:<12} {entity_id[:16]}{plat}{preview}")
    elif entity == "decision":
        typer.echo(f"[{ts}] [{entity:<8}] {action:<12} {entity_id[:16]}")
    else:
        typer.echo(f"[{ts}] [{entity:<8}] {action:<12} {entity_id[:16]}")
