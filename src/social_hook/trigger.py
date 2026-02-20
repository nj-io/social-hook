"""One-shot trigger: commit evaluation and draft creation pipeline."""

import json
import logging
import subprocess
import sys
from typing import Optional

import requests

from social_hook.config.yaml import load_full_config
from social_hook.db.connection import get_connection, init_database
from social_hook.db import operations as ops
from social_hook.errors import ConfigError, DatabaseError
from social_hook.filesystem import generate_id, get_db_path, get_base_path
from social_hook.llm.dry_run import DryRunContext
from social_hook.llm.prompts import assemble_evaluator_context
from social_hook.models import CommitInfo, Decision, Draft, DraftTweet, Post
from social_hook.config.yaml import TIER_CHAR_LIMITS
from social_hook.scheduling import calculate_optimal_time

logger = logging.getLogger(__name__)


def parse_commit_info(commit_hash: str, repo_path: str) -> CommitInfo:
    """Parse commit info from git.

    Args:
        commit_hash: Git commit hash
        repo_path: Path to the git repository

    Returns:
        CommitInfo with parsed data
    """
    try:
        # Get commit message
        message = subprocess.run(
            ["git", "-C", repo_path, "log", "-1", "--format=%s", commit_hash],
            capture_output=True, text=True, check=True,
        ).stdout.strip()

        # Get author date (ISO 8601 with timezone)
        timestamp = subprocess.run(
            ["git", "-C", repo_path, "log", "-1", "--format=%aI", commit_hash],
            capture_output=True, text=True, check=True,
        ).stdout.strip()

        # Get parent commit's author date (fails with exit 128 on first commit)
        parent_result = subprocess.run(
            ["git", "-C", repo_path, "log", "-1", "--format=%aI", f"{commit_hash}~1"],
            capture_output=True, text=True,
        )
        parent_timestamp = parent_result.stdout.strip() if parent_result.returncode == 0 else None

        # Get stat summary
        stat_output = subprocess.run(
            ["git", "-C", repo_path, "show", "--stat", "--format=", commit_hash],
            capture_output=True, text=True, check=True,
        ).stdout.strip()

        # Parse files changed from stat
        files_changed = []
        insertions = 0
        deletions = 0
        for line in stat_output.split("\n"):
            line = line.strip()
            if "|" in line and not line.startswith(" "):
                # "filename | N +++--"
                parts = line.split("|")
                if parts:
                    files_changed.append(parts[0].strip())
            elif "changed" in line:
                # Summary line: "N files changed, N insertions(+), N deletions(-)"
                if "insertion" in line:
                    for part in line.split(","):
                        part = part.strip()
                        if "insertion" in part:
                            insertions = int(part.split()[0])
                        elif "deletion" in part:
                            deletions = int(part.split()[0])

        # Get diff
        diff = subprocess.run(
            ["git", "-C", repo_path, "diff", f"{commit_hash}~1..{commit_hash}"],
            capture_output=True, text=True,
        ).stdout

        # Fallback for first commit (no parent)
        if not diff:
            diff = subprocess.run(
                ["git", "-C", repo_path, "show", "--format=", commit_hash],
                capture_output=True, text=True,
            ).stdout

        return CommitInfo(
            hash=commit_hash,
            message=message,
            diff=diff,
            files_changed=files_changed,
            insertions=insertions,
            deletions=deletions,
            timestamp=timestamp,
            parent_timestamp=parent_timestamp,
        )
    except subprocess.CalledProcessError:
        # Return minimal info if git commands fail
        return CommitInfo(
            hash=commit_hash,
            message="(unable to parse)",
            diff="",
        )


def git_remote_origin(repo_path: str) -> Optional[str]:
    """Get the git remote origin URL for worktree detection.

    Args:
        repo_path: Path to the git repository

    Returns:
        Remote origin URL, or None if not available
    """
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "remote", "get-url", "origin"],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip() or None
    except subprocess.CalledProcessError:
        return None


def send_telegram_notification(
    token: str,
    chat_id: str,
    message: str,
) -> bool:
    """Send a Telegram notification via direct HTTP to Bot API.

    Works independently of the bot daemon.

    Args:
        token: Telegram Bot API token
        chat_id: Target chat ID
        message: Message text (supports Markdown)

    Returns:
        True if message was sent successfully
    """
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown",
            },
            timeout=10,
        )
        return response.status_code == 200
    except requests.RequestException as e:
        logger.warning(f"Telegram notification failed: {e}")
        return False


