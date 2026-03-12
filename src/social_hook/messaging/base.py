"""Platform-agnostic messaging abstraction.

Mirrors the LLM layer pattern: ABC with normalized types,
provider-specific implementations in separate modules.

Template Method: send_message / edit_message / send_media handle
text sanitization and format-error retry at the base level.
Subclasses implement _do_send_message, _do_edit_message, _do_send_media
and optionally override sanitize_text / _is_format_error.

REUSABILITY: This file has zero project-specific imports.
Only stdlib (abc, dataclasses, logging, typing). Copy-paste safe.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Button:
    """Platform-agnostic button."""

    label: str  # Display text
    action: str  # Callback action identifier (e.g., "approve")
    payload: str = ""  # Action-specific data (e.g., draft_id)


@dataclass
class ButtonRow:
    """A row of buttons in a keyboard layout."""

    buttons: list[Button]


@dataclass
class OutboundMessage:
    """Platform-agnostic outbound message."""

    text: str
    parse_mode: str = "markdown"
    buttons: list[ButtonRow] = field(default_factory=list)


@dataclass
class SendResult:
    """Result of sending a message."""

    success: bool
    message_id: str | None = None  # Platform-specific message ID
    error: str | None = None
    raw: Any = None  # Platform-specific response


@dataclass
class InboundMessage:
    """Normalized inbound message from any platform."""

    chat_id: str
    text: str
    sender_id: str | None = None
    sender_name: str | None = None
    message_id: str | None = None
    raw: Any = None


@dataclass
class CallbackEvent:
    """Normalized button callback event."""

    chat_id: str
    callback_id: str  # Platform-specific callback query ID
    action: str  # Parsed from button data
    payload: str  # Parsed from button data
    message_id: str | None = None
    raw: Any = None


@dataclass
class PlatformCapabilities:
    """Declares what this platform supports."""

    max_message_length: int = 4096
    supports_buttons: bool = True
    supports_inline_buttons: bool = True
    supports_message_editing: bool = True
    supports_markdown: bool = True
    supports_html: bool = True
    button_text_max_length: int = 64
    supports_media: bool = True
    max_media_per_message: int = 4
    supported_media_types: list[str] = field(default_factory=lambda: ["png", "jpg", "jpeg", "gif"])


class MessagingAdapter(ABC):
    """Abstract base for messaging platform adapters.

    Template Method: send_message / edit_message / send_media sanitize
    text and retry on format errors. Subclasses implement _do_* methods
    and optionally override sanitize_text / _is_format_error.
    """

    platform: str  # "telegram", "slack", etc.

    def sanitize_text(self, text: str, parse_mode: str) -> str:
        """Sanitize text for this platform's parser. Override in subclasses."""
        return text

    def _is_format_error(self, result: SendResult) -> bool:
        """Check if a send failure was caused by text formatting. Override in subclasses."""
        return False

    def send_message(self, chat_id: str, message: OutboundMessage) -> SendResult:
        """Send a message with automatic sanitization and format-error retry."""
        sanitized = OutboundMessage(
            text=self.sanitize_text(message.text, message.parse_mode),
            parse_mode=message.parse_mode,
            buttons=message.buttons,
        )
        result = self._do_send_message(chat_id, sanitized)
        if not result.success and self._is_format_error(result) and message.parse_mode != "plain":
            logger.info("[%s] format error, retrying as plain text", self.platform)
            plain = OutboundMessage(text=message.text, parse_mode="plain", buttons=message.buttons)
            result = self._do_send_message(chat_id, plain)
        return result

    @abstractmethod
    def _do_send_message(self, chat_id: str, message: OutboundMessage) -> SendResult:
        """Platform-specific send implementation. Called by send_message."""
        ...

    def edit_message(self, chat_id: str, message_id: str, message: OutboundMessage) -> SendResult:
        """Edit a message with automatic sanitization and format-error retry."""
        sanitized = OutboundMessage(
            text=self.sanitize_text(message.text, message.parse_mode),
            parse_mode=message.parse_mode,
            buttons=message.buttons,
        )
        result = self._do_edit_message(chat_id, message_id, sanitized)
        if not result.success and self._is_format_error(result) and message.parse_mode != "plain":
            logger.info("[%s] format error on edit, retrying as plain text", self.platform)
            plain = OutboundMessage(text=message.text, parse_mode="plain", buttons=message.buttons)
            result = self._do_edit_message(chat_id, message_id, plain)
        return result

    @abstractmethod
    def _do_edit_message(
        self, chat_id: str, message_id: str, message: OutboundMessage
    ) -> SendResult:
        """Platform-specific edit implementation. Called by edit_message."""
        ...

    @abstractmethod
    def answer_callback(self, callback_id: str, text: str = "") -> bool:
        """Acknowledge a button callback."""
        ...

    @abstractmethod
    def get_capabilities(self) -> PlatformCapabilities:
        """Return platform capabilities."""
        ...

    def send_media(
        self, chat_id: str, file_path: str, caption: str = "", parse_mode: str = "markdown"
    ) -> SendResult:
        """Send media with automatic caption sanitization and format-error retry."""
        sanitized_caption = self.sanitize_text(caption, parse_mode) if caption else caption
        result = self._do_send_media(chat_id, file_path, sanitized_caption, parse_mode)
        if not result.success and self._is_format_error(result) and parse_mode != "plain":
            logger.info("[%s] format error on media caption, retrying as plain text", self.platform)
            result = self._do_send_media(chat_id, file_path, caption, "plain")
        return result

    def _do_send_media(
        self, chat_id: str, file_path: str, caption: str = "", parse_mode: str = "markdown"
    ) -> SendResult:
        """Platform-specific media send. Override in subclasses that support media."""
        return SendResult(success=False, error=f"{self.platform} does not support media uploads")

    def download_file(self, file_id: str, dest_dir: str) -> str | None:
        """Download a file by platform-specific ID. Returns local path, or None if unsupported."""
        return None
