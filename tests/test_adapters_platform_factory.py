"""Tests for social_hook.adapters.platform.factory — create_adapter routing."""

from unittest.mock import MagicMock, patch

import pytest

from social_hook.errors import ConfigError


def _mock_config(env=None, platforms=None):
    """Build a mock Config object with .env dict and .platforms dict."""
    config = MagicMock()
    config.env = env or {}
    config.platforms = platforms or {}
    return config


class TestCreateXAdapter:
    @patch("social_hook.adapters.platform.factory.auth.refresh_and_get_token")
    def test_create_x_adapter_from_db(self, mock_refresh):
        """X adapter created with Bearer token from DB refresh."""
        from social_hook.adapters.platform.factory import create_adapter

        mock_refresh.return_value = "test-access-token"
        x_platform_config = MagicMock()
        x_platform_config.account_tier = "free"

        config = _mock_config(
            env={"X_CLIENT_ID": "cid", "X_CLIENT_SECRET": "csec"},
            platforms={"x": x_platform_config},
        )

        adapter = create_adapter("x", config, db_path="/tmp/test.db")

        from social_hook.adapters.platform.x import XAdapter

        assert isinstance(adapter, XAdapter)
        assert adapter.access_token == "test-access-token"
        mock_refresh.assert_called_once()
        call_kwargs = mock_refresh.call_args
        assert call_kwargs[0][0] == "/tmp/test.db"  # db_path
        assert call_kwargs[1]["client_id"] == "cid"

    def test_create_x_adapter_missing_client_id(self):
        """Missing X_CLIENT_ID raises ConfigError."""
        from social_hook.adapters.platform.factory import create_adapter

        config = _mock_config(env={"X_CLIENT_SECRET": "csec"})

        with pytest.raises(ConfigError, match="X_CLIENT_ID"):
            create_adapter("x", config, db_path="/tmp/test.db")

    def test_create_x_adapter_missing_db_path(self):
        """db_path=None raises ConfigError for X adapter."""
        from social_hook.adapters.platform.factory import create_adapter

        config = _mock_config(env={"X_CLIENT_ID": "cid", "X_CLIENT_SECRET": "csec"})

        with pytest.raises(ConfigError, match="db_path required"):
            create_adapter("x", config, db_path=None)

    @patch("social_hook.adapters.platform.factory.auth.refresh_and_get_token")
    def test_x_adapter_uses_tier_from_config(self, mock_refresh):
        """X adapter picks up account_tier from platform config."""
        from social_hook.adapters.platform.factory import create_adapter

        mock_refresh.return_value = "tok"
        x_cfg = MagicMock()
        x_cfg.account_tier = "basic"

        config = _mock_config(
            env={"X_CLIENT_ID": "cid", "X_CLIENT_SECRET": "csec"},
            platforms={"x": x_cfg},
        )
        adapter = create_adapter("x", config, db_path="/tmp/t.db")
        assert adapter.tier == "basic"


class TestCreateLinkedInAdapter:
    def test_create_linkedin_adapter(self):
        """LinkedIn adapter created with access token from env."""
        from social_hook.adapters.platform.factory import create_adapter
        from social_hook.adapters.platform.linkedin import LinkedInAdapter

        config = _mock_config(env={"LINKEDIN_ACCESS_TOKEN": "li-tok-123"})
        adapter = create_adapter("linkedin", config)

        assert isinstance(adapter, LinkedInAdapter)

    def test_create_linkedin_missing_token(self):
        """Missing LINKEDIN_ACCESS_TOKEN raises ConfigError."""
        from social_hook.adapters.platform.factory import create_adapter

        config = _mock_config(env={})

        with pytest.raises(ConfigError, match="LinkedIn access token"):
            create_adapter("linkedin", config)


class TestCreateUnknownPlatform:
    def test_unknown_platform_raises(self):
        """Unknown platform name raises ConfigError."""
        from social_hook.adapters.platform.factory import create_adapter

        config = _mock_config()
        with pytest.raises(ConfigError, match="Unknown platform"):
            create_adapter("bluesky", config)
