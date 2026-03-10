"""Section Q: Queue / Evaluator Rework scenarios."""


def run(harness, runner):
    """Q8-Q12: Queue and evaluator rework scenarios.

    These test DB-level operations and model correctness for the evaluator
    rework (hold decisions, queue actions). No LLM calls required.
    """
    if not harness.project_id:
        harness.seed_project()

    # Q8: Decision type validation — only draft/hold/skip accepted
    def q8():

        from social_hook.models import Decision

        # 'draft' is valid
        d = Decision(
            id="test_q8",
            project_id=harness.project_id,
            commit_hash="abc123",
            decision="draft",
            reasoning="test draft value",
        )
        assert d.decision == "draft"
        row = d.to_row()
        assert row[4] == "draft"  # Column 5 is decision

        # 'hold' is valid
        d2 = Decision(
            id="test_q8b",
            project_id=harness.project_id,
            commit_hash="def456",
            decision="hold",
            reasoning="test hold value",
        )
        assert d2.decision == "hold"

        # 'skip' is valid
        d3 = Decision(
            id="test_q8c",
            project_id=harness.project_id,
            commit_hash="ghi789",
            decision="skip",
            reasoning="test skip",
        )
        assert d3.decision == "skip"

        # Old values like 'post_worthy' are rejected
        try:
            Decision(
                id="test_q8d",
                project_id=harness.project_id,
                commit_hash="jkl012",
                decision="post_worthy",
                reasoning="should fail",
            )
            raise AssertionError("post_worthy should have raised ValueError")
        except ValueError:
            pass  # Expected

        return "draft, hold, skip all parse correctly; old values rejected"

    runner.run_scenario("Q8", "Decision type validation: only draft/hold/skip", q8, isolate=True)

    # Q9: Hold decision stored and retrievable
    def q9():
        from social_hook.db import operations as ops
        from social_hook.models import Decision

        d = Decision(
            id="test_q9",
            project_id=harness.project_id,
            commit_hash="hold123",
            decision="hold",
            reasoning="Wait for related commits",
            commit_summary="Added initial auth scaffolding",
        )
        ops.insert_decision(harness.conn, d)
        harness.conn.commit()

        held = ops.get_held_decisions(harness.conn, harness.project_id)
        assert any(h.id == "test_q9" for h in held), (
            f"test_q9 not found in held decisions: {[h.id for h in held]}"
        )

        # Verify the decision roundtrips correctly
        found = [h for h in held if h.id == "test_q9"][0]
        assert found.commit_summary == "Added initial auth scaffolding"
        assert found.decision == "hold"

        return f"Hold decision stored, {len(held)} held total"

    runner.run_scenario("Q9", "Hold decision stored correctly", q9, isolate=True)

    # Q10: is_held and is_draftable helper functions
    def q10():
        from social_hook.models import is_draftable, is_held

        # Held decisions — only "hold" returns True
        assert is_held("hold"), "hold should be held"
        assert not is_held("draft"), "draft should not be held"
        assert not is_held("skip"), "skip should not be held"
        assert not is_held("consolidate"), "consolidate (old value) should not be held"

        # Draftable decisions — only "draft" returns True
        assert is_draftable("draft"), "draft should be draftable"
        assert not is_draftable("skip"), "skip should not be draftable"
        assert not is_draftable("hold"), "hold should not be draftable"
        assert not is_draftable("post_worthy"), "post_worthy (old value) should not be draftable"

        return "is_held and is_draftable correct for all decision types"

    runner.run_scenario("Q10", "Hold/draftable helper functions", q10)

    # Q11: Queue action — supersede
    def q11():
        from social_hook.db import operations as ops
        from social_hook.models import Decision, Draft

        d = Decision(
            id="test_q11_dec",
            project_id=harness.project_id,
            commit_hash="sup123",
            decision="draft",
            reasoning="test",
        )
        ops.insert_decision(harness.conn, d)

        draft = Draft(
            id="test_q11",
            project_id=harness.project_id,
            decision_id="test_q11_dec",
            platform="x",
            content="Original draft content",
            status="draft",
        )
        ops.insert_draft(harness.conn, draft)
        harness.conn.commit()

        ops.execute_queue_action(harness.conn, "supersede", "test_q11", "Replaced by newer commit")

        updated = ops.get_draft(harness.conn, "test_q11")
        assert updated is not None, "Draft not found after supersede"
        assert updated.status == "superseded", f"Expected superseded, got {updated.status}"

        return "Draft superseded successfully"

    runner.run_scenario("Q11", "Queue action: supersede", q11, isolate=True)

    # Q12: Queue action — drop
    def q12():
        from social_hook.db import operations as ops
        from social_hook.models import Decision, Draft

        d = Decision(
            id="test_q12_dec",
            project_id=harness.project_id,
            commit_hash="drop123",
            decision="draft",
            reasoning="test",
        )
        ops.insert_decision(harness.conn, d)

        draft = Draft(
            id="test_q12",
            project_id=harness.project_id,
            decision_id="test_q12_dec",
            platform="x",
            content="Stale draft content",
            status="draft",
        )
        ops.insert_draft(harness.conn, draft)
        harness.conn.commit()

        ops.execute_queue_action(harness.conn, "drop", "test_q12", "No longer relevant")

        updated = ops.get_draft(harness.conn, "test_q12")
        assert updated is not None, "Draft not found after drop"
        assert updated.status == "cancelled", f"Expected cancelled, got {updated.status}"
        assert "No longer relevant" in (updated.last_error or ""), (
            f"Reason not in last_error: {updated.last_error}"
        )

        return "Draft dropped (cancelled) with reason"

    runner.run_scenario("Q12", "Queue action: drop", q12, isolate=True)
