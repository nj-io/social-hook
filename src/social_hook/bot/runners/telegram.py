"""Telegram channel runner using long-polling."""

import logging
from collections.abc import Callable

import requests

from social_hook.bot.runner import ChannelRunner

logger = logging.getLogger(__name__)

POLL_TIMEOUT = 30


class TelegramRunner(ChannelRunner):
    """Telegram channel runner using long-polling."""

    def __init__(
        self,
        token: str,
        allowed_chat_ids: set[str] | None = None,
        on_command: Callable | None = None,
        on_callback: Callable | None = None,
        on_message: Callable | None = None,
    ) -> None:
        self.token = token
        self.allowed_chat_ids = allowed_chat_ids or set()
        self.on_command = on_command
        self.on_callback = on_callback
        self.on_message = on_message
        self._running = False
        self._offset = 0
        self._base_url = f"https://api.telegram.org/bot{token}"

    @property
    def platform(self) -> str:
        return "telegram"

    def _is_authorized(self, chat_id: str) -> bool:
        if not self.allowed_chat_ids:
            return True
        return str(chat_id) in self.allowed_chat_ids

    def _get_updates(self) -> list[dict]:
        try:
            response = requests.get(
                f"{self._base_url}/getUpdates",
                params={"offset": self._offset, "timeout": POLL_TIMEOUT},
                timeout=POLL_TIMEOUT + 5,
            )
            if response.status_code != 200:
                logger.warning(f"getUpdates returned {response.status_code}")
                return []
            data = response.json()
            if not data.get("ok"):
                logger.warning(f"getUpdates not ok: {data}")
                return []
            return data.get("result", [])  # type: ignore[no-any-return]
        except requests.RequestException as e:
            logger.warning(f"getUpdates failed: {e}")
            return []

    def _route_update(self, update: dict) -> None:
        if "callback_query" in update:
            callback = update["callback_query"]
            chat_id = str(callback.get("message", {}).get("chat", {}).get("id", ""))
            if not self._is_authorized(chat_id):
                return
            if self.on_callback:
                try:
                    self.on_callback(callback)
                except Exception:
                    logger.exception("Error handling callback query")
            return

        message = update.get("message", {})
        if not message:
            return
        chat_id = str(message.get("chat", {}).get("id", ""))
        if not self._is_authorized(chat_id):
            return

        # Handle photo messages (for media_upload pending replies)
        photo = message.get("photo")
        if photo and not message.get("text"):
            if self.on_message:
                try:
                    self.on_message(message)
                except Exception:
                    logger.exception("Error handling photo message")
            return

        text = message.get("text", "")
        if not text:
            return
        if text.startswith("/"):
            if self.on_command:
                try:
                    self.on_command(message)
                except Exception:
                    logger.exception("Error handling command")
        else:
            if self.on_message:
                try:
                    self.on_message(message)
                except Exception:
                    logger.exception("Error handling message")

    def run(self) -> None:
        self._running = True
        logger.info("Telegram polling started")
        while self._running:
            updates = self._get_updates()
            for update in updates:
                update_id = update.get("update_id", 0)
                self._offset = update_id + 1
                self._route_update(update)
        logger.info("Telegram polling stopped")

    def stop(self) -> None:
        self._running = False
