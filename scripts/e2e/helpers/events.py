"""Synthetic event injection for E2E consumer tests.

Inserts realistic pipeline events into web_events without LLM calls.
Use for testing CLI output, WebSocket delivery, and toast display.
"""

import sqlite3

from social_hook.db import emit_data_event


def emit_fake_pipeline_run(
    conn: sqlite3.Connection,
    project_id: str,
    commit_hash: str = "abcd1234",
    platform: str = "x",
    content: str = "Test draft content from synthetic pipeline run.",
) -> int:
    """Insert a realistic sequence of pipeline events.

    Emits: pipeline/evaluating → decision/created → pipeline/drafting → draft/created

    Returns the count of events inserted (4).
    """
    emit_data_event(conn, "pipeline", "evaluating", commit_hash[:8], project_id)
    emit_data_event(conn, "decision", "created", f"decision_fake_{commit_hash[:8]}", project_id)
    emit_data_event(conn, "pipeline", "drafting", commit_hash[:8], project_id)
    emit_data_event(
        conn,
        "draft",
        "created",
        f"draft_fake_{commit_hash[:8]}",
        project_id,
        extra={"content": content, "platform": platform},
    )
    return 4
