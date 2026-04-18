"""Inline button callback handlers for Telegram bot."""

import logging
import time
from dataclasses import dataclass
from typing import Any

from social_hook.messaging.base import (
    Button,
    ButtonRow,
    CallbackEvent,
    MessagingAdapter,
    OutboundMessage,
)
from social_hook.models.enums import EDITABLE_STATUSES, TERMINAL_STATUSES

logger = logging.getLogger(__name__)


@dataclass
class PendingReply:
    type: str  # "edit_text", "schedule_custom", "edit_angle", "reject_note"
    draft_id: str
    timestamp: float


_pending_replies: dict[str, PendingReply] = {}
_REPLY_TTL_SECONDS = 300  # 5 minutes
_EDIT_TTL_SECONDS = _REPLY_TTL_SECONDS  # backward-compat alias (used by e2e_test.py)


def get_pending_reply(chat_id: str) -> PendingReply | None:
    """Check for a pending reply without consuming it."""
    entry = _pending_replies.get(chat_id)
    if entry is None:
        return None
    if time.time() - entry.timestamp > _REPLY_TTL_SECONDS:
        del _pending_replies[chat_id]
        return None
    return entry


def clear_pending_reply(chat_id: str) -> None:
    """Remove pending reply after successful handling."""
    _pending_replies.pop(chat_id, None)


def get_pending_edit(chat_id: str) -> str | None:
    """Backward-compat wrapper: returns draft_id if pending edit_text reply exists."""
    pending = get_pending_reply(chat_id)
    if pending and pending.type == "edit_text":
        return pending.draft_id
    return None


def clear_pending_edit(chat_id: str) -> None:
    """Backward-compat wrapper: clears any pending reply."""
    clear_pending_reply(chat_id)


def _get_conn():
    """Get a fresh DB connection (per-request pattern)."""
    from social_hook.db import init_database
    from social_hook.filesystem import get_db_path

    return init_database(get_db_path())


def _send(adapter: MessagingAdapter, chat_id: str, text: str) -> bool:
    """Send a message via adapter."""
    result = adapter.send_message(chat_id, OutboundMessage(text=text))
    if not result.success:
        logger.warning("Failed to send to %s: %s", chat_id, result.error)
    return result.success


def _send_with_buttons(
    adapter: MessagingAdapter,
    chat_id: str,
    text: str,
    buttons: list[ButtonRow],
) -> bool:
    """Send a message with inline buttons via adapter."""
    result = adapter.send_message(chat_id, OutboundMessage(text=text, buttons=buttons))
    if not result.success:
        logger.warning("Failed to send buttons to %s: %s", chat_id, result.error)
    return result.success


def _send_media(
    adapter: MessagingAdapter,
    chat_id: str,
    file_path: str,
    caption: str = "",
) -> bool:
    """Send a media file via adapter."""
    result = adapter.send_media(chat_id, file_path, caption=caption)
    if not result.success:
        logger.warning("Failed to send media to %s: %s", chat_id, result.error)
    return result.success


def _answer_callback(adapter: MessagingAdapter, callback_id: str, text: str = "") -> bool:
    """Answer a callback query via adapter."""
    return adapter.answer_callback(callback_id, text)


def _guard_draft_editable(adapter, chat_id, draft):
    """Return True if draft is editable, else send error and return False."""
    if draft.status not in EDITABLE_STATUSES:
        _send(adapter, chat_id, f"Cannot edit media — draft is {draft.status}.")
        return False
    return True


def _parse_media_payload(payload: str, draft) -> tuple[str, str | None]:
    """Extract ``(draft_id, media_id)`` from a media-button callback payload.

    Supports two formats on Telegram's 64-byte callback_data budget:

    - **Legacy 2-part** ``draft_<12hex>`` — operates on ``media_specs[0]``
      when the draft has any existing media (backward-compat with older
      notifications issued before multi-media). Returns ``media_id=None``
      if no media exists; callers decide how to react.
    - **New 3-part** ``draft_<12hex>:media_<12hex>`` — explicit per-item.

    Never interpret the legacy form as "all items" for destructive actions.
    Bulk-op handlers (``btn_media_regen_all``) use the legacy form
    deliberately because they operate on every item by design.
    """
    parts = payload.split(":")
    if len(parts) == 1:
        draft_id = parts[0]
        media_id: str | None = None
        if draft is not None and getattr(draft, "media_specs", None):
            first = draft.media_specs[0] if draft.media_specs else None
            if isinstance(first, dict):
                media_id = first.get("id")
        return draft_id, media_id
    if len(parts) == 2:
        return parts[0], parts[1]
    logger.warning(
        "Unknown media payload format: %r (expected 1 or 2 colon-separated parts)", payload
    )
    return payload, None


def _clear_original_buttons(adapter, chat_id, message_id, draft_id, action_label):
    """Replace the original notification message buttons with a status line."""
    if not message_id:
        return
    try:
        status = f"Draft `{draft_id[:12]}…` — {action_label}"
        adapter.edit_message(chat_id, message_id, OutboundMessage(text=status))
    except Exception:
        logger.debug("Failed to clear buttons from original message", exc_info=True)


def handle_callback(
    event: CallbackEvent, adapter: MessagingAdapter, config: Any | None = None, **kwargs: Any
) -> None:
    """Route a callback query to the appropriate handler.

    Callback data format: "action:payload" (already parsed in CallbackEvent)

    Args:
        event: Normalized callback event
        adapter: Messaging adapter for sending responses
        config: Full Config object
        **kwargs: Forward-compat for future parameters
    """
    callback_id = event.callback_id
    chat_id = event.chat_id
    action = event.action
    payload = event.payload

    if not action or not chat_id:
        _answer_callback(adapter, callback_id, "Invalid callback")
        return

    handlers: dict[str, Any] = {
        "approve": btn_approve,
        "quick_approve": btn_quick_approve,
        "post_now": btn_post_now,
        "schedule": btn_schedule_submenu,
        "schedule_optimal": btn_schedule_optimal,
        "schedule_custom": btn_schedule_custom,
        "edit": btn_edit_submenu,
        "edit_text": btn_edit_text,
        "edit_media": btn_edit_media,
        "media_regen": btn_media_regen,
        "media_retry": btn_media_retry,
        "media_remove": btn_media_remove,
        "media_pick_tool": btn_media_pick_tool,
        "media_gen_spec": btn_media_gen_spec,
        "media_confirm_gen": btn_media_confirm_gen,
        "media_upload": btn_media_upload,
        "media_preview": btn_media_preview,
        "media_sync_siblings": btn_media_sync_siblings,
        "edit_angle": btn_edit_angle,
        "reject": btn_reject_submenu,
        "reject_now": btn_reject,
        "reject_note": btn_reject_note,
        "reject_skip_intro": btn_reject_skip_intro,
        "cancel": btn_cancel,
        "unapprove": btn_unapprove,
        "unschedule": btn_unschedule,
        "reopen": btn_reopen,
        "review": btn_review,
        "promote": btn_promote_submenu,
        "promote_to": btn_promote_to,
        "cycle_expand": handle_cycle_expand,
        "cycle_approve": handle_cycle_approve,
        "cycle_view": handle_cycle_view,
        "arc_approve": handle_arc_approve,
        "arc_dismiss": handle_arc_dismiss,
    }

    handler = handlers.get(action)
    if handler:
        handler(
            adapter, chat_id, callback_id, payload, config, message_id=event.message_id, **kwargs
        )
    else:
        _answer_callback(adapter, callback_id, f"Unknown action: {action}")