def run_trigger(
    commit_hash: str,
    repo_path: str,
    dry_run: bool = False,
    config_path: Optional[str] = None,
    verbose: bool = False,
    show_prompt: bool = False,
) -> int:
    """Run the commit-to-draft trigger pipeline.

    Exit codes:
        0 = success or unregistered (silent)
        1 = config error
        2 = DB error
        3 = LLM API error
        4 = Telegram error (non-fatal, draft still saved)

    Args:
        commit_hash: Git commit hash to evaluate
        repo_path: Path to the repository
        dry_run: If True, skip DB writes and real API calls
        config_path: Optional override for config location
        verbose: If True, print detailed output

    Returns:
        Exit code (0-4)
    """
    # 1. Load config
    try:
        config = load_full_config(
            yaml_path=config_path if config_path else None,
        )
    except ConfigError as e:
        logger.error(f"Config error: {e}")
        if verbose:
            print(f"Config error: {e}", file=sys.stderr)
        return 1

    # 2. Initialize DB
    try:
        db_path = get_db_path()
        conn = init_database(db_path)
    except DatabaseError as e:
        logger.error(f"Database error: {e}")
        if verbose:
            print(f"Database error: {e}", file=sys.stderr)
        return 2

    db = DryRunContext(conn, dry_run=dry_run)

    # 3. Check registration
    project = ops.get_project_by_path(conn, repo_path)
    if project is None:
        # Try worktree detection via origin
        origin = git_remote_origin(repo_path)
        if origin:
            projects = ops.get_project_by_origin(conn, origin)
            if projects:
                project = projects[0]  # Use first match

    if project is None:
        # Not registered - exit silently
        if verbose:
            print(f"Repository {repo_path} is not registered. Exiting.")
        conn.close()
        return 0

    if project.paused:
        if verbose:
            print(f"Project {project.name} is paused. Skipping.")
        conn.close()
        return 0

    # 4. Load project config
    from social_hook.config.project import load_project_config

    project_config = load_project_config(repo_path)

    # 5. Parse commit (needed for timestamp-filtered context)
    commit = parse_commit_info(commit_hash, repo_path)

    # 6. Assemble context (with commit timestamps for narrative filtering)
    context = assemble_evaluator_context(
        db, project.id, project_config,
        commit_timestamp=commit.timestamp,
        parent_timestamp=commit.parent_timestamp,
    )

    if verbose:
        print(f"Evaluating commit {commit.hash[:8]}: {commit.message}")

    # 7. Evaluate
    from social_hook.llm.factory import create_client
    from social_hook.llm.evaluator import Evaluator

    try:
        evaluator_client = create_client(config.models.evaluator, config, verbose=verbose)
    except ConfigError as e:
        logger.error(f"Config error: {e}")
        if verbose:
            print(f"Config error: {e}", file=sys.stderr)
        conn.close()
        return 1

    try:
        evaluator = Evaluator(evaluator_client)
        evaluation = evaluator.evaluate(commit, context, db, show_prompt=show_prompt)
    except Exception as e:
        logger.error(f"LLM API error during evaluation: {e}")
        if verbose:
            print(f"LLM API error: {e}", file=sys.stderr)
        conn.close()
        return 3

    # 8. Save decision
    decision = Decision(
        id=generate_id("decision"),
        project_id=project.id,
        commit_hash=commit_hash,
        decision=evaluation.decision,
        reasoning=evaluation.reasoning,
        angle=getattr(evaluation, "angle", None),
        episode_type=evaluation.episode_type,
        post_category=evaluation.post_category,
        arc_id=getattr(evaluation, "arc_id", None),
        media_tool=getattr(evaluation, "media_tool", None),
        platforms=getattr(evaluation, "platforms", {}),
    )
    db.insert_decision(decision)

    if verbose:
        print(f"Decision: {evaluation.decision}")
        print(f"Reasoning: {evaluation.reasoning}")

    # 9. If post-worthy, create draft
    if evaluation.decision == "post_worthy":
        try:
            drafter_client = create_client(config.models.drafter, config, verbose=verbose)
        except ConfigError as e:
            logger.error(f"Config error: {e}")
            if verbose:
                print(f"Config error: {e}", file=sys.stderr)
            conn.close()
            return 1

        try:
            from social_hook.llm.drafter import Drafter

            drafter = Drafter(drafter_client)

            # Determine platform and tier
            platform = "x"
            tier = "free"
            if config.platforms.x.enabled:
                platform = "x"
                tier = config.platforms.x.account_tier or "free"
            elif config.platforms.linkedin.enabled:
                platform = "linkedin"

            draft_result = drafter.create_draft(
                evaluation, context, commit, db,
                platform=platform, tier=tier,
                config=project_config.context,
            )

            # Format decision: narrative-driven, tier-enforced
            use_thread = _needs_thread(draft_result, platform, tier)

            thread_tweets = []
            if use_thread:
                thread_result = drafter.create_thread(
                    evaluation, context, commit, db, platform=platform,
                )
                # Parse thread content into individual tweets
                thread_tweets = _parse_thread_tweets(thread_result.content)
                # Store full concatenated content for human review
                draft_content = thread_result.content
                draft_reasoning = thread_result.reasoning
            else:
                draft_content = draft_result.content
                draft_reasoning = draft_result.reasoning
        except Exception as e:
            logger.error(f"LLM API error during drafting: {e}")
            if verbose:
                print(f"LLM API error during drafting: {e}", file=sys.stderr)
            conn.close()
            return 3

        # Pre-generate draft ID for media output directory
        draft_id = generate_id("draft")

        # --- Media generation ---
        media_paths = []
        media_type_str = None
        media_spec_dict = None

        # Resolve media type: prefer drafter's choice, fall back to evaluator's recommendation
        _drafter_media = (
            getattr(draft_result, 'media_type', None)
            and draft_result.media_type.value != "none"
        )
        _evaluator_media = (
            getattr(evaluation, 'media_tool', None)
            and evaluation.media_tool != "none"
        )

        if config.image_generation.enabled and (_drafter_media or _evaluator_media):
            if _drafter_media:
                media_type_str = draft_result.media_type.value
                media_spec_dict = draft_result.media_spec or {}
            elif _evaluator_media:
                media_type_str = evaluation.media_tool
                media_spec_dict = {}

            try:
                from social_hook.adapters.registry import get_media_adapter

                api_key = None
                if media_type_str == "nano_banana_pro":
                    api_key = config.env.get("GEMINI_API_KEY")
                    if not api_key:
                        logger.warning("nano_banana_pro requested but GEMINI_API_KEY not set")
                        media_type_str = None

                if media_type_str:
                    media_adapter = get_media_adapter(media_type_str, api_key=api_key)
                    if media_adapter:
                        output_dir = str(get_base_path() / "media-cache" / draft_id)
                        result = media_adapter.generate(
                            spec=media_spec_dict,
                            output_dir=output_dir,
                            dry_run=dry_run,
                        )
                        if result.success and result.file_path:
                            media_paths = [result.file_path]
                            if verbose:
                                print(f"Media generated: {result.file_path}")
                        else:
                            logger.warning(f"Media generation failed: {result.error}")
            except Exception as e:
                logger.warning(f"Media generation error (non-fatal): {e}")

        # Calculate optimal time
        schedule = calculate_optimal_time(
            conn,
            project.id,
            tz=config.scheduling.timezone,
            max_posts_per_day=config.scheduling.max_posts_per_day,
            min_gap_minutes=config.scheduling.min_gap_minutes,
            optimal_days=config.scheduling.optimal_days,
            optimal_hours=config.scheduling.optimal_hours,
        )

        # Save draft
        draft = Draft(
            id=draft_id,
            project_id=project.id,
            decision_id=decision.id,
            platform=platform,
            content=draft_content,
            media_paths=media_paths,
            media_type=media_type_str,
            media_spec=media_spec_dict,
            suggested_time=schedule.datetime,
            reasoning=draft_reasoning,
        )
        db.insert_draft(draft)

        # Save thread tweets if applicable
        if thread_tweets:
            for position, tweet_content in enumerate(thread_tweets):
                tweet = DraftTweet(
                    id=generate_id("tweet"),
                    draft_id=draft.id,
                    position=position,
                    content=tweet_content,
                )
                db.insert_draft_tweet(tweet)

        if verbose:
            print(f"Draft created: {draft.id}")
            if thread_tweets:
                print(f"Format: thread ({len(thread_tweets)} tweets)")
            print(f"Content: {draft_content[:100]}...")
            print(f"Suggested time: {schedule.datetime} ({schedule.time_reason})")

        # Send Telegram notification
        telegram_token = config.env.get("TELEGRAM_BOT_TOKEN")
        chat_ids_str = config.env.get("TELEGRAM_ALLOWED_CHAT_IDS", "")
        if telegram_token and chat_ids_str and not dry_run:
            from social_hook.bot.notifications import (
                format_draft_review,
                get_review_buttons_normalized,
            )
            from social_hook.messaging.base import OutboundMessage
            from social_hook.messaging.telegram import TelegramAdapter

            is_thread = bool(thread_tweets)
            tweet_count = len(thread_tweets) if is_thread else None
            suggested_time_str = schedule.datetime.strftime("%Y-%m-%d %H:%M UTC")
            media_info = f"{media_type_str} ({len(media_paths)} file)" if media_paths else None

            msg_text = format_draft_review(
                project_name=project.name,
                commit_hash=commit_hash[:8],
                commit_message=commit.message,
                platform=platform,
                content=draft_content,
                suggested_time=suggested_time_str,
                draft_id=draft.id,
                is_thread=is_thread,
                tweet_count=tweet_count,
                media_info=media_info,
            )
            buttons = get_review_buttons_normalized(draft.id)

            adapter = TelegramAdapter(token=telegram_token)
            msg = OutboundMessage(text=msg_text, buttons=buttons)

            chat_ids = [c.strip() for c in chat_ids_str.split(",") if c.strip()]
            for chat_id in chat_ids:
                result = adapter.send_message(chat_id, msg)
                if not result.success:
                    logger.warning(f"Failed to send Telegram notification to {chat_id}")

            # Send media attachments via adapter (if platform supports it)
            if media_paths:
                caps = adapter.get_capabilities()
                if getattr(caps, 'supports_media', False):
                    for media_path in media_paths:
                        for chat_id in chat_ids:
                            adapter.send_media(chat_id, media_path,
                                             caption=f"Media for draft `{draft.id[:12]}`")

            # Set draft context for each chat so immediate replies have context
            from social_hook.bot.commands import set_chat_draft_context

            for chat_id in chat_ids:
                set_chat_draft_context(chat_id, draft.id, project.id)

    conn.close()
    return 0


