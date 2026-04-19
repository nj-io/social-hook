"""Shared helpers for regenerating a single media item.

Consolidates the find-spec-by-id → resolve-adapter → generate → write
paths/errors → insert DraftChange sequence used across bot, web, and CLI
surfaces. Surfaces keep their own user-facing side effects (Telegram
replies, HTTP response shape, CLI rendering) at the caller layer.

Design notes:

* Uses ``resolve_media_adapter`` from ``adapters.registry`` so credential
  lookup + unknown-tool handling live in one place.
* Errors flow back through ``RegenResult.error`` rather than exceptions —
  matches the existing surface contracts (web returns ``{"error": ...}``,
  CLI appends to a results list, bot returns ``(ok, message)``).
* The output_dir is keyed on ``media_id`` (``media-cache/{id}/``) so regen
  and edit flows overwrite in place rather than accumulating orphan files.
* DraftChange rows carry ``field=f"media_spec:{media_id}"`` and the path
  transition (old_value → new_value). Uses ``insert_draft_change`` for all
  callers so the draft history model stays uniform.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from typing import Any

from social_hook.adapters.registry import resolve_media_adapter
from social_hook.db import operations as ops
from social_hook.errors import ConfigError
from social_hook.filesystem import generate_id, get_base_path
from social_hook.models.core import DraftChange

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegenResult:
    """Outcome of a single media regeneration attempt.

    On success ``path`` is the new file path and ``error`` is None. On
    failure ``path`` is None and ``error`` carries a human-readable
    message. ``media_id`` echoes the input for batch-result aggregation.
    """

    media_id: str
    path: str | None = None
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.path is not None and self.error is None


def _spec_for_adapter(spec: dict) -> dict:
    """Read the adapter payload out of a MediaSpecItem dict."""
    inner = spec.get("spec") if isinstance(spec, dict) else None
    return inner if isinstance(inner, dict) else {}


def regen_media_item(
    conn: sqlite3.Connection,
    draft_id: str,
    media_id: str,
    config: Any,
    *,
    changed_by: str = "human",
    enforce_spec_change: bool = False,
) -> RegenResult:
    """Regenerate one media slot on a draft.

    Args:
        conn: SQLite connection the caller owns (callers manage lifetime).
        draft_id: Draft containing the target media slot.
        media_id: Stable media id of the slot to regenerate.
        config: Full config (passed to ``resolve_media_adapter`` for
            credential lookup).
        changed_by: Value for the ``DraftChange.changed_by`` column —
            one of ``"human"``, ``"expert"``, ``"system"``. Defaults to
            ``"human"`` since every current caller is operator-triggered.
        enforce_spec_change: When True (bot Regen button), refuse if the
            current spec equals ``media_specs_used`` — bot flow only
            regenerates after an explicit edit. False (Retry, web, CLI)
            always regenerates.

    Returns:
        A ``RegenResult`` with ``path`` set on success, ``error`` set on
        failure. Write-side effects (update_draft_media / insert_draft_change
        / emit_data_event) happen before the return.
    """
    draft = ops.get_draft(conn, draft_id)
    if draft is None:
        return RegenResult(media_id=media_id, error="draft_not_found")

    specs = draft.media_specs or []
    idx = next(
        (i for i, s in enumerate(specs) if isinstance(s, dict) and s.get("id") == media_id),
        None,
    )
    if idx is None:
        return RegenResult(media_id=media_id, error=f"media_{media_id}_not_found")
    spec = specs[idx]
    if spec.get("user_uploaded"):
        return RegenResult(media_id=media_id, error="cannot_regen_user_upload")

    if enforce_spec_change:
        used = draft.media_specs_used or []
        prior = used[idx] if idx < len(used) else None
        if isinstance(prior, dict) and prior.get("spec") == spec.get("spec"):
            return RegenResult(
                media_id=media_id,
                error="Media spec unchanged — edit the spec first, or use Retry.",
            )

    tool_name = spec.get("tool") or ""
    try:
        adapter = resolve_media_adapter(tool_name, config)
    except ConfigError as exc:
        ops.update_draft_media(conn, draft_id, media_id, error=str(exc))
        return RegenResult(media_id=media_id, error=str(exc))

    output_dir = str(get_base_path() / "media-cache" / media_id)
    try:
        result = adapter.generate(spec=_spec_for_adapter(spec), output_dir=output_dir)
    except Exception as exc:  # adapters raise a wide range — log + surface
        logger.warning("Media adapter %r raised: %s", tool_name, exc, exc_info=True)
        ops.update_draft_media(conn, draft_id, media_id, error=str(exc))
        return RegenResult(media_id=media_id, error=str(exc))

    if not result.success or not result.file_path:
        msg = result.error or "generation_failed"
        ops.update_draft_media(conn, draft_id, media_id, error=msg)
        ops.emit_data_event(conn, "draft", "updated", draft_id, draft.project_id)
        return RegenResult(media_id=media_id, error=msg)

    old_path = (draft.media_paths[idx] if idx < len(draft.media_paths) else "") or ""
    ops.update_draft_media(
        conn,
        draft_id,
        media_id,
        path=result.file_path,
        spec_used=spec,
        error="",
    )
    ops.insert_draft_change(
        conn,
        DraftChange(
            id=generate_id("change"),
            draft_id=draft_id,
            field=f"media_spec:{media_id}",
            old_value=old_path,
            new_value=result.file_path,
            changed_by=changed_by,
        ),
    )
    ops.emit_data_event(conn, "draft", "updated", draft_id, draft.project_id)
    return RegenResult(media_id=media_id, path=result.file_path)
