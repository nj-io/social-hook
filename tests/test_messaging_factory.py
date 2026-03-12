"""Tests for the messaging adapter factory."""

from unittest.mock import MagicMock

import pytest

from social_hook.errors import ConfigError
from social_hook.messaging.factory import KNOWN_PLATFORMS, create_adapter
from social_hook.messaging.telegram import TelegramAdapter


def _make_config(env: dict) -> MagicMock:
    """Create a mock config with the given env dict."""
    config = MagicMock()
    config.env = env
    return config


class TestCreateAdapter:
    def test_create_telegram(self):
        """Create a TelegramAdapter with token from config."""
        config = _make_config({"TELEGRAM_BOT_TOKEN": "tok_123"})
        adapter = create_adapter("telegram", config)
        assert isinstance(adapter, TelegramAdapter)
        assert adapter.token == "tok_123"
        assert adapter.platform == "telegram"

    def test_create_telegram_no_token(self):
        """Missing TELEGRAM_BOT_TOKEN raises ConfigError."""
        config = _make_config({})
        with pytest.raises(ConfigError, match="TELEGRAM_BOT_TOKEN"):
            create_adapter("telegram", config)

    def test_create_telegram_empty_token(self):
        """Empty TELEGRAM_BOT_TOKEN raises ConfigError."""
        config = _make_config({"TELEGRAM_BOT_TOKEN": ""})
        with pytest.raises(ConfigError, match="TELEGRAM_BOT_TOKEN"):
            create_adapter("telegram", config)

    def test_create_slack_no_token(self):
        """Missing SLACK_BOT_TOKEN raises ConfigError (Slack stub exists in Chunk 5)."""
        config = _make_config({})
        # Slack module doesn't exist yet, so we expect an ImportError
        # wrapped by the lazy import. This test will be updated in Chunk 5.
        with pytest.raises((ConfigError, ImportError, ModuleNotFoundError)):
            create_adapter("slack", config)

    def test_unknown_platform(self):
        """Unknown platform raises ConfigError."""
        config = _make_config({})
        with pytest.raises(ConfigError, match="Unknown messaging platform"):
            create_adapter("discord", config)


class TestKnownPlatforms:
    def test_known_platforms(self):
        """KNOWN_PLATFORMS contains expected values."""
        assert "telegram" in KNOWN_PLATFORMS
        assert "slack" in KNOWN_PLATFORMS
