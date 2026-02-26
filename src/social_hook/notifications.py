"""Shared notification helper for sending messages to all configured channels."""

import logging
from typing import Optional

from social_hook.config.yaml import Config
from social_hook.messaging.base import OutboundMessage

logger = logging.getLogger(__name__)


def send_notification(
    config: Config,
    message: str,
    dry_run: bool = False,
) -> None:
    """Send a notification to all configured channels (Web + Telegram).

    Args:
        config: Full config object with web/env settings.
        message: Markdown-formatted notification text.
        dry_run: If True, skip all sends.
    """
    if dry_run:
        return

    msg = OutboundMessage(text=message)

    # Web dashboard
    if getattr(config, "web", None) and config.web.enabled:
        try:
            from social_hook.filesystem import get_db_path
            from social_hook.messaging.web import WebAdapter

            adapter = WebAdapter(db_path=str(get_db_path()))
            adapter.send_message("web", msg)
        except Exception as e:
            logger.warning(f"Web notification failed: {e}")

    # Telegram
    telegram_token = config.env.get("TELEGRAM_BOT_TOKEN")
    chat_ids_str = config.env.get("TELEGRAM_ALLOWED_CHAT_IDS", "")
    if telegram_token and chat_ids_str:
        try:
            from social_hook.messaging.telegram import TelegramAdapter

            adapter = TelegramAdapter(token=telegram_token)
            chat_ids = [c.strip() for c in chat_ids_str.split(",") if c.strip()]
            for chat_id in chat_ids:
                result = adapter.send_message(chat_id, msg)
                if not result.success:
                    logger.warning(f"Telegram notification to {chat_id} failed: {result.error}")
        except Exception as e:
            logger.warning(f"Telegram notification failed: {e}")
