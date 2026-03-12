"""Slack Bot adapter (stub).

Install slack-bolt for full support.
Uses slack-bolt for event handling and Web API for messaging.

REUSABILITY: Imports only from messaging.base (stdlib) and ConfigError.
No project-specific domain concepts.
"""

from social_hook.errors import ConfigError
from social_hook.messaging.base import (
    MessagingAdapter,
    OutboundMessage,
    PlatformCapabilities,
    SendResult,
)


class SlackAdapter(MessagingAdapter):
    """Slack Bot adapter (stub -- install slack-bolt for full support).

    Uses slack-bolt for event handling and Web API for messaging.
    """

    platform = "slack"

    def __init__(self, token: str) -> None:
        try:
            from slack_bolt import App  # noqa: F401
        except ImportError:
            raise ConfigError("slack-bolt package required for Slack integration.") from None
        self.token = token

    def send_message(self, chat_id: str, message: OutboundMessage) -> SendResult:
        """Send a message to a Slack channel."""
        raise NotImplementedError(
            "Slack adapter is a stub. Full implementation planned -- see ROADMAP.md for status."
        )

    def edit_message(self, chat_id: str, message_id: str, message: OutboundMessage) -> SendResult:
        """Edit an existing Slack message."""
        raise NotImplementedError("Slack adapter is a stub.")

    def answer_callback(self, callback_id: str, text: str = "") -> bool:
        """Acknowledge a Slack interaction."""
        raise NotImplementedError("Slack adapter is a stub.")

    def get_capabilities(self) -> PlatformCapabilities:
        """Return Slack platform capabilities."""
        return PlatformCapabilities(
            max_message_length=40000,
            supports_buttons=True,
            supports_inline_buttons=True,
            supports_message_editing=True,
            supports_markdown=True,
            supports_html=False,
            button_text_max_length=75,
        )
