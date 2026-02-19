"""Inline button callback handlers for Telegram bot."""

import logging
import time
from typing import Any, Optional

from social_hook.bot.notifications import send_notification, send_notification_with_buttons

logger = logging.getLogger(__name__)

# Pending edit state: chat_id → (draft_id, timestamp)
_pending_edits: dict[str, tuple[str, float]] = {}
_EDIT_TTL_SECONDS = 300  # 5 minutes


def get_pending_edit(chat_id: str) -> Optional[str]:
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


# Messaging adapter bridge: when set, _send() and _answer_callback() use adapter
_active_adapter: Optional[Any] = None


def set_adapter(adapter) -> None:
    """Set the active messaging adapter. Called by create_bot()."""
    global _active_adapter
    _active_adapter = adapter


def _get_conn():
    """Get a fresh DB connection (per-request pattern)."""
    from social_hook.db import init_database
    from social_hook.filesystem import get_db_path

    return init_database(get_db_path())


def _send(token: str, chat_id: str, text: str) -> bool:
    """Send a message. Uses adapter if available, falls back to direct HTTP."""
    if _active_adapter:
        from social_hook.bot.notifications import send_via_adapter

        return send_via_adapter(_active_adapter, chat_id, text)
    return send_notification(token, chat_id, text)


def _answer_callback(token: str, callback_query_id: str, text: str = "") -> bool:
    """Answer a callback query. Uses adapter if available, falls back to HTTP."""
    if _active_adapter:
        return _active_adapter.answer_callback(callback_query_id, text)

    import requests

    try:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        response = requests.post(
            f"https://api.telegram.org/bot{token}/answerCallbackQuery",
            json=payload,
            timeout=10,
        )
        return response.status_code == 200
    except requests.RequestException:
        return False


def handle_callback(callback: dict, token: str, config: Optional[Any] = None) -> None:
    """Route a callback query to the appropriate handler.

    Callback data format: "action:draft_id" or "action:draft_id:extra"

    Args:
        callback: Telegram callback_query dict
        token: Bot API token
        config: Full Config object
    """
    callback_id = callback.get("id", "")
    data = callback.get("data", "")
    message = callback.get("message", {})
    chat_id = str(message.get("chat", {}).get("id", ""))

    if not data or not chat_id:
        _answer_callback(token, callback_id, "Invalid callback")
        return

    parts = data.split(":", 1)
    action = parts[0]
    payload = parts[1] if len(parts) > 1 else ""

    handlers = {
        "approve": btn_approve,
        "quick_approve": btn_quick_approve,
        "schedule": btn_schedule_submenu,
        "schedule_optimal": btn_schedule_optimal,
        "schedule_custom": btn_schedule_custom,
        "edit": btn_edit_submenu,
        "edit_text": btn_edit_text,
        "edit_media": btn_edit_media,
        "edit_angle": btn_edit_angle,
        "reject": btn_reject_submenu,
        "reject_now": btn_reject,
        "reject_note": btn_reject_note,
        "cancel": btn_cancel,
        "review": btn_review,
    }

    handler = handlers.get(action)
    if handler:
        handler(token, chat_id, callback_id, payload, config)
    else:
        _answer_callback(token, callback_id, f"Unknown action: {action}")


def btn_approve(
    token: str,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Optional[Any],
) -> None:
    """Handle approve button press."""
    _answer_callback(token, callback_id, "Approving...")

    conn = _get_conn()
    try:
        from social_hook.bot.commands import set_chat_draft_context
        from social_hook.db import get_draft, update_draft

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(token, chat_id, f"Draft `{draft_id}` not found.")
            return

        set_chat_draft_context(chat_id, draft_id, draft.project_id)

        if draft.status not in ("draft", "approved"):
            _send(token, chat_id, f"Cannot approve draft with status: {draft.status}")
            return

        update_draft(conn, draft_id, status="approved")
        _send(token, chat_id, f"Draft `{draft_id[:12]}` approved and ready for posting.")
    finally:
        conn.close()


