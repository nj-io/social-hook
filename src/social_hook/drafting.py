"""Shared drafting pipeline: platform resolution, content generation, DB insertion."""

import logging
import re
import sqlite3
from dataclasses import dataclass
from typing import Optional

from social_hook.config.platforms import passes_content_filter, resolve_platform
from social_hook.config.yaml import TIER_CHAR_LIMITS
from social_hook.filesystem import generate_id, get_base_path
from social_hook.models import Draft, DraftTweet
from social_hook.scheduling import ScheduleResult, calculate_optimal_time

logger = logging.getLogger(__name__)


@dataclass
class DraftResult:
    """Result of drafting for a single platform."""

    draft: Draft
    schedule: ScheduleResult
    thread_tweets: list[str]


def draft_for_platforms(
    config,
    conn: sqlite3.Connection,
    db,
    project,
    decision_id: str,
    evaluation,
    context,
    commit,
    project_config=None,
    target_platform_names: Optional[list[str]] = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> list[DraftResult]:
    """Run the per-platform drafting pipeline: resolve, filter, draft, insert.

    This is a pure drafting function -- it does NOT handle notifications,
    arc counting, or connection lifecycle. Those remain in the caller.

    Args:
        config: Global Config object.
        conn: SQLite connection (for scheduling queries).
        db: DryRunContext wrapping conn.
        project: Project model instance.
        decision_id: ID of the decision that triggered drafting.
        evaluation: Evaluator result (evaluation result or similar).
        context: ProjectContext for drafter prompts.
        commit: CommitInfo for this commit.
        project_config: Optional ProjectConfig (per-project settings).
        target_platform_names: If provided, only draft for these platforms.
            None means all enabled platforms.
        dry_run: If True, skip DB writes and real API calls.
        verbose: If True, print detailed output.

    Returns:
        List of DraftResult for each successfully created draft.
        Empty list if no platforms resolve or all are filtered.
    """
    # 1. Resolve enabled platforms
    resolved_platforms = {}
    for pname, pcfg in config.platforms.items():
        if pcfg.enabled:
            resolved_platforms[pname] = resolve_platform(
                pname, pcfg, config.scheduling,
            )

    # Filter to target platforms if specified
    if target_platform_names is not None:
        resolved_platforms = {
            k: v for k, v in resolved_platforms.items()
            if k in target_platform_names
        }

    # Auto-inject preview platform when no platforms are enabled and no
    # explicit filter was requested — lets users draft without configuring
    # a real platform first.
    if not resolved_platforms and target_platform_names is None:
        from social_hook.config.platforms import OutputPlatformConfig
        preview_raw = OutputPlatformConfig(
            enabled=True,
            priority="secondary",
            type="custom",
            description="Generic preview for reviewing what the system would generate, without publishing",
            format="post",
            max_length=2000,
            filter="all",
        )
        resolved_platforms["preview"] = resolve_platform(
            "preview", preview_raw, config.scheduling,
        )
        if verbose:
            print("No enabled platforms — using built-in preview platform.")

    if not resolved_platforms:
        if verbose:
            print("No matching platforms. Skipping draft creation.")
        return []

    # 2. Apply content filter per platform
    ep_type = getattr(evaluation, "episode_type", None)
    if ep_type is not None and hasattr(ep_type, "value"):
        ep_type = ep_type.value
    target_platforms = {}
    for pname, rpcfg in resolved_platforms.items():
        if passes_content_filter(rpcfg.filter, ep_type):
            target_platforms[pname] = rpcfg
        elif verbose:
            print(f"Platform {pname}: filtered (filter={rpcfg.filter}, episode={ep_type})")

    if not target_platforms:
        if verbose:
            print("All platforms filtered this commit.")
        return []

    # 3. Create drafter client
    from social_hook.errors import ConfigError
    from social_hook.llm.factory import create_client

    try:
        drafter_client = create_client(config.models.drafter, config, verbose=verbose)
    except ConfigError as e:
        logger.error(f"Config error creating drafter client: {e}")
        if verbose:
            print(f"Config error: {e}")
        return []

    from social_hook.llm.drafter import Drafter

    drafter = Drafter(drafter_client)

    # 4. Generate media once (shared across platforms)
    media_paths, media_type_str, media_spec_dict = _generate_media(
        config, evaluation, dry_run=dry_run, verbose=verbose,
        project_config=project_config,
    )

    # 4b. Assemble arc context if this is an arc post
    arc_context = None
    _arc_id = getattr(evaluation, "arc_id", None)
    if _arc_id:
        try:
            from social_hook.db import operations as _ops
            arc_obj = _ops.get_arc(conn, _arc_id)
            if arc_obj:
                arc_context = {
                    "arc": arc_obj,
                    "posts": _ops.get_arc_posts(conn, _arc_id),
                }
        except Exception as e:
            logger.warning(f"Arc context assembly failed (non-fatal): {e}")

    # 5. Draft for each target platform
    results = []
    for pname, rpcfg in target_platforms.items():
        try:
            draft_result = drafter.create_draft(
                evaluation, context, commit, db,
                platform=pname,
                platform_config=rpcfg,
                arc_context=arc_context,
                config=project_config.context if project_config else None,
                media_config=config.media_generation,
                media_guidance=project_config.media_guidance if project_config else None,
            )

            # Override platform: LLM may return any string for unconstrained field
            draft_result.platform = pname

            use_thread = _needs_thread(
                draft_result, pname, rpcfg.account_tier or "free",
                thread_min=config.scheduling.thread_min_tweets,
            )
            thread_tweets = []
            if use_thread:
                thread_result = drafter.create_thread(
                    evaluation, context, commit, db, platform=pname,
                    media_config=config.media_generation,
                    media_guidance=project_config.media_guidance if project_config else None,
                )
                thread_tweets = _parse_thread_tweets(
                    thread_result.content,
                    thread_min=config.scheduling.thread_min_tweets,
                )
                draft_content = thread_result.content
                draft_reasoning = thread_result.reasoning
            else:
                draft_content = draft_result.content
                draft_reasoning = draft_result.reasoning

            # Per-platform scheduling
            schedule = calculate_optimal_time(
                conn, project.id,
                platform=pname,
                tz=config.scheduling.timezone,
                max_posts_per_day=rpcfg.max_posts_per_day,
                min_gap_minutes=rpcfg.min_gap_minutes,
                optimal_days=rpcfg.optimal_days,
                optimal_hours=rpcfg.optimal_hours,
                max_per_week=config.scheduling.max_per_week,
            )

            if schedule.deferred:
                if verbose:
                    print(f"Platform {pname}: deferred ({schedule.day_reason})")
                continue

            draft = Draft(
                id=generate_id("draft"),
                project_id=project.id,
                decision_id=decision_id,
                platform=pname,
                content=draft_content,
                media_paths=media_paths,
                media_type=media_type_str,
                media_spec=media_spec_dict,
                suggested_time=schedule.datetime,
                reasoning=draft_reasoning,
            )
            db.insert_draft(draft)
            db.emit_data_event("draft", "created", draft.id, project.id)

            if thread_tweets:
                for pos, tc in enumerate(thread_tweets):
                    db.insert_draft_tweet(DraftTweet(
                        id=generate_id("tweet"), draft_id=draft.id,
                        position=pos, content=tc,
                    ))

            results.append(DraftResult(
                draft=draft, schedule=schedule, thread_tweets=thread_tweets,
            ))

            if verbose:
                print(f"Draft created for {pname}: {draft.id}")
                if thread_tweets:
                    print(f"  Format: thread ({len(thread_tweets)} tweets)")
                print(f"  Content: {draft_content[:100]}...")
                print(f"  Suggested time: {schedule.datetime} ({schedule.time_reason})")

        except Exception as e:
            logger.error(f"LLM API error during drafting for {pname}: {e}")
            if verbose:
                print(f"LLM API error during drafting for {pname}: {e}")
            # Continue with other platforms

    return results


def _generate_media(config, evaluation, dry_run=False, verbose=False,
                    project_config=None):
    """Generate media based on evaluator's recommendation.

    Called ONCE before the per-platform drafting loop.
    Uses only evaluation.media_tool (not draft_result).

    Args:
        config: Global Config object.
        evaluation: Evaluator result.
        dry_run: If True, skip real generation.
        verbose: If True, print details.
        project_config: Optional ProjectConfig for per-tool overrides.

    Returns:
        Tuple of (media_paths, media_type_str, media_spec_dict)
    """
    media_paths = []
    media_type_str = None
    media_spec_dict = None

    _evaluator_media = (
        getattr(evaluation, 'media_tool', None)
        and evaluation.media_tool != "none"
    )

    if config.media_generation.enabled and _evaluator_media:
        media_type_str = evaluation.media_tool
        # Handle enum values
        if hasattr(media_type_str, 'value'):
            media_type_str = media_type_str.value

        # Per-tool check: global toggle (config.yaml)
        tool_enabled = config.media_generation.tools.get(media_type_str, True)
        # Project-level override (content-config.yaml) -- can only DISABLE, not re-enable
        if tool_enabled:
            guidance = project_config.media_guidance.get(media_type_str) if project_config else None
            if guidance and guidance.enabled is not None:
                tool_enabled = guidance.enabled
        if not tool_enabled:
            if verbose:
                print(f"Media tool {media_type_str} is disabled, skipping")
            return [], None, None

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
                    draft_id = generate_id("draft")
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

    return media_paths, media_type_str, media_spec_dict


def _needs_thread(draft_result, platform: str, tier: str,
                  thread_min: int = 4) -> bool:
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

    # Drafter explicitly chose single -> respect it (unless free tier overflow above)
    if format_hint == "single":
        return False

    # Drafter explicitly recommends thread
    if format_hint == "thread":
        return True

    # Content has thread_min+ narrative beats -> thread candidate
    if beat_count is not None and beat_count >= thread_min:
        return True

    return False


def _parse_thread_tweets(thread_content: str, thread_min: int = 4) -> list[str]:
    """Parse thread content into individual tweet texts.

    Handles numbered format (1/, 2/) and --- separators.
    """
    # Try numbered format first: "1/ ...\n\n2/ ..."
    numbered = re.split(r'(?:^|\n+)\d+/\s*', thread_content)
    # First element may be empty if content starts with "1/"
    numbered = [t.strip() for t in numbered if t.strip()]
    if len(numbered) >= thread_min:
        return numbered

    # Try --- separator
    separated = thread_content.split("---")
    separated = [t.strip() for t in separated if t.strip()]
    if len(separated) >= thread_min:
        return separated

    # Try double-newline separation
    paragraphs = thread_content.split("\n\n")
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    if len(paragraphs) >= thread_min:
        return paragraphs

    # Fallback: return as single tweet list (shouldn't normally happen for threads)
    return [thread_content.strip()] if thread_content.strip() else []
