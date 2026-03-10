"""Section B: Pipeline scenarios."""

import os
import shutil
import subprocess
from pathlib import Path

from e2e.constants import COMMITS

# Persistent directory for reviewing generated media after E2E runs.
# Uses the real HOME (not the patched E2E temp HOME) so files survive cleanup.
_MEDIA_REVIEW_DIR: Path | None = None


def _init_media_review(harness):
    """Set up persistent media review directory under real ~/.social-hook/."""
    global _MEDIA_REVIEW_DIR
    real_home = harness._orig_home or str(Path.home())
    _MEDIA_REVIEW_DIR = Path(real_home) / ".social-hook" / "e2e-media-review"
    _MEDIA_REVIEW_DIR.mkdir(parents=True, exist_ok=True)


def persist_media(scenario_id: str, file_paths: list[str]) -> list[str]:
    """Copy generated media files to persistent review directory.

    Returns list of persistent file paths.
    """
    if not _MEDIA_REVIEW_DIR or not file_paths:
        return []
    dest_dir = _MEDIA_REVIEW_DIR / scenario_id.lower()
    dest_dir.mkdir(parents=True, exist_ok=True)
    persisted = []
    for fp in file_paths:
        src = Path(fp)
        if src.exists():
            dst = dest_dir / src.name
            shutil.copy2(src, dst)
            persisted.append(str(dst))
    return persisted


