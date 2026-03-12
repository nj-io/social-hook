"""Section K: Cross-Cutting scenarios."""

from datetime import datetime, timedelta, timezone

from e2e.constants import COMMITS


def run(harness, runner, adapter):
    """K1-K6: Cross-cutting scenarios."""
    from social_hook.db import operations as ops

    if not harness.project_id:
        harness.seed_project()

    config = harness.load_config()
    chat_id = config.env.get("TELEGRAM_CHAT_ID", "test")

    # K1: Full chain: trigger → approve → schedule → post
    def k1():
        from social_hook.bot.commands import cmd_approve
        from social_hook.scheduler import scheduler_tick
        from social_hook.trigger import run_trigger

        exit_code = run_trigger(
            COMMITS["significant"], str(harness.repo_path), verbose=runner.verbose
        )
        assert exit_code == 0, f"Trigger failed: {exit_code}"

        drafts = ops.get_pending_drafts(harness.conn, harness.project_id)
        if not drafts:
            return "SKIP: No draft created (evaluator chose skip)"

        draft = drafts[0]
        adapter.clear()
        cmd_approve(adapter, chat_id, draft.id, config)

        updated = ops.get_draft(harness.conn, draft.id)
        if updated.status == "approved":
            # Need to schedule it
            from social_hook.bot.commands import cmd_schedule

            cmd_schedule(adapter, chat_id, draft.id, config)
            updated = ops.get_draft(harness.conn, draft.id)

        if updated.status == "scheduled":
            # Set time to past so scheduler picks it up
            harness.conn.execute(
                "UPDATE drafts SET scheduled_time = ? WHERE id = ?",
                ((datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(), draft.id),
            )
            harness.conn.commit()

            scheduler_tick(dry_run=True)

            updated = ops.get_draft(harness.conn, draft.id)
            assert updated.status == "posted", f"Status: {updated.status}"
            return "Full chain: trigger → approve → schedule → posted"

        return f"Chain completed with status: {updated.status}"

    runner.run_scenario(
        "K1", "Full chain: trigger → approve → post", k1, llm_call=True, isolate=True
    )

    # K2: Full chain: trigger → reject → no post
    def k2():
        from social_hook.bot.commands import cmd_reject
        from social_hook.trigger import run_trigger

        exit_code = run_trigger(
            COMMITS["major_feature"], str(harness.repo_path), verbose=runner.verbose
        )
        assert exit_code == 0

        drafts = ops.get_pending_drafts(harness.conn, harness.project_id)
        if not drafts:
            return "SKIP: No draft created"

        draft = drafts[0]
        adapter.clear()
        cmd_reject(adapter, chat_id, f"{draft.id} not the right angle", config)

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "rejected", f"Status: {updated.status}"
        return "Rejected, no post"

    runner.run_scenario(
        "K2", "Full chain: trigger → reject → no post", k2, llm_call=True, isolate=True
    )

    # K3: Dry-run end-to-end
    def k3():
        from social_hook.trigger import run_trigger

        before_decisions = len(ops.get_all_recent_decisions(harness.conn))

        exit_code = run_trigger(
            COMMITS["large_feature"],
            str(harness.repo_path),
            dry_run=True,
            verbose=runner.verbose,
        )
        assert exit_code == 0

        after_decisions = len(ops.get_all_recent_decisions(harness.conn))
        assert after_decisions == before_decisions, (
            f"Dry-run persisted: {after_decisions} vs {before_decisions}"
        )
        return "Dry-run: nothing persisted"

    runner.run_scenario("K3", "Dry-run end-to-end", k3)

    # K4: Full chain with arc verification
    def k4():
        arcs_before = ops.get_active_arcs(harness.conn, harness.project_id)
        arc_count_before = len(arcs_before)

        from social_hook.trigger import run_trigger

        exit_code = run_trigger(
            COMMITS["major_feature"], str(harness.repo_path), verbose=runner.verbose
        )
        assert exit_code == 0

        arcs_after = ops.get_active_arcs(harness.conn, harness.project_id)
        return f"Arcs: {arc_count_before} → {len(arcs_after)}"

    runner.run_scenario("K4", "Full chain: verify arc state", k4, llm_call=True, isolate=True)

    # K5: Debt accumulation → synthesis trigger
    def k5():
        # Reset and accumulate debt
        ops.reset_narrative_debt(harness.conn, harness.project_id)
        for _ in range(4):
            ops.increment_narrative_debt(harness.conn, harness.project_id)

        debt = ops.get_narrative_debt(harness.conn, harness.project_id)
        assert debt.debt_counter >= 3, f"Debt: {debt.debt_counter}"

        from social_hook.trigger import run_trigger

        exit_code = run_trigger(
            COMMITS["major_feature"], str(harness.repo_path), verbose=runner.verbose
        )
        assert exit_code == 0

        decisions = ops.get_recent_decisions(harness.conn, harness.project_id, limit=3)
        d = decisions[0] if decisions else None

        # Reset debt
        ops.reset_narrative_debt(harness.conn, harness.project_id)

        if d:
            runner.add_review_item(
                "K5",
                title="Debt accumulation → synthesis trigger",
                decision=d.decision,
                episode_type=d.episode_type,
                reasoning=d.reasoning or "",
                review_question="Did evaluator consider high debt? Synthesis?",
            )

            from social_hook.db import get_pending_drafts

            drafts = get_pending_drafts(harness.conn, harness.project_id)
            if drafts:
                runner.review_items[-1]["draft_content"] = drafts[0].content

            return f"Debt={debt.debt_counter}, Decision: {d.decision}"
        return f"Debt={debt.debt_counter}"

    runner.run_scenario(
        "K5", "Debt accumulation → synthesis trigger", k5, llm_call=True, isolate=True
    )

    # K6: Supersede draft (DB operation)
    def k6():
        draft1 = harness.seed_draft(harness.project_id, status="draft")
        draft2 = harness.seed_draft(harness.project_id, status="draft")

        result = ops.supersede_draft(harness.conn, draft1.id, draft2.id)
        assert result is True

        updated = ops.get_draft(harness.conn, draft1.id)
        assert updated.status == "superseded"
        assert updated.superseded_by == draft2.id
        return "Supersede: DB operation works"

    runner.run_scenario("K6", "Supersede draft (DB operation)", k6)
