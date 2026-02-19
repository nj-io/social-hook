"""Factory for creating messaging platform adapters.

Mirrors llm/factory.py pattern: lazy imports, ConfigError only.

REUSABILITY: Only imports ConfigError from social_hook.errors.
Replace with your own exception for copy-paste reuse.
"""

from social_hook.errors import ConfigError
from social_hook.messaging.base import MessagingAdapter

KNOWN_PLATFORMS = {"telegram", "slack"}


def create_adapter(platform: str, config) -> MessagingAdapter:
    """Create the appropriate messaging adapter.

    Args:
        platform: Platform name ("telegram", "slack")
        config: Config object with .env dict

    Returns:
        Configured MessagingAdapter instance

    Raises:
        ConfigError: If platform is unknown or required config is missing
    """
    if platform == "telegram":
        from social_hook.messaging.telegram import TelegramAdapter

        token = config.env.get("TELEGRAM_BOT_TOKEN", "")
        if not token:
            raise ConfigError("TELEGRAM_BOT_TOKEN required for Telegram")
        return TelegramAdapter(token=token)

    elif platform == "slack":
        from social_hook.messaging.slack import SlackAdapter

        token = config.env.get("SLACK_BOT_TOKEN", "")
        if not token:
            raise ConfigError("SLACK_BOT_TOKEN required for Slack")
        return SlackAdapter(token=token)

    raise ConfigError(f"Unknown messaging platform: {platform}")
