"""Section S: Cross-Post References scenarios."""

from e2e.constants import COMMITS


def _seed_post_record(harness, platform, content, external_id, external_url):
    """Create a fake Decision -> Draft -> Post chain in the DB.

    Gives the evaluator a visible entry in its "Post History" section.
    Returns the Post object.
    """
    from social_hook.db import insert_decision, insert_draft, insert_post
    from social_hook.filesystem import generate_id
    from social_hook.models.core import Decision, Draft, Post

    decision = Decision(
        id=generate_id("decision"),
        project_id=harness.project_id,
        commit_hash=f"seed_{generate_id('commit')[:12]}",
        decision="draft",
        reasoning="Seeded post for cross-post reference testing",
        episode_type="milestone",
        post_category="arc",
    )
    insert_decision(harness.conn, decision)

    draft = Draft(
        id=generate_id("draft"),
        project_id=harness.project_id,
        decision_id=decision.id,
        platform=platform,
        content=content,
        status="posted",
    )
    insert_draft(harness.conn, draft)

    post = Post(
        id=generate_id("post"),
        draft_id=draft.id,
        project_id=harness.project_id,
        platform=platform,
        content=content,
        external_id=external_id,
        external_url=external_url,
    )
    insert_post(harness.conn, post)

    return post, decision


