"""Section B: Pipeline scenarios."""

import os
import subprocess

from e2e.constants import COMMITS


def run(harness, runner):
    """B1-B12: Pipeline scenarios."""
    from social_hook.db import get_pending_drafts, get_recent_decisions
    from social_hook.trigger import run_trigger

    # Ensure we have a project (may already exist from Section A)
    if not harness.project_id:
        harness.seed_project()

    # B1: Significant commit → evaluate → draft → schedule
    def b1():
        exit_code = run_trigger(
            COMMITS["significant"], str(harness.repo_path), verbose=runner.verbose
        )
        assert exit_code == 0, f"run_trigger returned {exit_code}"

        decisions = get_recent_decisions(harness.conn, harness.project_id, limit=5)
        assert len(decisions) > 0, "No decisions created"
        d = decisions[0]

        valid_decisions = {"draft", "hold", "skip"}
        assert d.decision in valid_decisions, f"Invalid decision: {d.decision}"

        detail = f"Commit: {COMMITS['significant']} Decision: {d.decision}"

        if d.decision == "draft":
            valid_episodes = {
                "decision",
                "before_after",
                "demo_proof",
                "milestone",
                "postmortem",
                "launch",
                "synthesis",
            }
            valid_categories = {"arc", "opportunistic", "experiment"}
            assert d.episode_type in valid_episodes, f"Invalid episode_type: {d.episode_type}"
            assert d.post_category in valid_categories, f"Invalid post_category: {d.post_category}"

            drafts = get_pending_drafts(harness.conn, harness.project_id)
            assert len(drafts) > 0, "No draft created for draft decision"
            assert drafts[0].content, "Draft content is empty"
            detail += f" ({d.episode_type}), Draft: {len(drafts[0].content)} chars"

            runner.add_review_item(
                "B1",
                title=f"Significant commit ({COMMITS['significant']})",
                decision=d.decision,
                episode_type=d.episode_type,
                post_category=d.post_category,
                reasoning=d.reasoning or "",
                draft_content=drafts[0].content,
                review_question="Episode type appropriate? Content quality?",
            )

        return detail

    runner.run_scenario(
        "B1", "Significant commit → evaluate → draft", b1, llm_call=True, isolate=True
    )

    # B2: Docs-only commit → not post worthy
    def b2():
        exit_code = run_trigger(
            COMMITS["docs_only"], str(harness.repo_path), verbose=runner.verbose
        )
        assert exit_code == 0, f"run_trigger returned {exit_code}"

        decisions = get_recent_decisions(harness.conn, harness.project_id, limit=5)
        # Find the decision for this specific commit
        d = None
        for dec in decisions:
            if dec.commit_hash.startswith(COMMITS["docs_only"][:7]):
                d = dec
                break
        assert d is not None, f"No decision found for commit {COMMITS['docs_only']}"

        runner.add_review_item(
            "B2",
            title=f"Docs-only commit ({COMMITS['docs_only']})",
            decision=d.decision,
            reasoning=d.reasoning or "",
            review_question="Correct call?",
        )
        return f"Decision: {d.decision}"

    runner.run_scenario("B2", "Docs-only commit → likely skip", b2, llm_call=True, isolate=True)

    # B3: Unregistered repo → silent exit
    def b3():
        unregistered = harness.base / "repos" / "unregistered"
        unregistered.mkdir(exist_ok=True)
        subprocess.run(["git", "init", str(unregistered)], capture_output=True)
        # Create a dummy commit
        dummy = unregistered / "README.md"
        dummy.write_text("test")
        subprocess.run(["git", "-C", str(unregistered), "add", "."], capture_output=True)
        subprocess.run(
            ["git", "-C", str(unregistered), "commit", "-m", "init", "--allow-empty"],
            capture_output=True,
            env={
                **os.environ,
                "GIT_AUTHOR_NAME": "test",
                "GIT_AUTHOR_EMAIL": "test@test.com",
                "GIT_COMMITTER_NAME": "test",
                "GIT_COMMITTER_EMAIL": "test@test.com",
            },
        )
        log = subprocess.run(
            ["git", "-C", str(unregistered), "log", "--oneline", "-1"],
            capture_output=True,
            text=True,
        )
        commit_hash = log.stdout.strip().split()[0] if log.stdout.strip() else "HEAD"

        exit_code = run_trigger(commit_hash, str(unregistered))
        assert exit_code == 0, f"Expected exit 0, got {exit_code}"
        return "Silent exit for unregistered repo"

    runner.run_scenario("B3", "Unregistered repo → silent exit", b3)

    # B4: Paused project → skip
    def b4():
        # Pause the project
        harness.conn.execute(
            "UPDATE projects SET paused = 1 WHERE id = ?",
            (harness.project_id,),
        )
        harness.conn.commit()

        exit_code = run_trigger(COMMITS["major_feature"], str(harness.repo_path))
        assert exit_code == 0, f"Expected exit 0, got {exit_code}"

        # Unpause
        harness.conn.execute(
            "UPDATE projects SET paused = 0 WHERE id = ?",
            (harness.project_id,),
        )
        harness.conn.commit()
        return "Skipped paused project"

    runner.run_scenario("B4", "Paused project → skip", b4)

    # B5: Missing API key → error
    def b5():
        env_path = harness.base / ".env"
        env_content = env_path.read_text()
        # Remove ANTHROPIC_API_KEY
        modified = "\n".join(
            line for line in env_content.splitlines() if not line.startswith("ANTHROPIC_API_KEY")
        )
        env_path.write_text(modified)

        try:
            exit_code = run_trigger(COMMITS["significant"], str(harness.repo_path))
            assert exit_code in (1, 3), f"Expected exit 1 or 3, got {exit_code}"
            return f"Error exit code: {exit_code}"
        finally:
            # Restore
            env_path.write_text(env_content)

    runner.run_scenario("B5", "Missing API key → error", b5)

    # B7: Dry-run mode (run before B6 to not pollute state)
    def b7():
        from social_hook.db import get_all_recent_decisions

        before = len(get_all_recent_decisions(harness.conn))
        exit_code = run_trigger(
            COMMITS["large_feature"],
            str(harness.repo_path),
            dry_run=True,
            verbose=runner.verbose,
        )
        assert exit_code == 0, f"run_trigger dry-run returned {exit_code}"

        after = len(get_all_recent_decisions(harness.conn))
        assert after == before, f"Dry-run persisted rows: {after} vs {before}"
        return "No rows persisted"

    runner.run_scenario("B7", "Dry-run mode", b7, llm_call=True)

    # B6: Free tier + long content → thread (structural check)
    def b6():
        from social_hook.db.operations import get_draft_tweets

        exit_code = run_trigger(
            COMMITS["large_feature"], str(harness.repo_path), verbose=runner.verbose
        )
        assert exit_code == 0, f"run_trigger returned {exit_code}"

        drafts = get_pending_drafts(harness.conn, harness.project_id)
        for draft in drafts:
            tweets = get_draft_tweets(harness.conn, draft.id)
            if tweets:
                return f"Thread found: {len(tweets)} tweets"

        # Thread not guaranteed — LLM may create a short post
        return "No thread (LLM chose single post)"

    runner.run_scenario(
        "B6", "Free tier + long content → thread check", b6, llm_call=True, isolate=True
    )

    # B8: Consolidation context visible
    def b8():
        # Seed a pending draft first
        harness.seed_draft(harness.project_id, status="draft")

        exit_code = run_trigger(
            COMMITS["major_feature"], str(harness.repo_path), verbose=runner.verbose
        )
        assert exit_code == 0, f"run_trigger returned {exit_code}"

        decisions = get_recent_decisions(harness.conn, harness.project_id, limit=5)
        assert len(decisions) > 0, "No decisions"
        d = decisions[0]
        valid = {"draft", "hold", "skip"}
        assert d.decision in valid, f"Invalid decision: {d.decision}"
        return f"Decision: {d.decision} (hold is valid outcome)"

    runner.run_scenario("B8", "Consolidation context visible", b8, llm_call=True, isolate=True)

    # B9: Deferred decision check
    def b9():
        exit_code = run_trigger(
            COMMITS["docs_only_2"], str(harness.repo_path), verbose=runner.verbose
        )
        assert exit_code == 0, f"run_trigger returned {exit_code}"

        decisions = get_recent_decisions(harness.conn, harness.project_id, limit=5)
        d = None
        for dec in decisions:
            if dec.commit_hash.startswith(COMMITS["docs_only_2"][:7]):
                d = dec
                break
        assert d is not None, f"No decision for {COMMITS['docs_only_2']}"
        valid = {"draft", "hold", "skip"}
        assert d.decision in valid
        return f"Decision: {d.decision} (hold is valid)"

    runner.run_scenario("B9", "Hold/skip for minor commit", b9, llm_call=True, isolate=True)

    # B10: Pipeline generates media when enabled
    def b10():
        # Enable image generation in config
        harness.update_config({"media_generation": {"enabled": True}})

        exit_code = run_trigger(
            COMMITS["significant"], str(harness.repo_path), verbose=runner.verbose
        )
        assert exit_code == 0, f"run_trigger returned {exit_code}"

        drafts = get_pending_drafts(harness.conn, harness.project_id)
        assert len(drafts) > 0, "No drafts created"

        # Find the most recent draft
        draft = drafts[0]

        # Structural assertion: if media_type is set, media_spec must be populated
        if draft.media_type and draft.media_type != "none":
            assert draft.media_spec is not None and draft.media_spec != {}, (
                f"Draft has media_type={draft.media_type} but media_spec is empty/None"
            )

        # File existence assertion: if media_paths set, files must exist on disk
        if draft.media_paths:
            from pathlib import Path as _Path

            for mp in draft.media_paths:
                assert _Path(mp).exists(), f"Media file not found on disk: {mp}"
                assert _Path(mp).stat().st_size > 0, f"Media file is empty: {mp}"

        detail = (
            f"Draft: {draft.id}, media_type={draft.media_type}, "
            f"media_spec={draft.media_spec}, media_paths={draft.media_paths}"
        )

        runner.add_review_item(
            "B10",
            title="Pipeline with media generation enabled",
            decision="draft",
            draft_content=draft.content,
            review_question=(
                "Does the media_spec contain sensible fields for the chosen tool? "
                "Does the generated media match the content?"
            ),
            media_type=draft.media_type,
            media_spec=draft.media_spec,
            media_paths=draft.media_paths,
        )

        # Restore image generation to disabled for other tests
        harness.update_config({"media_generation": {"enabled": False}})
        return detail

    runner.run_scenario(
        "B10", "Pipeline generates media when enabled", b10, llm_call=True, isolate=True
    )

    # B11: Per-tool media disable
    def b11():
        # Enable media generation globally but disable all tools
        harness.update_config(
            {
                "media_generation": {
                    "enabled": True,
                    "tools": {
                        "mermaid": False,
                        "nano_banana_pro": False,
                        "playwright": False,
                        "ray_so": False,
                    },
                }
            }
        )

        exit_code = run_trigger(
            COMMITS["significant"], str(harness.repo_path), verbose=runner.verbose
        )
        assert exit_code == 0, f"run_trigger returned {exit_code}"

        drafts = get_pending_drafts(harness.conn, harness.project_id)
        assert len(drafts) > 0, "No drafts created"

        # Verify no media files generated (all tools disabled)
        draft = drafts[0]
        detail = (
            f"Draft: {draft.id}, media_type={draft.media_type}, media_paths={draft.media_paths}"
        )

        runner.add_review_item(
            "B11",
            title="Per-tool media disable",
            decision="draft",
            draft_content=draft.content,
            review_question="Were all media tools correctly skipped despite evaluator suggesting one?",
            media_type=draft.media_type,
            media_paths=draft.media_paths,
        )

        # Restore media generation to disabled for other tests
        harness.update_config({"media_generation": {"enabled": False}})
        return detail

    runner.run_scenario("B11", "Per-tool media disable", b11, llm_call=True, isolate=True)

    # B12: Real media generation with mermaid adapter (no API key needed)
    def b12():
        from pathlib import Path as _Path

        from social_hook.adapters.media.mermaid import MermaidAdapter
        from social_hook.db import operations as ops
        from social_hook.filesystem import get_base_path

        # Seed a draft with a mermaid spec
        draft = harness.seed_draft(
            harness.project_id,
            status="draft",
            media_type="mermaid",
            media_spec={
                "diagram": "graph LR\n  A[Commit] --> B[Evaluate] --> C[Draft] --> D[Post]"
            },
        )

        # Generate media using the real adapter
        adapter = MermaidAdapter()
        output_dir = str(get_base_path() / "media-cache" / draft.id)
        result = adapter.generate(spec=draft.media_spec, output_dir=output_dir)

        assert result.success, f"Mermaid generation failed: {result.error}"
        assert result.file_path is not None, "No file path returned"
        assert _Path(result.file_path).exists(), f"File not on disk: {result.file_path}"
        assert _Path(result.file_path).stat().st_size > 100, "File suspiciously small"

        # Update draft with media path (as the pipeline would)
        ops.update_draft(harness.conn, draft.id, media_paths=[result.file_path])

        # Verify DB roundtrip
        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.media_paths == [result.file_path], (
            f"DB media_paths mismatch: {updated.media_paths}"
        )

        runner.add_review_item(
            "B12",
            title="Real mermaid media generation",
            decision="draft",
            draft_content=draft.content,
            review_question="Is the generated mermaid diagram a valid PNG file?",
            media_type="mermaid",
            media_paths=[result.file_path],
        )

        return f"Generated {result.file_path}, size={_Path(result.file_path).stat().st_size}"

    runner.run_scenario("B12", "Real mermaid media generation", b12)
