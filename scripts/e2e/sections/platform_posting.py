"""Section U: Platform Posting scenarios."""

import logging

from e2e.constants import COMMITS
from e2e.helpers.snapshots import snapshot_rollback

log = logging.getLogger(__name__)


def _post_detail(result, platform):
    """Format post result as a readable string with clickable link."""
    lines = [
        f"       Platform:    {platform}",
        f"       External ID: {result.external_id}",
    ]
    if result.external_url:
        lines.append(f"       URL:         \033[4m{result.external_url}\033[0m")
    return "\n".join(lines)


def _pause_before_delete(pause, url=None):
    """If --pause is set, wait for user confirmation before deleting."""
    if not pause:
        return
    msg = "       Press Enter to delete"
    if url:
        msg += f" ({url})"
    msg += "..."
    input(msg)


def get_enabled_platforms(config):
    """Discover which platforms have valid credentials configured.

    Iterates known platform names, attempts create_adapter(), catches ConfigError
    for missing credentials, returns list of platform names that succeed.
    """
    from social_hook.adapters.platform.factory import create_adapter
    from social_hook.errors import ConfigError

    platforms = []
    for name in ("x", "linkedin"):
        try:
            create_adapter(name, config)
            platforms.append(name)
        except ConfigError:
            pass
    return platforms


