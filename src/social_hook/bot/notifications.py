"""Notification formatting and sending for Telegram."""

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


def send_notification(
    token: str,
    chat_id: str,
    message: str,
    parse_mode: str = "Markdown",
) -> bool:
    """Send a message via Telegram Bot API.

    Args:
        token: Bot API token
        chat_id: Target chat ID
        message: Message text
        parse_mode: Parse mode (Markdown or HTML)

    Returns:
        True if sent successfully
    """
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": parse_mode,
            },
            timeout=10,
        )
        return response.status_code == 200
    except requests.RequestException as e:
        logger.warning(f"Telegram send failed: {e}")
        return False


def send_notification_with_buttons(
    token: str,
    chat_id: str,
    message: str,
    buttons: list[list[dict]],
    parse_mode: str = "Markdown",
) -> Optional[int]:
    """Send a message with inline keyboard buttons.

    Args:
        token: Bot API token
        chat_id: Target chat ID
        message: Message text
        buttons: Inline keyboard layout [[{text, callback_data}, ...], ...]
        parse_mode: Parse mode

    Returns:
        Message ID if sent, None on failure
    """
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": parse_mode,
                "reply_markup": {
                    "inline_keyboard": buttons,
                },
            },
            timeout=10,
        )
        if response.status_code == 200:
            return response.json().get("result", {}).get("message_id")
        return None
    except requests.RequestException as e:
        logger.warning(f"Telegram send failed: {e}")
        return None


def format_draft_review(
    project_name: str,
    commit_hash: str,
    commit_message: str,
    platform: str,
    content: str,
    suggested_time: Optional[str] = None,
    draft_id: Optional[str] = None,
    char_count: Optional[int] = None,
    media_info: Optional[str] = None,
    is_thread: bool = False,
    tweet_count: Optional[int] = None,
    episode_type: Optional[str] = None,
    post_category: Optional[str] = None,
    angle: Optional[str] = None,
    evaluator_reasoning: Optional[str] = None,
) -> str:
    """Format a draft review notification message.

    Args:
        project_name: Project name
        commit_hash: Short commit hash
        commit_message: Commit message
        platform: Target platform
        content: Draft content
        suggested_time: Suggested posting time
        draft_id: Draft ID for reference
        char_count: Character count to display
        media_info: Media attachment description
        is_thread: Whether this is a thread
        tweet_count: Number of tweets in thread
        episode_type: Evaluator episode type
        post_category: Evaluator post category
        angle: Evaluator suggested angle
        evaluator_reasoning: Evaluator reasoning text

    Returns:
        Formatted Markdown message
    """
    lines = [
        "*New draft ready for review*",
        "",
        f"Project: {project_name}",
        f"Commit: `{commit_hash}` - {commit_message}",
        f"Platform: {platform}",
    ]
    if episode_type:
        lines.append(f"Episode: {episode_type}")
    if post_category:
        lines.append(f"Category: {post_category}")
    if angle:
        lines.append(f"Angle: _{angle}_")
    if evaluator_reasoning:
        lines.append(f"Reasoning: {evaluator_reasoning}")
    if is_thread and tweet_count:
        lines.append(f"Thread: {tweet_count} tweets")
    if char_count is not None:
        lines.append(f"Characters: {char_count}")
    if media_info:
        lines.append(f"Media: {media_info}")
    if draft_id:
        lines.append(f"Draft: `{draft_id}`")
    lines.extend([
        "",
        "```",
        content[:500],
        "```",
    ])
    if suggested_time:
        lines.append(f"\nSuggested time: {suggested_time}")
    return "\n".join(lines)


def format_post_confirmation(
    project_name: str,
    platform: str,
    content: str,
    external_url: Optional[str] = None,
    link_hint: Optional[str] = None,
) -> str:
    """Format a post confirmation notification.

    Args:
        project_name: Project name
        platform: Platform posted to
        content: Post content
        external_url: URL of the published post
        link_hint: Suggested link to post as reply

    Returns:
        Formatted Markdown message
    """
    lines = [
        "*Posted successfully*",
        "",
        f"Project: {project_name}",
        f"Platform: {platform}",
    ]
    if external_url:
        lines.append(f"URL: {external_url}")
    lines.extend([
        "",
        "```",
        content[:300],
        "```",
    ])
    if link_hint:
        lines.append(f"\nConsider posting this link as a reply: {link_hint}")
    return "\n".join(lines)


