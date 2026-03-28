"""Factory for creating messaging platform adapters.

Uses AdapterRegistry for dispatch instead of if/elif chains.
Each messaging platform has a private factory function registered
on the module-level registry.

REUSABILITY: Only imports ConfigError from social_hook.errors
and AdapterRegistry from social_hook.registry.
Replace with your own exception and registry for copy-paste reuse.
"""

from social_hook.errors import ConfigError
from social_hook.messaging.base import MessagingAdapter
from social_hook.registry import AdapterRegistry

# Module-level registry for messaging adapters
_messaging_registry = AdapterRegistry("messaging")
_registered = False

KNOWN_PLATFORMS = {"telegram", "slack", "web"}


# =============================================================================
# Per-platform factory functions
# =============================================================================


def _create_telegram(*, config=None, **_kw) -> MessagingAdapter:
    from social_hook.messaging.telegram import TelegramAdapter

    token = config.env.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise ConfigError("TELEGRAM_BOT_TOKEN required for Telegram")
    return TelegramAdapter(token=token)


def _create_slack(*, config=None, **_kw) -> MessagingAdapter:
    from social_hook.messaging.slack import SlackAdapter

    token = config.env.get("SLACK_BOT_TOKEN", "")
    if not token:
        raise ConfigError("SLACK_BOT_TOKEN required for Slack")
    return SlackAdapter(token=token)


def _create_web(*, db_path: str = "", **_kw) -> MessagingAdapter:
    from social_hook.messaging.web import WebAdapter

    if not db_path:
        raise ConfigError("db_path required for WebAdapter")
    return WebAdapter(db_path=db_path)


# =============================================================================
# Registration
# =============================================================================


def _ensure_registered():
    """Lazily register all messaging adapters."""
    global _registered
    if _registered:
        return
    _registered = True

    _messaging_registry.register("telegram", _create_telegram)
    _messaging_registry.register("slack", _create_slack)
    _messaging_registry.register("web", _create_web)


# =============================================================================
# Public API (backward-compatible)
# =============================================================================


def create_adapter(platform: str, config=None, **kwargs) -> MessagingAdapter:
    """Create the appropriate messaging adapter.

    Args:
        platform: Platform name ("telegram", "slack", "web")
        config: Config object with .env dict (optional for web)
        **kwargs: Platform-specific arguments (e.g., db_path for web)

    Returns:
        Configured MessagingAdapter instance

    Raises:
        ConfigError: If platform is unknown or required config is missing
    """
    _ensure_registered()

    if not _messaging_registry.has(platform):
        raise ConfigError(f"Unknown messaging platform: {platform}")

    return _messaging_registry.create(platform, config=config, **kwargs)