def run(harness, runner, live=False, pause=False):
    """U1-U6: Platform posting scenarios.

    Args:
        live: Use real API calls (vs VCR cassettes).
        pause: Pause after each live post for manual verification before deletion.
            Implies --live. Use with: python scripts/e2e_test.py --only platform-posting --pause
    """
    from social_hook.db import operations as ops

    if not harness.project_id:
        harness.seed_project()

    config = harness.load_config()
    enabled = get_enabled_platforms(config)

    if not enabled:
        print("       No platform credentials configured -- skipping Section U")
        return

    print(f"       Enabled platforms: {', '.join(enabled)}")

    for platform in enabled:
        from social_hook.adapters.platform.factory import create_adapter

        plat_adapter = create_adapter(platform, config)

        # Phase 1: Validation
        def u_validate(plat=platform, adapter=plat_adapter):
            from e2e.vcr_config import vcr_context

            with vcr_context(plat, f"U-{plat}-validate", live=live):
                success, info = adapter.validate()
                assert success, f"Validation failed for {plat}: {info}"
                runner.add_review_item(
                    f"U-{plat}-validate",
                    title=f"Platform validation: {plat}",
                    review_question=f"Validated as: {info}",
                )
                return f"Validated as {info}"

        runner.run_scenario(
            f"U-{platform}-validate",
            f"Validate {platform} credentials",
            u_validate,
        )

        # Phase 1b: Single post + delete
        def u_single_post(plat=platform, adapter=plat_adapter):
            from e2e.vcr_config import vcr_context

            log_path = harness.base / "e2e-platform-posts.log"

            with vcr_context(plat, f"U-{plat}-post", live=live):
                result = adapter.post(
                    f"E2E test post from social-hook ({plat}). Safe to delete. #{plat}test",
                    dry_run=not live,
                )
                assert result.success, f"Post failed: {result.error}"
                assert result.external_id, "No external_id returned"

                # Log the post for recovery
                with open(log_path, "a") as f:
                    f.write(f"{plat}\t{result.external_id}\t{result.external_url}\n")

                print(_post_detail(result, plat))

                runner.add_review_item(
                    f"U-{plat}-post",
                    title=f"Single post: {plat}",
                    review_question=f"Post created: {result.external_url}",
                    external_id=result.external_id,
                    external_url=result.external_url,
                )

                # Cleanup: delete the test post
                if live and result.external_id:
                    _pause_before_delete(pause, result.external_url)
                    try:
                        adapter.delete(result.external_id)
                        print(f"       Deleted: {result.external_id}")
                    except Exception as e:
                        log.warning(f"Failed to delete test post {result.external_id}: {e}")

                return f"Posted: {result.external_id}"

        runner.run_scenario(
            f"U-{platform}-post",
            f"Single post on {platform}",
            u_single_post,
        )

        # Phase 2: Capability-driven scenarios

        for cap in plat_adapter.capabilities():
            if cap.name == "single_post":
                continue

            def u_capability(plat=platform, adapter=plat_adapter, capability=cap):
                """Test capability declaration is consistent with adapter methods."""
                if capability.name == "thread":
                    assert adapter.supports_threads(), (
                        f"{plat} declares thread but supports_threads() is False"
                    )
                if capability.media_modes:
                    assert adapter.supports_media(), (
                        f"{plat} declares media modes but supports_media() is False"
                    )
                return f"Capability {capability.name}: {len(capability.media_modes)} media modes"

            runner.run_scenario(
                f"U-{platform}-{cap.name}",
                f"Capability: {platform}/{cap.name}",
                u_capability,
            )

        # Phase 3: post_now pipeline
        def u_post_now(plat=platform):
            with snapshot_rollback(harness):
                # Ensure audience_introduced >= 1
                harness.conn.execute(
                    "UPDATE projects SET audience_introduced = 1 WHERE id = ?",
                    (harness.project_id,),
                )
                harness.conn.commit()

                draft = harness.seed_draft(
                    harness.project_id,
                    status="draft",
                    platform=plat,
                    content=f"E2E post_now test for {plat}. #{plat}test",
                )

                # Call scheduler_tick with draft_id (dry_run to avoid real API call)
                from social_hook.scheduler import scheduler_tick

                # First update to scheduled
                ops.update_draft(
                    harness.conn,
                    draft.id,
                    status="scheduled",
                    scheduled_time="2020-01-01 00:00:00",
                )
                harness.conn.commit()

                result = scheduler_tick(draft_id=draft.id, dry_run=True)

                # Re-read the draft
                updated = ops.get_draft(harness.conn, draft.id)
                assert updated is not None, "Draft not found after post_now"

                # In dry_run, the scheduler simulates success
                detail = f"status={updated.status}, processed={result}"

                runner.add_review_item(
                    f"U-{plat}-post-now",
                    title=f"Post Now pipeline: {plat}",
                    review_question=f"Did post_now process the draft? {detail}",
                )
                return detail

        runner.run_scenario(
            f"U-{platform}-post-now",
            f"Post Now pipeline ({platform})",
            u_post_now,
        )

    # Phase 4: Full trigger-to-post (single scenario, uses first enabled platform)
    def u_full_flow():
        with snapshot_rollback(harness):
            # Ensure audience_introduced >= 1
            harness.conn.execute(
                "UPDATE projects SET audience_introduced = 1 WHERE id = ?",
                (harness.project_id,),
            )
            harness.conn.commit()

            from social_hook.trigger import run_trigger

            exit_code = run_trigger(
                COMMITS["significant"],
                str(harness.repo_path),
                verbose=runner.verbose,
            )
            assert exit_code == 0, f"run_trigger returned {exit_code}"

            decisions = ops.get_recent_decisions(harness.conn, harness.project_id, limit=5)
            real = [d for d in decisions if not d.commit_hash.startswith("seed_")]

            if real and real[0].decision == "draft":
                from social_hook.db import get_pending_drafts

                drafts = get_pending_drafts(harness.conn, harness.project_id)
                if drafts:
                    draft = drafts[0]
                    runner.add_review_item(
                        "U-full-flow",
                        title=f"Full trigger-to-draft ({COMMITS['significant']})",
                        decision=real[0].decision,
                        episode_type=real[0].episode_type,
                        reasoning=real[0].reasoning or "",
                        draft_content=draft.content,
                        review_question="Full pipeline produced a draft. Content quality OK?",
                    )
                    return f"Draft created: {draft.platform}, {len(draft.content)} chars"

            detail = f"Decision: {real[0].decision if real else 'none'}"
            return detail

    runner.run_scenario(
        "U-full-flow",
        "Full trigger-to-draft flow",
        u_full_flow,
        llm_call=True,
        isolate=True,
    )
