"""Unified drafting pipeline: vehicle resolution, content generation, DB insertion."""

from __future__ import annotations

import logging
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from social_hook.adapters.registry import THREAD_SAFE_KEY, media_registry
from social_hook.config.yaml import TIER_CHAR_LIMITS
from social_hook.filesystem import generate_id, get_base_path
from social_hook.models.core import Draft, DraftPart
from social_hook.scheduling import ScheduleResult, calculate_optimal_time

logger = logging.getLogger(__name__)


# Pre-populated at module import to eliminate a defaultdict-race on first
# access. Keys mirror ``adapters/registry.py`` entries marked
# ``THREAD_SAFE_KEY: False`` (playwright + ray_so — sync_playwright()
# asyncio loop cannot be reentered across threads). Adding a new non-
# thread-safe adapter requires a matching entry here — see
# docs/CODING_PRACTICES.md.
_ADAPTER_LOCKS: dict[str, threading.Lock] = {
    "playwright": threading.Lock(),
    "ray_so": threading.Lock(),
}


@dataclass
class MediaUpload:
    """An operator-uploaded reference image with optional context.

    Flows through ``DraftingIntent.uploads`` into ``Drafter.create_draft``
    (as vision content blocks) and, when moved into the draft's
    ``media-cache/uploads/<draft_id>/`` directory, materializes as a
    ``user_uploaded=True`` media spec that skips generation.
    """

    path: str
    context: str = ""


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

    # Operator-uploaded reference images (create-content flow only).
    # Other builders pass ``uploads=None``. Paths must be at their final
    # ``media-cache/uploads/<draft_id>/`` location before drafting starts.
    uploads: list[MediaUpload] | None = None


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

    # Media generation is driven by media_specs returned by the LLM. The
    # 4 parallel arrays (specs, paths, errors, specs_used) are built once
    # after the first successful draft and shared across platforms.
    media_specs: list[dict] = []
    media_paths: list[str] = []
    media_errors: list[str | None] = []
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
            uploads=intent.uploads,
        )

        # Override platform
        draft_result.platform = pname

        # Generate media once — parallel across all specs
        if not media_generated:
            media_specs = _normalize_specs_from_draft(draft_result)
            media_paths, media_errors = _generate_all_media(
                config,
                media_specs,
                dry_run=dry_run,
                verbose=verbose,
                project_config=project_config,
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
            media_specs=media_specs,
            media_paths=media_paths,
            media_errors=media_errors,
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
            uploads=intent.uploads,
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

    # Generate media once — parallel across all specs
    media_specs = _normalize_specs_from_draft(draft_result)
    media_paths, media_errors = _generate_all_media(
        config,
        media_specs,
        dry_run=dry_run,
        verbose=verbose,
        project_config=project_config,
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
                media_specs=media_specs,
                media_paths=media_paths,
                media_errors=media_errors,
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
    media_specs: list[dict],
    media_paths: list[str],
    media_errors: list[str | None],
    referenced_posts: list | None,
    dry_run: bool,
    verbose: bool,
) -> DraftResult | None:
    """ONE place for post-draft logic: scheduling, Draft construction,
    reference resolution, intro marking, DB insertion,
    materialize_vehicle_artifacts(), event emission, deferred notification.
    Called once per platform in the drafting loop.

    The 4 parallel media arrays (specs, paths, errors, specs_used) are
    written atomically via ``insert_draft`` — ``media_specs_used`` mirrors
    ``media_specs`` at creation time (spec-unchanged invariant), so the
    regen guard is always satisfied for the initial generation.
    """
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

    # Compose last_error summary from per-item errors (non-blocking; the
    # partial_media_failure diagnostic surfaces details at read time).
    err_summary: str | None = None
    failed = [e for e in (media_errors or []) if e]
    if failed:
        err_summary = (
            f"Media generation: {len(failed)} of {len(media_errors)} items failed "
            f"(first: {failed[0]})"
        )

    draft_obj = Draft(
        id=generate_id("draft"),
        project_id=project.id,
        decision_id=intent.decision_id,
        platform=pname,
        vehicle=vehicle,
        content=draft_content,
        media_specs=list(media_specs),
        media_paths=list(media_paths),
        media_errors=list(media_errors),
        # Mirror specs into specs_used so the spec-unchanged regen guard
        # holds for the initial state. Regen/edit flows update slots via
        # ops.update_draft_media.
        media_specs_used=list(media_specs),
        status="deferred" if is_deferred else "draft",
        suggested_time=None if is_deferred else schedule.datetime,
        reasoning=draft_reasoning,
        last_error=err_summary,
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


def _normalize_specs_from_draft(draft_result: Any) -> list[dict]:
    """Extract media_specs from a drafter response as a list of plain dicts.

    Pydantic MediaSpecItem models are coerced via ``.model_dump()``. Missing
    or falsy fields yield ``[]`` so downstream code treats a text-only
    draft the same as an empty list.
    """
    raw = getattr(draft_result, "media_specs", None)
    if not raw:
        return []
    out: list[dict] = []
    for item in raw:
        if hasattr(item, "model_dump"):
            out.append(item.model_dump())
        elif isinstance(item, dict):
            out.append(dict(item))
        else:
            logger.warning("Unexpected media_specs item type %s — skipping", type(item))
    return out


def _generate_one_media(
    config: Any,
    spec: dict,
    tool: str,
    dry_run: bool,
    verbose: bool,
    project_config: Any,
) -> str:
    """Run a single media adapter and return the output path.

    Raises the adapter error on failure — ``_generate_all_media`` catches
    per-item exceptions so one bad spec does not sink the batch.
    Respects the global ``media_generation.enabled`` toggle plus per-tool
    global and project-level overrides (same semantics as the old
    ``_generate_media``).
    """
    if not config.media_generation.enabled:
        raise RuntimeError("Media generation disabled globally")
    if not tool or tool == "none":
        raise RuntimeError(f"Invalid tool: {tool!r}")

    tool_enabled = config.media_generation.tools.get(tool, True)
    if tool_enabled:
        guidance = project_config.media_guidance.get(tool) if project_config else None
        if guidance and guidance.enabled is not None:
            tool_enabled = guidance.enabled
    if not tool_enabled:
        raise RuntimeError(f"Media tool {tool} disabled")

    from social_hook.adapters.registry import resolve_media_adapter
    from social_hook.errors import ConfigError as _ConfigError

    try:
        adapter = resolve_media_adapter(tool, config)
    except _ConfigError as exc:
        # _generate_all_media catches RuntimeError per-item; keep that
        # contract so one bad adapter never sinks the batch.
        raise RuntimeError(str(exc)) from exc

    # The filesystem directory is keyed on the spec's stable id so
    # regen + edit flows overwrite in place instead of accumulating
    # orphan files. Fall back to a fresh id only if the spec somehow
    # arrived without one (sanitizer should have stripped it).
    media_id = spec.get("id") or generate_id("media")
    output_dir = str(get_base_path() / "media-cache" / media_id)
    spec_body = spec.get("spec", {})
    result = adapter.generate(spec=spec_body, output_dir=output_dir, dry_run=dry_run)
    if not result.success or not result.file_path:
        raise RuntimeError(result.error or "Unknown media generation failure")
    if verbose:
        print(f"Media generated ({tool}): {result.file_path}")
    return str(result.file_path)


def _generate_one_media_guarded(
    config: Any,
    spec: dict,
    tool: str,
    dry_run: bool,
    verbose: bool,
    project_config: Any,
) -> str:
    """Run a single adapter, serializing non-thread-safe tools via per-tool lock.

    Thread-safety is read from the registry metadata
    (``THREAD_SAFE_KEY: False`` for ``playwright`` and ``ray_so``). The
    lock table ``_ADAPTER_LOCKS`` is pre-populated at module import so the
    first parallel call never loses a race to the default-dict pattern.
    """
    meta = media_registry.get_metadata(tool) if media_registry.has(tool) else {}
    if not meta.get(THREAD_SAFE_KEY, True):
        lock = _ADAPTER_LOCKS.get(tool)
        if lock is None:
            logger.warning(
                "No pre-populated lock for non-thread-safe adapter %s; creating on demand",
                tool,
            )
            lock = threading.Lock()
            _ADAPTER_LOCKS[tool] = lock
        with lock:
            return _generate_one_media(config, spec, tool, dry_run, verbose, project_config)
    return _generate_one_media(config, spec, tool, dry_run, verbose, project_config)


def _generate_all_media(
    config: Any,
    specs: list[dict],
    *,
    task_id: str | None = None,
    project_id: str | None = None,
    db: Any | None = None,
    dry_run: bool = False,
    verbose: bool = False,
    project_config: Any | None = None,
) -> tuple[list[str], list[str | None]]:
    """Generate all media items in parallel; return ``(paths, errors)``.

    Guarantees: ``len(paths) == len(errors) == len(specs)`` and index
    ``i`` in both aligns with ``specs[i]``. For ``user_uploaded=True``
    items generation is skipped — the path already points to the final
    upload location set before drafting began.

    When ``task_id`` and ``db`` are provided, a per-item stage event is
    emitted ("media_{i+1}_of_{n}") via ``db.emit_task_stage`` so the web
    frontend's ``useBackgroundTasks`` can show per-image progress. Route
    through ``db`` (DryRunContext-safe) — never call ``ops`` directly.
    """
    n = len(specs)
    paths: list[str] = ["" for _ in range(n)]
    errors: list[str | None] = [None for _ in range(n)]
    if n == 0:
        return paths, errors

    # User-uploaded items bypass the executor — their path is already on disk.
    for i, spec in enumerate(specs):
        if spec and spec.get("user_uploaded"):
            upload_path = (spec.get("spec") or {}).get("path", "")
            paths[i] = str(upload_path) if upload_path else ""
            if not upload_path:
                errors[i] = "user_uploaded spec missing spec.path"

    # Generate everything else in parallel. Non-thread-safe adapters
    # serialize via _ADAPTER_LOCKS inside _generate_one_media_guarded.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(
                _generate_one_media_guarded,
                config,
                specs[i],
                (specs[i] or {}).get("tool", ""),
                dry_run,
                verbose,
                project_config,
            ): i
            for i in range(n)
            if specs[i] and not specs[i].get("user_uploaded")
        }
        for future in as_completed(futures):
            i = futures[future]
            if task_id and db is not None:
                try:
                    db.emit_task_stage(
                        task_id, f"media_{i + 1}_of_{n}", f"Media {i + 1} of {n}", project_id
                    )
                except Exception as emit_err:  # noqa: BLE001 — boundary
                    logger.warning("emit_task_stage failed for item %d: %s", i, emit_err)
            try:
                paths[i] = future.result()
            except Exception as exc:  # noqa: BLE001 — per-item failure tolerated
                logger.warning(
                    "Media generation failed for item %d (tool=%s): %s",
                    i,
                    (specs[i] or {}).get("tool"),
                    exc,
                    exc_info=True,
                )
                errors[i] = str(exc)

    return paths, errors
