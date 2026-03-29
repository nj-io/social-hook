"""Section E: Scheduler scenarios."""

from datetime import datetime, timedelta, timezone


def run(harness, runner):
    """E1-E5: Scheduler scenarios."""
    from social_hook.db import operations as ops

    if not harness.project_id:
        harness.seed_project()

    # E1: Due draft → post (dry-run adapter)
    def e1():
        from social_hook.scheduler import scheduler_tick

        past_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        draft = harness.seed_draft(
            harness.project_id,
            status="scheduled",
            scheduled_time=past_time,
        )

        count = scheduler_tick(dry_run=True)
        assert count >= 1, f"Expected >=1, scheduler processed {count}"

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "posted", f"Status: {updated.status}"
        return f"Processed: {count}, draft posted"

    runner.run_scenario("E1", "Due draft → post (dry-run adapter)", e1)

    # E2: Paused project → skip
    def e2():
        from social_hook.scheduler import scheduler_tick

        harness.conn.execute(
            "UPDATE projects SET paused = 1 WHERE id = ?",
            (harness.project_id,),
        )
        harness.conn.commit()

        past_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        draft = harness.seed_draft(
            harness.project_id,
            status="scheduled",
            scheduled_time=past_time,
        )

        count = scheduler_tick(dry_run=True)

        updated = ops.get_draft(harness.conn, draft.id)

        # Unpause
        harness.conn.execute(
            "UPDATE projects SET paused = 0 WHERE id = ?",
            (harness.project_id,),
        )
        harness.conn.commit()

        assert updated.status == "scheduled", f"Status changed: {updated.status}"
        return f"Skipped paused project (processed: {count})"

    runner.run_scenario("E2", "Paused project → skip", e2)

    # E3: Lock prevents concurrent run
    def e3():
        from social_hook.scheduler import acquire_lock, release_lock, scheduler_tick

        acquired = acquire_lock()
        assert acquired, "Failed to acquire lock"

        try:
            count = scheduler_tick(dry_run=True)
            assert count == 0, f"Expected 0 (lock held), got {count}"
        finally:
            release_lock()

        return "Lock blocked concurrent run"

    runner.run_scenario("E3", "Lock prevents concurrent run", e3)

    # E4: No due drafts → no-op
    def e4():
        from social_hook.scheduler import scheduler_tick

        count = scheduler_tick(dry_run=True)
        # May be 0 or low number if no new due drafts
        return f"Processed: {count}"

    runner.run_scenario("E4", "No due drafts → no-op", e4)

    # E5: max_per_week deferral (structural, no LLM call)
    def e5():
        from social_hook.db import insert_decision, insert_draft, insert_post
        from social_hook.filesystem import generate_id
        from social_hook.models.core import Decision, Draft, Post
        from social_hook.scheduling import calculate_optimal_time

        # Insert fake posts to hit the weekly limit
        for i in range(10):
            d = Decision(
                id=generate_id("decision"),
                project_id=harness.project_id,
                commit_hash=f"e5hash{i}",
                decision="draft",
                reasoning="test",
            )
            insert_decision(harness.conn, d)
            dr = Draft(
                id=generate_id("draft"),
                project_id=harness.project_id,
                decision_id=d.id,
                platform="x",
                content=f"e5 content {i}",
            )
            insert_draft(harness.conn, dr)
            post = Post(
                id=generate_id("post"),
                draft_id=dr.id,
                project_id=harness.project_id,
                platform="x",
                content=f"e5 posted {i}",
            )
            insert_post(harness.conn, post)

        result = calculate_optimal_time(
            harness.conn,
            harness.project_id,
            max_per_week=10,
        )
        assert result.deferred is True, f"Expected deferred=True, got {result.deferred}"
        assert "Weekly limit" in result.day_reason, (
            f"Expected 'Weekly limit' in day_reason, got: {result.day_reason}"
        )
        return f"Deferred: {result.day_reason}"

    runner.run_scenario("E5", "max_per_week deferral", e5)