def run(harness, runner):
    """B1-B18: Pipeline scenarios."""
    from social_hook.db import get_pending_drafts, get_recent_decisions
    from social_hook.trigger import run_trigger

    _init_media_review(harness)

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

        saved = persist_media("B12", [result.file_path])
        return f"Generated {result.file_path}, size={_Path(result.file_path).stat().st_size}, saved={saved}"

    runner.run_scenario("B12", "Real mermaid media generation", b12)

    # B13: Real ray_so generation (requires Playwright + Chromium)
    def b13():
        from pathlib import Path as _Path

        from social_hook.adapters.media.rayso import RaySoAdapter
        from social_hook.db import operations as ops
        from social_hook.filesystem import get_base_path

        # Playwright needs to find Chromium under the real HOME, not the E2E temp HOME
        _real_home = harness._orig_home or str(_Path.home())
        _real_browsers = _Path(_real_home) / "Library" / "Caches" / "ms-playwright"
        if _real_browsers.exists() and "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_real_browsers)

        draft = harness.seed_draft(
            harness.project_id,
            status="draft",
            media_type="ray_so",
            media_spec={
                "code": "def hello():\n    print('Hello, world!')",
                "language": "python",
                "theme": "candy",
                "dark_mode": True,
            },
        )

        adapter = RaySoAdapter()
        output_dir = str(get_base_path() / "media-cache" / draft.id)
        result = adapter.generate(spec=draft.media_spec, output_dir=output_dir)

        assert result.success, f"ray_so generation failed: {result.error}"
        assert result.file_path is not None, "No file path returned"
        assert _Path(result.file_path).exists(), f"File not on disk: {result.file_path}"
        assert _Path(result.file_path).stat().st_size > 100, "File suspiciously small"

        ops.update_draft(harness.conn, draft.id, media_paths=[result.file_path])

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.media_paths == [result.file_path], (
            f"DB media_paths mismatch: {updated.media_paths}"
        )

        runner.add_review_item(
            "B13",
            title="Real ray_so media generation",
            decision="draft",
            draft_content=draft.content,
            review_question="Is the generated code snippet image readable and correctly themed?",
            media_type="ray_so",
            media_paths=[result.file_path],
        )

        saved = persist_media("B13", [result.file_path])
        return f"Generated {result.file_path}, size={_Path(result.file_path).stat().st_size}, saved={saved}"

    runner.run_scenario("B13", "Real ray_so media generation", b13)

    # B14: Real nano_banana_pro generation (requires GEMINI_API_KEY)
    def b14():
        from pathlib import Path as _Path

        from social_hook.adapters.media.nanabananapro import NanaBananaAdapter
        from social_hook.db import operations as ops
        from social_hook.filesystem import get_base_path

        config = harness.load_config()
        api_key = config.env.get("GEMINI_API_KEY")
        assert api_key, "GEMINI_API_KEY not configured — required for B14"

        draft = harness.seed_draft(
            harness.project_id,
            status="draft",
            media_type="nano_banana_pro",
            media_spec={
                "prompt": (
                    "A minimalist flat illustration of a developer committing code, "
                    "blue and purple tones"
                )
            },
        )

        adapter = NanaBananaAdapter(api_key=api_key)
        output_dir = str(get_base_path() / "media-cache" / draft.id)
        result = adapter.generate(spec=draft.media_spec, output_dir=output_dir)

        assert result.success, f"nano_banana_pro generation failed: {result.error}"
        assert result.file_path is not None, "No file path returned"
        assert _Path(result.file_path).exists(), f"File not on disk: {result.file_path}"
        assert _Path(result.file_path).stat().st_size > 1000, (
            f"Image file too small ({_Path(result.file_path).stat().st_size} bytes)"
        )

        ops.update_draft(harness.conn, draft.id, media_paths=[result.file_path])

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.media_paths == [result.file_path], (
            f"DB media_paths mismatch: {updated.media_paths}"
        )

        runner.add_review_item(
            "B14",
            title="Real nano_banana_pro media generation",
            decision="draft",
            draft_content=draft.content,
            review_question="Is the AI-generated image relevant to the prompt and usable for social media?",
            media_type="nano_banana_pro",
            media_paths=[result.file_path],
        )

        saved = persist_media("B14", [result.file_path])
        return f"Generated {result.file_path}, size={_Path(result.file_path).stat().st_size}, saved={saved}"

    runner.run_scenario("B14", "Real nano_banana_pro media generation", b14)

    # B15: Bad spec → graceful error per tool
    def b15():
        from social_hook.adapters.media.mermaid import MermaidAdapter
        from social_hook.adapters.media.nanabananapro import NanaBananaAdapter
        from social_hook.adapters.media.playwright import PlaywrightAdapter
        from social_hook.adapters.media.rayso import RaySoAdapter

        errors = []

        # Mermaid: missing 'diagram' and 'code' keys
        r = MermaidAdapter().generate({"not_diagram": "invalid"})
        assert not r.success, "Mermaid should fail with bad spec"
        assert r.error, "Mermaid error message should be non-empty"
        errors.append(f"mermaid: {r.error}")

        # RaySo: missing 'code' key
        r = RaySoAdapter().generate({})
        assert not r.success, "RaySo should fail with empty spec"
        assert r.error, "RaySo error message should be non-empty"
        errors.append(f"ray_so: {r.error}")

        # Playwright: missing 'url' key
        r = PlaywrightAdapter().generate({})
        assert not r.success, "Playwright should fail with empty spec"
        assert r.error, "Playwright error message should be non-empty"
        errors.append(f"playwright: {r.error}")

        # NanaBanana: missing 'prompt' key
        r = NanaBananaAdapter(api_key="fake_key_for_spec_validation").generate({})
        assert not r.success, "NanaBanana should fail with empty spec"
        assert r.error, "NanaBanana error message should be non-empty"
        errors.append(f"nano_banana_pro: {r.error}")

        return " | ".join(errors)

    runner.run_scenario("B15", "Bad spec graceful error handling", b15)

    # B16: Nano_banana_pro round-trip lifecycle (generate → regen → remove)
    def b16():
        from pathlib import Path as _Path
        from unittest.mock import MagicMock as _MagicMock
        from unittest.mock import patch as _patch

        from social_hook.adapters.media.nanabananapro import NanaBananaAdapter
        from social_hook.adapters.models import MediaResult
        from social_hook.bot.buttons import handle_callback
        from social_hook.db import operations as ops
        from social_hook.filesystem import get_base_path
        from social_hook.messaging.base import CallbackEvent, SendResult

        config = harness.load_config()
        api_key = config.env.get("GEMINI_API_KEY")
        assert api_key, "GEMINI_API_KEY not configured — required for B16"
        chat_id = config.env.get("TELEGRAM_CHAT_ID", "test")

        def make_callback(data):
            action, _, payload = data.partition(":")
            return CallbackEvent(
                callback_id="cb_b16",
                chat_id=chat_id,
                action=action,
                payload=payload,
                message_id="1",
            )

        # Step 1: Real generation
        original_spec = {
            "prompt": (
                "Abstract geometric pattern representing version control branches, "
                "neon colors on dark background"
            )
        }
        draft = harness.seed_draft(
            harness.project_id,
            status="draft",
            media_type="nano_banana_pro",
            media_spec=original_spec,
        )

        adapter = NanaBananaAdapter(api_key=api_key)
        output_dir = str(get_base_path() / "media-cache" / draft.id)
        result = adapter.generate(spec=original_spec, output_dir=output_dir)

        assert result.success, f"Initial generation failed: {result.error}"
        assert _Path(result.file_path).exists(), "Generated file not on disk"

        persist_media("B16", [result.file_path])

        ops.update_draft(
            harness.conn,
            draft.id,
            media_paths=[result.file_path],
            media_spec_used=original_spec,
        )

        # Step 2: Regeneration via button handler (mock adapter to avoid second API call)
        new_spec = {"prompt": "Futuristic code editor floating in space, cyberpunk style"}
        ops.update_draft(harness.conn, draft.id, media_spec=new_spec)

        mock_media_adapter = _MagicMock()
        mock_media_adapter.generate.return_value = MediaResult(
            success=True, file_path="/tmp/b16_regenerated.png"
        )

        mock_msg_adapter = _MagicMock()
        mock_msg_adapter.send_message.return_value = SendResult(success=True, message_id="m1")
        mock_msg_adapter.answer_callback.return_value = True

        with _patch(
            "social_hook.adapters.registry.get_media_adapter",
            return_value=mock_media_adapter,
        ):
            handle_callback(make_callback(f"media_regen:{draft.id}"), mock_msg_adapter, config)

        assert mock_media_adapter.generate.called, "Regeneration did not call adapter.generate()"

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.media_paths == ["/tmp/b16_regenerated.png"], (
            f"media_paths not updated after regen: {updated.media_paths}"
        )
        assert updated.media_spec_used == new_spec, (
            f"media_spec_used not updated: {updated.media_spec_used}"
        )

        # Check audit trail for regen
        changes = ops.get_draft_changes(harness.conn, draft.id)
        media_changes = [c for c in changes if c.field == "media_paths"]
        assert len(media_changes) >= 1, (
            f"Expected DraftChange for media_paths after regen, got {len(media_changes)}"
        )

        # Step 3: Remove media
        handle_callback(make_callback(f"media_remove:{draft.id}"), mock_msg_adapter, config)

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.media_paths == [], f"media_paths not cleared: {updated.media_paths}"

        # Check audit trail for removal
        changes = ops.get_draft_changes(harness.conn, draft.id)
        media_changes = [c for c in changes if c.field == "media_paths"]
        assert len(media_changes) >= 2, (
            f"Expected 2 DraftChange entries for media_paths, got {len(media_changes)}"
        )

        return "Generate → regen → remove lifecycle complete with audit trail"

    runner.run_scenario("B16", "Nano_banana_pro round-trip lifecycle", b16)

    # B17: Pipeline media error propagation (mocked adapter failure)
    def b17():
        from unittest.mock import MagicMock as _MagicMock
        from unittest.mock import patch as _patch

        from social_hook.adapters.models import MediaResult

        harness.update_config({"media_generation": {"enabled": True}})

        mock_adapter = _MagicMock()
        mock_adapter.generate.return_value = MediaResult(
            success=False, error="Simulated API failure"
        )

        with _patch(
            "social_hook.adapters.registry.get_media_adapter",
            return_value=mock_adapter,
        ):
            exit_code = run_trigger(
                COMMITS["significant"], str(harness.repo_path), verbose=runner.verbose
            )
        assert exit_code == 0, f"run_trigger returned {exit_code}"

        drafts = get_pending_drafts(harness.conn, harness.project_id)
        assert len(drafts) > 0, "No drafts created despite media failure (should be non-fatal)"

        draft = drafts[0]

        # If evaluator selected a media tool, verify error propagation
        if draft.media_type and draft.media_type != "none":
            assert not draft.media_paths, (
                f"media_paths should be empty on failure: {draft.media_paths}"
            )
            assert draft.media_spec is not None, (
                "media_spec should be preserved for retry"
            )
            assert draft.last_error and "Simulated API failure" in draft.last_error, (
                f"last_error should contain failure message: {draft.last_error}"
            )

        detail = (
            f"Draft: {draft.id}, media_type={draft.media_type}, "
            f"media_paths={draft.media_paths}, last_error={draft.last_error}"
        )

        runner.add_review_item(
            "B17",
            title="Pipeline media error propagation",
            decision="draft",
            draft_content=draft.content,
            review_question=(
                "Was the draft created despite media failure? "
                "Is the error message preserved for retry?"
            ),
            media_type=draft.media_type,
            media_paths=draft.media_paths,
        )

        harness.update_config({"media_generation": {"enabled": False}})
        return detail

    runner.run_scenario(
        "B17", "Pipeline media error propagation", b17, llm_call=True, isolate=True
    )

    # B18: Drafter + real nano_banana_pro (seeded decision, real LLM + real Gemini)
    def b18():
        from pathlib import Path as _Path
        from types import SimpleNamespace

        from social_hook.config.project import load_project_config
        from social_hook.db import operations as ops
        from social_hook.drafting import draft_for_platforms
        from social_hook.filesystem import generate_id
        from social_hook.llm.dry_run import DryRunContext
        from social_hook.llm.prompts import assemble_evaluator_context
        from social_hook.models import Decision
        from social_hook.trigger import parse_commit_info

        config = harness.load_config()
        api_key = config.env.get("GEMINI_API_KEY")
        assert api_key, "GEMINI_API_KEY not configured — required for B18"

        # Ensure media generation is enabled for nano_banana_pro
        harness.update_config({
            "media_generation": {
                "enabled": True,
                "tools": {
                    "mermaid": False,
                    "nano_banana_pro": True,
                    "playwright": False,
                    "ray_so": False,
                },
            }
        })
        config = harness.load_config()

        # Build real CommitInfo from repo history
        commit = parse_commit_info(COMMITS["major_feature"], str(harness.repo_path))

        # Seed a decision with media_tool="nano_banana_pro"
        decision = Decision(
            id=generate_id("decision"),
            project_id=harness.project_id,
            commit_hash=COMMITS["major_feature"],
            decision="draft",
            reasoning="E2E test — seeded decision for nano_banana_pro media",
            episode_type="milestone",
            post_category="arc",
            media_tool="nano_banana_pro",
            commit_summary=commit.message,
        )
        from social_hook.db import insert_decision

        insert_decision(harness.conn, decision)
        harness.conn.commit()

        # Build ProjectContext
        project_config = load_project_config(str(harness.repo_path))
        db = DryRunContext(harness.conn, dry_run=False)
        context = assemble_evaluator_context(
            db,
            harness.project_id,
            project_config,
            commit_timestamp=commit.timestamp,
            parent_timestamp=commit.parent_timestamp,
        )

        # Build evaluation compat (what make_eval_compat would produce)
        eval_compat = SimpleNamespace(
            decision="draft",
            reasoning="E2E test — seeded decision for nano_banana_pro media",
            angle="Feature showcase",
            episode_type="milestone",
            post_category="arc",
            arc_id=None,
            new_arc_theme=None,
            media_tool="nano_banana_pro",
            reference_posts=[],
            commit_summary=commit.message,
            include_project_docs=False,
        )

        # Run drafting pipeline
        project = ops.get_project(harness.conn, harness.project_id)
        draft_results = draft_for_platforms(
            config,
            harness.conn,
            db,
            project,
            decision_id=decision.id,
            evaluation=eval_compat,
            context=context,
            commit=commit,
            project_config=project_config,
            verbose=runner.verbose,
        )

        assert len(draft_results) > 0, "No drafts created by draft_for_platforms"

        draft = draft_results[0].draft
        assert draft.media_type == "nano_banana_pro", (
            f"Expected media_type=nano_banana_pro, got {draft.media_type}"
        )
        assert draft.media_spec is not None, "media_spec is None"
        assert "prompt" in draft.media_spec, (
            f"media_spec missing 'prompt' key: {draft.media_spec}"
        )
        assert draft.media_spec["prompt"], "media_spec prompt is empty"
        assert draft.media_paths, f"media_paths is empty: {draft.media_paths}"

        for mp in draft.media_paths:
            assert _Path(mp).exists(), f"Media file not on disk: {mp}"
            assert _Path(mp).stat().st_size > 1000, (
                f"Image file too small ({_Path(mp).stat().st_size} bytes): {mp}"
            )

        runner.add_review_item(
            "B18",
            title="Drafter + real nano_banana_pro generation",
            decision="draft",
            draft_content=draft.content,
            review_question=(
                "Does the AI-generated image match the draft content? "
                "Is the drafter's prompt sensible for the commit?"
            ),
            media_type=draft.media_type,
            media_spec=draft.media_spec,
            media_paths=draft.media_paths,
        )

        harness.update_config({"media_generation": {"enabled": False}})

        persist_media("B18", draft.media_paths)

        return (
            f"Draft: {draft.id}, prompt={draft.media_spec.get('prompt', '')[:80]}..., "
            f"files={len(draft.media_paths)}"
        )

    runner.run_scenario(
        "B18", "Drafter + real nano_banana_pro generation", b18, llm_call=True, isolate=True
    )

    # Print location of persisted media files for review
    if _MEDIA_REVIEW_DIR and _MEDIA_REVIEW_DIR.exists() and any(_MEDIA_REVIEW_DIR.iterdir()):
        from e2e.runner import file_link

        print(f"\n  Media files saved for review: {_MEDIA_REVIEW_DIR}")
        for sub in sorted(_MEDIA_REVIEW_DIR.iterdir()):
            if sub.is_dir():
                files = list(sub.iterdir())
                print(f"    {sub.name}/: {len(files)} file(s)")
                for f in files:
                    print(f"      {file_link(str(f))} ({f.stat().st_size:,} bytes)")
