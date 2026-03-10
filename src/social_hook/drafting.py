"""Shared drafting pipeline: platform resolution, content generation, DB insertion."""

import logging
import re
import sqlite3
from dataclasses import dataclass

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
    target_platform_names: list[str] | None = None,
    dry_run: bool = False,
    verbose: bool = False,
    skip_content_filter: bool = False,
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
        skip_content_filter: If True, bypass episode_type content filtering.
            Used when the user explicitly requests a draft (manual override).

    Returns:
        List of DraftResult for each successfully created draft.
        Empty list if no platforms resolve or all are filtered.
    """
    # 1. Resolve enabled platforms
    resolved_platforms = {}
    for pname, pcfg in config.platforms.items():
        if pcfg.enabled:
            resolved_platforms[pname] = resolve_platform(
                pname,
                pcfg,
                config.scheduling,
            )

    # Filter to target platforms if specified
    if target_platform_names is not None:
        resolved_platforms = {
            k: v for k, v in resolved_platforms.items() if k in target_platform_names
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
            "preview",
            preview_raw,
            config.scheduling,
        )
        if verbose:
            print("No enabled platforms — using built-in preview platform.")

    if not resolved_platforms:
        logger.info("No matching platforms. Skipping draft creation.")
        if verbose:
            print("No matching platforms. Skipping draft creation.")
        return []

    # 2. Apply content filter per platform (skipped for manual overrides)
    ep_type = getattr(evaluation, "episode_type", None)
    if ep_type is not None and hasattr(ep_type, "value"):
        ep_type = ep_type.value
    if skip_content_filter:
        target_platforms = dict(resolved_platforms)
    else:
        target_platforms = {}
        for pname, rpcfg in resolved_platforms.items():
            if passes_content_filter(rpcfg.filter, ep_type):
                target_platforms[pname] = rpcfg
            else:
                logger.info(
                    "Platform %s: filtered (filter=%s, episode_type=%s)",
                    pname,
                    rpcfg.filter,
                    ep_type,
                )
                if verbose:
                    print(f"Platform {pname}: filtered (filter={rpcfg.filter}, episode={ep_type})")

        if not target_platforms:
            logger.info("All platforms filtered out (episode_type=%s). No drafts created.", ep_type)
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

    # 4. Media will be generated after first successful draft (drafter produces spec)
    media_paths, media_type_str, media_spec_dict, media_error = [], None, None, None
    media_generated = False

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
                evaluation,
                context,
                commit,
                db,
                platform=pname,
                platform_config=rpcfg,
                arc_context=arc_context,
                config=project_config.context if project_config else None,
                media_config=config.media_generation,
                media_guidance=project_config.media_guidance if project_config else None,
            )

            # Override platform: LLM may return any string for unconstrained field
            draft_result.platform = pname

            # Generate media once after first successful draft
            if not media_generated:
                _mt = getattr(draft_result, "media_type", None)
                if _mt is not None and hasattr(_mt, "value"):
                    _mt = _mt.value
                _ms = getattr(draft_result, "media_spec", None)
                if _mt and _mt != "none":
                    if not _ms:
                        logger.warning(
                            "Drafter selected media_type=%s but media_spec is empty — skipping media generation",
                            _mt,
                        )
                        _mt = None
                    else:
                        media_paths, media_type_str, media_spec_dict, media_error = _generate_media(
                            config,
                            _mt,
                            _ms,
                            dry_run=dry_run,
                            verbose=verbose,
                            project_config=project_config,
                        )
                media_generated = True

            use_thread = _needs_thread(
                draft_result,
                pname,
                rpcfg.account_tier or "free",
                thread_min=config.scheduling.thread_min_tweets,
            )
            thread_tweets = []
            if use_thread:
                thread_result = drafter.create_thread(
                    evaluation,
                    context,
                    commit,
                    db,
                    platform=pname,
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
                conn,
                project.id,
                platform=pname,
                tz=config.scheduling.timezone,
                max_posts_per_day=rpcfg.max_posts_per_day,
                min_gap_minutes=rpcfg.min_gap_minutes,
                optimal_days=rpcfg.optimal_days,
                optimal_hours=rpcfg.optimal_hours,
                max_per_week=config.scheduling.max_per_week,
            )

            is_deferred = schedule.deferred
            if is_deferred and verbose:
                print(f"Platform {pname}: deferred ({schedule.day_reason})")

            draft = Draft(
                id=generate_id("draft"),
                project_id=project.id,
                decision_id=decision_id,
                platform=pname,
                content=draft_content,
                media_paths=media_paths,
                media_type=media_type_str,
                media_spec=media_spec_dict,
                media_spec_used=media_spec_dict if media_paths else None,
                status="deferred" if is_deferred else "draft",
                suggested_time=None if is_deferred else schedule.datetime,
                reasoning=draft_reasoning,
                last_error=f"Media generation failed: {media_error}"
                if media_error and not media_paths
                else None,
            )
            db.insert_draft(draft)
            db.emit_data_event(
                "draft",
                "created",
                draft.id,
                project.id,
                extra={"content": draft.content[:500], "platform": pname},
            )

            if thread_tweets:
                for pos, tc in enumerate(thread_tweets):
                    db.insert_draft_tweet(
                        DraftTweet(
                            id=generate_id("tweet"),
                            draft_id=draft.id,
                            position=pos,
                            content=tc,
                        )
                    )

            if is_deferred:
                from social_hook.notifications import send_notification

                send_notification(
                    config,
                    f"*Draft deferred*\n\nPlatform: {pname}\nReason: {schedule.day_reason}\n\n```\n{draft.content[:300]}\n```",
                    dry_run=dry_run,
                )
                continue

            results.append(
                DraftResult(
                    draft=draft,
                    schedule=schedule,
                    thread_tweets=thread_tweets,
                )
            )

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


def _generate_media(
    config, media_type_str, media_spec_dict, dry_run=False, verbose=False, project_config=None
):
    """Generate media using the drafter's spec.

    Called ONCE after the first successful draft in the per-platform loop.
    Callers validate that media_spec_dict is non-empty before calling.

    Args:
        config: Global Config object.
        media_type_str: Media tool name (e.g., "ray_so", "mermaid").
        media_spec_dict: Spec dict with tool-specific fields.
        dry_run: If True, skip real generation.
        verbose: If True, print details.
        project_config: Optional ProjectConfig for per-tool overrides.

    Returns:
        Tuple of (media_paths, media_type_str, media_spec_dict, media_error)
    """
    if not config.media_generation.enabled:
        if verbose:
            print("Media generation disabled globally, skipping")
        return [], None, None, None

    if not media_type_str or media_type_str == "none":
        return [], None, None, None

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
        return [], None, None, None

    # Defense-in-depth: reject empty spec even if caller didn't validate
    if not media_spec_dict:
        logger.warning(
            "media_spec_dict is empty for media_type=%s — skipping media generation",
            media_type_str,
        )
        return [], None, None, None

    media_paths = []
    media_error = None

    try:
        from social_hook.adapters.registry import get_media_adapter

        api_key = None
        if media_type_str == "nano_banana_pro":
            api_key = config.env.get("GEMINI_API_KEY")
            if not api_key:
                logger.warning("nano_banana_pro requested but GEMINI_API_KEY not set")
                return [], None, None, "GEMINI_API_KEY not set"

        media_adapter = get_media_adapter(media_type_str, api_key=api_key)
        if media_adapter:
            media_id = generate_id("media")
            output_dir = str(get_base_path() / "media-cache" / media_id)
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
                media_error = result.error or "Unknown media generation failure"
                logger.warning(f"Media generation failed: {media_error}")
    except Exception as e:
        media_error = str(e)
        logger.warning(f"Media generation error (non-fatal): {e}")

    return media_paths, media_type_str, media_spec_dict, media_error


def _needs_thread(draft_result, platform: str, tier: str, thread_min: int = 4) -> bool:
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
    return bool(beat_count is not None and beat_count >= thread_min)


def _parse_thread_tweets(thread_content: str, thread_min: int = 4) -> list[str]:
    """Parse thread content into individual tweet texts.

    Handles numbered format (1/, 2/) and --- separators.
    """
    # Try numbered format first: "1/ ...\n\n2/ ..."
    numbered = re.split(r"(?:^|\n+)\d+/\s*", thread_content)
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
