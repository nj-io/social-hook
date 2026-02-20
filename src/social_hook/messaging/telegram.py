"""Telegram Bot API adapter.

Wraps direct HTTP calls to api.telegram.org.
No framework dependency (no python-telegram-bot).

REUSABILITY: This file imports only from messaging.base (stdlib)
and requests (common dependency). No social-hook domain concepts.
"""

import logging
from typing import Optional

import requests

from social_hook.messaging.base import (
    ButtonRow,
    CallbackEvent,
    InboundMessage,
    MessagingAdapter,
    OutboundMessage,
    PlatformCapabilities,
    SendResult,
)

logger = logging.getLogger(__name__)


class TelegramAdapter(MessagingAdapter):
    """Telegram Bot API adapter."""

    platform = "telegram"

    def __init__(self, token: str) -> None:
        self.token = token
        self._base_url = f"https://api.telegram.org/bot{token}"

    def send_message(self, chat_id: str, message: OutboundMessage) -> SendResult:
        """Send a message to a Telegram chat."""
        payload: dict = {
            "chat_id": chat_id,
            "text": message.text,
            "parse_mode": self._map_parse_mode(message.parse_mode),
        }
        if message.buttons:
            payload["reply_markup"] = {
                "inline_keyboard": self._buttons_to_telegram(message.buttons)
            }
        return self._post("sendMessage", payload)

    def edit_message(
        self, chat_id: str, message_id: str, message: OutboundMessage
    ) -> SendResult:
        """Edit an existing Telegram message."""
        payload: dict = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": message.text,
            "parse_mode": self._map_parse_mode(message.parse_mode),
        }
        if message.buttons:
            payload["reply_markup"] = {
                "inline_keyboard": self._buttons_to_telegram(message.buttons)
            }
        return self._post("editMessageText", payload)

    def answer_callback(self, callback_id: str, text: str = "") -> bool:
        """Acknowledge a Telegram callback query."""
        payload: dict = {"callback_query_id": callback_id}
        if text:
            payload["text"] = text
        result = self._post("answerCallbackQuery", payload)
        return result.success

    def get_capabilities(self) -> PlatformCapabilities:
        """Return Telegram platform capabilities."""
        return PlatformCapabilities(
            max_message_length=4096,
            supports_buttons=True,
            supports_inline_buttons=True,
            supports_message_editing=True,
            supports_markdown=True,
            supports_html=True,
            button_text_max_length=64,
            supports_media=True,
            max_media_per_message=4,
            supported_media_types=["png", "jpg", "jpeg", "gif"],
        )

    def send_media(self, chat_id: str, file_path: str, caption: str = "",
                   parse_mode: str = "markdown") -> SendResult:
        """Send a media file via Telegram."""
        from pathlib import Path

        path = Path(file_path)
        if not path.exists():
            return SendResult(success=False, error=f"File not found: {file_path}")

        file_size = path.stat().st_size
        ext = path.suffix.lower().lstrip(".")
        is_photo = ext in ("jpg", "jpeg", "png", "gif") and file_size <= 10 * 1024 * 1024

        method = "sendPhoto" if is_photo else "sendDocument"
        file_key = "photo" if is_photo else "document"

        try:
            with open(file_path, "rb") as f:
                data = {
                    "chat_id": chat_id,
                    "parse_mode": self._map_parse_mode(parse_mode),
                }
                if caption:
                    data["caption"] = caption
                response = requests.post(
                    f"{self._base_url}/{method}",
                    data=data,
                    files={file_key: f},
                    timeout=30,  # File uploads are slower than JSON API calls
                )
                return self._parse_response(response)
        except requests.RequestException as e:
            logger.warning(f"Telegram API call failed: {e}")
            return SendResult(success=False, error=str(e))

    # --- Internal helpers ---

    def _post(self, method: str, payload: dict) -> SendResult:
        """Make a POST request to the Telegram Bot API."""
        try:
            response = requests.post(
                f"{self._base_url}/{method}",
                json=payload,
                timeout=10,
            )
            return self._parse_response(response)
        except requests.RequestException as e:
            logger.warning(f"Telegram API call failed: {e}")
            return SendResult(success=False, error=str(e))

    def _parse_response(self, response: "requests.Response") -> SendResult:
        """Parse a Telegram API response into SendResult."""
        if response.status_code == 200:
            data = response.json()
            result = data.get("result", {})
            message_id = result.get("message_id") if isinstance(result, dict) else None
            return SendResult(
                success=True,
                message_id=str(message_id) if message_id else None,
                raw=data,
            )
        return SendResult(
            success=False,
            error=f"HTTP {response.status_code}",
            raw=response.text,
        )

    def _buttons_to_telegram(self, rows: list[ButtonRow]) -> list[list[dict]]:
        """Convert ButtonRow list to Telegram inline_keyboard format."""
        return [
            [
                {
                    "text": btn.label,
                    "callback_data": f"{btn.action}:{btn.payload}"
                    if btn.payload
                    else btn.action,
                }
                for btn in row.buttons
            ]
            for row in rows
        ]

    @staticmethod
    def _map_parse_mode(mode: str) -> str:
        """Map generic parse mode to Telegram-specific value."""
        return {"markdown": "Markdown", "html": "HTML"}.get(mode, "Markdown")

    @staticmethod
    def parse_callback(callback: dict) -> CallbackEvent:
        """Parse a Telegram callback_query dict into CallbackEvent."""
        data = callback.get("data", "")
        parts = data.split(":", 1)
        return CallbackEvent(
            chat_id=str(
                callback.get("message", {}).get("chat", {}).get("id", "")
            ),
            callback_id=callback.get("id", ""),
            action=parts[0],
            payload=parts[1] if len(parts) > 1 else "",
            message_id=str(
                callback.get("message", {}).get("message_id", "")
            ),
            raw=callback,
        )

    @staticmethod
    def parse_message(message: dict) -> InboundMessage:
        """Parse a Telegram message dict into InboundMessage."""
        return InboundMessage(
            chat_id=str(message.get("chat", {}).get("id", "")),
            text=message.get("text", ""),
            sender_id=str(message.get("from", {}).get("id", "")),
            sender_name=message.get("from", {}).get("first_name", ""),
            message_id=str(message.get("message_id", "")),
            raw=message,
        )
