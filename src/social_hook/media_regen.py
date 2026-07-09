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
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from social_hook.adapters.registry import resolve_media_adapter, with_adapter_lock
from social_hook.db import operations as ops
from social_hook.errors import ConfigError
from social_hook.filesystem import generate_id, get_base_path
from social_hook.models.core import DraftChange

logger = logging.getLogger(__name__)

# Mirrors drafting._generate_all_media — balances throughput against LLM /
# adapter rate-limits. Higher values surface 429s without real wins.
REGEN_MAX_WORKERS = 4


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


def regen_all_media_items(
    conn_factory: Callable[[], sqlite3.Connection],
    draft_id: str,
    media_ids: list[str],
    config: Any,
    *,
    task_id: str | None = None,
    project_id: str | None = None,
    changed_by: str = "human",
    on_stage: Callable[[int, int], None] | None = None,
    max_workers: int = REGEN_MAX_WORKERS,
) -> list[RegenResult]:
    """Regenerate many media items in parallel, preserving input order.

    Each worker opens its own ``sqlite3.Connection`` via ``conn_factory``
    (sqlite connections are not thread-safe across threads), resolves the
    tool's thread-safety via ``with_adapter_lock``, and calls
    ``regen_media_item``. Per-item failures land in ``RegenResult.error``
    and do NOT sink the batch.

    The ``on_stage(index, total)`` callback fires on the calling thread as
    each item completes (``as_completed`` order); callers use it to emit
    ``media_{i+1}_of_{n}`` stage events via their own conn, matching the
    prior sequential behavior. The callback receives the item's original
    index (0-based) so labels can be stable across runs.

    Returns a ``list[RegenResult]`` aligned with the input ``media_ids``
    order. Callers aggregate ``{"items": [...], "count": n}`` themselves
    to keep the web response shape.
    """
    n = len(media_ids)
    if n == 0:
        return []

    tool_map = _lookup_tools_for_media(conn_factory, draft_id, media_ids)

    results: list[RegenResult | None] = [None] * n

    def _worker(idx: int, media_id: str) -> tuple[int, RegenResult]:
        conn = conn_factory()
        try:
            with with_adapter_lock(tool_map.get(media_id, "")):
                result = regen_media_item(
                    conn,
                    draft_id,
                    media_id,
                    config,
                    changed_by=changed_by,
                )
        finally:
            conn.close()
        return idx, result

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_worker, i, mid): i for i, mid in enumerate(media_ids)}
        for future in as_completed(futures):
            idx = futures[future]
            try:
                _, result = future.result()
            except Exception as exc:  # noqa: BLE001 — per-item failure tolerated
                logger.warning(
                    "regen_media_item raised for %s (unexpected — helper catches internally): %s",
                    media_ids[idx],
                    exc,
                    exc_info=True,
                )
                result = RegenResult(media_id=media_ids[idx], error=str(exc))
            results[idx] = result
            if on_stage is not None:
                try:
                    on_stage(idx, n)
                except Exception as stage_err:  # noqa: BLE001 — stage emit must never fail the batch
                    logger.warning("on_stage callback raised: %s", stage_err)

    # All slots filled — cast for the type checker.
    assert all(r is not None for r in results)
    return [r for r in results if r is not None]


def _lookup_tools_for_media(
    conn_factory: Callable[[], sqlite3.Connection],
    draft_id: str,
    media_ids: list[str],
) -> dict[str, str]:
    """Map ``media_id`` → ``tool`` for the lock dispatch in regen-all.

    Kept separate so the parallel workers can read the table without each
    one paying for a ``get_draft`` round-trip. Unknown ids map to ``""``,
    which ``with_adapter_lock`` treats as "thread-safe" (a no-op lock) —
    ``regen_media_item`` then surfaces the real "not found" error.
    """
    conn = conn_factory()
    try:
        draft = ops.get_draft(conn, draft_id)
    finally:
        conn.close()
    if draft is None:
        return {}
    specs = draft.media_specs or []
    out: dict[str, str] = {}
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        mid = spec.get("id")
        if mid and mid in media_ids:
            out[mid] = spec.get("tool") or ""
    return out


def replan_media_spec(
    config: Any,
    draft_content: str,
    tool_name: str,
) -> dict:
    """Ask the drafter LLM for a fresh spec for one media slot.

    Extracted from the bot + web replan flows so the LLM call itself can
    run inside a ``ThreadPoolExecutor`` — DB writes stay on the calling
    thread per-surface to preserve each surface's ``DraftChange`` /
    ``update_draft_media`` ordering. Raises the adapter / LLM exception
    unchanged; callers wrap in try/except and record per-slot failure.
    """
    from social_hook.adapters.registry import get_tool_spec_schema
    from social_hook.llm.base import extract_tool_call
    from social_hook.llm.factory import create_client
    from social_hook.llm.prompts import (
        assemble_spec_generation_prompt,
        build_spec_generation_tool,
    )

    client = create_client(config.models.drafter, config)
    schema = get_tool_spec_schema(tool_name)
    prompt = assemble_spec_generation_prompt(
        tool_name=tool_name, schema=schema, draft_content=draft_content
    )
    spec_tool = build_spec_generation_tool(tool_name, schema)
    response = client.complete(messages=[{"role": "user", "content": prompt}], tools=[spec_tool])
    payload = extract_tool_call(response, "generate_media_spec")
    if not isinstance(payload, dict):
        raise RuntimeError(
            f"replan: drafter returned non-dict payload for {tool_name}: {type(payload).__name__}"
        )
    return payload
