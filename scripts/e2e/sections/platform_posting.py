"""Section U: Platform Posting scenarios.

Tests platform adapter validation, posting (text, media, threads, quotes),
capability consistency checks, and pipeline integration. All scenarios that
create external posts support --pause for manual verification before cleanup.
"""

import logging
from pathlib import Path

from e2e.constants import COMMITS
from e2e.helpers.snapshots import snapshot_rollback

log = logging.getLogger(__name__)

# Path to media test fixtures (relative to this file)
_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "media"

# ---------------------------------------------------------------------------
# Media fixture registry — maps media mode name to fixture filenames.
# Add a file + dict entry to auto-discover new media mode tests.
# ---------------------------------------------------------------------------
MEDIA_FIXTURES: dict[str, list[str]] = {
    "single_image": ["test.png"],
    # Future: "gif": ["test.gif"], "video": ["test.mp4"]
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _safe_delete(adapter, external_id, label="post"):
    """Delete a post, logging warnings on failure."""
    try:
        adapter.delete(external_id)
        print(f"       Deleted {label}: {external_id}")
    except Exception as e:
        log.warning("Failed to delete %s %s: %s", label, external_id, e)


def _copy_real_tokens(harness):
    """Copy oauth_tokens from the real DB into the harness's isolated DB.

    In --live mode, the harness uses a temp directory with a fresh DB.
    Tokens saved by oauth2_setup.py live in the user's real ~/.social-hook/ DB.
    This copies them so the harness can create authenticated adapters.
    """
    import sqlite3

    # Use harness.real_base (captured before HOME is overridden)
    real_db = harness.real_base / "social-hook.db"
    if not real_db.exists():
        log.warning("Real DB not found at %s — skipping token copy", real_db)
        return

    try:
        real_conn = sqlite3.connect(str(real_db))
        real_conn.row_factory = sqlite3.Row
        rows = real_conn.execute(
            "SELECT account_name, platform, access_token, refresh_token, expires_at, updated_at FROM oauth_tokens"
        ).fetchall()
        real_conn.close()

        if not rows:
            log.warning("No tokens in real DB — run oauth2_setup.py first")
            return

        for row in rows:
            harness.conn.execute(
                """INSERT OR REPLACE INTO oauth_tokens
                   (account_name, platform, access_token, refresh_token, expires_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    row["account_name"],
                    row["platform"],
                    row["access_token"],
                    row["refresh_token"],
                    row["expires_at"],
                    row["updated_at"],
                ),
            )
        harness.conn.commit()
        print(f"       Copied {len(rows)} token(s) from real DB for live testing")
    except Exception as e:
        log.warning("Failed to copy tokens from real DB: %s", e)


# ---------------------------------------------------------------------------
# Platform discovery
# ---------------------------------------------------------------------------


def get_enabled_platforms(config, db_path=None):
    """Discover which platforms have valid credentials configured.

    Iterates config.platforms (instead of a hardcoded list), attempts
    create_adapter(), catches ConfigError for missing credentials, returns
    list of platform names that succeed.

    Args:
        config: Global Config object.
        db_path: Path to SQLite database (passed through to create_adapter).
    """
    from social_hook.adapters.platform.factory import create_adapter
    from social_hook.errors import ConfigError

    platforms = []
    for name in config.platforms:
        if not config.platforms[name].enabled:
            continue
        try:
            create_adapter(name, config, db_path=db_path)
            platforms.append(name)
        except ConfigError:
            pass
    return platforms


# ---------------------------------------------------------------------------
# Capability exercise functions (Phase 2)
# ---------------------------------------------------------------------------


def _exercise_thread(adapter, plat, runner, harness, live, pause):
    """U-{plat}-thread: Post a 2-tweet thread, verify, clean up."""
    from e2e.vcr_config import vcr_context

    if not adapter.supports_threads():
        return None  # skip — not supported

    log_path = harness.base / "e2e-platform-posts.log"

    def _run(plat=plat, adapter=adapter):
        with vcr_context(plat, f"U-{plat}-thread", live=live):
            thread_result = adapter.post_thread(
                [
                    {"content": f"E2E thread part 1 ({plat}). Safe to delete. #{plat}test"},
                    {"content": f"E2E thread part 2 ({plat}). Safe to delete. #{plat}test"},
                ],
                dry_run=not live,
            )
            assert thread_result.success, f"Thread failed: {thread_result.error}"
            assert len(thread_result.tweet_results) >= 2, (
                f"Expected >=2 results, got {len(thread_result.tweet_results)}"
            )
            for i, tr in enumerate(thread_result.tweet_results):
                assert tr.external_id, f"Tweet {i + 1} missing external_id"

            # Log and review
            head = thread_result.tweet_results[0]
            urls = [tr.external_url for tr in thread_result.tweet_results if tr.external_url]
            with open(log_path, "a") as f:
                for tr in thread_result.tweet_results:
                    f.write(f"{plat}\t{tr.external_id}\t{tr.external_url}\n")

            runner.add_review_item(
                f"U-{plat}-thread",
                title=f"Thread: {plat}",
                review_question=f"Thread posted ({len(urls)} tweets). Check chain: {', '.join(urls)}",
            )

            # Cleanup: pause then delete head tweet (deleting head removes thread)
            if live and head.external_id:
                _pause_before_delete(pause, head.external_url)
                _safe_delete(adapter, head.external_id, label="thread head")

            return f"Thread: {len(thread_result.tweet_results)} tweets"

    runner.run_scenario(
        f"U-{plat}-thread",
        f"Thread on {plat}",
        _run,
    )


def _exercise_quote(adapter, plat, runner, harness, live, pause):
    """U-{plat}-quote: Create seed post, quote it, verify, clean up."""
    from social_hook.adapters.models import PostReference, ReferenceType

    if not adapter.supports_reference_type(ReferenceType.QUOTE):
        return None  # skip — not supported

    from e2e.vcr_config import vcr_context

    log_path = harness.base / "e2e-platform-posts.log"

    def _run(plat=plat, adapter=adapter):
        with vcr_context(plat, f"U-{plat}-quote", live=live):
            # Step 1: create seed post
            seed = adapter.post(
                f"E2E seed for quote test ({plat}). Safe to delete. #{plat}test",
                dry_run=not live,
            )
            assert seed.success, f"Seed post failed: {seed.error}"
            assert seed.external_id, "Seed missing external_id"

            with open(log_path, "a") as f:
                f.write(f"{plat}\t{seed.external_id}\t{seed.external_url}\n")

            # Step 2: quote the seed
            try:
                ref = PostReference(
                    external_id=seed.external_id,
                    external_url=seed.external_url or "",
                    reference_type=ReferenceType.QUOTE,
                )
                quote_result = adapter.post_with_reference(
                    f"E2E quote test ({plat}). Safe to delete. #{plat}test",
                    ref,
                    dry_run=not live,
                )
                assert quote_result.success, f"Quote failed: {quote_result.error}"
                assert quote_result.external_id, "Quote missing external_id"

                with open(log_path, "a") as f:
                    f.write(f"{plat}\t{quote_result.external_id}\t{quote_result.external_url}\n")

                runner.add_review_item(
                    f"U-{plat}-quote",
                    title=f"Quote: {plat}",
                    review_question=f"Quote posted: {quote_result.external_url} (quotes {seed.external_url})",
                )

                # Cleanup: pause, then delete quote first, then seed
                if live:
                    _pause_before_delete(pause, quote_result.external_url)
                    if quote_result.external_id:
                        _safe_delete(adapter, quote_result.external_id, label="quote")
            finally:
                # Always clean up seed, even if quote assertion fails
                if live and seed.external_id:
                    _safe_delete(adapter, seed.external_id, label="seed")

            return f"Quoted: {quote_result.external_id}"

    runner.run_scenario(
        f"U-{plat}-quote",
        f"Quote on {plat}",
        _run,
    )


# Capability exercise registry — maps capability name to exercise function.
# Adding a new capability exercise = one function + one dict entry.
CAPABILITY_EXERCISES: dict[str, callable] = {
    "thread": _exercise_thread,
    "quote": _exercise_quote,
    # Future: "reply": _exercise_reply, "poll": _exercise_poll
}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run(harness, runner, live=False, pause=False):
    """U: Platform posting scenarios.

    Args:
        harness: E2EHarness with project seeded.
        runner: E2ERunner for scenario execution and review items.
        live: Use real API calls (vs VCR cassettes).
        pause: Pause after each live post for manual verification before deletion.
            Implies --live. Use with: python scripts/e2e_test.py --only platform-posting --pause
    """
    from social_hook.db import operations as ops

    if not harness.project_id:
        harness.seed_project()

    # For --live mode, copy OAuth tokens from the real DB into the harness DB.
    # The harness creates an isolated temp environment, so tokens saved via
    # oauth2_setup.py (in the real ~/.social-hook/) aren't available.
    if live and harness.db_path and harness.conn:
        _copy_real_tokens(harness)

    config = harness.load_config()
    db_path = str(harness.db_path) if harness.db_path else None
    enabled = get_enabled_platforms(config, db_path=db_path)

    if not enabled:
        print("       No platform credentials configured -- skipping Section U")
        return

    print(f"       Enabled platforms: {', '.join(enabled)}")

    for platform in enabled:
        from social_hook.adapters.platform.factory import create_adapter

        plat_adapter = create_adapter(platform, config, db_path=db_path)

        # ---------------------------------------------------------------
        # Phase 1: Auth & Basic Operations
        # ---------------------------------------------------------------

        # U-{plat}-validate
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

        # U-{plat}-post-text (was u_single_post)
        def u_post_text(plat=platform, adapter=plat_adapter):
            from e2e.vcr_config import vcr_context

            log_path = harness.base / "e2e-platform-posts.log"

            with vcr_context(plat, f"U-{plat}-post-text", live=live):
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
                    f"U-{plat}-post-text",
                    title=f"Single post: {plat}",
                    review_question=f"Post created: {result.external_url}",
                    external_id=result.external_id,
                    external_url=result.external_url,
                )

                # Cleanup: delete the test post
                if live and result.external_id:
                    _pause_before_delete(pause, result.external_url)
                    _safe_delete(adapter, result.external_id)

                return f"Posted: {result.external_id}"

        runner.run_scenario(
            f"U-{platform}-post-text",
            f"Single text post on {platform}",
            u_post_text,
        )

        # U-{plat}-post-media (NEW — OAuth 2.0 proof)
        def u_post_media(plat=platform, adapter=plat_adapter):
            if not adapter.supports_media():
                return "SKIP: adapter does not support media"

            from e2e.vcr_config import vcr_context

            fixture_path = str(_FIXTURES_DIR / MEDIA_FIXTURES["single_image"][0])
            log_path = harness.base / "e2e-platform-posts.log"

            with vcr_context(plat, f"U-{plat}-post-media", live=live):
                result = adapter.post(
                    f"E2E media test from social-hook ({plat}). Safe to delete. #{plat}test",
                    media_paths=[fixture_path],
                    dry_run=not live,
                )
                assert result.success, f"Media post failed: {result.error}"
                assert result.external_id, "No external_id returned for media post"

                # Log the post for recovery
                with open(log_path, "a") as f:
                    f.write(f"{plat}\t{result.external_id}\t{result.external_url}\n")

                print(_post_detail(result, plat))

                runner.add_review_item(
                    f"U-{plat}-post-media",
                    title=f"Media post: {plat}",
                    review_question=f"Post with image created: {result.external_url} -- check image renders",
                    external_id=result.external_id,
                    external_url=result.external_url,
                )

                # Cleanup
                if live and result.external_id:
                    _pause_before_delete(pause, result.external_url)
                    _safe_delete(adapter, result.external_id)

                return f"Media posted: {result.external_id}"

        runner.run_scenario(
            f"U-{platform}-post-media",
            f"Media post on {platform}",
            u_post_media,
        )

        # ---------------------------------------------------------------
        # Phase 2: Capability Exercise (per platform, registry-driven)
        # ---------------------------------------------------------------

        # Consistency check for all capabilities
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
                f"U-{platform}-caps-{cap.name}",
                f"Capability check: {platform}/{cap.name}",
                u_capability,
            )

        # Exercise functions for capabilities in the registry
        for cap in plat_adapter.capabilities():
            exercise_fn = CAPABILITY_EXERCISES.get(cap.name)
            if exercise_fn:
                exercise_fn(plat_adapter, platform, runner, harness, live, pause)

        # ---------------------------------------------------------------
        # Phase 3: Pipeline Integration
        # ---------------------------------------------------------------

        # U-{plat}-post-now
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

    # -------------------------------------------------------------------
    # Phase 4: Full trigger-to-draft (once, first enabled platform)
    # -------------------------------------------------------------------

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
