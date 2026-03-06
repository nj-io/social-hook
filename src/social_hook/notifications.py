"""Shared notification helper for sending messages to all configured channels."""

import logging
from dataclasses import replace

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
) -> None:
    """Send a notification to all configured channels (Web + Telegram).

    Args:
        config: Full config object with channels/env settings.
        message: OutboundMessage with text, optional buttons.
        media: Optional list of media file paths to send after the message.
        dry_run: If True, skip all sends.
        chat_context: Optional (draft_id, project_id) tuple for setting
            chat draft context on Telegram.
    """
    if dry_run:
        return

    channels = getattr(config, "channels", None) or {}

    # --- Web dashboard (enabled by default via DEFAULT_CONFIG) ---
    web_ch = channels.get("web")
    if not web_ch or web_ch.enabled:
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

            # Strip buttons if daemon not running (no callback handler)
            tg_msg = message
            if message.buttons:
                from social_hook.bot.process import is_running

                if not is_running():
                    tg_msg = replace(message, buttons=[])

            for chat_id in chat_ids:
                result = tg_adapter.send_message(chat_id, tg_msg)
                if not result.success:
                    logger.warning(f"Telegram notification to {chat_id} failed: {result.error}")

            if media:
                caps = tg_adapter.get_capabilities()
                if caps.supports_media:
                    for media_path in media:
                        for chat_id in chat_ids:
                            tg_adapter.send_media(chat_id, media_path, caption="Media attachment")

            if chat_context:
                from social_hook.bot.commands import set_chat_draft_context

                draft_id, project_id = chat_context
                for chat_id in chat_ids:
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
        )
        buttons = get_review_buttons_normalized(draft.id)
        msg = OutboundMessage(text=msg_text, buttons=buttons)
        broadcast_notification(
            config,
            msg,
            media=draft.media_paths or None,
            chat_context=(draft.id, project_id),
        )


def send_notification(
    config: Config,
    message: str,
    dry_run: bool = False,
) -> None:
    """Send a plain text notification to all configured channels.

    Backward-compatible wrapper around broadcast_notification().
    """
    broadcast_notification(config, OutboundMessage(text=message), dry_run=dry_run)