def _needs_thread(draft_result, platform: str, tier: str) -> bool:
    """Determine if content should be posted as a thread.

    LLM-driven format decision with platform constraint enforcement.
    """
    if platform != "x":
        return False

    format_hint = getattr(draft_result, "format_hint", None)
    beat_count = getattr(draft_result, "beat_count", None)
    content_len = len(draft_result.content)
    char_limit = TIER_CHAR_LIMITS.get(tier, 280)

    # Free tier overflow: MUST thread (platform constraint)
    if tier == "free" and content_len > char_limit:
        return True

    # Drafter explicitly chose single → respect it (unless free tier overflow above)
    if format_hint == "single":
        return False

    # Drafter explicitly recommends thread
    if format_hint == "thread":
        return True

    # Content has 4+ narrative beats → thread candidate
    if beat_count is not None and beat_count >= 4:
        return True

    return False


def _parse_thread_tweets(thread_content: str) -> list[str]:
    """Parse thread content into individual tweet texts.

    Handles numbered format (1/, 2/) and --- separators.
    """
    import re

    # Try numbered format first: "1/ ...\n\n2/ ..."
    numbered = re.split(r'(?:^|\n+)\d+/\s*', thread_content)
    # First element may be empty if content starts with "1/"
    numbered = [t.strip() for t in numbered if t.strip()]
    if len(numbered) >= 4:
        return numbered

    # Try --- separator
    separated = thread_content.split("---")
    separated = [t.strip() for t in separated if t.strip()]
    if len(separated) >= 4:
        return separated

    # Try double-newline separation
    paragraphs = thread_content.split("\n\n")
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    if len(paragraphs) >= 4:
        return paragraphs

    # Fallback: return as single tweet list (shouldn't normally happen for threads)
    return [thread_content.strip()] if thread_content.strip() else []