def format_error_notification(
    project_name: str,
    platform: str,
    error: str,
    draft_id: Optional[str] = None,
    retry_count: int = 0,
    max_retries: int = 3,
) -> str:
    """Format an error notification.

    Args:
        project_name: Project name
        platform: Target platform
        error: Error message
        draft_id: Draft ID
        retry_count: Current retry count
        max_retries: Maximum retries

    Returns:
        Formatted Markdown message
    """
    lines = [
        "*Post failed*",
        "",
        f"Project: {project_name}",
        f"Platform: {platform}",
        f"Error: {error}",
        f"Attempts: {retry_count}/{max_retries}",
    ]
    if draft_id:
        lines.append(f"Draft: `{draft_id}`")
    if retry_count >= max_retries:
        lines.append("\nDraft marked as failed. Use /retry to try again.")
    return "\n".join(lines)


def format_engagement_prompt() -> str:
    """Format an engagement reminder message.

    Returns:
        Formatted engagement prompt string
    """
    return "Replying to comments in the first hour has 150x the value of a like."


def get_review_buttons(draft_id: str) -> list[list[dict]]:
    """Get inline keyboard buttons for draft review.

    Uses submenu callback IDs for schedule, edit, reject.

    Args:
        draft_id: Draft ID for callback data

    Returns:
        Inline keyboard layout
    """
    return [
        [
            {"text": "Approve", "callback_data": f"approve:{draft_id}"},
            {"text": "Schedule", "callback_data": f"schedule:{draft_id}"},
        ],
        [
            {"text": "Edit", "callback_data": f"edit:{draft_id}"},
            {"text": "Reject", "callback_data": f"reject:{draft_id}"},
        ],
    ]


def send_via_adapter(adapter: "MessagingAdapter", chat_id: str, text: str) -> bool:
    """Send a plain message via adapter.

    Args:
        adapter: MessagingAdapter instance
        chat_id: Target chat ID
        text: Message text

    Returns:
        True if sent successfully
    """
    from social_hook.messaging.base import OutboundMessage

    result = adapter.send_message(chat_id, OutboundMessage(text=text))
    return result.success


def send_buttons_via_adapter(
    adapter: "MessagingAdapter",
    chat_id: str,
    text: str,
    buttons: list[list[dict]],
) -> Optional[str]:
    """Send message with buttons via adapter.

    Accepts legacy Telegram button format for backward compat,
    converts to ButtonRow internally.

    Args:
        adapter: MessagingAdapter instance
        chat_id: Target chat ID
        text: Message text
        buttons: Legacy Telegram inline keyboard format

    Returns:
        Message ID if successful, None otherwise
    """
    from social_hook.messaging.base import Button, ButtonRow, OutboundMessage

    rows = []
    for row in buttons:
        rows.append(
            ButtonRow(
                buttons=[
                    Button(
                        label=b["text"],
                        action=b["callback_data"].split(":")[0],
                        payload=b["callback_data"].split(":", 1)[1]
                        if ":" in b["callback_data"]
                        else "",
                    )
                    for b in row
                ]
            )
        )
    msg = OutboundMessage(text=text, buttons=rows)
    result = adapter.send_message(chat_id, msg)
    return result.message_id if result.success else None


def get_review_buttons_normalized(draft_id: str) -> list:
    """Get review buttons as normalized ButtonRow list.

    Args:
        draft_id: Draft ID for callback data

    Returns:
        List of ButtonRow instances
    """
    from social_hook.messaging.base import Button, ButtonRow

    return [
        ButtonRow(
            buttons=[
                Button(label="Approve", action="approve", payload=draft_id),
                Button(label="Schedule", action="schedule", payload=draft_id),
            ]
        ),
        ButtonRow(
            buttons=[
                Button(label="Edit", action="edit", payload=draft_id),
                Button(label="Reject", action="reject", payload=draft_id),
            ]
        ),
    ]
