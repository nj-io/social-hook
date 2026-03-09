"""Section D: Draft Lifecycle scenarios."""

from datetime import datetime, timezone


def run(harness, runner, adapter):
    """D1-D7: Draft lifecycle scenarios."""
    from social_hook.db import operations as ops

    if not harness.project_id:
        harness.seed_project()

    config = harness.load_config()
    chat_id = config.env.get("TELEGRAM_CHAT_ID", "test")

    # D1: Approve draft
    def d1():
        draft = harness.seed_draft(harness.project_id, status="draft")
        from social_hook.bot.commands import cmd_approve

        adapter.clear()
        cmd_approve(adapter, chat_id, draft.id, config)

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "approved", f"Status: {updated.status}"
        return "Draft approved"

    runner.run_scenario("D1", "Approve draft", d1)

    # D2: Reject draft with reason
    def d2():
        draft = harness.seed_draft(harness.project_id, status="draft")
        from social_hook.bot.commands import cmd_reject

        adapter.clear()
        cmd_reject(adapter, chat_id, f"{draft.id} too formal", config)

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "rejected", f"Status: {updated.status}"
        assert updated.last_error and "Rejected:" in updated.last_error, (
            f"last_error: {updated.last_error}"
        )
        return f"Rejected with reason: {updated.last_error}"

    runner.run_scenario("D2", "Reject draft with reason", d2)

    # D3: Schedule at optimal time
    def d3():
        draft = harness.seed_draft(harness.project_id, status="draft")
        from social_hook.bot.commands import cmd_schedule

        adapter.clear()
        cmd_schedule(adapter, chat_id, draft.id, config)

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "scheduled", f"Status: {updated.status}"
        assert updated.scheduled_time is not None, "No scheduled_time set"
        return f"Scheduled at: {updated.scheduled_time}"

    runner.run_scenario("D3", "Schedule at optimal time", d3)

    # D4: Schedule at custom time
    def d4():
        draft = harness.seed_draft(harness.project_id, status="draft")
        from social_hook.bot.commands import cmd_schedule

        adapter.clear()
        cmd_schedule(adapter, chat_id, f"{draft.id} 2026-03-01 14:00", config)

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "scheduled", f"Status: {updated.status}"
        assert updated.scheduled_time is not None
        return f"Scheduled at: {updated.scheduled_time}"

    runner.run_scenario("D4", "Schedule at custom time", d4)

    # D5: Cancel scheduled draft
    def d5():
        draft = harness.seed_draft(
            harness.project_id,
            status="scheduled",
            scheduled_time=datetime.now(timezone.utc).isoformat(),
        )
        from social_hook.bot.commands import cmd_cancel

        adapter.clear()
        cmd_cancel(adapter, chat_id, draft.id, config)

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "cancelled", f"Status: {updated.status}"
        return "Draft cancelled"

    runner.run_scenario("D5", "Cancel scheduled draft", d5)

    # D6: Retry failed draft (known bug: last_error not cleared)
    def d6():
        draft = harness.seed_draft(
            harness.project_id,
            status="failed",
            last_error="Posting failed: API timeout",
            retry_count=1,
        )
        from social_hook.bot.commands import cmd_retry

        adapter.clear()
        cmd_retry(adapter, chat_id, draft.id, config)

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "scheduled", f"Status: {updated.status}"

        # Known bug detection: last_error should be cleared but isn't
        if updated.last_error:
            detail = f"KNOWN BUG DETECTED: last_error not cleared: {updated.last_error}"
        else:
            detail = "Draft retried, last_error cleared (bug fixed!)"
        return detail

    runner.run_scenario("D6", "Retry failed draft (known bug check)", d6)

    # D7: Draft superseded
    def d7():
        draft1 = harness.seed_draft(harness.project_id, status="draft")
        draft2 = harness.seed_draft(harness.project_id, status="draft")

        result = ops.supersede_draft(harness.conn, draft1.id, draft2.id)
        assert result is True, "supersede_draft returned False"

        updated = ops.get_draft(harness.conn, draft1.id)
        assert updated.status == "superseded", f"Status: {updated.status}"
        assert updated.superseded_by == draft2.id
        return "Draft1 superseded by draft2"

    runner.run_scenario("D7", "Draft superseded", d7)
