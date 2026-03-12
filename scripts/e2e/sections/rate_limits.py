"""Section T: Rate Limits & Merge scenarios."""

from e2e.constants import COMMITS


def run(harness, runner):
    """T1-T2: Merge queue curation and batch drain after day rollover."""
    from social_hook.db import operations as ops

    if not harness.project_id:
        harness.seed_project()

    # T1: Merge queue curation under low capacity
    #
    # Three dimensions:
    #   1. Automated: decision exists, valid type, queue_action draft IDs from seeded set
    #   2. Human review: did evaluator merge aggressively? Was merge_instruction editorial?
    #   3. Manual walkthrough: seed drafts in web, trigger, review queue curation in dashboard
    def t1():
        from social_hook.trigger import run_trigger

        # Seed 5 drafts with overlapping rate-limiting content.
        # These simulate what a real evaluator would produce over several commits
        # that all touch the same feature — realistic length, overlapping angles.
        print("       Seeding 5 overlapping drafts about rate limiting:")
        draft_1 = harness.seed_draft(
            harness.project_id,
            status="draft",
            content=(
                "Pushed 8 commits yesterday refactoring the scheduler. Each one fired "
                "an evaluator call. 8 LLM round-trips for what was really one logical "
                "change — that's the kind of waste that sneaks up on you.\n\n"
                "Built a rate-limiting gate into the trigger pipeline. Configurable "
                "daily cap (default 15) plus a minimum gap between evaluations. When "
                "commit 9 lands, it doesn't burn tokens — it records a deferred_eval "
                "decision and queues for later. The gate fires before parse_commit_info() "
                "so you don't even pay the git subprocess cost for a doomed trigger.\n\n"
                "Manual overrides bypass the gate entirely. Your explicit intent always "
                "wins over automation throttling.\n\n"
                "What kills you with LLM costs isn't the big calls. It's the thousands "
                "of small ones nobody's counting."
            ),
            platform="x",
        )
        print(f"         1. [{draft_1.id[:12]}] rate limit gate — problem + solution")

        draft_2 = harness.seed_draft(
            harness.project_id,
            status="draft",
            content=(
                "New decision type: deferred_eval. When a commit trigger hits the rate "
                "limit, instead of silently dropping it, the pipeline records exactly "
                "why it was deferred and queues it for batch processing. Nothing gets "
                "lost, nothing gets silently ignored.\n\n"
                "The scheduler picks deferred triggers up on its next tick. It re-checks "
                "the rate limit, and if a slot opened, runs a fresh evaluation. Two drain "
                "modes: batch_throttled combines all deferred triggers into one LLM call "
                "with a synthetic commit. Individual mode evaluates them one at a time as "
                "slots open.\n\n"
                "The key insight: rate limiting shouldn't mean losing context. Every "
                "deferred commit still gets its moment — just not right now."
            ),
            platform="x",
        )
        print(f"         2. [{draft_2.id[:12]}] deferred_eval drain mechanism")

        draft_3 = harness.seed_draft(
            harness.project_id,
            status="draft",
            content=(
                "Rate limiting without visibility is a mystery box. You push code, "
                "nothing happens, and you don't know why. Fixed that.\n\n"
                "Dashboard card: evaluations today (7/15), countdown timer to the next "
                "available slot, deferred triggers waiting in queue. CLI equivalent: "
                "social-hook rate-limits prints the same data from your terminal.\n\n"
                "Deferred evaluations show up in the decision list with an amber badge. "
                "You can see exactly which commits are waiting and why they were deferred. "
                "No silent failures, no guessing why nothing happened after your last push.\n\n"
                "Observability isn't optional when you're automating decisions about "
                "your public-facing content."
            ),
            platform="x",
        )
        print(f"         3. [{draft_3.id[:12]}] rate limit visibility + dashboard")

        draft_4 = harness.seed_draft(
            harness.project_id,
            status="draft",
            content=(
                "The rate limit gate checks two things: daily cap (have you exceeded "
                "max_posts_per_day?) and gap timer (has enough time passed since the "
                "last evaluation?). Both are configurable in config.yaml.\n\n"
                "When either check fails, the trigger creates a deferred_eval decision "
                "instead of calling the LLM. The decision stores the reason — 'daily cap "
                "reached (15/15)' or 'gap timer: 3m remaining' — so you always know why.\n\n"
                "The gate runs before any expensive work: no git diff parsing, no file "
                "selection, no context assembly. A deferred trigger costs essentially zero."
            ),
            platform="x",
        )
        print(f"         4. [{draft_4.id[:12]}] rate limit config + gate mechanics")

        draft_5 = harness.seed_draft(
            harness.project_id,
            status="draft",
            content=(
                "Batch drain mode: when rate limit slots open up and multiple deferred "
                "triggers are queued, the scheduler combines them into a single evaluator "
                "call. Instead of N separate LLM round-trips, you get one call that sees "
                "all the deferred commits together and makes a holistic decision.\n\n"
                "The evaluator gets a synthetic commit that lists all deferred trigger "
                "hashes with their messages. It can draft about the most interesting one, "
                "hold some for consolidation, or skip the ones that aren't worth posting.\n\n"
                "This is the difference between rate limiting that loses information and "
                "rate limiting that preserves it. Every commit gets evaluated — just on "
                "the system's schedule, not the developer's."
            ),
            platform="x",
        )
        print(f"         5. [{draft_5.id[:12]}] batch drain mode")

        seeded_ids = {draft_1.id, draft_2.id, draft_3.id, draft_4.id, draft_5.id}

        # Mark audience as introduced so evaluator focuses on queue curation,
        # not intro logic (which overrides normal merge/supersede behavior)
        harness.conn.execute(
            "UPDATE projects SET audience_introduced = 1 WHERE id = ?",
            (harness.project_id,),
        )
        harness.conn.commit()

        # Low capacity: 1 post/day forces merge pressure
        harness.update_config({"scheduling": {"max_posts_per_day": 1}})
        print("       Config: max_posts_per_day=1 (forces merge pressure)")

        # Verify drafts are visible to the context builder
        visible = ops.get_pending_drafts(harness.conn, harness.project_id)
        print(f"       Pending drafts visible to evaluator: {len(visible)}")
        for v in visible:
            print(f"         [id={v.id[:12]}] {v.platform}:{v.status}")

        print(f"       Triggering commit: {COMMITS['bugfix'][:8]} (Fix setup wizard UX)")

        exit_code = run_trigger(COMMITS["bugfix"], str(harness.repo_path), verbose=runner.verbose)
        assert exit_code == 0, f"run_trigger returned {exit_code}"

        # Structural assertions
        decisions = ops.get_recent_decisions(harness.conn, harness.project_id, limit=5)
        assert len(decisions) > 0, "No decisions created"
        d = decisions[0]

        valid_decisions = {"draft", "hold", "skip"}
        assert d.decision in valid_decisions, f"Invalid decision: {d.decision}"

        # Report what happened
        print(f"       Result: decision={d.decision}")
        print(f"       Reasoning: {(d.reasoning or '')[:150]}")

        # Check seeded draft statuses
        print("       Seeded draft statuses:")
        for label, draft_obj in [
            ("1", draft_1),
            ("2", draft_2),
            ("3", draft_3),
            ("4", draft_4),
            ("5", draft_5),
        ]:
            refreshed = ops.get_draft(harness.conn, draft_obj.id)
            status = refreshed.status if refreshed else "MISSING"
            superseded_by = ""
            if refreshed and refreshed.superseded_by:
                superseded_by = f" -> replaced by {refreshed.superseded_by[:12]}"
            print(f"         {label}. [{draft_obj.id[:12]}] {status}{superseded_by}")

        # Check for superseded seeded drafts
        superseded = ops.get_drafts_filtered(
            harness.conn, status="superseded", project_id=harness.project_id
        )
        merged_originals = [dr for dr in superseded if dr.id in seeded_ids]

        if merged_originals:
            print(f"       Queue curation: {len(merged_originals)} seeded drafts merged/superseded")
            for mo in merged_originals:
                replaced_by = f" -> replaced by {mo.superseded_by[:12]}" if mo.superseded_by else ""
                print(f"         [{mo.id[:12]}] {mo.status}{replaced_by}")

        # Check for new drafts (from commit eval or merge replacement)
        pending = ops.get_pending_drafts(harness.conn, harness.project_id)
        new_drafts = [dr for dr in pending if dr.id not in seeded_ids]
        surviving_seeded = [dr for dr in pending if dr.id in seeded_ids]

        if new_drafts:
            print(f"       New drafts created: {len(new_drafts)}")
            for nd in new_drafts:
                print(f"         [{nd.id[:12]}] {nd.content[:80]}...")

        # Build detail summary
        detail = f"Decision: {d.decision}"
        if merged_originals:
            detail += f", {len(merged_originals)}/{len(seeded_ids)} seeded drafts superseded"
        if surviving_seeded:
            detail += f", {len(surviving_seeded)}/{len(seeded_ids)} seeded drafts unchanged"
        if new_drafts:
            detail += f", {len(new_drafts)} new draft(s)"

        # Human review: evaluate merge quality
        review_content = (
            new_drafts[0].content
            if new_drafts
            else pending[0].content
            if pending
            else "(no drafts)"
        )
        runner.add_review_item(
            "T1",
            title="Merge curation under low capacity (max_posts_per_day=1)",
            decision=d.decision,
            reasoning=d.reasoning or "",
            draft_content=review_content,
            review_question=(
                "Did the evaluator reduce 5 drafts to fit 1 daily slot? "
                "Were queue_actions issued (merge/supersede/drop)? "
                "Or did it ignore the queue entirely?"
            ),
        )

        # Restore config
        harness.update_config({"scheduling": {"max_posts_per_day": 5}})

        return detail

    runner.run_scenario(
        "T1", "Merge queue curation under low capacity", t1, llm_call=True, isolate=True
    )

    # T2: Batch drain after day rollover (10 commits)
    #
    # Flow:
    #   1. Seed 2 usage_log rows to simulate an exhausted daily cap (no LLM calls)
    #   2. Trigger 10 real commits — all hit the rate limit gate and defer instantly
    #   3. Backdate usage_log to simulate day rollover (daily count resets to 0)
    #   4. Run batch drain — combines all 10 deferred triggers into 1 evaluator call
    #
    # Three dimensions:
    #   1. Automated: 10 deferred decisions created, all consumed after drain,
    #      batch decision exists with commit_hash starting "batch-"
    #   2. Human review: does the batch draft coherently synthesize 10 diverse commits?
    #   3. Manual walkthrough: push commits rapidly until capped, wait for day rollover,
    #      observe batch drain in CLI events / dashboard
    #
    # Uses snapshot_rollback because _drain_deferred_evaluations bypasses
    # run_scenario's isolate mechanism.
    def t2():
        from e2e.helpers.snapshots import snapshot_rollback
        from social_hook.scheduler import _drain_deferred_evaluations
        from social_hook.trigger import run_trigger

        with snapshot_rollback(harness):
            # Configure: low daily cap, no gap, batch mode
            harness.update_config(
                {
                    "rate_limits": {
                        "max_evaluations_per_day": 2,
                        "min_evaluation_gap_minutes": 0,
                        "batch_throttled": True,
                    },
                }
            )
            config = harness.load_config()

            # Phase 1: Seed usage_log to simulate 2 exhausted evaluations.
            # No real LLM calls needed — we just need the daily count to hit the cap.
            from social_hook.filesystem import generate_id

            print("       Phase 1: Seeding 2 usage_log rows (simulating exhausted daily cap)")
            for _i in range(2):
                harness.conn.execute(
                    "INSERT INTO usage_log (id, project_id, operation_type, model,"
                    " input_tokens, output_tokens, cost_cents, trigger_source)"
                    " VALUES (?, ?, 'evaluate', 'claude-cli/sonnet', 100, 50, 0.5, 'auto')",
                    (generate_id("usage"), harness.project_id),
                )
            harness.conn.commit()

            today_count = ops.get_today_auto_evaluation_count(harness.conn)
            assert today_count >= 2, f"Expected >= 2 auto evals, got {today_count}"
            print(f"       Cap hit: {today_count}/2 evaluations today")

            # Phase 2: Trigger 10 more commits — all should be deferred
            print("       Phase 2: Triggering 10 commits (all should defer)")
            deferred_keys = [
                "large_feature",
                "bugfix",
                "docs_only",
                "docs_only_2",
                "initial",
                "web_dashboard",
                "arc_llm_roles",
                "arc_journey",
                "arc_multi_provider",
                "arc_media_pipeline",
            ]
            for key in deferred_keys:
                exit_code = run_trigger(
                    COMMITS[key], str(harness.repo_path), verbose=runner.verbose
                )
                assert exit_code == 0, f"run_trigger({key}) returned {exit_code}"

            deferred = ops.get_deferred_eval_decisions(harness.conn, harness.project_id)
            assert len(deferred) == 10, f"Expected 10 deferred_eval decisions, got {len(deferred)}"
            print(f"       {len(deferred)} deferred_eval decisions created:")
            for d in deferred:
                print(f"         - {d.commit_hash[:8]} (reason: {d.reasoning})")

            # Phase 3: Simulate day rollover by backdating usage_log entries
            print("       Phase 3: Backdating usage_log (simulating day rollover)")
            harness.conn.execute(
                "UPDATE usage_log SET created_at = datetime('now', '-1 day')"
                " WHERE trigger_source = 'auto'"
            )
            harness.conn.commit()

            today_after = ops.get_today_auto_evaluation_count(harness.conn)
            assert today_after == 0, f"Expected 0 auto evals after backdate, got {today_after}"
            print(f"       Daily count reset: {today_after}/2")

            # Phase 4: Drain — batch mode combines all 10 into one evaluator call
            # Show what the batch request will look like
            from social_hook.trigger import parse_commit_info

            print("       Phase 4: Running batch drain (1 LLM call for 10 commits)")
            print("       Batch request preview:")
            for d in deferred:
                try:
                    ci = parse_commit_info(d.commit_hash, str(harness.repo_path))
                    summary = ci.message.splitlines()[0][:80]
                except Exception:
                    summary = d.commit_hash[:8]
                print(f"         - {d.commit_hash[:8]}: {summary}")

            _drain_deferred_evaluations(harness.conn, config, dry_run=False)

            # Verify: all deferred decisions should be gone
            remaining = ops.get_deferred_eval_decisions(harness.conn, harness.project_id)
            assert len(remaining) == 0, (
                f"Expected 0 deferred_eval after drain, got {len(remaining)}"
            )

            # Find the batch decision (commit_hash starts with "batch-")
            all_decisions = ops.get_recent_decisions(harness.conn, harness.project_id, limit=20)
            batch_decisions = [d for d in all_decisions if d.commit_hash.startswith("batch-")]

            detail = "Deferred: 10 -> drained"

            if batch_decisions:
                bd = batch_decisions[0]
                detail += f", batch decision: {bd.decision}"

                if bd.decision == "draft":
                    batch_drafts = ops.get_drafts_filtered(
                        harness.conn, project_id=harness.project_id, decision_id=bd.id
                    )
                    if batch_drafts:
                        detail += f", draft: {len(batch_drafts[0].content)} chars"

                        runner.add_review_item(
                            "T2",
                            title="Batch drain: 10 diverse commits -> 1 draft",
                            decision=bd.decision,
                            reasoning=bd.reasoning or "",
                            draft_content=batch_drafts[0].content,
                            review_question=(
                                "Does this draft coherently synthesize 10 diverse commits "
                                "(features, bugfixes, docs, new subsystems)? "
                                "Or is it just a bullet-point list? "
                                "Is the angle meaningful given the mix of changes?"
                            ),
                        )
                    else:
                        runner.add_review_item(
                            "T2",
                            title="Batch drain: draft decision but no draft content",
                            decision=bd.decision,
                            reasoning=bd.reasoning or "",
                            review_question="Draft decision was made but no draft found. Why?",
                        )
                else:
                    runner.add_review_item(
                        "T2",
                        title=f"Batch drain: 10 commits -> {bd.decision}",
                        decision=bd.decision,
                        reasoning=bd.reasoning or "",
                        review_question=(
                            f"Evaluator chose '{bd.decision}' for a batch of 10 commits. "
                            "Is this reasonable? Were the commits too minor to post about?"
                        ),
                    )
            else:
                detail += ", no batch decision found (drain may have failed silently)"
                runner.add_review_item(
                    "T2",
                    title="Batch drain: no batch decision created",
                    review_question="No batch decision was created. Check logs for errors.",
                )

            return detail

    runner.run_scenario("T2", "Batch drain after day rollover (10 commits)", t2, llm_call=True)