def btn_approve(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Handle approve button press."""
    _answer_callback(adapter, callback_id, "Approving...")

    conn = _get_conn()
    try:
        from social_hook.bot.commands import set_chat_draft_context
        from social_hook.db import get_draft, update_draft
        from social_hook.db import operations as ops

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return

        set_chat_draft_context(chat_id, draft_id, draft.project_id)

        if draft.preview_mode:
            _send(
                adapter,
                chat_id,
                "No account connected. Run 'social-hook account add' to connect and enable posting.",
            )
            return

        # Scheduled drafts go through the scheduler; use unschedule first
        if draft.status not in ("draft", "approved", "deferred"):
            _send(adapter, chat_id, f"Cannot approve draft with status: {draft.status}")
            return

        # Non-auto-postable vehicles → advisory instead of approve
        from social_hook.vehicle import check_auto_postable, handle_advisory_approval

        if not check_auto_postable(draft):
            handle_advisory_approval(conn, draft, config)
            _clear_original_buttons(
                adapter, chat_id, kwargs.get("message_id"), draft_id, "advisory"
            )
            _send(
                adapter, chat_id, f"Draft `{draft_id[:12]}` → advisory (requires manual posting)."
            )
            return

        update_draft(conn, draft_id, status="approved")
        ops.emit_data_event(conn, "draft", "approved", draft_id, draft.project_id)
        _clear_original_buttons(adapter, chat_id, kwargs.get("message_id"), draft_id, "approved")
        _send(adapter, chat_id, f"Draft `{draft_id[:12]}` approved and ready for posting.")
        if config:
            from social_hook.notifications import broadcast_notification

            broadcast_notification(
                config,
                OutboundMessage(text=f"Draft `{draft_id[:12]}` approved ({draft.platform})"),
                exclude_chat=chat_id,
            )
    finally:
        conn.close()


def btn_schedule_optimal(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Handle schedule (optimal time) button press."""
    _answer_callback(adapter, callback_id, "Calculating optimal time...")

    conn = _get_conn()
    try:
        from social_hook.bot.commands import set_chat_draft_context
        from social_hook.db import get_draft, update_draft
        from social_hook.db import operations as ops
        from social_hook.scheduling import calculate_optimal_time

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return

        set_chat_draft_context(chat_id, draft_id, draft.project_id)

        if draft.preview_mode:
            _send(
                adapter,
                chat_id,
                "No account connected. Run 'social-hook account add' to connect and enable posting.",
            )
            return

        result = calculate_optimal_time(
            conn,
            draft.project_id,
            platform=draft.platform,
            tz=config.scheduling.timezone if config else "UTC",
            max_posts_per_day=config.scheduling.max_posts_per_day if config else 3,
            min_gap_minutes=config.scheduling.min_gap_minutes if config else 30,
            optimal_days=config.scheduling.optimal_days if config else None,
            optimal_hours=config.scheduling.optimal_hours if config else None,
        )
        scheduled_str = result.datetime.isoformat()

        # Non-auto-postable vehicles → advisory with due_date
        from social_hook.vehicle import check_auto_postable, handle_advisory_approval

        if not check_auto_postable(draft):
            handle_advisory_approval(conn, draft, config, scheduled_time=scheduled_str)
            _clear_original_buttons(
                adapter, chat_id, kwargs.get("message_id"), draft_id, "advisory"
            )
            _send(adapter, chat_id, f"Draft `{draft_id[:12]}` → advisory (due {scheduled_str}).")
            return

        update_draft(conn, draft_id, status="scheduled", scheduled_time=scheduled_str)
        ops.emit_data_event(conn, "draft", "scheduled", draft_id, draft.project_id)
        _clear_original_buttons(adapter, chat_id, kwargs.get("message_id"), draft_id, "scheduled")
        _send(
            adapter,
            chat_id,
            f"Draft `{draft_id[:12]}` scheduled for {scheduled_str}\n{result.time_reason}",
        )
        if config:
            from social_hook.notifications import broadcast_notification

            broadcast_notification(
                config,
                OutboundMessage(
                    text=f"Draft `{draft_id[:12]}` scheduled for {scheduled_str} ({draft.platform})"
                ),
                exclude_chat=chat_id,
            )
    finally:
        conn.close()


def btn_edit_text(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Handle edit text button press.

    Sends the current content, registers a pending edit, and asks user
    to reply with new text.
    """
    _answer_callback(adapter, callback_id, "Edit mode")

    conn = _get_conn()
    try:
        from social_hook.bot.commands import set_chat_draft_context
        from social_hook.db import get_draft

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return

        set_chat_draft_context(chat_id, draft_id, draft.project_id)

        # Warn if overwriting a different pending reply
        existing = get_pending_reply(chat_id)
        if existing and existing.draft_id != draft_id:
            _send(
                adapter,
                chat_id,
                f"Switching edit to `{draft_id[:12]}` (edit for `{existing.draft_id[:12]}` cancelled).",
            )

        _pending_replies[chat_id] = PendingReply(
            type="edit_text", draft_id=draft_id, timestamp=time.time()
        )

        _send(
            adapter,
            chat_id,
            f"*Current content for* `{draft_id[:12]}`:\n\n"
            f"```\n{draft.content}\n```\n\n"
            f"Reply with new content to update this draft.",
        )
    finally:
        conn.close()


def btn_reject(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Handle reject button press (direct reject)."""
    _answer_callback(adapter, callback_id, "Rejecting...")

    conn = _get_conn()
    try:
        from social_hook.bot.commands import set_chat_draft_context
        from social_hook.db import get_draft, update_draft
        from social_hook.db import operations as ops

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return

        set_chat_draft_context(chat_id, draft_id, draft.project_id)

        update_draft(conn, draft_id, status="rejected")
        ops.emit_data_event(conn, "draft", "rejected", draft_id, draft.project_id)
        _clear_original_buttons(adapter, chat_id, kwargs.get("message_id"), draft_id, "rejected")

        # Cascade re-draft if this was an intro draft
        from social_hook.intro_lifecycle import on_intro_rejected

        cascade_msg = on_intro_rejected(conn, draft, draft.project_id, verbose=False)

        reject_msg = f"Draft `{draft_id[:12]}` rejected."
        if cascade_msg:
            reject_msg += f"\n{cascade_msg}"
        _send(adapter, chat_id, reject_msg)
        if config:
            from social_hook.notifications import broadcast_notification

            broadcast_notification(
                config,
                OutboundMessage(text=f"Draft `{draft_id[:12]}` rejected ({draft.platform})"),
                exclude_chat=chat_id,
            )
    finally:
        conn.close()


def btn_quick_approve(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Approve and schedule at optimal time in one step."""
    _answer_callback(adapter, callback_id, "Approving and scheduling...")

    conn = _get_conn()
    try:
        from social_hook.bot.commands import set_chat_draft_context
        from social_hook.db import get_draft, update_draft
        from social_hook.db import operations as ops
        from social_hook.scheduling import calculate_optimal_time

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return

        set_chat_draft_context(chat_id, draft_id, draft.project_id)

        if draft.preview_mode:
            _send(
                adapter,
                chat_id,
                "No account connected. Run 'social-hook account add' to connect and enable posting.",
            )
            return

        # Scheduled drafts go through the scheduler; use unschedule first
        if draft.status not in ("draft", "approved", "deferred"):
            _send(adapter, chat_id, f"Cannot approve draft with status: {draft.status}")
            return

        result = calculate_optimal_time(
            conn,
            draft.project_id,
            platform=draft.platform,
            tz=config.scheduling.timezone if config else "UTC",
            max_posts_per_day=config.scheduling.max_posts_per_day if config else 3,
            min_gap_minutes=config.scheduling.min_gap_minutes if config else 30,
            optimal_days=config.scheduling.optimal_days if config else None,
            optimal_hours=config.scheduling.optimal_hours if config else None,
        )
        scheduled_str = result.datetime.isoformat()

        # Non-auto-postable vehicles → advisory with due_date
        from social_hook.vehicle import check_auto_postable, handle_advisory_approval

        if not check_auto_postable(draft):
            handle_advisory_approval(conn, draft, config, scheduled_time=scheduled_str)
            _clear_original_buttons(
                adapter, chat_id, kwargs.get("message_id"), draft_id, "advisory"
            )
            _send(adapter, chat_id, f"Draft `{draft_id[:12]}` → advisory (due {scheduled_str}).")
            return

        update_draft(conn, draft_id, status="scheduled", scheduled_time=scheduled_str)
        ops.emit_data_event(conn, "draft", "approved", draft_id, draft.project_id)
        _clear_original_buttons(
            adapter, chat_id, kwargs.get("message_id"), draft_id, "approved + scheduled"
        )
        _send(
            adapter,
            chat_id,
            f"Draft `{draft_id[:12]}` approved and scheduled for {scheduled_str}",
        )
        if config:
            from social_hook.notifications import broadcast_notification

            broadcast_notification(
                config,
                OutboundMessage(
                    text=f"Draft `{draft_id[:12]}` approved and scheduled for {scheduled_str} ({draft.platform})"
                ),
                exclude_chat=chat_id,
            )
    finally:
        conn.close()


def btn_post_now(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Handle post now button press."""
    _answer_callback(adapter, callback_id, "Posting now...")

    conn = _get_conn()
    try:
        from social_hook.bot.commands import set_chat_draft_context
        from social_hook.db import get_draft, update_draft
        from social_hook.db import operations as ops

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return

        set_chat_draft_context(chat_id, draft_id, draft.project_id)

        if draft.status not in ("draft", "approved", "deferred"):
            _send(adapter, chat_id, f"Cannot post: draft status is {draft.status}")
            return

        if draft.preview_mode:
            _send(
                adapter,
                chat_id,
                "No account connected. Run 'social-hook account add' to connect and enable posting.",
            )
            return

        # Check project is not paused
        project = ops.get_project(conn, draft.project_id)
        if project and project.paused:
            _send(adapter, chat_id, "Project is paused. Unpause before posting.")
            return

        # Non-auto-postable vehicles → advisory immediately
        from social_hook.vehicle import check_auto_postable, handle_advisory_approval

        if not check_auto_postable(draft):
            handle_advisory_approval(conn, draft, config)
            _clear_original_buttons(
                adapter, chat_id, kwargs.get("message_id"), draft_id, "advisory"
            )
            _send(
                adapter, chat_id, f"Draft `{draft_id[:12]}` → advisory (requires manual posting)."
            )
            return

        from datetime import datetime, timezone

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        update_draft(conn, draft_id, status="scheduled", scheduled_time=now_str)
        ops.emit_data_event(conn, "draft", "updated", draft_id, draft.project_id)
    finally:
        conn.close()

    # Call scheduler_tick outside the conn block (it opens its own connection)
    from social_hook.scheduler import scheduler_tick

    scheduler_tick(draft_id=draft_id, dry_run=False)

    # Re-open connection to check result
    conn = _get_conn()
    try:
        from social_hook.db import get_draft

        draft_after = get_draft(conn, draft_id)
        if draft_after and draft_after.status == "posted":
            _clear_original_buttons(adapter, chat_id, kwargs.get("message_id"), draft_id, "posted")
            _send(adapter, chat_id, f"Draft `{draft_id[:12]}` posted successfully!")
        elif draft_after and draft_after.status == "scheduled":
            _send(
                adapter,
                chat_id,
                f"Post failed for draft `{draft_id[:12]}`. Check logs for details.",
            )
        else:
            status = draft_after.status if draft_after else "unknown"
            _send(adapter, chat_id, f"Draft `{draft_id[:12]}` status: {status}")
    finally:
        conn.close()


def btn_schedule_submenu(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Show schedule submenu with optimal/custom options."""
    _answer_callback(adapter, callback_id)

    buttons = [
        ButtonRow(
            buttons=[
                Button(label="Optimal time", action="schedule_optimal", payload=draft_id),
                Button(label="Custom time", action="schedule_custom", payload=draft_id),
            ]
        ),
    ]
    _send_with_buttons(adapter, chat_id, f"Schedule `{draft_id[:12]}`:", buttons)


def btn_schedule_custom(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Prompt user to reply with a custom time."""
    _answer_callback(adapter, callback_id)

    conn = _get_conn()
    try:
        from social_hook.db import get_draft

        draft = get_draft(conn, draft_id)
        if draft and draft.preview_mode:
            _send(
                adapter,
                chat_id,
                "No account connected. Run 'social-hook account add' to connect and enable posting.",
            )
            return
    finally:
        conn.close()

    _pending_replies[chat_id] = PendingReply(
        type="schedule_custom", draft_id=draft_id, timestamp=time.time()
    )
    _send(
        adapter,
        chat_id,
        f"Reply with desired time for `{draft_id[:12]}`\n"
        f"Send an ISO 8601 datetime, e.g. 2026-03-15T14:30:00",
    )


def btn_edit_submenu(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Show edit submenu with text/media/angle options."""
    _answer_callback(adapter, callback_id)
    _clear_original_buttons(adapter, chat_id, kwargs.get("message_id"), draft_id, "editing")

    # Check if this is an intro draft to adjust label
    angle_label = "Change angle"
    conn = _get_conn()
    try:
        from social_hook.db import get_draft

        draft = get_draft(conn, draft_id)
        if draft and getattr(draft, "is_intro", False):
            angle_label = "Change intro angle"
    finally:
        conn.close()

    buttons = [
        ButtonRow(
            buttons=[
                Button(label="Change text", action="edit_text", payload=draft_id),
                Button(label="Change media", action="edit_media", payload=draft_id),
            ]
        ),
        ButtonRow(
            buttons=[
                Button(label=angle_label, action="edit_angle", payload=draft_id),
            ]
        ),
    ]
    _send_with_buttons(adapter, chat_id, f"Edit `{draft_id[:12]}`:", buttons)


def btn_edit_media(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    payload: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Show current media and per-item action buttons, or offer to add if none.

    Payload is the draft_id from the top-level Edit submenu. One preview +
    action row is shown per existing media item with 3-part payloads
    ``action:draft_id:media_id``. Bulk actions (Add, Regen all, Replan
    specs) sit above the per-item rows.
    """
    draft_id = payload
    _answer_callback(adapter, callback_id, "Loading media...")
    conn = _get_conn()
    try:
        from social_hook.bot.commands import set_chat_draft_context
        from social_hook.db import get_draft

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return
        set_chat_draft_context(chat_id, draft_id, draft.project_id)

        if not _guard_draft_editable(adapter, chat_id, draft):
            return

        specs = draft.media_specs or []
        paths = draft.media_paths or []
        errors = draft.media_errors or []
        caps = adapter.get_capabilities()

        if not specs:
            # No media yet — offer to add a new slot or upload.
            _send_with_buttons(
                adapter,
                chat_id,
                f"No media on `{draft_id[:12]}`. Add some?",
                [
                    ButtonRow(
                        buttons=[
                            Button(label="Add media", action="media_add", payload=draft_id),
                            Button(label="Upload file", action="media_upload", payload=draft_id),
                        ]
                    ),
                ],
            )
            return

        # Header row: batch operations across all items.
        _send_with_buttons(
            adapter,
            chat_id,
            f"Media for `{draft_id[:12]}` ({len(specs)} item(s)):",
            [
                ButtonRow(
                    buttons=[
                        Button(label="Add", action="media_add", payload=draft_id),
                        Button(label="Regen all", action="media_regen_all", payload=draft_id),
                        Button(label="Replan", action="media_replan_specs", payload=draft_id),
                    ]
                ),
            ],
        )

        for i, spec in enumerate(specs):
            if not isinstance(spec, dict):
                continue
            mid = spec.get("id")
            if not mid:
                continue
            pay = f"{draft_id}:{mid}"
            tool = spec.get("tool") or "?"
            path = paths[i] if i < len(paths) else ""
            err = errors[i] if i < len(errors) else None

            if path and caps.supports_media:
                _send_media(adapter, chat_id, path, caption=f"Media {i + 1} ({tool})")
            elif err:
                _send(adapter, chat_id, f"Media {i + 1} ({tool}) failed: {err}")
            else:
                _send(adapter, chat_id, f"Media {i + 1} ({tool}) — pending generation.")

            _send_with_buttons(
                adapter,
                chat_id,
                f"`{mid}`",
                [
                    ButtonRow(
                        buttons=[
                            Button(label="Regen", action="media_regen", payload=pay),
                            Button(label="Retry", action="media_retry", payload=pay),
                            Button(label="Edit spec", action="media_gen_spec", payload=pay),
                        ]
                    ),
                    ButtonRow(
                        buttons=[
                            Button(label="Preview", action="media_preview", payload=pay),
                            Button(label="Remove", action="media_remove", payload=pay),
                        ]
                    ),
                ],
            )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Media handlers (multi-media aware). Payload formats:
#   - 2-part legacy  "draft_id"              → operates on media_specs[0]
#   - 3-part new     "draft_id:media_id"     → explicit per-item
# Destructive btn_media_remove uses an inline-keyboard confirm step (never
# a web Modal) with payload prefix "confirm:..." on the second click.
# ---------------------------------------------------------------------------


def _generate_for_media_item(config: Any, spec: dict, output_dir: str):
    """Shared adapter lookup + generate for one media spec. Raises ValueError
    when the tool is missing / misconfigured so the caller can render a
    concise error string.
    """
    from social_hook.adapters.registry import get_media_adapter

    tool_name = spec.get("tool", "")
    if not tool_name or tool_name == "legacy_upload":
        raise ValueError(f"Tool {tool_name!r} has no generator")
    api_key = None
    if tool_name == "nano_banana_pro":
        api_key = config.env.get("GEMINI_API_KEY") if config else None
        if not api_key:
            raise ValueError("GEMINI_API_KEY not configured")
    media_adapter = get_media_adapter(tool_name, api_key=api_key)
    if media_adapter is None:
        raise ValueError(f"Media adapter '{tool_name}' not available")
    return media_adapter.generate(spec=spec.get("spec", {}), output_dir=output_dir)


def _regen_one_media(
    draft,
    media_id: str,
    config: Any | None,
    *,
    enforce_spec_change: bool,
) -> tuple[bool, str | None]:
    """Regenerate one media item by id. Writes via update_draft_media and
    inserts a DraftChange with ``field=f"media_spec:{media_id}"``. Returns
    ``(success, path_or_error)``.
    """
    from social_hook.db import operations as ops
    from social_hook.filesystem import generate_id, get_base_path
    from social_hook.models.core import DraftChange

    specs = draft.media_specs or []
    idx = next(
        (i for i, s in enumerate(specs) if isinstance(s, dict) and s.get("id") == media_id), None
    )
    if idx is None:
        return False, f"Media id {media_id} not found on this draft."
    spec = specs[idx]
    if spec.get("user_uploaded"):
        return False, f"Cannot regenerate user-uploaded media {media_id}."

    if enforce_spec_change:
        used = draft.media_specs_used or []
        prior = used[idx] if idx < len(used) else None
        if isinstance(prior, dict) and prior.get("spec") == spec.get("spec"):
            return False, "Media spec unchanged — edit the spec first, or use Retry."

    output_dir = str(get_base_path() / "media-cache" / media_id)
    conn = _get_conn()
    try:
        try:
            result = _generate_for_media_item(config, spec, output_dir)
        except ValueError as e:
            ops.update_draft_media(conn, draft.id, media_id, error=str(e))
            return False, str(e)
        if result.success and result.file_path:
            old_path = (draft.media_paths[idx] if idx < len(draft.media_paths) else "") or ""
            ops.update_draft_media(
                conn,
                draft.id,
                media_id,
                path=result.file_path,
                spec_used=spec,
                error="",
            )
            ops.insert_draft_change(
                conn,
                DraftChange(
                    id=generate_id("change"),
                    draft_id=draft.id,
                    field=f"media_spec:{media_id}",
                    old_value=old_path,
                    new_value=result.file_path,
                    changed_by="human",
                ),
            )
            ops.emit_data_event(conn, "draft", "updated", draft.id, draft.project_id)
            return True, result.file_path
        msg = result.error or "generation failed"
        ops.update_draft_media(conn, draft.id, media_id, error=msg)
        return False, msg
    finally:
        conn.close()


def btn_media_regen(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    payload: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Regenerate a single media item (guards spec-unchanged)."""
    _answer_callback(adapter, callback_id, "Regenerating...")
    conn = _get_conn()
    try:
        from social_hook.db import get_draft

        draft_id, media_id = _parse_media_payload(payload, None)
        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return
        if not _guard_draft_editable(adapter, chat_id, draft):
            return
        if media_id is None:
            _, media_id = _parse_media_payload(payload, draft)
        if media_id is None:
            _send(adapter, chat_id, "No media items on this draft. Add one first.")
            return
    finally:
        conn.close()

    ok, message = _regen_one_media(draft, media_id, config, enforce_spec_change=True)
    if ok and message:
        caps = adapter.get_capabilities()
        if caps.supports_media:
            _send_media(
                adapter, chat_id, message, caption=f"Regenerated {media_id} on `{draft_id[:12]}`"
            )
        _send(adapter, chat_id, "Media regenerated.")
    else:
        _send(adapter, chat_id, f"Regeneration failed: {message}")


def btn_media_retry(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    payload: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Retry generation for a single media item (no spec-unchanged guard)."""
    _answer_callback(adapter, callback_id, "Retrying...")
    conn = _get_conn()
    try:
        from social_hook.db import get_draft

        draft_id, media_id = _parse_media_payload(payload, None)
        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return
        if not _guard_draft_editable(adapter, chat_id, draft):
            return
        if media_id is None:
            _, media_id = _parse_media_payload(payload, draft)
        if media_id is None:
            _send(adapter, chat_id, "No media items on this draft.")
            return
    finally:
        conn.close()

    ok, message = _regen_one_media(draft, media_id, config, enforce_spec_change=False)
    if ok and message:
        caps = adapter.get_capabilities()
        if caps.supports_media:
            _send_media(
                adapter, chat_id, message, caption=f"Retried {media_id} on `{draft_id[:12]}`"
            )
        _send(adapter, chat_id, "Media retry succeeded.")
    else:
        _send(adapter, chat_id, f"Media retry failed: {message}")


def btn_media_remove(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    payload: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Inline-keyboard confirm then splice the item from all four arrays.

    First press: show a Confirm button with payload ``confirm:draft:media``.
    Second press: perform the splice via ``ops.remove_draft_media``.
    """
    _answer_callback(adapter, callback_id, "Removing...")
    parts = payload.split(":")
    is_confirm = parts[0] == "confirm"
    if is_confirm:
        parts = parts[1:]
    inner_payload = ":".join(parts)

    conn = _get_conn()
    try:
        from social_hook.db import get_draft

        draft_id, media_id = _parse_media_payload(inner_payload, None)
        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return
        if not _guard_draft_editable(adapter, chat_id, draft):
            return
        if media_id is None:
            _, media_id = _parse_media_payload(inner_payload, draft)
        if media_id is None:
            _send(adapter, chat_id, "No media items to remove.")
            return

        if not is_confirm:
            confirm_payload = f"confirm:{draft_id}:{media_id}"
            _send_with_buttons(
                adapter,
                chat_id,
                f"Remove media `{media_id}` from `{draft_id[:12]}`? This cannot be undone.",
                [
                    ButtonRow(
                        buttons=[
                            Button(
                                label="Confirm remove",
                                action="media_remove",
                                payload=confirm_payload,
                            ),
                        ]
                    ),
                ],
            )
            return

        from social_hook.db import operations as ops
        from social_hook.filesystem import generate_id
        from social_hook.models.core import DraftChange

        if not ops.remove_draft_media(conn, draft_id, media_id):
            _send(adapter, chat_id, f"Could not remove {media_id}.")
            return
        ops.insert_draft_change(
            conn,
            DraftChange(
                id=generate_id("change"),
                draft_id=draft_id,
                field=f"media_spec:{media_id}",
                old_value=media_id,
                new_value="null",
                changed_by="human",
            ),
        )
        ops.emit_data_event(conn, "draft", "updated", draft_id, draft.project_id)
        _send(adapter, chat_id, f"Removed {media_id} from `{draft_id[:12]}`.")
    finally:
        conn.close()


def btn_media_pick_tool(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    payload: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Show tool buttons for adding/switching a media slot.

    When a draft already has ≥1 media items and no media_id is named in the
    payload, first prompt "for which item?" per plan §Agent 3 Task #3.
    """
    _answer_callback(adapter, callback_id)

    conn = _get_conn()
    try:
        from social_hook.db import get_draft

        draft_id, media_id = _parse_media_payload(payload, None)
        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return
        if not _guard_draft_editable(adapter, chat_id, draft):
            return

        if draft.media_specs and media_id is None and ":" not in payload:
            rows: list[ButtonRow] = []
            for i, spec in enumerate(draft.media_specs):
                if not isinstance(spec, dict):
                    continue
                sid = spec.get("id") or f"item_{i}"
                rows.append(
                    ButtonRow(
                        buttons=[
                            Button(
                                label=f"Item {i + 1} ({spec.get('tool', '?')})",
                                action="media_pick_tool",
                                payload=f"{draft_id}:{sid}",
                            )
                        ]
                    )
                )
            rows.append(
                ButtonRow(
                    buttons=[
                        Button(label="+ New slot", action="media_add", payload=draft_id),
                    ]
                )
            )
            _send_with_buttons(adapter, chat_id, f"Which item on `{draft_id[:12]}`?", rows)
            return
    finally:
        conn.close()

    from social_hook.adapters.registry import list_available_tools

    tools = list_available_tools()
    rows = []
    for tool in tools:
        target = f"{draft_id}:{media_id}" if media_id else draft_id
        rows.append(
            ButtonRow(
                buttons=[
                    Button(
                        label=tool["display_name"],
                        action="media_gen_spec",
                        payload=f"{target}|{tool['name']}",
                    )
                ]
            )
        )
    header = f"Pick a media tool for `{draft_id[:12]}`"
    if media_id:
        header += f" / {media_id}"
    _send_with_buttons(adapter, chat_id, header + ":", rows)


def btn_media_gen_spec(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    payload: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """User picked a tool — generate a spec for a specific media_id (or new slot).

    Payload formats:
      ``draft_id|tool_name``                  → append a new slot
      ``draft_id:media_id|tool_name``         → replace spec on existing
    """
    _answer_callback(adapter, callback_id, "Generating spec...")

    left, _, tool_name = payload.rpartition("|")
    if not left or not tool_name:
        _send(adapter, chat_id, "Invalid tool selection.")
        return
    draft_id, media_id = _parse_media_payload(left, None)

    conn = _get_conn()
    try:
        from social_hook.adapters.registry import get_tool_spec_schema
        from social_hook.db import get_draft
        from social_hook.db import operations as ops

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return
        if not _guard_draft_editable(adapter, chat_id, draft):
            return

        if media_id is None:
            media_id = ops.append_draft_media(
                conn, draft_id, {"tool": tool_name, "spec": {}, "user_uploaded": False}
            )
            if media_id is None:
                _send(adapter, chat_id, "Could not create media slot.")
                return
        else:
            existing = next(
                (s for s in draft.media_specs if isinstance(s, dict) and s.get("id") == media_id),
                None,
            )
            if existing is None:
                _send(adapter, chat_id, f"Media `{media_id}` not found on draft.")
                return
            new_spec = dict(existing)
            new_spec["tool"] = tool_name
            ops.update_draft_media(conn, draft_id, media_id, spec=new_spec)

        spec = None
        try:
            if config:
                from social_hook.llm.base import extract_tool_call
                from social_hook.llm.factory import create_client
                from social_hook.llm.prompts import (
                    assemble_spec_generation_prompt,
                    build_spec_generation_tool,
                )

                schema = get_tool_spec_schema(tool_name)
                prompt = assemble_spec_generation_prompt(
                    tool_name=tool_name,
                    schema=schema,
                    draft_content=draft.content,
                )
                spec_tool = build_spec_generation_tool(tool_name, schema)
                client = create_client(config.models.drafter, config)

                _task_id = kwargs.get("task_id")
                if _task_id:
                    ops.emit_task_stage(
                        conn, _task_id, "generating", "Generating media spec", draft.project_id
                    )

                response = client.complete(
                    messages=[{"role": "user", "content": prompt}],
                    tools=[spec_tool],
                )
                spec = extract_tool_call(response, "generate_media_spec")
        except Exception:
            logger.debug("LLM spec generation failed, falling back to manual", exc_info=True)

        if spec:
            import json

            item = next(
                (s for s in draft.media_specs if isinstance(s, dict) and s.get("id") == media_id),
                {"id": media_id, "tool": tool_name, "user_uploaded": False},
            )
            new_item = dict(item)
            new_item["tool"] = tool_name
            new_item["spec"] = spec
            ops.update_draft_media(conn, draft_id, media_id, spec=new_item)

            spec_display = json.dumps(spec, indent=2)
            buttons = [
                ButtonRow(
                    buttons=[
                        Button(
                            label="Generate media",
                            action="media_confirm_gen",
                            payload=f"{draft_id}:{media_id}",
                        ),
                    ]
                ),
            ]
            _send_with_buttons(
                adapter,
                chat_id,
                f"Generated spec for `{draft_id[:12]}` / `{media_id}` ({tool_name}):\n"
                f"```json\n{spec_display}\n```\n"
                f"Confirm to generate, or reply with edited JSON.",
                buttons,
            )
            _pending_replies[chat_id] = PendingReply(
                type=f"edit_media_spec:{media_id}", draft_id=draft_id, timestamp=time.time()
            )
        else:
            schema = get_tool_spec_schema(tool_name)
            required = schema.get("required", {})
            optional = schema.get("optional", {})
            schema_lines = []
            for k, desc in required.items():
                schema_lines.append(f"  *{k}* (required): {desc}")
            for k, desc in optional.items():
                schema_lines.append(f"  {k} (optional): {desc}")
            schema_text = "\n".join(schema_lines) if schema_lines else "  (no schema)"

            _send(
                adapter,
                chat_id,
                f"Tool: {tool_name} (media {media_id})\nSpec fields:\n{schema_text}\n\n"
                f"Reply with JSON spec, e.g.:\n"
                f'```json\n{{"key": "value"}}\n```',
            )
            _pending_replies[chat_id] = PendingReply(
                type=f"edit_media_spec:{media_id}", draft_id=draft_id, timestamp=time.time()
            )
    finally:
        conn.close()


def btn_media_confirm_gen(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    payload: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Confirm and generate media for a specific media_id. Initial generation
    does not apply the spec-unchanged guard (it's never "used" yet).
    """
    _answer_callback(adapter, callback_id, "Generating media...")
    _pending_replies.pop(chat_id, None)

    conn = _get_conn()
    try:
        from social_hook.db import get_draft

        draft_id, media_id = _parse_media_payload(payload, None)
        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return
        if not _guard_draft_editable(adapter, chat_id, draft):
            return
        if media_id is None:
            _, media_id = _parse_media_payload(payload, draft)
        if media_id is None:
            _send(adapter, chat_id, "No media slot configured — pick a tool first.")
            return
    finally:
        conn.close()

    ok, message = _regen_one_media(draft, media_id, config, enforce_spec_change=False)
    if ok and message:
        caps = adapter.get_capabilities()
        if caps.supports_media:
            _send_media(
                adapter, chat_id, message, caption=f"Generated {media_id} for `{draft_id[:12]}`"
            )
        _send(adapter, chat_id, "Media generated successfully.")
        conn2 = _get_conn()
        try:
            _offer_sibling_sync(adapter, chat_id, conn2, draft_id)
        finally:
            conn2.close()
    else:
        _send(adapter, chat_id, f"Media generation failed: {message}")


def _offer_sibling_sync(adapter, chat_id, conn, draft_id):
    """If draft has sister drafts, offer to sync the full media list to them."""
    from social_hook.db.operations import get_sister_drafts

    sisters = get_sister_drafts(conn, draft_id)
    editable = [s for s in sisters if s.status in EDITABLE_STATUSES]
    if editable:
        platforms = ", ".join(s.platform for s in editable)
        buttons = [
            ButtonRow(
                buttons=[
                    Button(
                        label=f"Sync to {len(editable)} sibling(s)",
                        action="media_sync_siblings",
                        payload=draft_id,
                    ),
                ]
            ),
        ]
        _send_with_buttons(
            adapter, chat_id, f"Sister drafts found ({platforms}). Sync media?", buttons
        )


def btn_media_upload(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    payload: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Arm a pending reply for an upload to APPEND as a new slot (not
    overwrite slot 0). ``_handle_pending_reply`` handles the actual save.
    """
    _answer_callback(adapter, callback_id)
    draft_id = payload
    conn = _get_conn()
    try:
        from social_hook.db import get_draft

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return
        if not _guard_draft_editable(adapter, chat_id, draft):
            return
    finally:
        conn.close()

    _pending_replies[chat_id] = PendingReply(
        type="media_upload", draft_id=draft_id, timestamp=time.time()
    )
    _send(
        adapter,
        chat_id,
        f"Send a media file (png/jpg/webp/gif, ≤5 MiB) to attach to `{draft_id[:12]}` "
        "as a new media slot.",
    )


def btn_media_preview(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    payload: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Show a text preview of a single media item (or all if no media_id).

    Legacy 2-part payload shows an overview of every item; 3-part payload
    shows the detailed preview for one item via ``adapter.preview_text``.
    """
    _answer_callback(adapter, callback_id)
    conn = _get_conn()
    try:
        from social_hook.adapters.registry import get_media_adapter
        from social_hook.db import get_draft

        draft_id, media_id = _parse_media_payload(payload, None)
        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return

        specs = draft.media_specs or []
        if not specs:
            _send(adapter, chat_id, "No media items on this draft.")
            return

        if media_id is None and ":" not in payload:
            lines = []
            for i, s in enumerate(specs):
                if not isinstance(s, dict):
                    continue
                lines.append(f"[{i}] {s.get('id', '?')} — {s.get('tool', '?')}")
            _send(
                adapter,
                chat_id,
                f"Media on `{draft_id[:12]}`:\n```\n" + "\n".join(lines) + "\n```",
            )
            return

        if media_id is None:
            _, media_id = _parse_media_payload(payload, draft)
        target = next((s for s in specs if isinstance(s, dict) and s.get("id") == media_id), None)
        if target is None:
            _send(adapter, chat_id, f"Media `{media_id}` not found.")
            return

        tool = target.get("tool", "unknown")
        try:
            media_adapter = get_media_adapter(tool) if tool != "legacy_upload" else None
        except (ValueError, Exception):
            media_adapter = None

        if media_adapter and hasattr(media_adapter, "preview_text"):
            preview = media_adapter.preview_text(target.get("spec", {}))
        else:
            import json

            preview = json.dumps(target.get("spec", {}), indent=2)

        _send(
            adapter,
            chat_id,
            f"Preview `{draft_id[:12]}` / `{media_id}` ({tool}):\n```\n{preview}\n```",
        )
    finally:
        conn.close()


def btn_media_sync_siblings(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    payload: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Copy the full media_specs + media_paths list to sister drafts."""
    _answer_callback(adapter, callback_id, "Syncing...")
    draft_id = payload
    conn = _get_conn()
    try:
        from social_hook.db import get_draft
        from social_hook.db.operations import get_sister_drafts, sync_media_to_drafts

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return
        sisters = get_sister_drafts(conn, draft_id)
        if not sisters:
            _send(adapter, chat_id, "No sister drafts to sync to.")
            return
        editable = [s for s in sisters if s.status in EDITABLE_STATUSES]
        if not editable:
            _send(adapter, chat_id, "No editable sister drafts to sync to.")
            return
        count = sync_media_to_drafts(conn, draft_id, [s.id for s in editable])
        platforms = ", ".join(s.platform for s in editable)
        _send(adapter, chat_id, f"Synced media to {count} sister draft(s): {platforms}.")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# New handlers — media_add, media_regen_all, media_replan_specs
# ---------------------------------------------------------------------------


def btn_media_add(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    payload: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Create an empty slot on the draft and dispatch pick-tool for it."""
    _answer_callback(adapter, callback_id, "Adding slot...")
    draft_id = payload
    conn = _get_conn()
    try:
        from social_hook.db import get_draft
        from social_hook.db import operations as ops

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return
        if not _guard_draft_editable(adapter, chat_id, draft):
            return
        new_id = ops.append_draft_media(
            conn, draft_id, {"tool": "nano_banana_pro", "spec": {}, "user_uploaded": False}
        )
        if not new_id:
            _send(adapter, chat_id, "Could not add a new media slot.")
            return
        ops.emit_data_event(conn, "draft", "updated", draft_id, draft.project_id)
    finally:
        conn.close()
    btn_media_pick_tool(adapter, chat_id, callback_id, f"{draft_id}:{new_id}", config, **kwargs)


def btn_media_regen_all(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    payload: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Regenerate every non-uploaded media item on the draft.

    LLM-bearing — the caller (web/daemon dispatch path) wraps this handler
    in ``_run_background_task`` so the bot HTTP response returns quickly.
    One DraftChange row per affected item, never aggregated.
    """
    _answer_callback(adapter, callback_id, "Regenerating all...")
    draft_id = payload
    conn = _get_conn()
    try:
        from social_hook.db import get_draft

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return
        if not _guard_draft_editable(adapter, chat_id, draft):
            return
        if not draft.media_specs:
            _send(adapter, chat_id, "No media items to regenerate.")
            return
    finally:
        conn.close()

    successes = 0
    failures = 0
    for spec in draft.media_specs:
        if not isinstance(spec, dict) or spec.get("user_uploaded"):
            continue
        mid = spec.get("id")
        if not mid:
            continue
        ok, _msg = _regen_one_media(draft, mid, config, enforce_spec_change=False)
        if ok:
            successes += 1
        else:
            failures += 1

    _send(
        adapter,
        chat_id,
        f"Regen all: {successes} succeeded, {failures} failed on `{draft_id[:12]}`.",
    )


def btn_media_replan_specs(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    payload: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Ack a replan request. Full drafter-driven replan lives in the web
    endpoint ``POST /api/drafts/{id}/media/replan``. On Telegram we keep
    things simple: ack and point the operator at per-item controls.
    """
    _answer_callback(adapter, callback_id, "Replan request acknowledged.")
    draft_id = payload
    _send(
        adapter,
        chat_id,
        f"Replan queued for `{draft_id[:12]}`. The full drafter replan runs via the web "
        "endpoint (`POST /api/drafts/{id}/media/replan`). From Telegram, use per-item "
        "Edit / Regen buttons to adjust individual items.",
    )


def btn_edit_angle(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Prompt user to reply with a new angle."""
    _answer_callback(adapter, callback_id)
    _pending_replies[chat_id] = PendingReply(
        type="edit_angle", draft_id=draft_id, timestamp=time.time()
    )
    _send(adapter, chat_id, f"Reply with new angle for `{draft_id[:12]}`")


def btn_reject_submenu(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Show reject submenu with just reject/reject with note, plus skip-intro for intro drafts."""
    _answer_callback(adapter, callback_id)

    reject_buttons = [
        Button(label="Just reject", action="reject_now", payload=draft_id),
        Button(label="Reject with note", action="reject_note", payload=draft_id),
    ]

    # Check if this is an intro draft — offer "Don't intro" option
    conn = _get_conn()
    try:
        from social_hook.db import get_draft

        draft = get_draft(conn, draft_id)
        if draft and getattr(draft, "is_intro", False):
            reject_buttons.append(
                Button(
                    label=f"Don't intro on {draft.platform}",
                    action="reject_skip_intro",
                    payload=draft_id,
                )
            )
    finally:
        conn.close()

    buttons = [ButtonRow(buttons=reject_buttons)]
    _send_with_buttons(adapter, chat_id, f"Reject `{draft_id[:12]}`:", buttons)


def btn_reject_note(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Prompt user to reply with a rejection reason."""
    _answer_callback(adapter, callback_id)
    _pending_replies[chat_id] = PendingReply(
        type="reject_note", draft_id=draft_id, timestamp=time.time()
    )
    _send(adapter, chat_id, f"Reply with rejection reason for `{draft_id[:12]}`")


def btn_reject_skip_intro(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Reject intro draft and mark platform as introduced (skip intro)."""
    _answer_callback(adapter, callback_id, "Skipping intro...")

    conn = _get_conn()
    try:
        from social_hook.bot.commands import set_chat_draft_context
        from social_hook.db import get_draft, update_draft
        from social_hook.db import operations as ops

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return

        set_chat_draft_context(chat_id, draft_id, draft.project_id)

        update_draft(conn, draft_id, status="rejected")
        ops.emit_data_event(conn, "draft", "rejected", draft_id, draft.project_id)
        _clear_original_buttons(adapter, chat_id, kwargs.get("message_id"), draft_id, "rejected")

        # Skip intro: mark platform as introduced, no cascade re-draft
        from social_hook.intro_lifecycle import on_intro_rejected

        on_intro_rejected(conn, draft, draft.project_id, verbose=False, skip_intro=True)

        msg = f"Draft `{draft_id[:12]}` rejected. Intro skipped for {draft.platform}."
        _send(adapter, chat_id, msg)
        if config:
            from social_hook.notifications import broadcast_notification

            broadcast_notification(
                config,
                OutboundMessage(
                    text=f"Draft `{draft_id[:12]}` rejected — intro skipped ({draft.platform})"
                ),
                exclude_chat=chat_id,
            )
    finally:
        conn.close()


def btn_cancel(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Handle cancel button press from scheduled list."""
    _answer_callback(adapter, callback_id, "Cancelling...")

    conn = _get_conn()
    try:
        from social_hook.bot.commands import set_chat_draft_context
        from social_hook.db import get_draft, update_draft
        from social_hook.db import operations as ops

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return

        set_chat_draft_context(chat_id, draft_id, draft.project_id)

        update_draft(conn, draft_id, status="cancelled")
        ops.emit_data_event(conn, "draft", "cancelled", draft_id, draft.project_id)
        _clear_original_buttons(adapter, chat_id, kwargs.get("message_id"), draft_id, "cancelled")
        _send(adapter, chat_id, f"Draft `{draft_id[:12]}` cancelled.")
        if config:
            from social_hook.notifications import broadcast_notification

            broadcast_notification(
                config,
                OutboundMessage(text=f"Draft `{draft_id[:12]}` cancelled ({draft.platform})"),
                exclude_chat=chat_id,
            )
    finally:
        conn.close()


def btn_unapprove(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Handle unapprove button press — revert approved draft back to draft."""
    _answer_callback(adapter, callback_id, "Reverting approval...")

    conn = _get_conn()
    try:
        from social_hook.bot.commands import set_chat_draft_context
        from social_hook.db import get_draft, update_draft
        from social_hook.db import operations as ops

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return

        set_chat_draft_context(chat_id, draft_id, draft.project_id)

        if draft.status != "approved":
            _send(adapter, chat_id, f"Cannot unapprove: status is '{draft.status}'")
            return

        update_draft(conn, draft_id, status="draft")
        ops.emit_data_event(conn, "draft", "unapproved", draft_id, draft.project_id)
        _clear_original_buttons(adapter, chat_id, kwargs.get("message_id"), draft_id, "unapproved")
        _send(adapter, chat_id, f"Draft `{draft_id[:12]}` approval reverted — back to draft.")
        if config:
            from social_hook.notifications import broadcast_notification

            broadcast_notification(
                config,
                OutboundMessage(
                    text=f"Draft `{draft_id[:12]}` approval reverted ({draft.platform})"
                ),
                exclude_chat=chat_id,
            )
    finally:
        conn.close()


def btn_unschedule(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Handle unschedule button press — revert scheduled draft back to draft."""
    _answer_callback(adapter, callback_id, "Unscheduling...")

    conn = _get_conn()
    try:
        from social_hook.bot.commands import set_chat_draft_context
        from social_hook.db import get_draft, update_draft
        from social_hook.db import operations as ops

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return

        set_chat_draft_context(chat_id, draft_id, draft.project_id)

        if draft.status != "scheduled":
            _send(adapter, chat_id, f"Cannot unschedule: status is '{draft.status}'")
            return

        update_draft(conn, draft_id, status="draft", scheduled_time="")
        ops.emit_data_event(conn, "draft", "unscheduled", draft_id, draft.project_id)
        _clear_original_buttons(adapter, chat_id, kwargs.get("message_id"), draft_id, "unscheduled")
        _send(adapter, chat_id, f"Draft `{draft_id[:12]}` unscheduled — back to draft.")
        if config:
            from social_hook.notifications import broadcast_notification

            broadcast_notification(
                config,
                OutboundMessage(text=f"Draft `{draft_id[:12]}` unscheduled ({draft.platform})"),
                exclude_chat=chat_id,
            )
    finally:
        conn.close()


def btn_reopen(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Handle reopen button press — reopen cancelled/rejected draft back to draft."""
    _answer_callback(adapter, callback_id, "Reopening...")

    conn = _get_conn()
    try:
        from social_hook.bot.commands import set_chat_draft_context
        from social_hook.db import get_draft, update_draft
        from social_hook.db import operations as ops

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return

        set_chat_draft_context(chat_id, draft_id, draft.project_id)

        if draft.status not in ("cancelled", "rejected"):
            _send(adapter, chat_id, f"Cannot reopen: status is '{draft.status}'")
            return

        if getattr(draft, "is_intro", False):
            _send(adapter, chat_id, "Intro drafts cannot be reopened — create a new draft instead.")
            return

        update_draft(conn, draft_id, status="draft", last_error="")
        ops.emit_data_event(conn, "draft", "reopened", draft_id, draft.project_id)
        _clear_original_buttons(adapter, chat_id, kwargs.get("message_id"), draft_id, "reopened")
        _send(adapter, chat_id, f"Draft `{draft_id[:12]}` reopened.")
        if config:
            from social_hook.notifications import broadcast_notification

            broadcast_notification(
                config,
                OutboundMessage(text=f"Draft `{draft_id[:12]}` reopened ({draft.platform})"),
                exclude_chat=chat_id,
            )
    finally:
        conn.close()


def btn_review(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Show full draft review via button callback."""
    _answer_callback(adapter, callback_id)

    from social_hook.bot.commands import cmd_review

    cmd_review(adapter, chat_id, draft_id, config)


def btn_promote_submenu(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Show platform selection for promoting a preview draft."""
    _answer_callback(adapter, callback_id)

    conn = _get_conn()
    try:
        from social_hook.db import get_draft

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return
        if not draft.preview_mode:
            _send(adapter, chat_id, "Only preview-mode drafts can be promoted.")
            return
        if draft.status in TERMINAL_STATUSES:
            _send(adapter, chat_id, f"Cannot promote: draft status is '{draft.status}'")
            return
    finally:
        conn.close()

    if not config:
        _send(adapter, chat_id, "Config not available.")
        return

    real_platforms = [name for name, pcfg in config.platforms.items() if pcfg.enabled]

    if not real_platforms:
        _send(
            adapter,
            chat_id,
            "No platforms are enabled yet. Enable a platform in Settings → Platforms first, "
            "then come back to promote this draft.",
        )
        return

    buttons = [
        ButtonRow(
            buttons=[
                Button(label=f"→ {p}", action="promote_to", payload=f"{draft_id}:{p}")
                for p in real_platforms
            ]
        )
    ]
    _send_with_buttons(adapter, chat_id, f"Promote `{draft_id[:12]}` to:", buttons)


def btn_promote_to(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    payload: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Execute promote: redraft a preview draft for a specific platform."""
    _answer_callback(adapter, callback_id, "Promoting...")

    # Parse compound payload: "draft_id:platform"
    parts = payload.split(":", 1)
    if len(parts) != 2:
        _send(adapter, chat_id, "Invalid promote payload.")
        return
    draft_id, platform = parts

    conn = _get_conn()
    try:
        from social_hook.db import get_draft
        from social_hook.db import operations as ops

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return
        if not draft.preview_mode:
            _send(adapter, chat_id, "Only preview-mode drafts can be promoted.")
            return
        if draft.status in TERMINAL_STATUSES:
            _send(adapter, chat_id, f"Cannot promote: draft status is '{draft.status}'")
            return

        if not config:
            _send(adapter, chat_id, "Config not available.")
            return

        pcfg = config.platforms.get(platform)
        if not pcfg or not pcfg.enabled:
            _send(adapter, chat_id, f"Platform '{platform}' is not enabled.")
            return

        decision = ops.get_decision(conn, draft.decision_id)
        if not decision:
            _send(adapter, chat_id, "Decision not found.")
            return

        project = ops.get_project(conn, decision.project_id)
        if not project:
            _send(adapter, chat_id, "Project not found.")
            return

        from social_hook.config.project import ProjectConfig, load_project_config
        from social_hook.drafting import draft as run_draft
        from social_hook.drafting_intents import intent_from_decision
        from social_hook.errors import ConfigError
        from social_hook.llm.dry_run import DryRunContext
        from social_hook.llm.prompts import assemble_evaluator_context
        from social_hook.models.core import CommitInfo

        try:
            project_config = load_project_config(project.repo_path)
        except ConfigError:
            project_config = ProjectConfig(repo_path=project.repo_path)

        from social_hook.trigger import parse_commit_info

        try:
            commit = parse_commit_info(decision.commit_hash, project.repo_path)
        except Exception:
            commit = CommitInfo(
                hash=decision.commit_hash,
                message=decision.commit_message or "",
                diff="",
                files_changed=[],
            )

        db = DryRunContext(conn, dry_run=False)
        context = assemble_evaluator_context(
            db,
            project.id,
            project_config,
            commit_timestamp=getattr(commit, "timestamp", None),
            parent_timestamp=getattr(commit, "parent_timestamp", None),
        )

        intent = intent_from_decision(decision, config, conn, target_platform=platform)

        results = run_draft(
            intent,
            config,
            conn,
            db,
            project,
            context,
            commit,
            project_config=project_config,
        )

        if not results:
            _send(adapter, chat_id, "No draft created during promote.")
            return

        new_draft = results[0].draft
        ops.supersede_draft(conn, draft_id, new_draft.id)
        ops.emit_data_event(conn, "draft", "updated", draft_id, draft.project_id)

        # Send review with buttons for the new draft
        from social_hook.bot.notifications import get_review_buttons_normalized

        buttons = get_review_buttons_normalized(
            new_draft.id, platform=new_draft.platform, preview_mode=new_draft.preview_mode
        )
        _send_with_buttons(
            adapter,
            chat_id,
            f"Preview draft promoted to {platform}.\n\n"
            f"New draft: `{new_draft.id[:12]}`\n\n"
            f"```\n{new_draft.content[:500]}\n```",
            buttons,
        )
    except Exception as e:
        logger.exception("Error promoting draft")
        _send(adapter, chat_id, f"Error promoting draft: {e}")
    finally:
        conn.close()


# =============================================================================
# Cycle-level callback handlers
# =============================================================================


def handle_cycle_expand(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    payload: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Expand all drafts in a cycle. Payload is cycle_id."""
    _answer_callback(adapter, callback_id, "Expanding...")

    cycle_id = payload
    conn = _get_conn()
    try:
        from social_hook.db import operations as ops

        drafts = ops.get_drafts_by_cycle(conn, cycle_id)
        if not drafts:
            _send(adapter, chat_id, f"No drafts found for cycle `{cycle_id[:12]}`.")
            return

        lines = [f"*Cycle* `{cycle_id[:12]}` — {len(drafts)} draft(s)"]
        for draft in drafts:
            strategy = getattr(draft, "strategy", None) or draft.platform
            lines.append(f"\n*{strategy}* (`{draft.id[:12]}`) — {draft.status}")
            lines.append(f"```\n{draft.content}\n```")
        _send(adapter, chat_id, "\n".join(lines))
    finally:
        conn.close()


def handle_cycle_approve(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    payload: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Approve all editable drafts in a cycle. Payload is cycle_id."""
    _answer_callback(adapter, callback_id, "Approving all...")

    cycle_id = payload
    conn = _get_conn()
    try:
        from social_hook.db import operations as ops

        drafts = ops.get_drafts_by_cycle(conn, cycle_id)
        if not drafts:
            _send(adapter, chat_id, f"No drafts found for cycle `{cycle_id[:12]}`.")
            return

        from social_hook.vehicle import check_auto_postable, handle_advisory_approval

        approved = advisory = already = terminal = 0
        for draft in drafts:
            if draft.status in EDITABLE_STATUSES:
                if not check_auto_postable(draft):
                    handle_advisory_approval(conn, draft, config)
                    advisory += 1
                else:
                    ops.update_draft(conn, draft.id, status="approved")
                    ops.emit_data_event(conn, "draft", "approved", draft.id, draft.project_id)
                    approved += 1
            elif draft.status in TERMINAL_STATUSES:
                terminal += 1
            else:
                already += 1  # approved, scheduled — already processed

        parts = [f"Approved {approved}."]
        if advisory:
            parts.append(f"Advisory: {advisory}.")
        if already:
            parts.append(f"Already processed: {already}.")
        if terminal:
            parts.append(f"Skipped (terminal): {terminal}.")
        _send(adapter, chat_id, " ".join(parts))
    finally:
        conn.close()


def handle_cycle_view(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    payload: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """View a single draft from a cycle. Payload is 'cycle_id:draft_id'."""
    _answer_callback(adapter, callback_id, "Loading...")

    parts = payload.split(":", 1)
    if len(parts) != 2:
        _send(adapter, chat_id, "Invalid cycle view payload.")
        return
    _cycle_id, draft_id = parts

    conn = _get_conn()
    try:
        from social_hook.bot.notifications import get_review_buttons_normalized
        from social_hook.db import operations as ops

        draft = ops.get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id[:12]}` not found.")
            return

        strategy = getattr(draft, "strategy", None) or draft.platform
        text = f"*{strategy}* — `{draft.id[:12]}` ({draft.status})\n\n```\n{draft.content}\n```"
        buttons = get_review_buttons_normalized(
            draft.id, platform=draft.platform, preview_mode=draft.preview_mode
        )
        _send_with_buttons(adapter, chat_id, text, buttons)
    finally:
        conn.close()


def handle_arc_approve(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    payload: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Approve a proposed arc. Payload is arc_id."""
    arc_id = payload
    conn = _get_conn()
    try:
        from social_hook.db import operations as ops

        updated = ops.update_arc(conn, arc_id, status="active")
        if updated:
            _answer_callback(adapter, callback_id, "Arc approved")
            _send(adapter, chat_id, f"Arc `{arc_id[:12]}` approved.")
        else:
            _answer_callback(adapter, callback_id, "Arc not found")
            _send(adapter, chat_id, f"Arc `{arc_id[:12]}` not found.")
    finally:
        conn.close()


def handle_arc_dismiss(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    payload: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Dismiss a proposed arc. Payload is arc_id."""
    arc_id = payload
    conn = _get_conn()
    try:
        from social_hook.db import operations as ops

        updated = ops.update_arc(conn, arc_id, status="abandoned")
        if updated:
            _answer_callback(adapter, callback_id, "Arc dismissed")
            _send(adapter, chat_id, f"Arc `{arc_id[:12]}` dismissed.")
        else:
            _answer_callback(adapter, callback_id, "Arc not found")
            _send(adapter, chat_id, f"Arc `{arc_id[:12]}` not found.")
    finally:
        conn.close()
