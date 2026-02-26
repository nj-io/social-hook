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
        config: Full config object with channels/env settings.
        message: Markdown-formatted notification text.
        dry_run: If True, skip all sends.
    """
    if dry_run:
        return

    msg = OutboundMessage(text=message)
    channels = getattr(config, "channels", None) or {}

    # Web dashboard (enabled by default via DEFAULT_CONFIG)
    web_ch = channels.get("web")
    if not web_ch or web_ch.enabled:
        try:
            from social_hook.filesystem import get_db_path
            from social_hook.messaging.web import WebAdapter

            adapter = WebAdapter(db_path=str(get_db_path()))
            adapter.send_message("web", msg)
        except Exception as e:
            logger.warning(f"Web notification failed: {e}")

    # Telegram
    token = config.env.get("TELEGRAM_BOT_TOKEN")
    telegram_ch = channels.get("telegram")
    telegram_enabled = telegram_ch.enabled if telegram_ch else bool(token)
    chat_ids = (
        telegram_ch.allowed_chat_ids if telegram_ch
        else [c.strip() for c in config.env.get("TELEGRAM_ALLOWED_CHAT_IDS", "").split(",") if c.strip()]
    )

    if telegram_enabled and token and chat_ids:
        try:
            from social_hook.messaging.telegram import TelegramAdapter

            adapter = TelegramAdapter(token=token)
            for chat_id in chat_ids:
                result = adapter.send_message(chat_id, msg)
                if not result.success:
                    logger.warning(f"Telegram notification to {chat_id} failed: {result.error}")
        except Exception as e:
            logger.warning(f"Telegram notification failed: {e}")
