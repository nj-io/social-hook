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
    post_category: str | None = None,
    angle: str | None = None,
    evaluator_reasoning: str | None = None,
    episode_tags: list[str] | None = None,
    is_intro: bool = False,
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
        post_category: Evaluator post category
        angle: Evaluator suggested angle
        evaluator_reasoning: Evaluator reasoning text
        episode_tags: Evaluator episode tags
        is_intro: Whether this is an introduction post

    Returns:
        Formatted Markdown message
    """
    # Build metadata tag line
    tags = []
    if is_intro:
        tags.append("[INTRO]")
    if post_category:
        tags.append(f"[{post_category}]")
    if episode_tags:
        for t in episode_tags:
            tags.append(f"[{t}]")
    tag_line = " ".join(tags)

    header = "*New draft ready for review*"
    if tag_line:
        header = f"{tag_line} {header}"

    lines = [
        header,
        "",
        f"Project: {project_name}",
        f"Commit: `{commit_hash}` - {commit_message}",
        f"Platform: {platform}",
    ]
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


def get_review_buttons_normalized(
    draft_id: str, platform: str = "", is_intro: bool = False
) -> list:
    """Get review buttons as normalized ButtonRow list.

    Args:
        draft_id: Draft ID for callback data
        platform: Platform name — when "preview", shows Promote instead of
            approve/schedule/post-now buttons.
        is_intro: Whether this draft is an introduction post

    Returns:
        List of ButtonRow instances
    """
    from social_hook.messaging.base import Button, ButtonRow

    if platform == "preview":
        return [
            ButtonRow(
                buttons=[
                    Button(label="Edit", action="edit", payload=draft_id),
                    Button(label="Reject", action="reject", payload=draft_id),
                    Button(label="Promote", action="promote", payload=draft_id),
                ]
            ),
        ]

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
