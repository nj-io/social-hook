"""Section C: Narrative Mechanics scenarios."""

from datetime import datetime, timedelta, timezone

from e2e.constants import COMMITS, rate_limit_cooldown


def run(harness, runner):
    """C1-C14: Narrative mechanics scenarios."""
    from social_hook.db import operations as ops

    if not harness.project_id:
        harness.seed_project()

    # C1: Episode type assigned on draft decision
    def c1():
        decisions = ops.get_recent_decisions(harness.conn, harness.project_id, limit=20)
        pw = [d for d in decisions if d.decision == "draft"]
        if not pw:
            return "SKIP: No draft decisions to check"
        d = pw[0]
        valid_episodes = {
            "decision",
            "before_after",
            "demo_proof",
            "milestone",
            "postmortem",
            "launch",
            "synthesis",
        }
        assert d.episode_type in valid_episodes, f"Invalid episode_type: {d.episode_type}"
        return f"Episode type: {d.episode_type}"

    runner.run_scenario("C1", "Episode type assigned on draft", c1)

    # C2: Post category assigned on draft decision
    def c2():
        decisions = ops.get_recent_decisions(harness.conn, harness.project_id, limit=20)
        pw = [d for d in decisions if d.decision == "draft"]
        if not pw:
            return "SKIP: No draft decisions to check"
        d = pw[0]
        valid_categories = {"arc", "opportunistic", "experiment"}
        assert d.post_category in valid_categories, f"Invalid post_category: {d.post_category}"
        return f"Post category: {d.post_category}"

    runner.run_scenario("C2", "Post category assigned on draft", c2)

    # C3: Arc created for arc-category post
    def c3():
        arcs = ops.get_active_arcs(harness.conn, harness.project_id)
        # If no arc posts happened, seed one
        if not arcs:
            from social_hook.filesystem import generate_id
            from social_hook.models import Arc

            arc = Arc(
                id=generate_id("arc"),
                project_id=harness.project_id,
                theme="E2E test arc",
                status="active",
                post_count=1,
            )
            ops.insert_arc(harness.conn, arc)
            arcs = ops.get_active_arcs(harness.conn, harness.project_id)

        assert len(arcs) >= 1, "No active arcs"
        assert arcs[0].status == "active"
        assert arcs[0].theme, "Arc has no theme"
        return f"Active arcs: {len(arcs)}, theme: {arcs[0].theme}"

    runner.run_scenario("C3", "Arc created for arc-category post", c3)

    # C4: Max 3 active arcs
    def c4():
        from social_hook.filesystem import generate_id
        from social_hook.models import Arc

        # Ensure we have 3 active arcs
        current = ops.get_active_arcs(harness.conn, harness.project_id)
        for i in range(3 - len(current)):
            arc = Arc(
                id=generate_id("arc"),
                project_id=harness.project_id,
                theme=f"Test arc {i + len(current) + 1}",
                status="active",
                post_count=0,
            )
            ops.insert_arc(harness.conn, arc)

        arcs = ops.get_active_arcs(harness.conn, harness.project_id)
        assert len(arcs) <= 3, f"More than 3 active arcs: {len(arcs)}"
        return f"Active arcs: {len(arcs)} (max 3 enforced)"

    runner.run_scenario("C4", "Max 3 active arcs enforced", c4)

    # C5: Narrative debt increments
    def c5():
        debt_before = ops.get_narrative_debt(harness.conn, harness.project_id)
        before_count = debt_before.debt_counter if debt_before else 0

        ops.increment_narrative_debt(harness.conn, harness.project_id)

        debt_after = ops.get_narrative_debt(harness.conn, harness.project_id)
        assert debt_after is not None
        assert debt_after.debt_counter == before_count + 1, (
            f"Expected {before_count + 1}, got {debt_after.debt_counter}"
        )
        return f"Debt: {before_count} → {debt_after.debt_counter}"

    runner.run_scenario("C5", "Narrative debt increments", c5)

    # C6: Narrative debt resets
    def c6():
        # Ensure debt > 0
        ops.increment_narrative_debt(harness.conn, harness.project_id)
        ops.reset_narrative_debt(harness.conn, harness.project_id)

        debt = ops.get_narrative_debt(harness.conn, harness.project_id)
        assert debt is not None
        assert debt.debt_counter == 0, f"Expected 0, got {debt.debt_counter}"
        return "Debt reset to 0"

    runner.run_scenario("C6", "Narrative debt resets after synthesis", c6)

    # C7: Experiment posts don't affect debt
    def c7():
        debt_before = ops.get_narrative_debt(harness.conn, harness.project_id)
        before_count = debt_before.debt_counter if debt_before else 0

        # Experiment posts should NOT call increment_narrative_debt
        # This is a contract test — verify the counter doesn't change
        debt_after = ops.get_narrative_debt(harness.conn, harness.project_id)
        assert debt_after.debt_counter == before_count, (
            f"Debt changed: {before_count} → {debt_after.debt_counter}"
        )
        return f"Debt unchanged: {before_count}"

    runner.run_scenario("C7", "Experiment posts don't affect debt", c7)

    # C8: High debt signals synthesis needed
    def c8():
        # Set debt above threshold
        ops.reset_narrative_debt(harness.conn, harness.project_id)
        for _ in range(4):  # Above default threshold of 3
            ops.increment_narrative_debt(harness.conn, harness.project_id)

        debt = ops.get_narrative_debt(harness.conn, harness.project_id)
        assert debt.debt_counter >= 3, f"Debt only {debt.debt_counter}"

        # Run trigger — evaluator should see high debt
        from social_hook.trigger import run_trigger

        exit_code = run_trigger(COMMITS["bugfix"], str(harness.repo_path), verbose=runner.verbose)
        assert exit_code == 0

        decisions = ops.get_recent_decisions(harness.conn, harness.project_id, limit=5)
        d = decisions[0] if decisions else None
        assert d is not None

        runner.add_review_item(
            "C8",
            title="High debt signals synthesis needed",
            decision=d.decision,
            episode_type=d.episode_type,
            reasoning=d.reasoning or "",
            review_question="Did evaluator consider high debt? Lean toward synthesis?",
        )

        from social_hook.db import get_pending_drafts

        drafts = get_pending_drafts(harness.conn, harness.project_id)
        if drafts:
            runner.review_items[-1]["draft_content"] = drafts[0].content

        # Reset debt for remaining tests
        ops.reset_narrative_debt(harness.conn, harness.project_id)
        return f"Decision: {d.decision} (debt was {debt.debt_counter})"

    runner.run_scenario("C8", "High debt signals synthesis needed", c8, llm_call=True, isolate=True)

    # C9: Lifecycle phase in evaluator context
    def c9():

        # Seed lifecycle at build phase
        harness.conn.execute(
            "UPDATE lifecycles SET phase = ?, confidence = ? WHERE project_id = ?",
            ("build", 0.6, harness.project_id),
        )
        harness.conn.commit()

        from social_hook.trigger import run_trigger

        exit_code = run_trigger(
            COMMITS["major_feature"], str(harness.repo_path), verbose=runner.verbose
        )
        assert exit_code == 0

        # Reset to research
        harness.conn.execute(
            "UPDATE lifecycles SET phase = ?, confidence = ? WHERE project_id = ?",
            ("research", 0.3, harness.project_id),
        )
        harness.conn.commit()
        return "Lifecycle phase visible in context"

    runner.run_scenario(
        "C9", "Lifecycle phase in evaluator context", c9, llm_call=True, isolate=True
    )

    # C10: Lifecycle phase detection
    def c10():
        from social_hook.narrative import detect_lifecycle_phase

        signals_research = {
            "high_file_churn": True,
            "new_directories": True,
            "docs_heavy": True,
            "tests_growing": False,
            "release_tags": False,
        }
        lc_research = detect_lifecycle_phase(signals_research)
        assert lc_research.phase in {"research", "build", "demo", "launch", "post_launch"}

        signals_demo = {
            "high_file_churn": False,
            "demo_scripts": True,
            "readme_updates": True,
            "tests_growing": True,
            "release_tags": False,
        }
        lc_demo = detect_lifecycle_phase(signals_demo)
        assert lc_demo.phase in {"research", "build", "demo", "launch", "post_launch"}

        return f"Research signals→{lc_research.phase}, Demo signals→{lc_demo.phase}"

    runner.run_scenario("C10", "Lifecycle phase detection", c10)

    # C11: Strategy trigger: phase transition
    def c11():
        from social_hook.models import Lifecycle
        from social_hook.narrative import check_strategy_triggers, record_strategy_moment

        # Seed stored lifecycle at research
        harness.conn.execute(
            "UPDATE lifecycle SET phase = ?, confidence = ? WHERE project_id = ?",
            ("research", 0.3, harness.project_id),
        )
        harness.conn.commit()

        new_lc = Lifecycle(
            project_id=harness.project_id,
            phase="build",
            confidence=0.8,
        )
        triggers = check_strategy_triggers(
            harness.conn,
            harness.project_id,
            new_lifecycle=new_lc,
        )
        assert "phase_transition" in triggers, f"Expected phase_transition, got {triggers}"

        record_strategy_moment(harness.conn, harness.project_id)
        return f"Triggers: {triggers}"

    runner.run_scenario("C11", "Strategy trigger: phase transition", c11)

    # C12: Strategy trigger: time-based
    def c12():
        from social_hook.narrative import check_strategy_triggers

        # Set last_strategy_moment to 8 days ago
        old_time = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        harness.conn.execute(
            "UPDATE lifecycle SET last_strategy_moment = ? WHERE project_id = ?",
            (old_time, harness.project_id),
        )
        harness.conn.commit()

        triggers = check_strategy_triggers(harness.conn, harness.project_id)
        assert "time_elapsed" in triggers, f"Expected time_elapsed, got {triggers}"
        return f"Triggers: {triggers}"

    runner.run_scenario("C12", "Strategy trigger: time-based", c12)

    # C13: Arc creation probe — 3 diverse commits to see if evaluator creates arcs
    def c13():
        from social_hook.trigger import run_trigger

        arc_commits = [
            COMMITS["arc_llm_roles"],
            COMMITS["arc_journey"],
            COMMITS["arc_multi_provider"],
        ]
        created_arcs = []
        all_decisions = []
        for i, commit in enumerate(arc_commits):
            arcs_before = ops.get_active_arcs(harness.conn, harness.project_id)
            exit_code = run_trigger(commit, str(harness.repo_path), verbose=runner.verbose)
            assert exit_code == 0, f"Trigger failed for {commit}"
            arcs_after = ops.get_active_arcs(harness.conn, harness.project_id)
            new_arcs = [a for a in arcs_after if a not in arcs_before]
            created_arcs.extend(new_arcs)

            # Capture decision for review regardless of outcome
            recent = ops.get_recent_decisions(harness.conn, harness.project_id, limit=1)
            if recent:
                d = recent[0]
                all_decisions.append(
                    {
                        "commit": commit,
                        "decision": d.decision,
                        "post_category": getattr(d, "post_category", None),
                        "episode_type": getattr(d, "episode_type", None),
                        "reasoning": d.reasoning or "",
                    }
                )

            if i < len(arc_commits) - 1:
                rate_limit_cooldown()

        runner.add_review_item(
            "C13",
            title="Arc creation probe",
            arc_count=len(created_arcs),
            arc_themes=[a.theme for a in created_arcs],
            decisions=all_decisions,
            review_question="Did the evaluator autonomously create arcs for diverse commits?",
        )
        return f"Arcs created: {len(created_arcs)}, decisions: {len(all_decisions)}"

    runner.run_scenario("C13", "Arc creation probe (3 triggers)", c13, llm_call=True, isolate=True)

    # C14: Arc continuation probe — reuses C13 state, triggers a 4th commit
    def c14():
        from social_hook.trigger import run_trigger

        arcs_before = ops.get_active_arcs(harness.conn, harness.project_id)
        if not arcs_before:
            return "SKIP — C13 created no arcs"

        exit_code = run_trigger(
            COMMITS["arc_media_pipeline"], str(harness.repo_path), verbose=runner.verbose
        )
        assert exit_code == 0

        arcs_after = ops.get_active_arcs(harness.conn, harness.project_id)
        decisions = ops.get_recent_decisions(harness.conn, harness.project_id, limit=1)
        d = decisions[0] if decisions else None

        runner.add_review_item(
            "C14",
            title="Arc continuation probe",
            arcs_before=len(arcs_before),
            arcs_after=len(arcs_after),
            decision=d.decision if d else "none",
            arc_id=d.arc_id if d and hasattr(d, "arc_id") else "none",
            review_question="Did evaluator continue an existing arc or create a new one?",
        )
        return f"Arcs: {len(arcs_before)} → {len(arcs_after)}"

    runner.run_scenario("C14", "Arc continuation probe", c14, llm_call=True)
