"""Telegram bot daemon with long-polling loop."""

import logging
import signal
import sys
import time
from typing import Any, Callable, Optional

import requests

from social_hook.bot.process import remove_pid, write_pid

logger = logging.getLogger(__name__)

# Polling timeout in seconds (Telegram long-polling)
POLL_TIMEOUT = 30


class BotDaemon:
    """Telegram bot daemon using long-polling.

    Uses raw HTTP requests to the Telegram Bot API (no framework dependency).

    Args:
        token: Telegram Bot API token
        allowed_chat_ids: Set of authorized chat IDs (empty = allow all)
        on_command: Callback for /command messages
        on_callback: Callback for inline button presses
        on_message: Callback for free-text messages
    """

    def __init__(
        self,
        token: str,
        allowed_chat_ids: Optional[set[str]] = None,
        on_command: Optional[Callable] = None,
        on_callback: Optional[Callable] = None,
        on_message: Optional[Callable] = None,
    ) -> None:
        self.token = token
        self.allowed_chat_ids = allowed_chat_ids or set()
        self.on_command = on_command
        self.on_callback = on_callback
        self.on_message = on_message
        self._running = False
        self._offset = 0
        self._base_url = f"https://api.telegram.org/bot{token}"

    def _is_authorized(self, chat_id: str) -> bool:
        """Check if a chat ID is authorized."""
        if not self.allowed_chat_ids:
            return True
        return str(chat_id) in self.allowed_chat_ids

    def _get_updates(self) -> list[dict]:
        """Fetch updates from Telegram via long-polling."""
        try:
            response = requests.get(
                f"{self._base_url}/getUpdates",
                params={
                    "offset": self._offset,
                    "timeout": POLL_TIMEOUT,
                },
                timeout=POLL_TIMEOUT + 5,
            )
            if response.status_code != 200:
                logger.warning(f"getUpdates returned {response.status_code}")
                return []
            data = response.json()
            if not data.get("ok"):
                logger.warning(f"getUpdates not ok: {data}")
                return []
            return data.get("result", [])
        except requests.RequestException as e:
            logger.warning(f"getUpdates failed: {e}")
            return []

    def _route_update(self, update: dict) -> None:
        """Route an update to the appropriate handler."""
        # Handle callback queries (inline button presses)
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

        text = message.get("text", "")
        if not text:
            return

        # Commands start with /
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

    def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str = "Markdown",
        reply_markup: Optional[dict] = None,
    ) -> Optional[dict]:
        """Send a message via Telegram Bot API.

        Returns the sent message dict on success, None on failure.
        """
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            response = requests.post(
                f"{self._base_url}/sendMessage",
                json=payload,
                timeout=10,
            )
            if response.status_code == 200:
                return response.json().get("result")
            logger.warning(f"sendMessage returned {response.status_code}")
            return None
        except requests.RequestException as e:
            logger.warning(f"sendMessage failed: {e}")
            return None

    def answer_callback(
        self, callback_query_id: str, text: Optional[str] = None
    ) -> bool:
        """Answer a callback query (acknowledge button press)."""
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        try:
            response = requests.post(
                f"{self._base_url}/answerCallbackQuery",
                json=payload,
                timeout=10,
            )
            return response.status_code == 200
        except requests.RequestException:
            return False

    def edit_message(
        self,
        chat_id: str,
        message_id: int,
        text: str,
        parse_mode: str = "Markdown",
        reply_markup: Optional[dict] = None,
    ) -> bool:
        """Edit an existing message."""
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            response = requests.post(
                f"{self._base_url}/editMessageText",
                json=payload,
                timeout=10,
            )
            return response.status_code == 200
        except requests.RequestException:
            return False

    def run(self, pid_file=None) -> None:
        """Start the long-polling loop.

        Args:
            pid_file: Optional PID file path for daemon mode
        """
        self._running = True

        if pid_file:
            write_pid(pid_file)

        # Install signal handlers for graceful shutdown
        def _handle_signal(signum, frame):
            logger.info(f"Received signal {signum}, shutting down")
            self._running = False

        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)

        logger.info("Bot polling started")
        try:
            while self._running:
                updates = self._get_updates()
                for update in updates:
                    update_id = update.get("update_id", 0)
                    self._offset = update_id + 1
                    self._route_update(update)
        finally:
            if pid_file:
                remove_pid(pid_file)
            logger.info("Bot polling stopped")

    def stop(self) -> None:
        """Signal the polling loop to stop."""
        self._running = False


def create_bot(
    token: str,
    allowed_chat_ids: Optional[set[str]] = None,
    config: Optional[Any] = None,
) -> BotDaemon:
    """Create a configured BotDaemon with command/callback/message handlers.

    Args:
        token: Telegram Bot API token
        allowed_chat_ids: Set of authorized chat IDs
        config: Full Config object for DB/LLM access

    Returns:
        Configured BotDaemon instance
    """
    from social_hook.bot.buttons import handle_callback
    from social_hook.bot.buttons import set_adapter as set_buttons_adapter
    from social_hook.bot.commands import handle_command, handle_message
    from social_hook.bot.commands import set_adapter as set_commands_adapter
    from social_hook.messaging.telegram import TelegramAdapter

    adapter = TelegramAdapter(token=token)
    set_buttons_adapter(adapter)
    set_commands_adapter(adapter)

    def on_command(message: dict) -> None:
        handle_command(message, token, config)

    def on_callback(callback: dict) -> None:
        handle_callback(callback, token, config)

    def on_message(message: dict) -> None:
        handle_message(message, token, config)

    return BotDaemon(
        token=token,
        allowed_chat_ids=allowed_chat_ids,
        on_command=on_command,
        on_callback=on_callback,
        on_message=on_message,
    )
