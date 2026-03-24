"""Notification formatting helpers."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


# --- Action/status emoji mapping ---
_ACTION_EMOJI = {
    "draft": "\u270f\ufe0f",
    "skip": "\u23ed\ufe0f",
    "holding": "\u23f8\ufe0f",
}


def format_evaluation_cycle(
    project_name: str,
    trigger_description: str,
    strategy_outcomes: dict[str, dict[str, Any]],
    drafts: list,
    arc_info: dict[str, Any] | None = None,
    queue_actions: list[dict[str, str]] | None = None,
) -> str:
    """Format a grouped evaluation cycle notification.

    Args:
        project_name: Project name.
        trigger_description: Human-readable description of what triggered the cycle.
        strategy_outcomes: Dict mapping strategy name to its decision dict.
            Expected keys per entry: {"action", "reason", "arc_id", "topic_id"}.
        drafts: List of Draft model instances.
        arc_info: Optional dict with arc proposal info.
            Expected keys: {"arc_id", "theme", "parts", "reasoning"}.
        queue_actions: Optional list of queue action dicts.
            Expected keys per entry: {"type", "draft_id", "reason"}.

    Returns:
        Formatted Markdown message.
    """
    lines = [
        f"*Evaluation cycle* — {trigger_description}",
        "",
        f"Project: {project_name}",
    ]

    # Build a lookup of drafts by strategy for content preview
    drafts_by_strategy: dict[str, Any] = {}
    for draft in drafts:
        strategy = getattr(draft, "strategy", None) or ""
        if strategy:
            drafts_by_strategy[strategy] = draft

    # Strategy outcomes
    for strategy_name, outcome in strategy_outcomes.items():
        action = outcome.get("action", "unknown")
        reason = outcome.get("reason", "")
        emoji = _ACTION_EMOJI.get(action, "")
        line = f"\n{strategy_name}: {action} {emoji}".rstrip()
        lines.append(line)

        if reason:
            lines.append(f"  \u2192 {reason}")

        # Show draft content preview if action produced a draft
        draft = drafts_by_strategy.get(strategy_name)
        if draft and action == "draft":
            content_preview = (draft.content or "")[:80]
            if len(draft.content or "") > 80:
                content_preview += "\u2026"
            lines.append(f'  \u2192 "{content_preview}"')

        # Arc info per strategy outcome
        arc_id = outcome.get("arc_id")
        arc_theme = outcome.get("arc_theme", "")
        arc_post_number = outcome.get("arc_post_number")
        arc_reasoning = outcome.get("arc_reasoning", "")
        if arc_id and arc_theme:
            arc_label = f'Arc: "{arc_theme}"'
            if arc_post_number:
                arc_label += f" (post {arc_post_number} of ongoing)"
            lines.append(f"  \u2192 {arc_label}")
        if arc_reasoning:
            lines.append(f'  \u2192 Arc reasoning: "{arc_reasoning}"')

    # Queue actions (superseded, dropped)
    if queue_actions:
        lines.append("")
        lines.append("Queue actions:")
        for qa in queue_actions:
            qa_type = qa.get("type", "")
            qa_draft_id = qa.get("draft_id", "")
            qa_reason = qa.get("reason", "")
            label = f"  \u2192 {qa_type.capitalize()} {qa_draft_id}"
            if qa_reason:
                label += f': "{qa_reason}"'
            lines.append(label)

    # Arc proposal
    if arc_info:
        arc_id = arc_info.get("arc_id", "")
        theme = arc_info.get("theme", "")
        parts = arc_info.get("parts", 0)
        reasoning = arc_info.get("reasoning", "")
        lines.append("")
        lines.append(f'\U0001f517 Arc proposed: "{theme}" ({parts} parts)')
        if reasoning:
            lines.append(f'  \u2192 Reasoning: "{reasoning}"')

    return "\n".join(lines)


def get_cycle_buttons(
    cycle_id: str,
    drafts: list,
    arc_info: dict[str, Any] | None = None,
) -> list:
    """Get buttons for an evaluation cycle notification.

    Args:
        cycle_id: Evaluation cycle ID.
        drafts: List of Draft model instances in this cycle.
        arc_info: Optional arc proposal info dict.

    Returns:
        List of ButtonRow instances.
    """
    from social_hook.messaging.base import Button, ButtonRow

    rows: list[ButtonRow] = []

    # Arc proposal buttons (if present)
    if arc_info:
        arc_id = arc_info.get("arc_id", "")
        rows.append(
            ButtonRow(
                buttons=[
                    Button(label="Approve Arc", action="arc_approve", payload=arc_id),
                    Button(label="Dismiss Arc", action="arc_dismiss", payload=arc_id),
                ]
            )
        )

    # Cycle-level action buttons
    action_buttons = [
        Button(label="Expand All", action="cycle_expand", payload=cycle_id),
        Button(label="Approve All", action="cycle_approve", payload=cycle_id),
    ]
    rows.append(ButtonRow(buttons=action_buttons))

    # Per-draft view buttons
    view_buttons = []
    for draft in drafts:
        strategy = getattr(draft, "strategy", None) or draft.platform
        label = f"View {strategy}"
        # payload format: cycle_id:draft_id
        payload = f"{cycle_id}:{draft.id}"
        view_buttons.append(Button(label=label, action="cycle_view", payload=payload))
    if view_buttons:
        rows.append(ButtonRow(buttons=view_buttons))

    return rows


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
