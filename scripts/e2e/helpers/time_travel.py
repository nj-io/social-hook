"""Time simulation for E2E scenarios.

Backdates DB timestamps to simulate time progression without waiting.
Use when testing time-dependent behavior: rate limits (daily caps),
scheduling gaps (min_gap_minutes), posting history ("days since last
post"), narrative debt, and arc stagnation detection.

Pattern: after each run_trigger() call in a setup loop, call
backdate_recent_records() to shift the new records into the past.
Subsequent evaluator calls see a realistic timeline.

Example — simulate 20 commits arriving one per day::

    for i, commit_hash in enumerate(commits):
        run_trigger(commit_hash, repo_path)
        days_ago = len(commits) - i  # first commit = oldest
        backdate_recent_records(harness, days_ago, since=before_trigger)
"""

from datetime import datetime, timedelta, timezone


def backdate_recent_records(
    harness,
    days_ago: int,
    since: str | None = None,
) -> int:
    """Backdate all recent DB records to simulate time passage.

    Updates created_at/posted_at timestamps on decisions, drafts, posts,
    evaluation_cycles, content_topics, and usage_log rows that were
    created after ``since`` (or all records for the project if None).

    Args:
        harness: E2EHarness with ``conn`` and ``project_id``.
        days_ago: How many days in the past to set timestamps.
        since: ISO timestamp — only records created after this are
            backdated. Use ``datetime.now(timezone.utc).isoformat()``
            captured before a run_trigger() call. If None, backdates
            all records for the project.

    Returns:
        Total number of rows updated across all tables.
    """
    target_time = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    conn = harness.conn
    project_id = harness.project_id
    total = 0

    tables_and_columns = [
        ("decisions", "created_at"),
        ("drafts", "created_at"),
        ("posts", "posted_at"),
        ("evaluation_cycles", "created_at"),
        ("content_topics", "created_at"),
        ("content_topics", "last_commit_at"),
        ("usage_log", "created_at"),
    ]

    for table, column in tables_and_columns:
        if since:
            result = conn.execute(
                f"UPDATE {table} SET {column} = ? "  # noqa: S608
                f"WHERE project_id = ? AND {column} > ?",
                (target_time, project_id, since),
            )
        else:
            result = conn.execute(
                f"UPDATE {table} SET {column} = ? WHERE project_id = ?",  # noqa: S608
                (target_time, project_id),
            )
        total += result.rowcount

    conn.commit()
    return total


def capture_timestamp() -> str:
    """Capture current UTC timestamp for use as ``since`` parameter.

    Call this immediately before ``run_trigger()`` to mark the boundary
    between pre-existing and newly created records::

        before = capture_timestamp()
        run_trigger(commit_hash, repo_path)
        backdate_recent_records(harness, days_ago=5, since=before)
    """
    return datetime.now(timezone.utc).isoformat()
