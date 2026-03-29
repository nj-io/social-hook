"""Seed demo data for rate limit web UI testing.

Usage (from worktree root):
    PYTHONPATH=$(pwd)/src python3 scripts/seed_rate_limits_demo.py

Seeds: 1 project, 5 auto usage_log entries (simulating past evaluations),
1 manual usage_log entry, 2 deferred_eval decisions, and 3 pending drafts.
This gives the rate limit dashboard card something to display.
"""

from datetime import datetime, timedelta, timezone

from social_hook.db import operations as ops
from social_hook.db.connection import init_database
from social_hook.filesystem import generate_id, get_db_path
from social_hook.models.core import Decision, Draft, Project
from social_hook.models.infra import UsageLog
from social_hook.models.narrative import Lifecycle


def main():
    db_path = get_db_path()
    conn = init_database(db_path)

    # Check if already seeded
    existing = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    if existing > 0:
        print(f"DB already has {existing} project(s). Skipping seed.")
        print(
            "Use: PYTHONPATH=$(pwd)/src python3 -m social_hook snapshot restore pre-rate-limit-test"
        )
        conn.close()
        return

    # 1. Register a project
    project = Project(
        id=generate_id("project"),
        name="social-hook",
        repo_path="/Users/neil/dev/social-media-auto-hook",
    )
    ops.insert_project(conn, project)

    lifecycle = Lifecycle(project_id=project.id, phase="build")
    ops.insert_lifecycle(conn, lifecycle)
    print(f"Registered project: {project.name} ({project.id})")

    # 2. Seed usage_log entries (5 auto evals spread over today)
    now = datetime.now(timezone.utc)
    for i in range(5):
        _ts = now - timedelta(minutes=90 - i * 15)  # noqa: F841 — used after stash apply
        usage = UsageLog(
            id=generate_id("usage"),
            operation_type="evaluate",
            model="anthropic/claude-opus-4-5",
            input_tokens=2000 + i * 500,
            output_tokens=800 + i * 100,
            cache_read_tokens=0,
            cache_creation_tokens=0,
            cost_cents=3.5 + i * 0.8,
            project_id=project.id,
            commit_hash=f"abc{i:04d}",
            trigger_source="auto",
        )
        ops.insert_usage(conn, usage)
    print("Seeded 5 auto evaluation usage_log entries")

    # 3. Seed 1 manual eval
    usage = UsageLog(
        id=generate_id("usage"),
        operation_type="evaluate",
        model="anthropic/claude-opus-4-5",
        input_tokens=3000,
        output_tokens=1200,
        cache_read_tokens=0,
        cache_creation_tokens=0,
        cost_cents=5.2,
        project_id=project.id,
        commit_hash="manual001",
        trigger_source="manual",
    )
    ops.insert_usage(conn, usage)
    print("Seeded 1 manual evaluation usage_log entry")

    # 4. Seed 2 deferred_eval decisions
    for i in range(2):
        d = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash=f"deferred{i:03d}",
            decision="deferred_eval",
            reasoning="Daily limit reached: 15/15" if i == 0 else "Gap not elapsed: 4m remaining",
            trigger_source="commit",
        )
        ops.insert_decision(d if hasattr(ops.insert_decision, "__wrapped__") else conn, d)
    print("Seeded 2 deferred_eval decisions")

    # 5. Seed 3 pending drafts (with supporting draft decisions)
    for i, (platform, content) in enumerate(
        [
            (
                "x",
                "Rate limiting is live. 15 evaluations per day, 10 minute gaps. Your commits still get tracked -- they just queue up.",
            ),
            (
                "x",
                "The merge queue action lets the evaluator say 'combine these 3 drafts into 1'. Creative direction flows through merge_instruction.",
            ),
            (
                "linkedin",
                "Building rate limits into the Social Hook pipeline. The throttle gate fires before parse_commit_info() so you don't even pay the git subprocess cost for a doomed trigger.",
            ),
        ]
    ):
        dec = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash=f"draft{i:03d}",
            decision="draft",
            reasoning="Post-worthy",
            commit_message=f"feat: rate limit feature part {i + 1}",
            trigger_source="commit",
        )
        ops.insert_decision(conn, dec)

        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=dec.id,
            platform=platform,
            content=content,
            status="draft",
        )
        ops.insert_draft(conn, draft)
    print("Seeded 3 pending drafts (2 x, 1 linkedin)")

    conn.commit()
    conn.close()
    print("\nDone! Run: PYTHONPATH=$(pwd)/src python3 -m social_hook web")
    print("Rate limit card should show: 5/15 evals, 1 manual, 2 queued, ~$9 cost")


if __name__ == "__main__":
    main()