def btn_schedule_optimal(
    token: str,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Optional[Any],
) -> None:
    """Handle schedule (optimal time) button press."""
    _answer_callback(token, callback_id, "Calculating optimal time...")

    conn = _get_conn()
    try:
        from social_hook.bot.commands import set_chat_draft_context
        from social_hook.db import get_draft, update_draft
        from social_hook.scheduling import calculate_optimal_time

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(token, chat_id, f"Draft `{draft_id}` not found.")
            return

        set_chat_draft_context(chat_id, draft_id, draft.project_id)

        result = calculate_optimal_time(
            conn,
            draft.project_id,
            tz=config.scheduling.timezone if config else "UTC",
            max_posts_per_day=config.scheduling.max_posts_per_day if config else 3,
            min_gap_minutes=config.scheduling.min_gap_minutes if config else 30,
            optimal_days=config.scheduling.optimal_days if config else None,
            optimal_hours=config.scheduling.optimal_hours if config else None,
        )
        scheduled_str = result.datetime.isoformat()
        update_draft(conn, draft_id, status="scheduled", scheduled_time=scheduled_str)
        _send(
            token,
            chat_id,
            f"Draft `{draft_id[:12]}` scheduled for {scheduled_str}\n{result.time_reason}",
        )
    finally:
        conn.close()


def btn_edit_text(
    token: str,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Optional[Any],
) -> None:
    """Handle edit text button press.

    Sends the current content, registers a pending edit, and asks user
    to reply with new text.
    """
    _answer_callback(token, callback_id, "Edit mode")

    conn = _get_conn()
    try:
        from social_hook.bot.commands import set_chat_draft_context
        from social_hook.db import get_draft

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(token, chat_id, f"Draft `{draft_id}` not found.")
            return

        set_chat_draft_context(chat_id, draft_id, draft.project_id)

        # Warn if overwriting a different pending edit
        existing = get_pending_edit(chat_id)
        if existing and existing != draft_id:
            _send(
                token,
                chat_id,
                f"Switching edit to `{draft_id[:12]}` (edit for `{existing[:12]}` cancelled).",
            )

        _pending_edits[chat_id] = (draft_id, time.time())

        _send(
            token,
            chat_id,
            f"*Current content for* `{draft_id[:12]}`:\n\n"
            f"```\n{draft.content[:500]}\n```\n\n"
            f"Reply with new content to update this draft.",
        )
    finally:
        conn.close()


def btn_reject(
    token: str,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Optional[Any],
) -> None:
    """Handle reject button press (direct reject)."""
    _answer_callback(token, callback_id, "Rejecting...")

    conn = _get_conn()
    try:
        from social_hook.bot.commands import set_chat_draft_context
        from social_hook.db import get_draft, update_draft

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(token, chat_id, f"Draft `{draft_id}` not found.")
            return

        set_chat_draft_context(chat_id, draft_id, draft.project_id)

        update_draft(conn, draft_id, status="rejected")
        _send(token, chat_id, f"Draft `{draft_id[:12]}` rejected.")
    finally:
        conn.close()


def btn_quick_approve(
    token: str,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Optional[Any],
) -> None:
    """Approve and schedule at optimal time in one step."""
    _answer_callback(token, callback_id, "Approving and scheduling...")

    conn = _get_conn()
    try:
        from social_hook.bot.commands import set_chat_draft_context
        from social_hook.db import get_draft, update_draft
        from social_hook.scheduling import calculate_optimal_time

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(token, chat_id, f"Draft `{draft_id}` not found.")
            return

        set_chat_draft_context(chat_id, draft_id, draft.project_id)

        if draft.status not in ("draft", "approved"):
            _send(token, chat_id, f"Cannot approve draft with status: {draft.status}")
            return

        result = calculate_optimal_time(
            conn,
            draft.project_id,
            tz=config.scheduling.timezone if config else "UTC",
            max_posts_per_day=config.scheduling.max_posts_per_day if config else 3,
            min_gap_minutes=config.scheduling.min_gap_minutes if config else 30,
            optimal_days=config.scheduling.optimal_days if config else None,
            optimal_hours=config.scheduling.optimal_hours if config else None,
        )
        scheduled_str = result.datetime.isoformat()
        update_draft(conn, draft_id, status="scheduled", scheduled_time=scheduled_str)
        _send(
            token,
            chat_id,
            f"Draft `{draft_id[:12]}` approved and scheduled for {scheduled_str}",
        )
    finally:
        conn.close()


