"""Scheduler tick: posts due drafts and manages lock file."""

import json
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Optional

from social_hook.config.yaml import load_full_config
from social_hook.notifications import send_notification
from social_hook.db import operations as ops
from social_hook.db.connection import get_connection, init_database
from social_hook.errors import ConfigError, DatabaseError, ErrorType, classify_error, classify_x_error
from social_hook.filesystem import generate_id, get_base_path, get_db_path
from social_hook.models import Post

logger = logging.getLogger(__name__)


# =============================================================================
# Lock file management
# =============================================================================


def get_lock_path() -> Path:
    """Get the path to the scheduler lock file."""
    return get_base_path() / "scheduler.lock"


def get_lock_pid(lock_path: Path) -> Optional[int]:
    """Read PID from lock file.

    Returns:
        PID as int, or None if file doesn't exist or is invalid
    """
    if not lock_path.exists():
        return None
    try:
        content = lock_path.read_text().strip()
        return int(content)
    except (ValueError, OSError):
        return None


def is_lock_stale(lock_path: Path) -> bool:
    """Check if a lock file is stale (process no longer running).

    Args:
        lock_path: Path to the lock file

    Returns:
        True if lock is stale (can be cleaned up)
    """
    pid = get_lock_pid(lock_path)
    if pid is None:
        return True

    try:
        os.kill(pid, 0)  # Signal 0 = check if process exists
        return False  # Process is alive
    except ProcessLookupError:
        return True  # Process is dead
    except PermissionError:
        return False  # Process exists but we can't signal it


def acquire_lock(lock_path: Optional[Path] = None) -> bool:
    """Acquire the scheduler lock.

    Args:
        lock_path: Override lock file path (for testing)

    Returns:
        True if lock was acquired, False if held by another process
    """
    if lock_path is None:
        lock_path = get_lock_path()

    if lock_path.exists():
        if not is_lock_stale(lock_path):
            return False
        # Stale lock - clean up
        logger.info(f"Cleaning up stale lock file: {lock_path}")
        lock_path.unlink()

    # Create lock with our PID
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(str(os.getpid()))
    return True


def release_lock(lock_path: Optional[Path] = None) -> None:
    """Release the scheduler lock.

    Args:
        lock_path: Override lock file path (for testing)
    """
    if lock_path is None:
        lock_path = get_lock_path()

    if lock_path.exists():
        # Only remove if it's our lock
        pid = get_lock_pid(lock_path)
        if pid == os.getpid():
            lock_path.unlink(missing_ok=True)


# =============================================================================
# Scheduler tick
# =============================================================================


def scheduler_tick(
    dry_run: bool = False,
    config_path: Optional[str] = None,
    lock_path: Optional[Path] = None,
) -> int:
    """Run one scheduler tick: post all due drafts.

    Args:
        dry_run: If True, simulate posting
        config_path: Optional config file override
        lock_path: Optional lock file path override (for testing)

    Returns:
        Number of drafts processed (posted or failed)
    """
    # Acquire lock
    if not acquire_lock(lock_path):
        logger.info("Scheduler tick skipped: lock held by another process")
        return 0

    effective_lock = lock_path or get_lock_path()

    try:
        # Load config
        config = load_full_config(yaml_path=config_path)

        # Init DB
        db_path = get_db_path()
        conn = init_database(db_path)

        # Get due drafts
        due_drafts = ops.get_due_drafts(conn)
        if not due_drafts:
            conn.close()
            return 0

        processed = 0

        for draft in due_drafts:
            try:
                # Apply pending changes if any
                changes = ops.get_draft_changes(conn, draft.id)
                for change in changes:
                    if change.field == "content" and change.new_value:
                        draft.content = change.new_value

                # Get project for this draft
                project = ops.get_project(conn, draft.project_id)
                if not project:
                    logger.error(f"Project not found for draft {draft.id}")
                    continue

                if project.paused:
                    logger.info(f"Skipping draft {draft.id}: project {project.name} is paused")
                    continue

                if dry_run:
                    # Simulate success
                    from social_hook.adapters.dry_run import dry_run_post_result
                    result = dry_run_post_result()
                else:
                    # Post via adapter
                    result = _post_draft(conn, draft, config)

                if result.success:
                    # Record success
                    ops.update_draft(conn, draft.id, status="posted")
                    post = Post(
                        id=generate_id("post"),
                        draft_id=draft.id,
                        project_id=draft.project_id,
                        platform=draft.platform,
                        external_id=result.external_id,
                        external_url=result.external_url,
                        content=draft.content,
                    )
                    ops.insert_post(conn, post)

                    send_notification(
                        config,
                        f"*Posted successfully*\n\n"
                        f"Project: {project.name}\n"
                        f"Platform: {draft.platform}\n"
                        f"URL: {result.external_url or 'N/A'}\n\n"
                        f"```\n{draft.content[:300]}\n```",
                        dry_run=dry_run,
                    )
                else:
                    _handle_post_failure(conn, draft, result.error or "Unknown error",
                                        config, dry_run)

                processed += 1

            except Exception as e:
                logger.error(f"Error processing draft {draft.id}: {e}")
                _handle_post_failure(conn, draft, str(e), config, dry_run)
                processed += 1

        conn.close()
        return processed

    finally:
        release_lock(effective_lock)


