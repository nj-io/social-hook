"""Inline button callback handlers for Telegram bot."""

import logging
import time
from typing import Any

from social_hook.messaging.base import (
    Button,
    ButtonRow,
    CallbackEvent,
    MessagingAdapter,
    OutboundMessage,
)

logger = logging.getLogger(__name__)

# Pending edit state: chat_id → (draft_id, timestamp)
_pending_edits: dict[str, tuple[str, float]] = {}
_EDIT_TTL_SECONDS = 300  # 5 minutes


def get_pending_edit(chat_id: str) -> str | None:
    """Check for a pending edit without consuming it.

    Returns draft_id if a non-expired pending edit exists, else None.
    """
    entry = _pending_edits.get(chat_id)
    if entry is None:
        return None
    draft_id, ts = entry
    if time.time() - ts > _EDIT_TTL_SECONDS:
        del _pending_edits[chat_id]
        return None
    return draft_id


def clear_pending_edit(chat_id: str) -> None:
    """Remove pending edit after successful save."""
    _pending_edits.pop(chat_id, None)


def _get_conn():
    """Get a fresh DB connection (per-request pattern)."""
    from social_hook.db import init_database
    from social_hook.filesystem import get_db_path

    return init_database(get_db_path())


def _send(adapter: MessagingAdapter, chat_id: str, text: str) -> bool:
    """Send a message via adapter."""
    result = adapter.send_message(chat_id, OutboundMessage(text=text))
    return result.success


def _answer_callback(adapter: MessagingAdapter, callback_id: str, text: str = "") -> bool:
    """Answer a callback query via adapter."""
    return adapter.answer_callback(callback_id, text)


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
        "media_remove": btn_media_remove,
        "edit_angle": btn_edit_angle,
        "reject": btn_reject_submenu,
        "reject_now": btn_reject,
        "reject_note": btn_reject_note,
        "cancel": btn_cancel,
        "review": btn_review,
    }

    handler = handlers.get(action)
    if handler:
        handler(adapter, chat_id, callback_id, payload, config, **kwargs)
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

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return

        set_chat_draft_context(chat_id, draft_id, draft.project_id)

        if draft.status not in ("draft", "approved"):
            _send(adapter, chat_id, f"Cannot approve draft with status: {draft.status}")
            return

        update_draft(conn, draft_id, status="approved")
        _send(adapter, chat_id, f"Draft `{draft_id[:12]}` approved and ready for posting.")
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
        _send(
            adapter,
            chat_id,
            f"Draft `{draft_id[:12]}` scheduled for {scheduled_str}\n{result.time_reason}",
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

        # Warn if overwriting a different pending edit
        existing = get_pending_edit(chat_id)
        if existing and existing != draft_id:
            _send(
                adapter,
                chat_id,
                f"Switching edit to `{draft_id[:12]}` (edit for `{existing[:12]}` cancelled).",
            )

        _pending_edits[chat_id] = (draft_id, time.time())

        _send(
            adapter,
            chat_id,
            f"*Current content for* `{draft_id[:12]}`:\n\n"
            f"```\n{draft.content[:500]}\n```\n\n"
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

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return

        set_chat_draft_context(chat_id, draft_id, draft.project_id)

        update_draft(conn, draft_id, status="rejected")

        # Cascade re-draft if this was an intro draft
        from social_hook.intro_lifecycle import on_intro_rejected

        cascade_msg = on_intro_rejected(conn, draft, draft.project_id, verbose=False)

        reject_msg = f"Draft `{draft_id[:12]}` rejected."
        if cascade_msg:
            reject_msg += f"\n{cascade_msg}"
        _send(adapter, chat_id, reject_msg)
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
        from social_hook.scheduling import calculate_optimal_time

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return

        set_chat_draft_context(chat_id, draft_id, draft.project_id)

        if draft.status not in ("draft", "approved"):
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
        _send(
            adapter,
            chat_id,
            f"Draft `{draft_id[:12]}` approved and scheduled for {scheduled_str}",
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
    adapter.send_message(
        chat_id,
        OutboundMessage(
            text=f"Schedule `{draft_id[:12]}`:",
            buttons=buttons,
        ),
    )


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
    _send(
        adapter,
        chat_id,
        f"Reply with desired time for `{draft_id[:12]}`\n"
        f"(e.g., '2pm', 'tomorrow 9am', '2026-02-15T14:00:00')",
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

    buttons = [
        ButtonRow(
            buttons=[
                Button(label="Change text", action="edit_text", payload=draft_id),
                Button(label="Change media", action="edit_media", payload=draft_id),
            ]
        ),
        ButtonRow(
            buttons=[
                Button(label="Change angle", action="edit_angle", payload=draft_id),
            ]
        ),
    ]
    adapter.send_message(
        chat_id,
        OutboundMessage(
            text=f"Edit `{draft_id[:12]}`:",
            buttons=buttons,
        ),
    )


def btn_edit_media(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Show current media and action buttons (regenerate/remove)."""
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

        if draft.media_paths:
            # Send current media via adapter
            caps = adapter.get_capabilities()
            if caps.supports_media:
                for path in draft.media_paths:
                    adapter.send_media(
                        chat_id,
                        path,
                        caption=f"Current media for `{draft_id[:12]}`",
                    )
            # Show action buttons
            buttons = [
                ButtonRow(
                    buttons=[
                        Button(label="Regenerate", action="media_regen", payload=draft_id),
                        Button(label="Remove media", action="media_remove", payload=draft_id),
                    ]
                ),
            ]
            adapter.send_message(
                chat_id,
                OutboundMessage(
                    text=f"Media for `{draft_id[:12]}` ({draft.media_type or 'unknown'}):",
                    buttons=buttons,
                ),
            )
        else:
            _send(adapter, chat_id, f"No media attached to `{draft_id[:12]}`.")
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
            update_draft(conn, draft_id, media_paths=[result.file_path])

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
                adapter.send_media(
                    chat_id,
                    result.file_path,
                    caption=f"Regenerated media for `{draft_id[:12]}`",
                )
            _send(adapter, chat_id, "Media regenerated.")
        else:
            _send(adapter, chat_id, f"Regeneration failed: {result.error}")
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
        old_paths = draft.media_paths if draft else []

        update_draft(conn, draft_id, media_paths=[])

        if draft:
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
    _send(adapter, chat_id, f"Reply with new angle for `{draft_id[:12]}`")


def btn_reject_submenu(
    adapter: MessagingAdapter,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Any | None,
    **kwargs: Any,
) -> None:
    """Show reject submenu with just reject/reject with note."""
    _answer_callback(adapter, callback_id)

    buttons = [
        ButtonRow(
            buttons=[
                Button(label="Just reject", action="reject_now", payload=draft_id),
                Button(label="Reject with note", action="reject_note", payload=draft_id),
            ]
        ),
    ]
    adapter.send_message(
        chat_id,
        OutboundMessage(
            text=f"Reject `{draft_id[:12]}`:",
            buttons=buttons,
        ),
    )


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
    _send(adapter, chat_id, f"Reply with rejection reason for `{draft_id[:12]}`")


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

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return

        set_chat_draft_context(chat_id, draft_id, draft.project_id)

        update_draft(conn, draft_id, status="cancelled")
        _send(adapter, chat_id, f"Draft `{draft_id[:12]}` cancelled.")
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