def btn_schedule_submenu(
    token: str,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Optional[Any],
) -> None:
    """Show schedule submenu with optimal/custom options."""
    _answer_callback(token, callback_id)

    buttons = [
        [
            {"text": "Optimal time", "callback_data": f"schedule_optimal:{draft_id}"},
            {"text": "Custom time", "callback_data": f"schedule_custom:{draft_id}"},
        ],
    ]
    send_notification_with_buttons(
        token, chat_id, f"Schedule `{draft_id[:12]}`:", buttons,
    )


def btn_schedule_custom(
    token: str,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Optional[Any],
) -> None:
    """Prompt user to reply with a custom time."""
    _answer_callback(token, callback_id)
    _send(
        token,
        chat_id,
        f"Reply with desired time for `{draft_id[:12]}`\n"
        f"(e.g., '2pm', 'tomorrow 9am', '2026-02-15T14:00:00')",
    )


def btn_edit_submenu(
    token: str,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Optional[Any],
) -> None:
    """Show edit submenu with text/media/angle options."""
    _answer_callback(token, callback_id)

    buttons = [
        [
            {"text": "Change text", "callback_data": f"edit_text:{draft_id}"},
            {"text": "Change media", "callback_data": f"edit_media:{draft_id}"},
        ],
        [
            {"text": "Change angle", "callback_data": f"edit_angle:{draft_id}"},
        ],
    ]
    send_notification_with_buttons(
        token, chat_id, f"Edit `{draft_id[:12]}`:", buttons,
    )


def btn_edit_media(
    token: str,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Optional[Any],
) -> None:
    """Prompt user to reply with a new media path."""
    _answer_callback(token, callback_id)
    _send(token, chat_id, f"Reply with media path or URL for `{draft_id[:12]}`")


def btn_edit_angle(
    token: str,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Optional[Any],
) -> None:
    """Prompt user to reply with a new angle."""
    _answer_callback(token, callback_id)
    _send(token, chat_id, f"Reply with new angle for `{draft_id[:12]}`")


def btn_reject_submenu(
    token: str,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Optional[Any],
) -> None:
    """Show reject submenu with just reject/reject with note."""
    _answer_callback(token, callback_id)

    buttons = [
        [
            {"text": "Just reject", "callback_data": f"reject_now:{draft_id}"},
            {"text": "Reject with note", "callback_data": f"reject_note:{draft_id}"},
        ],
    ]
    send_notification_with_buttons(
        token, chat_id, f"Reject `{draft_id[:12]}`:", buttons,
    )


def btn_reject_note(
    token: str,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Optional[Any],
) -> None:
    """Prompt user to reply with a rejection reason."""
    _answer_callback(token, callback_id)
    _send(token, chat_id, f"Reply with rejection reason for `{draft_id[:12]}`")


def btn_cancel(
    token: str,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Optional[Any],
) -> None:
    """Handle cancel button press from scheduled list."""
    _answer_callback(token, callback_id, "Cancelling...")

    conn = _get_conn()
    try:
        from social_hook.bot.commands import set_chat_draft_context
        from social_hook.db import get_draft, update_draft

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(token, chat_id, f"Draft `{draft_id}` not found.")
            return

        set_chat_draft_context(chat_id, draft_id, draft.project_id)

        update_draft(conn, draft_id, status="cancelled")
        _send(token, chat_id, f"Draft `{draft_id[:12]}` cancelled.")
    finally:
        conn.close()


def btn_review(
    token: str,
    chat_id: str,
    callback_id: str,
    draft_id: str,
    config: Optional[Any],
) -> None:
    """Show full draft review via button callback."""
    _answer_callback(token, callback_id)

    from social_hook.bot.commands import cmd_review

    cmd_review(token, chat_id, draft_id, config)
