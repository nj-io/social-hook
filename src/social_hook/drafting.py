"""Shared drafting pipeline: platform resolution, content generation, DB insertion."""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass
from typing import Any

from social_hook.config.platforms import resolve_platform
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
    post_category: str | None = None
    angle: str | None = None
    episode_tags: list[str] | None = None


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
    logger.warning(
        "Using legacy platform-based drafting. Configure targets for per-strategy control."
    )
    resolved = _resolve_and_filter_platforms(config, target_platform_names, verbose)
    if not resolved:
        return []
    return _draft_for_resolved_platforms(
        resolved,
        config,
        conn,
        db,
        project,
        decision_id=decision_id,
        evaluation=evaluation,
        context=context,
        commit=commit,
        project_config=project_config,
        dry_run=dry_run,
        verbose=verbose,
    )


def _resolve_and_filter_platforms(config, target_platform_names, verbose):
    """Resolve enabled platforms.

    Returns:
        Dict of platform_name -> ResolvedPlatformConfig, or empty dict if none resolve.
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

    if not resolved_platforms:
        logger.info("No matching platforms. Skipping draft creation.")
        if verbose:
            print("No matching platforms. Skipping draft creation.")
        return {}

    return dict(resolved_platforms)


def _draft_for_resolved_platforms(
    platforms,
    config,
    conn: sqlite3.Connection,
    db,
    project,
    decision_id: str,
    evaluation,
    context,
    commit,
    project_config=None,
    dry_run: bool = False,
    verbose: bool = False,
    preview_targets: set[str] | None = None,
    shared_group: bool = False,
    content_source_context: dict[str, str] | None = None,
    topic_id: str | None = None,
    arc_id: str | None = None,
    cycle_id: str | None = None,
) -> list[DraftResult]:
    """Core drafting loop: create drafter client, draft per platform, schedule, insert.

    Called directly by merge execution (bypasses resolution + filter).
    Called by draft_for_platforms() after resolution + filtering.

    Args:
        preview_targets: Set of target/platform names that are in preview mode
            (accountless targets). Drafts for these get preview_mode=True.
        shared_group: When True and multiple platforms are present, call the
            drafter once for the most constrained platform and adapt the result
            for the remaining platforms. Saves LLM calls.
    """
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
    arc_context: dict[str, Any] | None = None
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

    # 4c. Arc safety net: if evaluator set arc_id but not reference_posts,
    # auto-inject the arc's latest post so the draft gets a structural link
    _ref_post_ids = getattr(evaluation, "reference_posts", None)
    if _arc_id and not _ref_post_ids and arc_context:
        _arc_posts: list = arc_context.get("posts", [])
        if _arc_posts:
            _ref_post_ids = [_arc_posts[0].id]

    # 4d. Resolve reference posts for drafter context
    referenced_posts = None
    if _ref_post_ids:
        from social_hook.db import operations as _ops

        referenced_posts = _ops.get_posts_by_ids(conn, _ref_post_ids)

    # 5. Shared group optimisation: one LLM call, adapt for remaining platforms
    if shared_group and len(platforms) > 1:
        return _draft_shared_group(
            platforms=platforms,
            drafter=drafter,
            config=config,
            conn=conn,
            db=db,
            project=project,
            decision_id=decision_id,
            evaluation=evaluation,
            context=context,
            commit=commit,
            project_config=project_config,
            dry_run=dry_run,
            verbose=verbose,
            preview_targets=preview_targets,
            arc_context=arc_context,
            referenced_posts=referenced_posts,
            content_source_context=content_source_context,
            topic_id=topic_id,
            arc_id=arc_id,
            cycle_id=cycle_id,
        )

    # 5b. Draft for each target platform (default: one LLM call per platform)
    results = []
    for pname, rpcfg in platforms.items():
        # Per-platform introduction check
        platform_is_introduced = context.platform_introduced.get(pname, False)

        # Resolve identity for this platform
        from social_hook.config.yaml import resolve_identity
        from social_hook.db import operations as _id_ops

        resolved_identity = resolve_identity(config, pname)
        target_post_count = len([p for p in context.recent_posts if p.platform == pname])
        is_first_post = not platform_is_introduced
        first_post_date = _id_ops.get_first_post_date(conn, project.id, pname)

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
                referenced_posts=referenced_posts,
                platform_introduced=platform_is_introduced,
                identity=resolved_identity,
                target_post_count=target_post_count,
                is_first_post=is_first_post,
                first_post_date=first_post_date,
                content_source_context=content_source_context,
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
                    identity=resolved_identity,
                    target_post_count=target_post_count,
                    is_first_post=is_first_post,
                    first_post_date=first_post_date,
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
                preview_mode=bool(preview_targets and pname in preview_targets),
                topic_id=topic_id,
                arc_id=arc_id,
                evaluation_cycle_id=cycle_id,
            )

            # Set reference post info from evaluator (prefer same-platform for native quote)
            if referenced_posts:
                same_platform = [
                    p for p in referenced_posts if p.platform == pname and p.external_id
                ]
                any_published = [p for p in referenced_posts if p.external_id]
                ref_post = (
                    same_platform[0]
                    if same_platform
                    else (any_published[0] if any_published else None)
                )
                if ref_post:
                    draft.reference_post_id = ref_post.id
                    if ref_post.platform == pname:
                        draft.post_format = "quote"

            # Mark as intro if platform not yet introduced
            if not platform_is_introduced and not dry_run:
                draft.is_intro = True

            db.insert_draft(draft)

            # After draft insertion, mark platform as introduced
            if not platform_is_introduced and not dry_run:
                from social_hook.db import operations as _intro_ops

                _intro_ops.set_platform_introduced(conn, project.id, pname, True)
                context.platform_introduced[pname] = True
                db.emit_data_event("project", "updated", project.id, project.id)

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

            # Extract metadata from evaluation for notification pass-through
            _post_cat = getattr(evaluation, "post_category", None)
            if _post_cat is not None and hasattr(_post_cat, "value"):
                _post_cat = _post_cat.value
            _angle = getattr(evaluation, "angle", None)
            _ep_tags = getattr(evaluation, "episode_tags", None)

            results.append(
                DraftResult(
                    draft=draft,
                    schedule=schedule,
                    thread_tweets=thread_tweets,
                    post_category=_post_cat,
                    angle=_angle,
                    episode_tags=_ep_tags,
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


def draft_for_targets(
    target_actions: list,  # list[RoutedTarget] — imported lazily
    config,
    conn: sqlite3.Connection,
    db,
    project,
    decision_id: str,
    evaluation,
    context,
    commit,
    content_source_registry=None,
    project_config=None,
    dry_run: bool = False,
    verbose: bool = False,
    cycle_id: str | None = None,
) -> list[DraftResult]:
    """Draft for resolved target actions.

    Replaces draft_for_platforms() when targets config exists.
    Groups targets by draft_group for draft sharing.
    Assembles per-target context via ContentSource registry.
    """
    from social_hook.content_sources import content_sources as default_registry

    registry = content_source_registry or default_registry

    # Only process targets with "draft" action
    draft_actions = [ta for ta in target_actions if ta.action == "draft"]
    if not draft_actions:
        if verbose:
            print("No targets with 'draft' action.")
        return []

    # Group by draft_group for draft sharing
    groups: dict[str, list] = {}
    ungrouped: list = []
    for ta in draft_actions:
        if ta.draft_group:
            groups.setdefault(ta.draft_group, []).append(ta)
        else:
            ungrouped.append(ta)

    # Resolve content sources for each strategy decision
    resolved_context: dict[str, dict[str, str]] = {}
    for ta in draft_actions:
        strategy_name = ta.target_config.strategy
        if strategy_name in resolved_context:
            continue
        # Get context source spec from the strategy decision
        spec = getattr(ta.strategy_decision, "context_source", None)
        topic_id = getattr(ta.strategy_decision, "topic_id", None)
        if topic_id:
            if spec is None:
                from social_hook.llm.schemas import ContextSourceSpec

                spec = ContextSourceSpec(types=["topic"], topic_id=topic_id)
            else:
                if "topic" not in spec.types:
                    spec.types.append("topic")
                spec.topic_id = topic_id  # always sync to match top-level topic_id
        if spec and hasattr(spec, "types") and spec.types:
            kwargs: dict[str, Any] = {
                "conn": conn,
                "project_id": project.id,
            }
            if hasattr(spec, "topic_id") and spec.topic_id:
                kwargs["topic_id"] = spec.topic_id
            if hasattr(spec, "suggestion_id") and spec.suggestion_id:
                kwargs["suggestion_id"] = spec.suggestion_id
            resolved_context[strategy_name] = registry.resolve(source_types=spec.types, **kwargs)
        else:
            resolved_context[strategy_name] = {}

    all_results: list[DraftResult] = []

    # Collect accountless targets — these get preview_mode=True on their drafts
    _preview_targets = {ta.target_name for ta in draft_actions if not ta.target_config.account}

    def _resolve_target_platform(ta):
        """Resolve a ResolvedPlatformConfig for a target action."""
        account = ta.account_config
        platform_name = account.platform
        pcfg = config.platforms.get(platform_name)
        if pcfg:
            return resolve_platform(platform_name, pcfg, config.scheduling)
        from social_hook.config.platforms import OutputPlatformConfig

        raw = OutputPlatformConfig(
            enabled=True,
            priority="primary" if ta.target_config.primary else "secondary",
            type="builtin" if platform_name in ("x", "linkedin") else "custom",
            account_tier=account.tier,
        )
        return resolve_platform(platform_name, raw, config.scheduling)

    def _draft_batch(
        platforms_map,
        shared_group: bool = False,
        content_source_context: dict[str, str] | None = None,
        topic_id: str | None = None,
        arc_id: str | None = None,
    ):
        """Run _draft_for_resolved_platforms with shared kwargs."""
        return _draft_for_resolved_platforms(
            platforms_map,
            config,
            conn,
            db,
            project,
            decision_id=decision_id,
            evaluation=evaluation,
            context=context,
            commit=commit,
            project_config=project_config,
            dry_run=dry_run,
            verbose=verbose,
            preview_targets=_preview_targets,
            shared_group=shared_group,
            content_source_context=content_source_context,
            topic_id=topic_id,
            arc_id=arc_id,
            cycle_id=cycle_id,
        )

    # Process grouped targets (shared draft per group — single LLM call)
    for _group_name, group_targets in groups.items():
        platforms_for_group = {ta.target_name: _resolve_target_platform(ta) for ta in group_targets}
        content_ctx = resolved_context.get(group_targets[0].target_config.strategy, {})
        all_results.extend(
            _draft_batch(
                platforms_for_group,
                shared_group=True,
                content_source_context=content_ctx or None,
                topic_id=getattr(group_targets[0].strategy_decision, "topic_id", None),
                arc_id=getattr(group_targets[0].strategy_decision, "arc_id", None),
            )
        )

    # Process ungrouped targets individually
    for ta in ungrouped:
        content_ctx = resolved_context.get(ta.target_config.strategy, {})
        all_results.extend(
            _draft_batch(
                {ta.target_name: _resolve_target_platform(ta)},
                content_source_context=content_ctx or None,
                topic_id=getattr(ta.strategy_decision, "topic_id", None),
                arc_id=getattr(ta.strategy_decision, "arc_id", None),
            )
        )

    return all_results


def _draft_shared_group(
    platforms,
    drafter,
    config,
    conn: sqlite3.Connection,
    db,
    project,
    decision_id: str,
    evaluation,
    context,
    commit,
    project_config=None,
    dry_run: bool = False,
    verbose: bool = False,
    preview_targets: set[str] | None = None,
    arc_context=None,
    referenced_posts=None,
    content_source_context: dict[str, str] | None = None,
    topic_id: str | None = None,
    arc_id: str | None = None,
    cycle_id: str | None = None,
) -> list[DraftResult]:
    """Single LLM call produces per-platform variants for a shared strategy group.

    Each platform gets its own Draft row, scheduling, and preview_mode.
    The LLM receives all platform constraints and produces optimized variants.
    """
    from social_hook.config.yaml import resolve_identity
    from social_hook.db import operations as _id_ops

    if verbose:
        print(f"Shared group: {len(platforms)} platforms, single multi-variant LLM call")

    # Build platform_configs list (deduplicated by platform name)
    platform_configs: list[tuple[str, Any]] = []
    seen_platforms: set[str] = set()
    first_pname = None
    first_rpcfg = None
    for pname, rpcfg in platforms.items():
        real_name = rpcfg.name  # platform name like "x", not target name like "lead-timeline"
        if real_name not in seen_platforms:
            seen_platforms.add(real_name)
            platform_configs.append((real_name, rpcfg))
            if first_pname is None:
                first_pname, first_rpcfg = pname, rpcfg

    # Resolve per-platform identity + intro state
    platform_intro_states: dict[str, dict] = {}
    for real_name, _rpcfg in platform_configs:
        is_introduced = context.platform_introduced.get(real_name, False)
        post_count = len([p for p in context.recent_posts if p.platform == real_name])
        platform_intro_states[real_name] = {
            "is_first": not is_introduced,
            "post_count": post_count,
        }

    # Use first platform for system prompt identity/intro context
    first_real = first_rpcfg.name if first_rpcfg else "x"
    first_identity = resolve_identity(config, first_real)
    first_is_introduced = context.platform_introduced.get(first_real, False)
    first_post_count = len([p for p in context.recent_posts if p.platform == first_real])
    first_first_date = _id_ops.get_first_post_date(conn, project.id, first_real)

    # Single LLM call with all platform constraints
    try:
        draft_result = drafter.create_draft(
            evaluation,
            context,
            commit,
            db,
            platform=first_real,
            platform_configs=platform_configs,
            arc_context=arc_context,
            config=project_config.context if project_config else None,
            media_config=config.media_generation,
            media_guidance=project_config.media_guidance if project_config else None,
            referenced_posts=referenced_posts,
            platform_introduced=first_is_introduced,
            identity=first_identity,
            target_post_count=first_post_count,
            is_first_post=not first_is_introduced,
            first_post_date=first_first_date,
            content_source_context=content_source_context,
            platform_intro_states=platform_intro_states,
        )
    except Exception as e:
        logger.error(f"LLM API error during shared-group drafting: {e}")
        if verbose:
            print(f"LLM API error during shared-group drafting: {e}")
        return []

    # Build variant lookup by platform name
    variant_by_platform: dict[str, Any] = {}
    if draft_result.variants:
        for v in draft_result.variants:
            variant_by_platform[v.platform] = v
    if not variant_by_platform:
        # Fallback: no variants returned — use flat content for all platforms
        logger.warning(
            "Drafter returned no variants for shared group — using flat content for all platforms"
        )

    draft_reasoning = draft_result.reasoning

    # Generate media once from the draft result
    media_paths, media_type_str, media_spec_dict, media_error = [], None, None, None
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

    # Create a Draft + DraftResult for each platform using variant content
    results: list[DraftResult] = []

    for pname, rpcfg in platforms.items():
        try:
            platform_is_introduced = context.platform_introduced.get(pname, False)
            real_name = rpcfg.name

            # Get variant content for this platform (fallback to flat content)
            variant = variant_by_platform.get(real_name)
            if variant:
                draft_content = variant.content
                variant_format_hint = variant.format_hint
                variant_beat_count = variant.beat_count
            else:
                draft_content = draft_result.content
                variant_format_hint = draft_result.format_hint
                variant_beat_count = draft_result.beat_count

            # Per-platform thread validation
            from types import SimpleNamespace

            variant_obj = SimpleNamespace(
                content=draft_content,
                format_hint=variant_format_hint,
                beat_count=variant_beat_count,
            )
            was_threaded = _needs_thread(
                variant_obj,
                real_name,
                rpcfg.account_tier or "free",
                thread_min=config.scheduling.thread_min_tweets,
            )
            thread_tweets: list[str] = []
            if was_threaded:
                # Thread validation triggered — need a separate create_thread call
                p_identity = resolve_identity(config, real_name)
                p_intro = platform_intro_states.get(real_name, {})
                p_first_date = _id_ops.get_first_post_date(conn, project.id, real_name)
                thread_result = drafter.create_thread(
                    evaluation,
                    context,
                    commit,
                    db,
                    platform=real_name,
                    media_config=config.media_generation,
                    media_guidance=project_config.media_guidance if project_config else None,
                    identity=p_identity,
                    target_post_count=p_intro.get("post_count", 0),
                    is_first_post=p_intro.get("is_first", False),
                    first_post_date=p_first_date,
                )
                thread_tweets = _parse_thread_tweets(
                    thread_result.content,
                    thread_min=config.scheduling.thread_min_tweets,
                )
                draft_content = thread_result.content

            if verbose:
                print(f"  {pname} ({real_name}): variant {'found' if variant else 'fallback'}")

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
                preview_mode=bool(preview_targets and pname in preview_targets),
                topic_id=topic_id,
                arc_id=arc_id,
                evaluation_cycle_id=cycle_id,
            )

            # Set reference post info from evaluator
            if referenced_posts:
                same_platform = [
                    p for p in referenced_posts if p.platform == pname and p.external_id
                ]
                any_published = [p for p in referenced_posts if p.external_id]
                ref_post = (
                    same_platform[0]
                    if same_platform
                    else (any_published[0] if any_published else None)
                )
                if ref_post:
                    draft.reference_post_id = ref_post.id
                    if ref_post.platform == pname:
                        draft.post_format = "quote"

            # Mark as intro if platform not yet introduced
            if not platform_is_introduced and not dry_run:
                draft.is_intro = True

            db.insert_draft(draft)

            # After draft insertion, mark platform as introduced
            if not platform_is_introduced and not dry_run:
                from social_hook.db import operations as _intro_ops

                _intro_ops.set_platform_introduced(conn, project.id, pname, True)
                context.platform_introduced[pname] = True
                db.emit_data_event("project", "updated", project.id, project.id)

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

            # Extract metadata from evaluation for notification pass-through
            _post_cat = getattr(evaluation, "post_category", None)
            if _post_cat is not None and hasattr(_post_cat, "value"):
                _post_cat = _post_cat.value
            _angle = getattr(evaluation, "angle", None)
            _ep_tags = getattr(evaluation, "episode_tags", None)

            results.append(
                DraftResult(
                    draft=draft,
                    schedule=schedule,
                    thread_tweets=thread_tweets,
                    post_category=_post_cat,
                    angle=_angle,
                    episode_tags=_ep_tags,
                )
            )

            if verbose:
                print(f"Draft created for {pname}: {draft.id}")
                if thread_tweets:
                    print(f"  Format: thread ({len(thread_tweets)} tweets)")
                print(f"  Content: {draft_content[:100]}...")
                print(f"  Suggested time: {schedule.datetime} ({schedule.time_reason})")

        except Exception as e:
            logger.error(f"Error creating draft for {pname} in shared group: {e}")
            if verbose:
                print(f"Error creating draft for {pname} in shared group: {e}")

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
