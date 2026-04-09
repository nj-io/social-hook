"""Vehicle pipeline stage: resolution, validation, materialization, dispatch, parsing."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from social_hook.adapters.models import PostCapability, PostResult

if TYPE_CHECKING:
    from social_hook.adapters.models import PostReference
    from social_hook.adapters.platform.base import PlatformAdapter
    from social_hook.models.core import Draft, DraftPart

logger = logging.getLogger(__name__)


def resolve_vehicle(
    evaluator_suggestion: str | None,
    operator_choice: str | None,
    platform_capabilities: list[PostCapability],
) -> str | None:
    """Three-tier fallback: operator > evaluator > None (drafter decides).

    Validates against platform capabilities.
    """
    capability_names = {cap.name for cap in platform_capabilities}

    # Operator choice takes priority
    chosen = operator_choice or evaluator_suggestion
    if chosen is None:
        return None

    if chosen in capability_names:
        return chosen

    logger.warning(
        "Vehicle '%s' not supported by platform capabilities %s, falling back to drafter decision",
        chosen,
        capability_names,
    )
    return None


@dataclass(frozen=True)
class VehicleValidation:
    """Result of validating draft content against vehicle constraints."""

    valid: bool
    violation: str | None = None
    suggested_vehicle: str | None = None


def validate_draft_for_vehicle(
    content: str,
    vehicle: str,
    platform: str,
    char_limit: int,
    thread_min: int = 4,
) -> VehicleValidation:
    """Pure function. Hard platform constraints only. No LLM."""
    content_len = len(content)

    if vehicle == "single":
        if content_len > char_limit:
            return VehicleValidation(
                valid=False,
                violation=f"Content ({content_len} chars) exceeds {platform} limit ({char_limit} chars)",
                suggested_vehicle="thread" if platform == "x" else None,
            )
        return VehicleValidation(valid=True)

    if vehicle == "thread":
        if platform not in ("x",):
            return VehicleValidation(
                valid=False,
                violation=f"Platform '{platform}' does not support threads",
                suggested_vehicle="single",
            )
        parts = parse_thread_parts(content, platform, thread_min)
        if len(parts) < thread_min:
            return VehicleValidation(
                valid=False,
                violation=f"Thread has {len(parts)} parts, minimum is {thread_min}",
                suggested_vehicle="single",
            )
        return VehicleValidation(valid=True)

    if vehicle == "article":
        return VehicleValidation(valid=True)

    logger.warning("Unknown vehicle '%s', treating as valid", vehicle)
    return VehicleValidation(valid=True)


def materialize_vehicle_artifacts(
    draft_id: str,
    vehicle: str,
    platform: str,
    content: str,
    platform_capabilities: list[PostCapability],
    db: Any,
) -> None:
    """Single canonical function for creating/deleting draft parts.

    Deletes existing parts first (handles vehicle changes), then creates
    new parts if vehicle requires them (thread -> parse_thread_parts).
    Checks capabilities before creating parts.
    """
    from social_hook.filesystem import generate_id
    from social_hook.models.core import DraftPart

    capability_names = {cap.name for cap in platform_capabilities}

    # Always delete existing parts first (handles vehicle changes)
    db.replace_draft_parts(draft_id, [])

    if vehicle == "thread" and "thread" in capability_names:
        parts = parse_thread_parts(content, platform)
        for pos, part_content in enumerate(parts):
            db.insert_draft_part(
                DraftPart(
                    id=generate_id("part"),
                    draft_id=draft_id,
                    position=pos,
                    content=part_content,
                )
            )
        logger.info("Materialized %d thread parts for draft %s", len(parts), draft_id)
    elif vehicle == "thread":
        logger.warning(
            "Vehicle 'thread' requested but platform capabilities %s don't include it; "
            "skipping part materialization for draft %s",
            capability_names,
            draft_id,
        )
    else:
        logger.debug(
            "Vehicle '%s' does not require part materialization for draft %s", vehicle, draft_id
        )


def parse_thread_parts(content: str, platform: str, thread_min: int = 4) -> list[str]:
    """Platform-aware thread parsing. Splits content into individual thread parts."""
    # Try numbered format first: "1/ ...\n\n2/ ..."
    numbered = re.split(r"(?:^|\n+)\d+/\s*", content)
    numbered = [t.strip() for t in numbered if t.strip()]
    if len(numbered) >= thread_min:
        return numbered

    # Try --- separator
    separated = content.split("---")
    separated = [t.strip() for t in separated if t.strip()]
    if len(separated) >= thread_min:
        return separated

    # Try double-newline separation
    paragraphs = content.split("\n\n")
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    if len(paragraphs) >= thread_min:
        return paragraphs

    # Fallback: return as single part list
    return [content.strip()] if content.strip() else []


def rematerialize_draft_parts(
    conn: Any,
    draft: Draft,
    content: str,
) -> None:
    """Convenience wrapper: re-materializes draft parts after content or vehicle change.

    Looks up platform capabilities from PLATFORM_VEHICLE_SUPPORT, wraps conn
    in DryRunContext, and calls materialize_vehicle_artifacts(). Use this from
    bot handlers, CLI, and any code that edits draft content or vehicle.
    """
    from social_hook.config.platforms import PLATFORM_VEHICLE_SUPPORT
    from social_hook.llm.dry_run import DryRunContext

    vehicle = draft.vehicle or "single"
    caps = PLATFORM_VEHICLE_SUPPORT.get(draft.platform, [])
    db = DryRunContext(conn, dry_run=False) if not hasattr(conn, "insert_draft_part") else conn
    materialize_vehicle_artifacts(draft.id, vehicle, draft.platform, content, caps, db)


def post_by_vehicle(
    adapter: PlatformAdapter,
    draft: Draft,
    parts: list[DraftPart] | None,
    media_paths: list[str] | None,
    reference: PostReference | None = None,
    dry_run: bool = False,
    db: Any = None,
) -> PostResult:
    """Posting orchestrator. Handles full posting lifecycle including
    per-part result tracking for threads.

    Uses adapter.capabilities() for validation.
    Uses PostCapability.auto_postable to identify advisory vehicles.
    Handles reference wrapping (quote/reply) for any vehicle.
    Updates draft_part rows with external_id/posted_at on success.
    """
    capabilities = {cap.name: cap for cap in adapter.capabilities()}
    vehicle = getattr(draft, "vehicle", "single") or "single"
    cap = capabilities.get(vehicle)

    # Advisory: vehicle exists but is not auto-postable (e.g., article)
    if cap and not getattr(cap, "auto_postable", True):
        return PostResult(success=False, error=f"ADVISORY:{cap.description}")

    # Validate platform supports this vehicle
    if vehicle not in ("single",) and not cap:
        return PostResult(success=False, error=f"Unsupported vehicle: {vehicle}")

    # Reference posting wraps any vehicle
    if reference:
        from social_hook.adapters.models import ReferenceType

        ref_type = reference.reference_type
        if not adapter.supports_reference_type(ref_type):
            ref_type = ReferenceType.LINK
        from social_hook.adapters.models import PostReference as PR

        ref = PR(reference.external_id, reference.external_url, ref_type)
        return adapter.post_with_reference(draft.content, ref, media_paths, dry_run)

    # Thread: post parts, track per-part results
    if vehicle == "thread" and parts:
        tweet_dicts = [{"content": t.content, "media_paths": t.media_paths or []} for t in parts]
        if media_paths and not tweet_dicts[0].get("media_paths"):
            tweet_dicts[0]["media_paths"] = media_paths
        result = adapter.post_thread(tweet_dicts, dry_run)
        # Update draft_part rows with external_id/posted_at
        if result.part_results and db:
            _update_part_results(db, parts, result.part_results)
        # Set wrapper external_id from first part
        if result.part_results and result.part_results[0].external_id:
            result.external_id = result.part_results[0].external_id
            result.external_url = result.part_results[0].external_url
        return result

    # Default: single post
    return adapter.post(draft.content, media_paths, dry_run)


def _update_part_results(
    db: Any,
    parts: list[DraftPart],
    part_results: list[PostResult],
) -> None:
    """Update draft_part rows with posting results."""
    now_iso = datetime.now(timezone.utc).isoformat()
    for part, pr in zip(parts, part_results, strict=False):
        if pr.success and pr.external_id:
            db.update_draft_part(
                part.id,
                external_id=pr.external_id,
                posted_at=now_iso,
            )
        elif pr.error:
            db.update_draft_part(part.id, error=pr.error)
        else:
            logger.debug("No result update needed for part %s", part.id)
