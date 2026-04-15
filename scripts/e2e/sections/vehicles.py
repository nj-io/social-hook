"""Section V: Content Vehicle & Advisory scenarios.

Tests vehicle-aware approval routing: article drafts create advisory items
instead of entering the scheduler. Covers bot commands, bot buttons, CLI
commands, batch approve, and the scheduler safety net.
"""


def run(harness, runner, adapter):
    """V1-V7: Vehicle and advisory routing scenarios."""
    from social_hook.db import operations as ops

    if not harness.project_id:
        harness.seed_project()

    config = harness.load_config()
    chat_id = config.env.get("TELEGRAM_CHAT_ID", "test")

    # V1: Approve article draft → advisory (bot command)
    def v1():
        draft = harness.seed_draft(harness.project_id, status="draft", vehicle="article")
        from social_hook.bot.commands import cmd_approve

        adapter.clear()
        cmd_approve(adapter, chat_id, draft.id, config)

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "advisory", f"Expected advisory, got {updated.status}"
        items = ops.get_advisory_items(harness.conn, project_id=harness.project_id)
        linked = [i for i in items if i.linked_entity_id == draft.id]
        assert len(linked) == 1, f"Expected 1 advisory item, got {len(linked)}"
        return f"Article draft → advisory, advisory item {linked[0].id}"

    runner.run_scenario("V1", "Approve article → advisory (bot command)", v1)

    # V2: Quick approve article draft → advisory with due_date (bot button)
    def v2():
        draft = harness.seed_draft(harness.project_id, status="draft", vehicle="article")
        from social_hook.bot.buttons import btn_quick_approve

        adapter.clear()
        btn_quick_approve(adapter, chat_id, "web_0", draft.id, config)

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "advisory", f"Expected advisory, got {updated.status}"
        items = ops.get_advisory_items(harness.conn, project_id=harness.project_id)
        linked = [i for i in items if i.linked_entity_id == draft.id]
        assert len(linked) == 1, f"Expected 1 advisory item, got {len(linked)}"
        assert linked[0].due_date is not None, "Advisory should have due_date from schedule"
        return f"Quick approve → advisory with due_date {linked[0].due_date}"

    runner.run_scenario("V2", "Quick approve article → advisory with due_date", v2)

    # V3: Post Now article draft → advisory (bot button)
    def v3():
        draft = harness.seed_draft(harness.project_id, status="draft", vehicle="article")
        from social_hook.bot.buttons import btn_post_now

        adapter.clear()
        btn_post_now(adapter, chat_id, "web_0", draft.id, config)

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "advisory", f"Expected advisory, got {updated.status}"
        items = ops.get_advisory_items(harness.conn, project_id=harness.project_id)
        linked = [i for i in items if i.linked_entity_id == draft.id]
        assert len(linked) == 1, f"Expected 1 advisory item, got {len(linked)}"
        return "Post Now article → advisory (no scheduler involved)"

    runner.run_scenario("V3", "Post Now article → advisory (bot button)", v3)

    # V4: Approve single draft → normal approve (not advisory)
    def v4():
        draft = harness.seed_draft(harness.project_id, status="draft", vehicle="single")
        from social_hook.bot.commands import cmd_approve

        adapter.clear()
        cmd_approve(adapter, chat_id, draft.id, config)

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "approved", f"Expected approved, got {updated.status}"
        return "Single draft → approved (normal flow, no advisory)"

    runner.run_scenario("V4", "Approve single draft → normal (not advisory)", v4)

    # V5: Batch approve mixed vehicles
    def v5():
        from social_hook.filesystem import generate_id

        # Create a cycle with both single and article drafts
        cycle_id = generate_id("cycle")
        harness.conn.execute(
            "INSERT INTO evaluation_cycles (id, project_id, trigger_type, created_at) "
            "VALUES (?, ?, 'manual', datetime('now'))",
            (cycle_id, harness.project_id),
        )
        harness.conn.commit()

        single_draft = harness.seed_draft(harness.project_id, status="draft", vehicle="single")
        article_draft = harness.seed_draft(harness.project_id, status="draft", vehicle="article")

        # Link drafts to cycle
        harness.conn.execute(
            "UPDATE drafts SET evaluation_cycle_id = ? WHERE id IN (?, ?)",
            (cycle_id, single_draft.id, article_draft.id),
        )
        harness.conn.commit()

        from social_hook.bot.buttons import handle_cycle_approve

        adapter.clear()
        handle_cycle_approve(adapter, chat_id, "web_0", cycle_id, config)

        single_after = ops.get_draft(harness.conn, single_draft.id)
        article_after = ops.get_draft(harness.conn, article_draft.id)
        assert single_after.status == "approved", f"Single: {single_after.status}"
        assert article_after.status == "advisory", f"Article: {article_after.status}"
        return "Batch: single → approved, article → advisory"

    runner.run_scenario("V5", "Batch approve mixed vehicles", v5)

    # V6: CLI approve article → advisory
    def v6():
        draft = harness.seed_draft(harness.project_id, status="draft", vehicle="article")

        from social_hook.vehicle import check_auto_postable, handle_advisory_approval

        assert not check_auto_postable(draft), "Article should not be auto-postable"
        handle_advisory_approval(harness.conn, draft, config)

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "advisory", f"Expected advisory, got {updated.status}"
        return "CLI path: check_auto_postable + handle_advisory_approval works"

    runner.run_scenario("V6", "CLI advisory helpers direct call", v6)

    # V7: Scheduler safety net — article draft in scheduled status
    def v7():
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        draft = harness.seed_draft(
            harness.project_id,
            status="scheduled",
            vehicle="article",
            scheduled_time=now,
        )

        from social_hook.scheduler import scheduler_tick

        scheduler_tick(draft_id=draft.id, dry_run=False)

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "advisory", f"Expected advisory, got {updated.status}"
        items = ops.get_advisory_items(harness.conn, project_id=harness.project_id)
        linked = [i for i in items if i.linked_entity_id == draft.id]
        assert len(linked) >= 1, "Safety net should create advisory item"
        return "Scheduler safety net: scheduled article → advisory"

    runner.run_scenario("V7", "Scheduler safety net for article", v7)
