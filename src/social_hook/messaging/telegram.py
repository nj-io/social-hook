"""Telegram Bot API adapter.

Wraps direct HTTP calls to api.telegram.org.
No framework dependency (no python-telegram-bot).

REUSABILITY: This file imports only from messaging.base (stdlib)
and requests (common dependency). No project-specific domain concepts.
"""

import logging
import re

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

    def sanitize_text(self, text: str, parse_mode: str) -> str:
        """Escape characters that break Telegram's Markdown parser.

        Preserves intentional formatting (text inside backtick code spans)
        while escaping stray underscores and other special chars in plain
        text segments. Only applies to Markdown mode — HTML is returned
        unchanged.
        """
        if parse_mode != "markdown":
            return text
        parts = re.split(r"(`[^`]*`)", text)
        for i, part in enumerate(parts):
            if part.startswith("`"):
                continue
            parts[i] = re.sub(r"(?<!\\)_", r"\\_", part)
        return "".join(parts)

    def _is_format_error(self, result: SendResult) -> bool:
        """Check if Telegram rejected the message due to Markdown parse errors."""
        if isinstance(result.raw, dict):
            desc = result.raw.get("description", "")
            return "parse entities" in desc if desc else False
        return False

    def _do_send_message(self, chat_id: str, message: OutboundMessage) -> SendResult:
        """Send a message to a Telegram chat."""
        payload: dict = {
            "chat_id": chat_id,
            "text": message.text,
        }
        pm = self._map_parse_mode(message.parse_mode)
        if pm:
            payload["parse_mode"] = pm
        if message.buttons:
            payload["reply_markup"] = {
                "inline_keyboard": self._buttons_to_telegram(message.buttons)
            }
        return self._post("sendMessage", payload)

    def _do_edit_message(
        self, chat_id: str, message_id: str, message: OutboundMessage
    ) -> SendResult:
        """Edit an existing Telegram message."""
        payload: dict = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": message.text,
        }
        pm = self._map_parse_mode(message.parse_mode)
        if pm:
            payload["parse_mode"] = pm
        if message.buttons:
            payload["reply_markup"] = {
                "inline_keyboard": self._buttons_to_telegram(message.buttons)
            }
        else:
            payload["reply_markup"] = {"inline_keyboard": []}
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

    def _do_send_media(
        self, chat_id: str, file_path: str, caption: str = "", parse_mode: str = "markdown"
    ) -> SendResult:
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
                data: dict = {"chat_id": chat_id}
                pm = self._map_parse_mode(parse_mode)
                if pm:
                    data["parse_mode"] = pm
                if caption:
                    data["caption"] = caption  # Already sanitized by base
                response = requests.post(
                    f"{self._base_url}/{method}",
                    data=data,
                    files={file_key: f},
                    timeout=30,
                )
                return self._parse_response(response)
        except requests.RequestException as e:
            logger.warning(f"Telegram API call failed: {e}")
            return SendResult(success=False, error=str(e))

    def download_file(self, file_id: str, dest_dir: str) -> str | None:
        """Download a file from Telegram by file_id.

        Args:
            file_id: Telegram file_id
            dest_dir: Directory to save the file

        Returns:
            Local file path or None on failure
        """
        from pathlib import Path

        try:
            # Get file info
            response = requests.get(
                f"{self._base_url}/getFile",
                params={"file_id": file_id},
                timeout=10,
            )
            if response.status_code != 200:
                logger.warning(f"getFile failed: HTTP {response.status_code}")
                return None
            data = response.json()
            if not data.get("ok"):
                return None
            file_path = data["result"].get("file_path", "")
            if not file_path:
                return None

            # Download the file
            download_url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
            file_response = requests.get(download_url, timeout=30)
            if file_response.status_code != 200:
                return None

            # Save to dest_dir
            dest = Path(dest_dir)
            dest.mkdir(parents=True, exist_ok=True)
            filename = Path(file_path).name
            local_path = dest / filename
            local_path.write_bytes(file_response.content)
            return str(local_path)
        except requests.RequestException as e:
            logger.warning(f"Failed to download file: {e}")
            return None

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
            if not data.get("ok", True):
                error_msg = data.get("description", "Unknown Telegram error")
                logger.warning("Telegram API rejected request: %s", error_msg)
                return SendResult(success=False, error=error_msg, raw=data)
            result = data.get("result", {})
            message_id = result.get("message_id") if isinstance(result, dict) else None
            return SendResult(
                success=True,
                message_id=str(message_id) if message_id else None,
                raw=data,
            )
        try:
            data = response.json()
            desc = data.get("description", "")
        except Exception:
            data = response.text
            desc = ""
        error_msg = (
            f"HTTP {response.status_code}: {desc}" if desc else f"HTTP {response.status_code}"
        )
        logger.warning("Telegram API error: %s", error_msg)
        return SendResult(success=False, error=error_msg, raw=data)

    def _buttons_to_telegram(self, rows: list[ButtonRow]) -> list[list[dict]]:
        """Convert ButtonRow list to Telegram inline_keyboard format."""
        return [
            [
                {
                    "text": btn.label,
                    "callback_data": f"{btn.action}:{btn.payload}" if btn.payload else btn.action,
                }
                for btn in row.buttons
            ]
            for row in rows
        ]

    @staticmethod
    def _map_parse_mode(mode: str) -> str | None:
        """Map generic parse mode to Telegram-specific value.

        Returns None for unrecognized modes (e.g. "plain"), signaling
        that parse_mode should be omitted from the API payload.
        """
        return {"markdown": "Markdown", "html": "HTML"}.get(mode)

    @staticmethod
    def parse_callback(callback: dict) -> CallbackEvent:
        """Parse a Telegram callback_query dict into CallbackEvent."""
        data = callback.get("data", "")
        parts = data.split(":", 1)
        return CallbackEvent(
            chat_id=str(callback.get("message", {}).get("chat", {}).get("id", "")),
            callback_id=callback.get("id", ""),
            action=parts[0],
            payload=parts[1] if len(parts) > 1 else "",
            message_id=str(callback.get("message", {}).get("message_id", "")),
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
