"""Shared notification helper for sending messages to all configured channels."""

import logging

from social_hook.config.yaml import Config
from social_hook.messaging.base import OutboundMessage

logger = logging.getLogger(__name__)


def broadcast_notification(
    config: Config,
    message: OutboundMessage,
    *,
    media: list[str] | None = None,
    dry_run: bool = False,
    chat_context: tuple[str, str] | None = None,
    exclude_chat: str | None = None,
) -> None:
    """Send a notification to all configured channels (Web + Telegram).

    Args:
        config: Full config object with channels/env settings.
        message: OutboundMessage with text, optional buttons.
        media: Optional list of media file paths to send after the message.
        dry_run: If True, skip all sends.
        chat_context: Optional (draft_id, project_id) tuple for setting
            chat draft context on Telegram.
        exclude_chat: Optional chat_id to skip (avoids double-notifying the
            originator). For web origins, starts with "web:".
    """
    if dry_run:
        return

    channels = getattr(config, "channels", None) or {}

    # --- Web dashboard (enabled by default via DEFAULT_CONFIG) ---
    # Skip web broadcast if originator is a web tab (data events handle refresh)
    web_ch = channels.get("web")
    skip_web = exclude_chat is not None and exclude_chat.startswith("web:")
    if (not web_ch or web_ch.enabled) and not skip_web:
        try:
            from social_hook.filesystem import get_db_path
            from social_hook.messaging.web import WebAdapter

            adapter = WebAdapter(db_path=str(get_db_path()))
            adapter.send_message("web", message)
            if media:
                for path in media:
                    adapter.send_media("web", path, caption="Media attachment")
        except Exception as e:
            logger.warning(f"Web notification failed: {e}")

    # --- Telegram ---
    token = config.env.get("TELEGRAM_BOT_TOKEN")
    telegram_ch = channels.get("telegram")
    telegram_enabled = telegram_ch.enabled if telegram_ch else bool(token)
    chat_ids = (
        telegram_ch.allowed_chat_ids
        if telegram_ch
        else [
            c.strip()
            for c in config.env.get("TELEGRAM_ALLOWED_CHAT_IDS", "").split(",")
            if c.strip()
        ]
    )

    if telegram_enabled and token and chat_ids:
        try:
            from social_hook.messaging.telegram import TelegramAdapter

            tg_adapter = TelegramAdapter(token=token)

            for chat_id in chat_ids:
                if chat_id == exclude_chat:
                    continue
                result = tg_adapter.send_message(chat_id, message)
                if not result.success:
                    logger.warning(f"Telegram notification to {chat_id} failed: {result.error}")

            if media:
                caps = tg_adapter.get_capabilities()
                if caps.supports_media:
                    for media_path in media:
                        for chat_id in chat_ids:
                            if chat_id == exclude_chat:
                                continue
                            tg_adapter.send_media(chat_id, media_path, caption="Media attachment")

            if chat_context:
                from social_hook.bot.commands import set_chat_draft_context

                draft_id, project_id = chat_context
                for chat_id in chat_ids:
                    if chat_id == exclude_chat:
                        continue
                    set_chat_draft_context(chat_id, draft_id, project_id)
        except Exception as e:
            logger.warning(f"Telegram notification failed: {e}")


def notify_draft_review(
    config: Config,
    project_name: str,
    project_id: str,
    commit_hash: str,
    commit_message: str,
    draft_results: list,
) -> None:
    """Send draft review notifications for a list of DraftResult objects.

    Shared by the trigger pipeline and the web API create-draft endpoint.
    """
    from social_hook.bot.notifications import format_draft_review, get_review_buttons_normalized

    for result in draft_results:
        draft = result.draft
        schedule = result.schedule
        thread_tweets = result.thread_tweets
        is_thread = bool(thread_tweets)
        tweet_count = len(thread_tweets) if is_thread else None
        suggested_time_str = schedule.datetime.strftime("%Y-%m-%d %H:%M UTC")
        media_info = (
            f"{draft.media_type} ({len(draft.media_paths)} file)" if draft.media_paths else None
        )

        msg_text = format_draft_review(
            project_name=project_name,
            commit_hash=commit_hash[:8],
            commit_message=commit_message,
            platform=draft.platform,
            content=draft.content,
            suggested_time=suggested_time_str,
            draft_id=draft.id,
            is_thread=is_thread,
            tweet_count=tweet_count,
            media_info=media_info,
            post_category=result.post_category,
            angle=result.angle,
            episode_tags=result.episode_tags,
            is_intro=getattr(draft, "is_intro", False),
        )
        buttons = get_review_buttons_normalized(
            draft.id,
            platform=draft.platform,
            is_intro=getattr(draft, "is_intro", False),
        )
        msg = OutboundMessage(text=msg_text, buttons=buttons)
        broadcast_notification(
            config,
            msg,
            media=draft.media_paths or None,
            chat_context=(draft.id, project_id),
        )


