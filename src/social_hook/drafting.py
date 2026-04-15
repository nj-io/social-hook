"""Unified drafting pipeline: vehicle resolution, content generation, DB insertion."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from social_hook.config.yaml import TIER_CHAR_LIMITS
from social_hook.filesystem import generate_id, get_base_path
from social_hook.models.core import Draft, DraftPart
from social_hook.scheduling import ScheduleResult, calculate_optimal_time

logger = logging.getLogger(__name__)


@dataclass
class DraftResult:
    """Result of drafting for a single platform."""

    draft: Draft
    schedule: ScheduleResult
    thread_parts: list[str]
    post_category: str | None = None
    angle: str | None = None
    episode_tags: list[str] | None = None


@dataclass
class PlatformSpec:
    """A single platform target within a DraftingIntent."""

    platform: str
    resolved: Any  # ResolvedPlatformConfig
    target_id: str | None = None
    preview_mode: bool = False


@dataclass
class DraftingIntent:
    """Everything the drafting pipeline needs to produce a draft.

    ONE input type. No SimpleNamespace, no compat layer.
    Field names match what assemble_drafter_prompt reads via getattr().
    """

    # What to say
    decision: str = "draft"
    vehicle: str | None = None
    angle: str = ""
    reasoning: str = ""
    post_category: str | None = None
    commit_summary: str | None = None
    episode_type: str | None = None

    # Where to publish
    platforms: list[PlatformSpec] = field(default_factory=list)

    # Content enrichment
    arc_id: str | None = None
    reference_posts: list[str] | None = None
    media_tool: str | None = None
    include_project_docs: bool = False
    content_source_context: dict[str, str] | None = None
    topic_id: str | None = None

    # Pipeline metadata
    decision_id: str = ""
    episode_tags: list[str] | None = None
    cycle_id: str | None = None


def draft(
    intent: DraftingIntent,
    config: Any,
    conn: sqlite3.Connection,
    db: Any,
    project: Any,
    context: Any,
    commit: Any,
    project_config: Any = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> list[DraftResult]:
    """The single drafting entry point.

    Handles: vehicle resolution, LLM draft creation, vehicle validation,
    artifact materialization, media generation, scheduling, DB insertion.

    If len(intent.platforms) > 1: shared-group LLM call (multi-variant).
    If len(intent.platforms) == 1: single-platform LLM call.
    """
    from social_hook.errors import ConfigError
    from social_hook.llm.factory import create_client
    from social_hook.vehicle import parse_thread_parts, validate_draft_for_vehicle

    if not intent.platforms:
        logger.info("No platforms in DraftingIntent, skipping draft creation.")
        return []

    # Create drafter client
    try:
        drafter_client = create_client(config.models.drafter, config, verbose=verbose)
    except ConfigError as e:
        logger.error("Config error creating drafter client: %s", e)
        if verbose:
            print(f"Config error: {e}")
        return []

    from social_hook.llm.drafter import Drafter

    drafter = Drafter(drafter_client)

    # Assemble arc context
    arc_context: dict[str, Any] | None = None
    if intent.arc_id:
        try:
            from social_hook.db import operations as _ops

            arc_obj = _ops.get_arc(conn, intent.arc_id)
            if arc_obj:
                arc_context = {
                    "arc": arc_obj,
                    "posts": _ops.get_arc_posts(conn, intent.arc_id),
                }
        except Exception as e:
            logger.warning("Arc context assembly failed (non-fatal): %s", e)

    # Arc safety net: auto-inject latest arc post if no reference_posts set
    ref_post_ids = intent.reference_posts
    if intent.arc_id and not ref_post_ids and arc_context:
        arc_posts: list = arc_context.get("posts", [])
        if arc_posts:
            ref_post_ids = [arc_posts[0].id]

    # Resolve reference posts
    referenced_posts = None
    if ref_post_ids:
        from social_hook.db import operations as _ops

        referenced_posts = _ops.get_posts_by_ids(conn, ref_post_ids)

    # Resolve vehicle: validate intent.vehicle against first platform's capabilities.
    # intent.vehicle is the operator/evaluator merged value — passed as operator_choice
    # so it takes priority over any evaluator suggestion in resolve_vehicle's fallback chain.
    # If None, drafter decides. If unsupported by platform, falls back to None (drafter decides).
    from social_hook.config.platforms import PLATFORM_VEHICLE_SUPPORT
    from social_hook.vehicle import resolve_vehicle as _resolve_vehicle

    first_spec = intent.platforms[0] if intent.platforms else None
    first_caps = PLATFORM_VEHICLE_SUPPORT.get(first_spec.platform, []) if first_spec else []
    resolved_vehicle = _resolve_vehicle(None, intent.vehicle, first_caps)

    # Load project documentation if requested
    project_docs_text: str | None = None
    if intent.include_project_docs and project.repo_path:
        try:
            from social_hook.file_reader import read_files_within_budget
            from social_hook.parsing import safe_json_loads

            # Determine token budget: 40K for articles, 10K default
            doc_budget = 40_000 if resolved_vehicle == "article" else 10_000

            # Gather doc paths: discovery files + prompt_docs
            doc_paths: list[str] = []
            if project.discovery_files:
                doc_paths.extend(
                    safe_json_loads(project.discovery_files, "project.discovery_files", default=[])
                )
            if project.prompt_docs:
                doc_paths.extend(
                    safe_json_loads(project.prompt_docs, "project.prompt_docs", default=[])
                )
            if doc_paths:
                text, _tokens = read_files_within_budget(
                    doc_paths,
                    project.repo_path,
                    max_tokens=doc_budget,
                )
                if text:
                    project_docs_text = text
        except Exception as e:
            logger.warning("Project docs loading failed (non-fatal): %s", e)

    # Media generation: done once after first successful draft
    media_paths: list[str] = []
    media_type_str: str | None = None
    media_spec_dict: dict | None = None
    media_error: str | None = None
    media_generated = False

    # Shared-group: multi-variant LLM call
    if len(intent.platforms) > 1:
        return _draft_shared(
            intent=intent,
            drafter=drafter,
            config=config,
            conn=conn,
            db=db,
            project=project,
            context=context,
            commit=commit,
            project_config=project_config,
            dry_run=dry_run,
            verbose=verbose,
            arc_context=arc_context,
            referenced_posts=referenced_posts,
            resolved_vehicle=resolved_vehicle,
            project_docs_text=project_docs_text,
        )

    # Single platform path
    results: list[DraftResult] = []
    pspec = intent.platforms[0]
    pname = pspec.platform
    rpcfg = pspec.resolved

    platform_is_introduced = context.platform_introduced.get(pname, False)

    from social_hook.config.yaml import resolve_identity
    from social_hook.db import operations as _id_ops

    resolved_identity = resolve_identity(config, pname)
    target_post_count = len([p for p in context.recent_posts if p.platform == pname])
    is_first_post = not platform_is_introduced
    first_post_date = _id_ops.get_first_post_date(conn, project.id, pname)

    try:
        draft_result = drafter.create_draft(
            intent,  # used as evaluation — getattr reads angle, arc_id, etc.
            context,
            commit,
            db,
            platform=pname,
            vehicle=resolved_vehicle,
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
            content_source_context=intent.content_source_context,
            project_docs_text=project_docs_text,
        )

        # Override platform
        draft_result.platform = pname

        # Generate media once
        if not media_generated:
            media_paths, media_type_str, media_spec_dict, media_error = _extract_and_generate_media(
                draft_result, config, dry_run, verbose, project_config
            )
            media_generated = True

        # Determine vehicle from LLM response if not pre-resolved
        vehicle = resolved_vehicle or getattr(draft_result, "vehicle", None) or "single"

        # Vehicle validation
        tier = rpcfg.account_tier or "free"
        char_limit = TIER_CHAR_LIMITS.get(tier, 25000)
        validation = validate_draft_for_vehicle(
            draft_result.content,
            vehicle,
            pname,
            char_limit,
            thread_min=config.scheduling.thread_min_tweets,
        )
        if not validation.valid and validation.suggested_vehicle:
            logger.info(
                "Vehicle '%s' invalid for %s: %s. Retrying with '%s'",
                vehicle,
                pname,
                validation.violation,
                validation.suggested_vehicle,
            )
            vehicle = validation.suggested_vehicle

        # Parse thread parts if vehicle is thread
        thread_parts: list[str] = []
        if vehicle == "thread":
            thread_parts = parse_thread_parts(
                draft_result.content,
                pname,
                thread_min=config.scheduling.thread_min_tweets,
            )

        result = _finalize_draft(
            intent=intent,
            platform_spec=pspec,
            draft_content=draft_result.content,
            draft_reasoning=draft_result.reasoning,
            vehicle=vehicle,
            thread_parts=thread_parts,
            config=config,
            conn=conn,
            db=db,
            project=project,
            context=context,
            media_paths=media_paths,
            media_type_str=media_type_str,
            media_spec_dict=media_spec_dict,
            media_error=media_error,
            referenced_posts=referenced_posts,
            dry_run=dry_run,
            verbose=verbose,
        )
        if result:
            results.append(result)

    except Exception as e:
        logger.error("LLM API error during drafting for %s: %s", pname, e)
        if verbose:
            print(f"LLM API error during drafting for {pname}: {e}")

    return results


def _draft_shared(
    intent: DraftingIntent,
    drafter: Any,
    config: Any,
    conn: sqlite3.Connection,
    db: Any,
    project: Any,
    context: Any,
    commit: Any,
    project_config: Any,
    dry_run: bool,
    verbose: bool,
    arc_context: dict | None,
    referenced_posts: list | None,
    resolved_vehicle: str | None,
    project_docs_text: str | None = None,
) -> list[DraftResult]:
    """Multi-platform shared group: single LLM call with variants."""
    from social_hook.config.yaml import resolve_identity
    from social_hook.db import operations as _id_ops
    from social_hook.vehicle import parse_thread_parts, validate_draft_for_vehicle

    if verbose:
        print(f"Shared group: {len(intent.platforms)} platforms, single multi-variant LLM call")

    # Build platform_configs list (deduplicated by platform name)
    platform_configs: list[tuple[str, Any]] = []
    seen_platforms: set[str] = set()
    first_pname = None
    first_rpcfg = None
    for pspec in intent.platforms:
        real_name = pspec.resolved.name
        if real_name not in seen_platforms:
            seen_platforms.add(real_name)
            platform_configs.append((real_name, pspec.resolved))
            if first_pname is None:
                first_pname = pspec.platform
                first_rpcfg = pspec.resolved

    # Per-platform intro state
    platform_intro_states: dict[str, dict] = {}
    for real_name, _rpcfg in platform_configs:
        is_introduced = context.platform_introduced.get(real_name, False)
        post_count = len([p for p in context.recent_posts if p.platform == real_name])
        platform_intro_states[real_name] = {
            "is_first": not is_introduced,
            "post_count": post_count,
        }

    first_real = first_rpcfg.name if first_rpcfg else "x"
    first_identity = resolve_identity(config, first_real)
    first_is_introduced = context.platform_introduced.get(first_real, False)
    first_post_count = len([p for p in context.recent_posts if p.platform == first_real])
    first_first_date = _id_ops.get_first_post_date(conn, project.id, first_real)

    try:
        draft_result = drafter.create_draft(
            intent,
            context,
            commit,
            db,
            platform=first_real,
            vehicle=resolved_vehicle,
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
            content_source_context=intent.content_source_context,
            platform_intro_states=platform_intro_states,
            project_docs_text=project_docs_text,
        )
    except Exception as e:
        logger.error("LLM API error during shared-group drafting: %s", e)
        if verbose:
            print(f"LLM API error during shared-group drafting: {e}")
        return []

    # Build variant lookup
    variant_by_platform: dict[str, Any] = {}
    if draft_result.variants:
        for v in draft_result.variants:
            variant_by_platform[v.platform] = v
    if not variant_by_platform:
        logger.warning(
            "Drafter returned no variants for shared group — using flat content for all platforms"
        )

    # Generate media once
    media_paths, media_type_str, media_spec_dict, media_error = _extract_and_generate_media(
        draft_result, config, dry_run, verbose, project_config
    )

    results: list[DraftResult] = []

    for pspec in intent.platforms:
        pname = pspec.platform
        rpcfg = pspec.resolved
        try:
            real_name = rpcfg.name

            # Get variant content
            variant = variant_by_platform.get(real_name)
            if variant:
                draft_content = variant.content
                variant_vehicle = variant.vehicle
            else:
                draft_content = draft_result.content
                variant_vehicle = draft_result.vehicle

            # Determine vehicle
            vehicle = resolved_vehicle or variant_vehicle or "single"

            # Vehicle validation
            tier = rpcfg.account_tier or "free"
            char_limit = TIER_CHAR_LIMITS.get(tier, 25000)
            validation = validate_draft_for_vehicle(
                draft_content,
                vehicle,
                real_name,
                char_limit,
                thread_min=config.scheduling.thread_min_tweets,
            )
            if not validation.valid and validation.suggested_vehicle:
                vehicle = validation.suggested_vehicle

            # Parse thread parts
            thread_parts: list[str] = []
            if vehicle == "thread":
                thread_parts = parse_thread_parts(
                    draft_content,
                    real_name,
                    thread_min=config.scheduling.thread_min_tweets,
                )

            if verbose:
                print(f"  {pname} ({real_name}): variant {'found' if variant else 'fallback'}")

            result = _finalize_draft(
                intent=intent,
                platform_spec=pspec,
                draft_content=draft_content,
                draft_reasoning=draft_result.reasoning,
                vehicle=vehicle,
                thread_parts=thread_parts,
                config=config,
                conn=conn,
                db=db,
                project=project,
                context=context,
                media_paths=media_paths,
                media_type_str=media_type_str,
                media_spec_dict=media_spec_dict,
                media_error=media_error,
                referenced_posts=referenced_posts,
                dry_run=dry_run,
                verbose=verbose,
            )
            if result:
                results.append(result)

        except Exception as e:
            logger.error("Error creating draft for %s in shared group: %s", pname, e)
            if verbose:
                print(f"Error creating draft for {pname} in shared group: {e}")

    return results


def _finalize_draft(
    intent: DraftingIntent,
    platform_spec: PlatformSpec,
    draft_content: str,
    draft_reasoning: str,
    vehicle: str,
    thread_parts: list[str],
    config: Any,
    conn: sqlite3.Connection,
    db: Any,
    project: Any,
    context: Any,
    media_paths: list[str],
    media_type_str: str | None,
    media_spec_dict: dict | None,
    media_error: str | None,
    referenced_posts: list | None,
    dry_run: bool,
    verbose: bool,
) -> DraftResult | None:
    """ONE place for post-draft logic: scheduling, Draft construction,
    reference resolution, intro marking, DB insertion,
    materialize_vehicle_artifacts(), event emission, deferred notification.
    Called once per platform in the drafting loop."""
    pname = platform_spec.platform
    rpcfg = platform_spec.resolved
    platform_is_introduced = context.platform_introduced.get(pname, False)

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

    draft_obj = Draft(
        id=generate_id("draft"),
        project_id=project.id,
        decision_id=intent.decision_id,
        platform=pname,
        vehicle=vehicle,
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
        preview_mode=platform_spec.preview_mode,
        topic_id=intent.topic_id,
        arc_id=intent.arc_id,
        evaluation_cycle_id=intent.cycle_id,
    )

    # Set target_id from platform spec
    if platform_spec.target_id:
        draft_obj.target_id = platform_spec.target_id

    # Set reference post info from evaluator
    if referenced_posts:
        same_platform = [p for p in referenced_posts if p.platform == pname and p.external_id]
        any_published = [p for p in referenced_posts if p.external_id]
        ref_post = (
            same_platform[0] if same_platform else (any_published[0] if any_published else None)
        )
        if ref_post:
            draft_obj.reference_post_id = ref_post.id
            if ref_post.platform == pname:
                draft_obj.reference_type = "quote"

    # Mark as intro if platform not yet introduced
    if not platform_is_introduced and not dry_run:
        draft_obj.is_intro = True

    db.insert_draft(draft_obj)

    # After draft insertion, mark platform as introduced
    if not platform_is_introduced and not dry_run:
        from social_hook.db import operations as _intro_ops

        _intro_ops.set_platform_introduced(conn, project.id, pname, True)
        context.platform_introduced[pname] = True
        db.emit_data_event("project", "updated", project.id, project.id)

    db.emit_data_event(
        "draft",
        "created",
        draft_obj.id,
        project.id,
        extra={"content": draft_obj.content[:500], "platform": pname},
    )

    # Materialize thread parts in DB
    if thread_parts:
        for pos, tc in enumerate(thread_parts):
            db.insert_draft_part(
                DraftPart(
                    id=generate_id("part"),
                    draft_id=draft_obj.id,
                    position=pos,
                    content=tc,
                )
            )

    if is_deferred:
        from social_hook.notifications import send_notification

        send_notification(
            config,
            f"*Draft deferred*\n\nPlatform: {pname}\nReason: {schedule.day_reason}\n\n```\n{draft_obj.content[:300]}\n```",
            dry_run=dry_run,
        )
        return None

    # Extract metadata from intent
    _post_cat = intent.post_category
    _angle = intent.angle
    _ep_tags = intent.episode_tags

    result = DraftResult(
        draft=draft_obj,
        schedule=schedule,
        thread_parts=thread_parts,
        post_category=_post_cat,
        angle=_angle,
        episode_tags=_ep_tags,
    )

    if verbose:
        print(f"Draft created for {pname}: {draft_obj.id}")
        if thread_parts:
            print(f"  Format: thread ({len(thread_parts)} parts)")
        print(f"  Content: {draft_content[:100]}...")
        print(f"  Suggested time: {schedule.datetime} ({schedule.time_reason})")

    return result


def _extract_and_generate_media(
    draft_result: Any,
    config: Any,
    dry_run: bool,
    verbose: bool,
    project_config: Any,
) -> tuple[list[str], str | None, dict | None, str | None]:
    """Extract media spec from draft result and generate."""
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
            return [], None, None, None
        return _generate_media(  # type: ignore[no-any-return]
            config, _mt, _ms, dry_run=dry_run, verbose=verbose, project_config=project_config
        )
    return [], None, None, None


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
                logger.warning("Media generation failed: %s", media_error)
    except Exception as e:
        media_error = str(e)
        logger.warning("Media generation error (non-fatal): %s", e)

    return media_paths, media_type_str, media_spec_dict, media_error
