"""Platform-agnostic messaging abstraction.

Mirrors the LLM layer pattern: ABC with normalized types,
provider-specific implementations in separate modules.

REUSABILITY: This file has zero social-hook imports.
Only stdlib (abc, dataclasses, typing). Copy-paste safe.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


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
    message_id: Optional[str] = None  # Platform-specific message ID
    error: Optional[str] = None
    raw: Any = None  # Platform-specific response


@dataclass
class InboundMessage:
    """Normalized inbound message from any platform."""

    chat_id: str
    text: str
    sender_id: Optional[str] = None
    sender_name: Optional[str] = None
    message_id: Optional[str] = None
    raw: Any = None


@dataclass
class CallbackEvent:
    """Normalized button callback event."""

    chat_id: str
    callback_id: str  # Platform-specific callback query ID
    action: str  # Parsed from button data
    payload: str  # Parsed from button data
    message_id: Optional[str] = None
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


class MessagingAdapter(ABC):
    """Abstract base for messaging platform adapters.

    Mirrors LLMClient pattern -- ABC with normalized types,
    provider-specific implementations.
    """

    platform: str  # "telegram", "slack", etc.

    @abstractmethod
    def send_message(self, chat_id: str, message: OutboundMessage) -> SendResult:
        """Send a message to a chat."""
        ...

    @abstractmethod
    def edit_message(
        self, chat_id: str, message_id: str, message: OutboundMessage
    ) -> SendResult:
        """Edit an existing message."""
        ...

    @abstractmethod
    def answer_callback(self, callback_id: str, text: str = "") -> bool:
        """Acknowledge a button callback."""
        ...

    @abstractmethod
    def get_capabilities(self) -> PlatformCapabilities:
        """Return platform capabilities."""
        ...
