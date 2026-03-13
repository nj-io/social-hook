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
    if draft.status not in ("draft", "deferred"):
        _send(adapter, chat_id, f"Cannot edit media — draft is {draft.status}.")
        return False
    return True


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

    handlers = {
        "approve": btn_approve,
        "quick_approve": btn_quick_approve,
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
        "review": btn_review,
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

        if draft.status not in ("draft", "approved", "deferred"):
            _send(adapter, chat_id, f"Cannot approve draft with status: {draft.status}")
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
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Show current media and action buttons, or offer to add media if none exists."""
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

        if draft.media_paths:
            # Send current media via adapter
            caps = adapter.get_capabilities()
            if caps.supports_media:
                for path in draft.media_paths:
                    _send_media(
                        adapter,
                        chat_id,
                        path,
                        caption=f"Current media for `{draft_id[:12]}`",
                    )
            # Show action buttons including switch tool
            buttons = [
                ButtonRow(
                    buttons=[
                        Button(label="Regenerate", action="media_regen", payload=draft_id),
                        Button(label="Retry", action="media_retry", payload=draft_id),
                    ]
                ),
                ButtonRow(
                    buttons=[
                        Button(label="Switch tool", action="media_pick_tool", payload=draft_id),
                        Button(label="Remove media", action="media_remove", payload=draft_id),
                    ]
                ),
            ]
            _send_with_buttons(
                adapter,
                chat_id,
                f"Media for `{draft_id[:12]}` ({draft.media_type or 'unknown'}):",
                buttons,
            )
        else:
            # No media — offer to add
            buttons = [
                ButtonRow(
                    buttons=[
                        Button(label="Add media", action="media_pick_tool", payload=draft_id),
                        Button(label="Upload file", action="media_upload", payload=draft_id),
                    ]
                ),
            ]
            _send_with_buttons(
                adapter,
                chat_id,
                f"No media on `{draft_id[:12]}`. Add some?",
                buttons,
            )
    finally:
        conn.close()


def btn_media_regen(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Regenerate media using the stored media_spec."""
    _answer_callback(adapter, callback_id, "Regenerating...")
    conn = _get_conn()
    try:
        import json

        from social_hook.adapters.registry import get_media_adapter
        from social_hook.db import get_draft, update_draft
        from social_hook.db.operations import insert_draft_change
        from social_hook.filesystem import generate_id, get_base_path
        from social_hook.models import DraftChange

        draft = get_draft(conn, draft_id)
        if not draft or not draft.media_type or not draft.media_spec:
            _send(adapter, chat_id, "No media spec available for regeneration.")
            return

        if not _guard_draft_editable(adapter, chat_id, draft):
            return

        # Guard: refuse if spec unchanged since last generation
        if draft.media_spec == draft.media_spec_used:
            _send(
                adapter, chat_id, "Media spec unchanged — edit the spec first before regenerating."
            )
            return

        api_key = None
        if draft.media_type == "nano_banana_pro":
            api_key = config.env.get("GEMINI_API_KEY") if config else None
            if not api_key:
                _send(
                    adapter,
                    chat_id,
                    "Cannot regenerate: GEMINI_API_KEY not configured.",
                )
                return

        try:
            media_adapter = get_media_adapter(draft.media_type, api_key=api_key)
        except ValueError as e:
            _send(adapter, chat_id, f"Media adapter error: {e}")
            return
        if not media_adapter:
            _send(
                adapter,
                chat_id,
                f"Media adapter '{draft.media_type}' not available.",
            )
            return

        output_dir = str(get_base_path() / "media-cache" / draft_id)
        result = media_adapter.generate(spec=draft.media_spec, output_dir=output_dir)

        if result.success and result.file_path:
            old_paths = draft.media_paths
            update_draft(
                conn,
                draft_id,
                media_paths=[result.file_path],
                media_spec_used=draft.media_spec,
                last_error="",
            )

            insert_draft_change(
                conn,
                DraftChange(
                    id=generate_id("change"),
                    draft_id=draft_id,
                    field="media_paths",
                    old_value=json.dumps(old_paths),
                    new_value=json.dumps([result.file_path]),
                    changed_by="human",
                ),
            )

            caps = adapter.get_capabilities()
            if caps.supports_media:
                _send_media(
                    adapter,
                    chat_id,
                    result.file_path,
                    caption=f"Regenerated media for `{draft_id[:12]}`",
                )
            _send(adapter, chat_id, "Media regenerated.")
        else:
            _send(adapter, chat_id, f"Regeneration failed: {result.error}")
    finally:
        conn.close()


def btn_media_retry(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Retry media generation without requiring spec changes (bypasses spec==spec_used guard)."""
    _answer_callback(adapter, callback_id, "Retrying media generation...")
    conn = _get_conn()
    try:
        import json

        from social_hook.adapters.registry import get_media_adapter
        from social_hook.db import get_draft, update_draft
        from social_hook.db.operations import insert_draft_change
        from social_hook.filesystem import generate_id, get_base_path
        from social_hook.models import DraftChange

        draft = get_draft(conn, draft_id)
        if not draft or not draft.media_type or not draft.media_spec:
            _send(adapter, chat_id, "No media spec available for retry.")
            return

        if not _guard_draft_editable(adapter, chat_id, draft):
            return

        api_key = None
        if draft.media_type == "nano_banana_pro":
            api_key = config.env.get("GEMINI_API_KEY") if config else None
            if not api_key:
                _send(
                    adapter,
                    chat_id,
                    "Cannot retry: GEMINI_API_KEY not configured.",
                )
                return

        try:
            media_adapter = get_media_adapter(draft.media_type, api_key=api_key)
        except ValueError as e:
            _send(adapter, chat_id, f"Media adapter error: {e}")
            return
        if not media_adapter:
            _send(
                adapter,
                chat_id,
                f"Media adapter '{draft.media_type}' not available.",
            )
            return

        output_dir = str(get_base_path() / "media-cache" / draft_id)
        result = media_adapter.generate(spec=draft.media_spec, output_dir=output_dir)

        if result.success and result.file_path:
            old_paths = draft.media_paths
            update_draft(
                conn,
                draft_id,
                media_paths=[result.file_path],
                media_spec_used=draft.media_spec,
                last_error="",
            )

            insert_draft_change(
                conn,
                DraftChange(
                    id=generate_id("change"),
                    draft_id=draft_id,
                    field="media_paths",
                    old_value=json.dumps(old_paths),
                    new_value=json.dumps([result.file_path]),
                    changed_by="human",
                ),
            )

            caps = adapter.get_capabilities()
            if caps.supports_media:
                _send_media(
                    adapter,
                    chat_id,
                    result.file_path,
                    caption=f"Retried media for `{draft_id[:12]}`",
                )
            _send(adapter, chat_id, "Media retry succeeded.")
        else:
            _send(adapter, chat_id, f"Media retry failed: {result.error}")
    finally:
        conn.close()


def btn_media_remove(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Remove media from a draft."""
    _answer_callback(adapter, callback_id, "Removing...")
    conn = _get_conn()
    try:
        import json

        from social_hook.db import get_draft, update_draft
        from social_hook.db.operations import insert_draft_change
        from social_hook.filesystem import generate_id
        from social_hook.models import DraftChange

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return
        if not _guard_draft_editable(adapter, chat_id, draft):
            return

        old_paths = draft.media_paths

        update_draft(conn, draft_id, media_paths=[])

        insert_draft_change(
            conn,
            DraftChange(
                id=generate_id("change"),
                draft_id=draft_id,
                field="media_paths",
                old_value=json.dumps(old_paths),
                new_value="[]",
                changed_by="human",
            ),
        )

        _send(adapter, chat_id, f"Media removed from `{draft_id[:12]}`.")
    finally:
        conn.close()


def btn_media_pick_tool(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Show buttons for each available media tool."""
    _answer_callback(adapter, callback_id)

    from social_hook.adapters.registry import list_available_tools

    tools = list_available_tools()
    rows = []
    for tool in tools:
        # payload encodes both draft_id and tool name
        payload = f"{draft_id}|{tool['name']}"
        rows.append(
            ButtonRow(
                buttons=[
                    Button(
                        label=tool["display_name"],
                        action="media_gen_spec",
                        payload=payload,
                    )
                ]
            )
        )

    _send_with_buttons(adapter, chat_id, f"Pick a media tool for `{draft_id[:12]}`:", rows)


def btn_media_gen_spec(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """User picked a tool — generate spec from draft content or prompt for manual entry."""
    _answer_callback(adapter, callback_id, "Generating spec...")

    parts = draft_id.split("|", 1)
    if len(parts) != 2:
        _send(adapter, chat_id, "Invalid tool selection.")
        return

    draft_id, tool_name = parts

    conn = _get_conn()
    try:
        from social_hook.adapters.registry import get_tool_spec_schema
        from social_hook.db import get_draft, update_draft

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return

        if not _guard_draft_editable(adapter, chat_id, draft):
            return

        # Update the draft's media_type to the new tool
        update_draft(conn, draft_id, media_type=tool_name)

        # Try LLM-assisted spec generation
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
                response = client.complete(
                    messages=[{"role": "user", "content": prompt}],
                    tools=[spec_tool],
                )
                spec = extract_tool_call(response, "generate_media_spec")
        except Exception:
            logger.debug("LLM spec generation failed, falling back to manual", exc_info=True)

        if spec:
            import json

            # Show generated spec and ask for confirmation
            update_draft(conn, draft_id, media_spec=spec)
            spec_display = json.dumps(spec, indent=2)
            buttons = [
                ButtonRow(
                    buttons=[
                        Button(
                            label="Generate media",
                            action="media_confirm_gen",
                            payload=draft_id,
                        ),
                    ]
                ),
            ]
            _send_with_buttons(
                adapter,
                chat_id,
                f"Generated spec for `{draft_id[:12]}` ({tool_name}):\n"
                f"```json\n{spec_display}\n```\n"
                f"Confirm to generate, or reply with edited JSON.",
                buttons,
            )
            # Register pending reply so user can edit the spec inline
            _pending_replies[chat_id] = PendingReply(
                type="edit_media_spec", draft_id=draft_id, timestamp=time.time()
            )
        else:
            # Manual spec entry — show schema and prompt
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
                f"Tool: {tool_name}\nSpec fields:\n{schema_text}\n\n"
                f"Reply with JSON spec, e.g.:\n"
                f'```json\n{{"key": "value"}}\n```',
            )
            _pending_replies[chat_id] = PendingReply(
                type="edit_media_spec", draft_id=draft_id, timestamp=time.time()
            )
    finally:
        conn.close()


def btn_media_confirm_gen(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Confirm and generate media using the current spec on the draft."""
    _answer_callback(adapter, callback_id, "Generating media...")

    # Clear any pending spec-edit reply since user confirmed via button
    _pending_replies.pop(chat_id, None)

    conn = _get_conn()
    try:
        import json

        from social_hook.adapters.registry import get_media_adapter
        from social_hook.db import get_draft, update_draft
        from social_hook.db.operations import insert_draft_change
        from social_hook.filesystem import generate_id, get_base_path
        from social_hook.models import DraftChange

        draft = get_draft(conn, draft_id)
        if not draft or not draft.media_type or not draft.media_spec:
            _send(adapter, chat_id, "No media spec configured. Pick a tool first.")
            return

        if not _guard_draft_editable(adapter, chat_id, draft):
            return

        api_key = None
        if draft.media_type == "nano_banana_pro":
            api_key = config.env.get("GEMINI_API_KEY") if config else None
            if not api_key:
                _send(adapter, chat_id, "Cannot generate: GEMINI_API_KEY not configured.")
                return

        try:
            media_adapter = get_media_adapter(draft.media_type, api_key=api_key)
        except ValueError as e:
            _send(adapter, chat_id, f"Media adapter error: {e}")
            return
        if not media_adapter:
            _send(adapter, chat_id, f"Media adapter '{draft.media_type}' not available.")
            return

        output_dir = str(get_base_path() / "media-cache" / draft_id)
        result = media_adapter.generate(spec=draft.media_spec, output_dir=output_dir)

        if result.success and result.file_path:
            old_paths = draft.media_paths
            update_draft(
                conn,
                draft_id,
                media_paths=[result.file_path],
                media_spec_used=draft.media_spec,
                last_error="",
            )

            insert_draft_change(
                conn,
                DraftChange(
                    id=generate_id("change"),
                    draft_id=draft_id,
                    field="media_paths",
                    old_value=json.dumps(old_paths),
                    new_value=json.dumps([result.file_path]),
                    changed_by="human",
                ),
            )

            caps = adapter.get_capabilities()
            if caps.supports_media:
                _send_media(
                    adapter,
                    chat_id,
                    result.file_path,
                    caption=f"Generated media for `{draft_id[:12]}`",
                )
            _send(adapter, chat_id, "Media generated successfully.")
            _offer_sibling_sync(adapter, chat_id, conn, draft_id)
        else:
            _send(adapter, chat_id, f"Media generation failed: {result.error}")
    finally:
        conn.close()


def _offer_sibling_sync(adapter, chat_id, conn, draft_id):
    """If draft has sister drafts, offer to sync media to them."""
    from social_hook.db.operations import get_sister_drafts

    sisters = get_sister_drafts(conn, draft_id)
    editable = [s for s in sisters if s.status in ("draft", "deferred")]
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
            adapter,
            chat_id,
            f"Sister drafts found ({platforms}). Sync media?",
            buttons,
        )


def btn_media_upload(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Set up pending reply for user to send a media file."""
    _answer_callback(adapter, callback_id)

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
        f"Send a media file (image/photo) to attach to `{draft_id[:12]}`.",
    )


def btn_media_preview(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Show a text preview of what the current media spec will generate."""
    _answer_callback(adapter, callback_id)
    conn = _get_conn()
    try:
        from social_hook.adapters.registry import get_media_adapter
        from social_hook.db import get_draft

        draft = get_draft(conn, draft_id)
        if not draft or not draft.media_type or not draft.media_spec:
            _send(adapter, chat_id, "No media spec to preview.")
            return

        # Use the adapter's preview_text method
        try:
            media_adapter = get_media_adapter(draft.media_type)
        except (ValueError, Exception):
            media_adapter = None

        if media_adapter:
            preview = media_adapter.preview_text(draft.media_spec)
        else:
            import json

            preview = json.dumps(draft.media_spec, indent=2)

        _send(
            adapter,
            chat_id,
            f"Preview for `{draft_id[:12]}` ({draft.media_type}):\n```\n{preview}\n```",
        )
    finally:
        conn.close()


def btn_media_sync_siblings(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Sync media from this draft to its sister drafts (same decision_id)."""
    _answer_callback(adapter, callback_id, "Syncing...")
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

        # Only sync to editable sisters
        editable = [s for s in sisters if s.status in ("draft", "deferred")]
        if not editable:
            _send(adapter, chat_id, "No editable sister drafts to sync to.")
            return

        count = sync_media_to_drafts(conn, draft_id, [s.id for s in editable])
        platforms = ", ".join(s.platform for s in editable)
        _send(
            adapter,
            chat_id,
            f"Synced media to {count} sister draft(s): {platforms}.",
        )
    finally:
        conn.close()


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