def run(harness, runner):
    """S1-S6: Cross-post reference scenarios."""
    from social_hook.db import operations as ops

    if not harness.project_id:
        harness.seed_project()

    # S1: Natural cross-post reference (no nudging)
    def s1():
        from social_hook.trigger import run_trigger

        # Seed a post on X about the LLM layer
        seeded_post, _seed_dec = _seed_post_record(
            harness,
            platform="x",
            content=(
                "Built the foundation of Social Hook's LLM layer — role-based agents "
                "(evaluator, drafter, gatekeeper) that each handle a specific step in "
                "the content pipeline."
            ),
            external_id="1234567890",
            external_url="https://x.com/user/status/1234567890",
        )

        # Trigger a related commit (multi-provider extends LLM layer)
        exit_code = run_trigger(
            COMMITS["arc_multi_provider"], str(harness.repo_path), verbose=runner.verbose
        )
        assert exit_code == 0, f"run_trigger returned {exit_code}"

        decisions = ops.get_recent_decisions(harness.conn, harness.project_id, limit=10)
        # Filter out seed decisions
        real_decisions = [d for d in decisions if not d.commit_hash.startswith("seed_")]
        assert len(real_decisions) > 0, "No non-seed decisions created"
        d = real_decisions[0]

        detail = f"Decision: {d.decision}"
        referenced = False

        if d.reference_posts and seeded_post.id in d.reference_posts:
            referenced = True
            detail += f", referenced seeded post {seeded_post.id}"

            # Verify draft also got reference_post_id
            if d.decision == "draft":
                from social_hook.db import get_pending_drafts

                drafts = get_pending_drafts(harness.conn, harness.project_id)
                if drafts and drafts[0].reference_post_id:
                    detail += f", draft ref={drafts[0].reference_post_id}"
        else:
            detail += ", no reference (observational — not required)"

        evaluation = {
            "angle": d.angle,
            "post_category": d.post_category,
            "arc_id": d.arc_id,
            "reference_posts": d.reference_posts,
            "media_tool": d.media_tool,
            "commit_summary": d.commit_summary,
        }
        runner.add_review_item(
            "S1",
            title=f"Natural cross-post reference ({COMMITS['arc_multi_provider']})",
            decision=d.decision,
            episode_type=d.episode_type,
            reasoning=d.reasoning or "",
            evaluation=evaluation,
            review_question=(
                "Did evaluator naturally reference the seeded LLM-layer post? "
                f"Referenced: {referenced}"
            ),
        )
        return detail

    runner.run_scenario(
        "S1", "Natural cross-post reference (no nudging)", s1, llm_call=True, isolate=True
    )

    # S2: Direct instruction cross-post reference
    def s2():
        from social_hook.trigger import run_trigger

        # Write context-notes.md instructing evaluator to use reference_posts
        context_notes_path = harness.repo_path / ".social-hook" / "context-notes.md"
        context_notes_path.write_text(
            "# Context Notes\n\n"
            "| Date | Note | Source |\n"
            "|------|------|--------|\n"
            "| 2025-01-01 | TEST MODE: When evaluating commits, check Post History "
            "for previous posts. If the current commit is related to a previous "
            "post's topic, you MUST include that post's ID in the reference_posts "
            "field of your target decision. This is required to verify the cross-post "
            "reference pipeline. | test |\n"
        )

        # Seed a post on X about the adapter framework
        seeded_post, _seed_dec = _seed_post_record(
            harness,
            platform="x",
            content=(
                "Shipped the complete adapter framework for Social Hook — X API v2 "
                "(OAuth 1.0a), LinkedIn REST API (OAuth 2.0), and four media generation "
                "adapters."
            ),
            external_id="9876543210",
            external_url="https://x.com/user/status/9876543210",
        )

        try:
            exit_code = run_trigger(
                COMMITS["major_feature"], str(harness.repo_path), verbose=runner.verbose
            )
            assert exit_code == 0, f"run_trigger returned {exit_code}"

            decisions = ops.get_recent_decisions(harness.conn, harness.project_id, limit=10)
            real_decisions = [d for d in decisions if not d.commit_hash.startswith("seed_")]
            assert len(real_decisions) > 0, "No non-seed decisions created"
            d = real_decisions[0]

            detail = f"Decision: {d.decision}"

            if d.decision == "draft":
                assert d.reference_posts and len(d.reference_posts) > 0, (
                    "Draft decision but reference_posts is empty — context-notes.md "
                    "instructed evaluator to reference"
                )
                detail += f", reference_posts={d.reference_posts}"

                from social_hook.db import get_pending_drafts

                drafts = get_pending_drafts(harness.conn, harness.project_id)
                if drafts:
                    draft = drafts[0]
                    if draft.reference_post_id:
                        detail += f", draft ref_id={draft.reference_post_id}"
                    if draft.post_format:
                        detail += f", post_format={draft.post_format}"

            evaluation = {
                "angle": d.angle,
                "post_category": d.post_category,
                "arc_id": d.arc_id,
                "reference_posts": d.reference_posts,
                "media_tool": d.media_tool,
                "commit_summary": d.commit_summary,
            }
            runner.add_review_item(
                "S2",
                title=f"Direct instruction cross-post ref ({COMMITS['major_feature']})",
                decision=d.decision,
                episode_type=d.episode_type,
                reasoning=d.reasoning or "",
                evaluation=evaluation,
                review_question=(
                    "Did evaluator follow context-notes.md instruction to reference "
                    "the seeded adapter-framework post?"
                ),
            )
            return detail
        finally:
            # Clean up context-notes.md
            if context_notes_path.exists():
                context_notes_path.unlink()

    runner.run_scenario(
        "S2", "Direct instruction cross-post reference", s2, llm_call=True, isolate=True
    )

    # S3: Arc-based cross-post reference
    def s3():
        from social_hook.filesystem import generate_id
        from social_hook.models.narrative import Arc
        from social_hook.trigger import run_trigger

        # Create an Arc
        arc = Arc(
            id=generate_id("arc"),
            project_id=harness.project_id,
            theme="LLM Provider Architecture",
            status="active",
            post_count=1,
        )
        ops.insert_arc(harness.conn, arc)

        # Seed a post within that arc
        seeded_post, seed_dec = _seed_post_record(
            harness,
            platform="x",
            content=(
                "Introduced Social Hook's LLM layer — a role-based agent system where "
                "each agent (evaluator, drafter, gatekeeper) handles one step of the "
                "content pipeline."
            ),
            external_id="1111111111",
            external_url="https://x.com/user/status/1111111111",
        )
        # Link the seed decision to the arc
        harness.conn.execute(
            "UPDATE decisions SET arc_id = ? WHERE id = ?",
            (arc.id, seed_dec.id),
        )
        harness.conn.commit()

        # Trigger a related commit
        exit_code = run_trigger(
            COMMITS["arc_multi_provider"], str(harness.repo_path), verbose=runner.verbose
        )
        assert exit_code == 0, f"run_trigger returned {exit_code}"

        decisions = ops.get_recent_decisions(harness.conn, harness.project_id, limit=10)
        real_decisions = [d for d in decisions if not d.commit_hash.startswith("seed_")]
        assert len(real_decisions) > 0, "No non-seed decisions created"
        d = real_decisions[0]

        continued_arc = d.arc_id == arc.id
        referenced = d.reference_posts and seeded_post.id in d.reference_posts

        detail = f"Decision: {d.decision}, continued_arc={continued_arc}, referenced={referenced}"

        evaluation = {
            "angle": d.angle,
            "post_category": d.post_category,
            "arc_id": d.arc_id,
            "reference_posts": d.reference_posts,
            "media_tool": d.media_tool,
            "commit_summary": d.commit_summary,
            "continued_arc": continued_arc,
        }
        runner.add_review_item(
            "S3",
            title=f"Arc-based cross-post reference ({COMMITS['arc_multi_provider']})",
            decision=d.decision,
            episode_type=d.episode_type,
            reasoning=d.reasoning or "",
            evaluation=evaluation,
            review_question=(
                f"Did evaluator continue arc '{arc.theme}'? "
                f"continued_arc={continued_arc}, referenced={referenced}"
            ),
        )
        return detail

    runner.run_scenario("S3", "Arc-based cross-post reference", s3, llm_call=True, isolate=True)

    # S4: Adapter post_with_reference() structural test (no LLM)
    def s4():
        from unittest.mock import MagicMock, patch

        from social_hook.adapters.models import PostResult, ReferenceType
        from social_hook.db import insert_decision, insert_draft
        from social_hook.filesystem import generate_id
        from social_hook.models.core import Decision, Draft
        from social_hook.scheduler import _post_draft

        # Seed a post on X with an external_id
        seeded_post, _seed_dec = _seed_post_record(
            harness,
            platform="x",
            content="Seed post for S4 structural test.",
            external_id="s4_external_123",
            external_url="https://x.com/user/status/s4_external_123",
        )

        # Create a Decision + Draft with post_format="quote" and reference_post_id
        decision = Decision(
            id=generate_id("decision"),
            project_id=harness.project_id,
            commit_hash=f"s4_{generate_id('commit')[:12]}",
            decision="draft",
            reasoning="S4 structural test",
            episode_type="milestone",
            post_category="arc",
        )
        insert_decision(harness.conn, decision)

        draft = Draft(
            id=generate_id("draft"),
            project_id=harness.project_id,
            decision_id=decision.id,
            platform="x",
            content="This post references a previous one. #test",
            status="scheduled",
            post_format="quote",
            reference_post_id=seeded_post.id,
        )
        insert_draft(harness.conn, draft)
        harness.conn.commit()

        # Create a mock adapter
        mock_adapter = MagicMock()
        mock_adapter.post_with_reference.return_value = PostResult(
            success=True, external_id="posted_123"
        )
        mock_adapter.supports_reference_type.return_value = True

        config = harness.load_config()

        with patch(
            "social_hook.adapters.platform.factory.create_adapter",
            return_value=mock_adapter,
        ):
            result = _post_draft(harness.conn, draft, config)

        assert mock_adapter.post_with_reference.called, "post_with_reference() was not called"

        call_args = mock_adapter.post_with_reference.call_args
        reference_arg = call_args[0][1]  # second positional arg is reference
        assert reference_arg.reference_type == ReferenceType.QUOTE, (
            f"Expected QUOTE, got {reference_arg.reference_type}"
        )
        assert reference_arg.external_id == "s4_external_123", (
            f"Wrong external_id: {reference_arg.external_id}"
        )
        assert result.success, f"Post failed: {result.error}"

        return "post_with_reference() called with ReferenceType.QUOTE"

    runner.run_scenario("S4", "Adapter post_with_reference() structural test", s4)

    # S5: Arc continuation regression (no LLM)
    def s5():
        from unittest.mock import MagicMock, patch

        from social_hook.adapters.models import PostResult
        from social_hook.db import insert_decision, insert_draft, insert_post
        from social_hook.filesystem import generate_id
        from social_hook.models.core import Decision, Draft, Post
        from social_hook.models.narrative import Arc
        from social_hook.scheduler import _post_draft

        # Create an Arc
        arc = Arc(
            id=generate_id("arc"),
            project_id=harness.project_id,
            theme="S5 test arc",
            status="active",
            post_count=1,
        )
        ops.insert_arc(harness.conn, arc)

        # Seed first Decision + Draft + Post in this arc
        first_decision = Decision(
            id=generate_id("decision"),
            project_id=harness.project_id,
            commit_hash=f"s5a_{generate_id('commit')[:12]}",
            decision="draft",
            reasoning="S5 first arc post",
            episode_type="milestone",
            post_category="arc",
            arc_id=arc.id,
        )
        insert_decision(harness.conn, first_decision)

        first_draft = Draft(
            id=generate_id("draft"),
            project_id=harness.project_id,
            decision_id=first_decision.id,
            platform="x",
            content="First post in the arc.",
            status="posted",
        )
        insert_draft(harness.conn, first_draft)

        first_post = Post(
            id=generate_id("post"),
            draft_id=first_draft.id,
            project_id=harness.project_id,
            platform="x",
            content="First post in the arc.",
            external_id="s5_first_post",
            external_url="https://x.com/user/status/s5_first_post",
        )
        insert_post(harness.conn, first_post)

        # Create second Decision + Draft for "current" commit in same arc (no post_format set)
        second_decision = Decision(
            id=generate_id("decision"),
            project_id=harness.project_id,
            commit_hash=f"s5b_{generate_id('commit')[:12]}",
            decision="draft",
            reasoning="S5 second arc post",
            episode_type="milestone",
            post_category="arc",
            arc_id=arc.id,
        )
        insert_decision(harness.conn, second_decision)

        second_draft = Draft(
            id=generate_id("draft"),
            project_id=harness.project_id,
            decision_id=second_decision.id,
            platform="x",
            content="Second post continuing the arc.",
            status="scheduled",
            # Intentionally no post_format or reference_post_id
        )
        insert_draft(harness.conn, second_draft)
        harness.conn.commit()

        # Mock adapter to avoid real API calls
        mock_adapter = MagicMock()
        mock_adapter.post_with_reference.return_value = PostResult(
            success=True, external_id="s5_posted"
        )
        mock_adapter.supports_reference_type.return_value = True

        config = harness.load_config()

        with patch(
            "social_hook.adapters.platform.factory.create_adapter",
            return_value=mock_adapter,
        ):
            result = _post_draft(harness.conn, second_draft, config)

        # _post_draft should have detected arc continuation and set post_format + reference_post_id
        updated = ops.get_draft(harness.conn, second_draft.id)
        assert updated.post_format == "quote", (
            f"Expected post_format='quote', got '{updated.post_format}'"
        )
        assert updated.reference_post_id == first_post.id, (
            f"Expected reference_post_id='{first_post.id}', got '{updated.reference_post_id}'"
        )
        assert result.success, f"Post failed: {result.error}"

        return (
            f"Arc continuation: post_format={updated.post_format}, "
            f"reference_post_id={updated.reference_post_id}"
        )

    runner.run_scenario("S5", "Arc continuation regression", s5)

    # S6: Deterministic drafting pipeline
    def s6():
        from types import SimpleNamespace

        from social_hook.config.project import load_project_config
        from social_hook.drafting import draft_for_platforms
        from social_hook.filesystem import generate_id
        from social_hook.llm.dry_run import DryRunContext
        from social_hook.llm.prompts import assemble_evaluator_context
        from social_hook.models.core import Decision
        from social_hook.trigger import parse_commit_info

        # Seed a post on X
        seeded_post, _seed_dec = _seed_post_record(
            harness,
            platform="x",
            content="Seeded post for S6 deterministic drafting test.",
            external_id="s6_external_999",
            external_url="https://x.com/user/status/s6_external_999",
        )

        # Create a Decision record
        decision = Decision(
            id=generate_id("decision"),
            project_id=harness.project_id,
            commit_hash=COMMITS["major_feature"],
            decision="draft",
            reasoning="S6 deterministic drafting test",
            episode_type="milestone",
            post_category="arc",
            reference_posts=[seeded_post.id],
        )
        from social_hook.db import insert_decision

        insert_decision(harness.conn, decision)
        harness.conn.commit()

        # Build evaluation with reference_posts pointing to seeded post
        evaluation = SimpleNamespace(
            decision="draft",
            reasoning="S6 test",
            angle="Feature showcase",
            episode_type="milestone",
            post_category="arc",
            arc_id=None,
            new_arc_theme=None,
            media_tool=None,
            reference_posts=[seeded_post.id],
            commit_summary="WS3 adapters implementation",
            include_project_docs=False,
        )

        config = harness.load_config()
        project_config = load_project_config(str(harness.repo_path))
        commit = parse_commit_info(COMMITS["major_feature"], str(harness.repo_path))

        db = DryRunContext(harness.conn, dry_run=False)
        context = assemble_evaluator_context(
            db,
            harness.project_id,
            project_config,
            commit_timestamp=commit.timestamp,
            parent_timestamp=commit.parent_timestamp,
        )

        project = ops.get_project(harness.conn, harness.project_id)

        draft_results = draft_for_platforms(
            config,
            harness.conn,
            db,
            project,
            decision_id=decision.id,
            evaluation=evaluation,
            context=context,
            commit=commit,
            project_config=project_config,
            verbose=runner.verbose,
        )

        assert len(draft_results) > 0, "No drafts created by draft_for_platforms"

        draft = draft_results[0].draft
        assert draft.reference_post_id == seeded_post.id, (
            f"Expected reference_post_id={seeded_post.id}, got {draft.reference_post_id}"
        )
        assert draft.post_format == "quote", (
            f"Expected post_format='quote', got '{draft.post_format}'"
        )

        detail = (
            f"Draft ref_id={draft.reference_post_id}, "
            f"post_format={draft.post_format}, "
            f"content_len={len(draft.content)}"
        )

        runner.add_review_item(
            "S6",
            title="Deterministic drafting pipeline with reference_posts",
            decision="draft",
            episode_type="milestone",
            reasoning="S6 test — seeded evaluation with reference_posts",
            draft_content=draft.content,
            evaluation={
                "reference_posts": [seeded_post.id],
                "post_format": draft.post_format,
                "reference_post_id": draft.reference_post_id,
            },
            review_question=(
                "Does the draft reference the seeded post? "
                "Is reference_post_id and post_format='quote' set correctly?"
            ),
        )
        return detail

    runner.run_scenario("S6", "Deterministic drafting pipeline", s6, llm_call=True, isolate=True)