def resend_draft_notification(
    config: Config,
    draft_id: str,
) -> None:
    """Re-broadcast an existing draft's review notification to all channels.

    Looks up the draft and its decision from the DB, formats the review
    message, and sends it via broadcast_notification — same as the original
    notification but without needing a DraftResult object.
    """
    from social_hook.bot.notifications import format_draft_review, get_review_buttons_normalized
    from social_hook.db import operations as ops
    from social_hook.db.connection import init_database
    from social_hook.filesystem import get_db_path

    conn = init_database(get_db_path())
    try:
        draft = ops.get_draft(conn, draft_id)
        if not draft:
            raise ValueError(f"Draft {draft_id} not found")

        project = ops.get_project(conn, draft.project_id)
        project_name = project.name if project else "Unknown"

        decision = ops.get_decision(conn, draft.decision_id)
        commit_hash = decision.commit_hash[:8] if decision else "unknown"
        commit_message = decision.commit_message or "" if decision else ""

        media_info = (
            f"{draft.media_type} ({len(draft.media_paths)} file)" if draft.media_paths else None
        )

        msg_text = format_draft_review(
            project_name=project_name,
            commit_hash=commit_hash,
            commit_message=commit_message,
            platform=draft.platform,
            content=draft.content,
            suggested_time=draft.suggested_time.strftime("%Y-%m-%d %H:%M UTC")
            if draft.suggested_time
            else None,
            draft_id=draft.id,
            media_info=media_info,
            angle=decision.angle if decision else None,
            post_category=decision.post_category if decision else None,
            episode_tags=decision.episode_tags if decision else None,
            is_intro=getattr(draft, "is_intro", False),
        )
        buttons = get_review_buttons_normalized(
            draft.id,
            platform=draft.platform,
            is_intro=getattr(draft, "is_intro", False),
        )
        msg = OutboundMessage(text=msg_text, buttons=buttons)
        broadcast_notification(
            config,
            msg,
            media=draft.media_paths or None,
            chat_context=(draft.id, draft.project_id),
        )
    finally:
        conn.close()


def notify_evaluation_cycle(
    config: Config,
    project_name: str,
    project_id: str,
    cycle_id: str,
    trigger_description: str,
    strategy_outcomes: dict[str, dict],
    drafts: list,
    arc_info: dict | None = None,
    queue_actions: list[dict[str, str]] | None = None,
    dry_run: bool = False,
) -> None:
    """Send grouped notification for an evaluation cycle.

    Receives pre-fetched data — no DB access. Formats via format_evaluation_cycle(),
    constructs OutboundMessage with ButtonRow, and calls broadcast_notification().

    Args:
        config: Full config object.
        project_name: Project display name.
        project_id: Project ID.
        cycle_id: Evaluation cycle ID.
        trigger_description: Human-readable trigger (e.g. 'Topic "auth" matured (5 commits)').
        strategy_outcomes: Dict mapping strategy name to decision dict.
            Expected keys per entry: {"action", "reason", "arc_id", "topic_id"}.
        drafts: List of Draft model instances already fetched by the caller.
        arc_info: Optional arc proposal dict (arc_id, theme, parts, reasoning).
        queue_actions: Optional list of queue action dicts (type, draft_id, reason).
        dry_run: If True, skip all sends.
    """
    if dry_run:
        return

    from social_hook.bot.notifications import format_evaluation_cycle, get_cycle_buttons

    msg_text = format_evaluation_cycle(
        project_name=project_name,
        trigger_description=trigger_description,
        strategy_outcomes=strategy_outcomes,
        drafts=drafts,
        arc_info=arc_info,
        queue_actions=queue_actions,
    )
    buttons = get_cycle_buttons(
        cycle_id=cycle_id,
        drafts=drafts,
        arc_info=arc_info,
    )
    msg = OutboundMessage(text=msg_text, buttons=buttons)
    broadcast_notification(config, msg)


def send_notification(
    config: Config,
    message: str,
    dry_run: bool = False,
) -> None:
    """Send a plain text notification to all configured channels.

    Backward-compatible wrapper around broadcast_notification().
    """
    broadcast_notification(config, OutboundMessage(text=message), dry_run=dry_run)