def _post_draft(conn, draft, config):
    """Post a draft using the appropriate platform adapter.

    Args:
        conn: Database connection (for thread tweet lookup)
        draft: Draft object to post
        config: Full config object

    Returns:
        PostResult or ThreadResult
    """
    from social_hook.adapters.models import PostResult

    if draft.platform == "x":
        from social_hook.adapters.platform.x import XAdapter

        api_key = config.env.get("X_API_KEY", "")
        api_secret = config.env.get("X_API_SECRET", "")
        access_token = config.env.get("X_ACCESS_TOKEN", "")
        access_secret = config.env.get("X_ACCESS_TOKEN_SECRET", "")

        if not all([api_key, api_secret, access_token, access_secret]):
            return PostResult(success=False, error="Missing X API credentials")

        x_config = config.platforms.get("x")
        tier = (x_config.account_tier if x_config else None) or "free"
        adapter = XAdapter(api_key, api_secret, access_token, access_secret, tier=tier)

        # Check if this is a thread (has draft_tweets)
        tweets = ops.get_draft_tweets(conn, draft.id)
        if tweets:
            tweet_dicts = []
            for i, t in enumerate(tweets):
                td = {"content": t.content, "media_paths": t.media_paths}
                # Attach draft-level media to first tweet if tweet has no own media
                if i == 0 and not t.media_paths and draft.media_paths:
                    td["media_paths"] = draft.media_paths
                tweet_dicts.append(td)
            thread_result = adapter.post_thread(tweet_dicts)

            # Update each draft_tweet with external_id and posted_at
            if thread_result.success:
                from datetime import datetime, timezone
                now_iso = datetime.now(timezone.utc).isoformat()
                for tweet, tweet_result in zip(tweets, thread_result.tweet_results):
                    if tweet_result.success:
                        ops.update_draft_tweet(
                            conn, tweet.id,
                            external_id=tweet_result.external_id,
                            posted_at=now_iso,
                        )
                    else:
                        ops.update_draft_tweet(
                            conn, tweet.id,
                            error=tweet_result.error,
                        )

            # Return first tweet's result as the PostResult for compatibility
            first = thread_result.tweet_results[0] if thread_result.tweet_results else None
            return PostResult(
                success=thread_result.success,
                external_id=first.external_id if first else None,
                external_url=first.external_url if first else None,
                error=thread_result.error,
            )

        return adapter.post(draft.content, media_paths=draft.media_paths or None)

    elif draft.platform == "linkedin":
        from social_hook.adapters.platform.linkedin import LinkedInAdapter

        access_token = config.env.get("LINKEDIN_ACCESS_TOKEN", "")
        if not access_token:
            return PostResult(success=False, error="Missing LinkedIn access token")

        adapter = LinkedInAdapter(access_token)
        # LinkedIn doesn't support threads — always post single content
        return adapter.post(draft.content, media_paths=draft.media_paths or None)

    else:
        return PostResult(success=False, error=f"Unsupported platform: {draft.platform}")


def _handle_post_failure(conn, draft, error_msg, config, dry_run):
    """Handle a failed post attempt with retry logic."""
    new_retry_count = draft.retry_count + 1

    if new_retry_count >= 3:
        # Max retries exceeded
        ops.update_draft(
            conn, draft.id,
            status="failed",
            retry_count=new_retry_count,
            last_error=error_msg,
        )
        logger.error(f"Draft {draft.id} failed after {new_retry_count} attempts: {error_msg}")

        project = ops.get_project(conn, draft.project_id)
        project_name = project.name if project else "Unknown"
        send_notification(
            config,
            f"*Post failed*\n\n"
            f"Project: {project_name}\n"
            f"Platform: {draft.platform}\n"
            f"Error: {error_msg}\n"
            f"Attempts: {new_retry_count}/3\n\n"
            f"Draft {draft.id} marked as failed.",
            dry_run=dry_run,
        )
    else:
        # Schedule retry with backoff
        from datetime import datetime, timedelta, timezone
        backoff_minutes = 5 * (2 ** new_retry_count)  # 10, 20 minutes
        retry_time = datetime.now(timezone.utc) + timedelta(minutes=backoff_minutes)

        ops.update_draft(
            conn, draft.id,
            status="scheduled",
            scheduled_time=retry_time.strftime("%Y-%m-%d %H:%M:%S"),
            retry_count=new_retry_count,
            last_error=error_msg,
        )
        logger.info(
            f"Draft {draft.id} retry {new_retry_count}/3 scheduled for "
            f"{retry_time.strftime('%H:%M UTC')} (backoff: {backoff_minutes}m)"
        )
