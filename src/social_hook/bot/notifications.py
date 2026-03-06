"""Notification formatting helpers."""

import logging

logger = logging.getLogger(__name__)


def format_draft_review(
    project_name: str,
    commit_hash: str,
    commit_message: str,
    platform: str,
    content: str,
    suggested_time: str | None = None,
    draft_id: str | None = None,
    char_count: int | None = None,
    media_info: str | None = None,
    is_thread: bool = False,
    tweet_count: int | None = None,
    episode_type: str | None = None,
    post_category: str | None = None,
    angle: str | None = None,
    evaluator_reasoning: str | None = None,
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
    lines.extend(
        [
            "",
            "```",
            content,
            "```",
        ]
    )
    if suggested_time:
        lines.append(f"\nSuggested time: {suggested_time}")
    return "\n".join(lines)


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
                Button(label="Quick Approve", action="quick_approve", payload=draft_id),
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
