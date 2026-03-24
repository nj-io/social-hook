"""Tests for create_adapter_from_account() and resolve_platform_creds()."""

import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from social_hook.adapters.auth import _DT_FORMAT, save_tokens
from social_hook.adapters.platform.factory import (
    create_adapter_from_account,
    resolve_platform_creds,
)
from social_hook.config.targets import AccountConfig, PlatformCredentialConfig
from social_hook.errors import ConfigError


def _future(seconds=3600):
    """Return an ISO 8601 UTC timestamp in the future."""
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).strftime(_DT_FORMAT)


@pytest.fixture
def db_path(tmp_path):
    """Create a temp DB with oauth_tokens table."""
    path = str(tmp_path / "test.db")
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE oauth_tokens (
            account_name TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            access_token TEXT NOT NULL,
            refresh_token TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    conn.commit()
    conn.close()
    return path


class TestResolvePlatformCreds:
    def test_explicit_app_reference(self):
        account = AccountConfig(platform="x", app="my-x-app")
        creds = {
            "my-x-app": PlatformCredentialConfig(
                platform="x", client_id="cid", client_secret="csec"
            ),
        }
        result = resolve_platform_creds(account, creds)
        assert result.client_id == "cid"

    def test_explicit_app_not_found(self):
        account = AccountConfig(platform="x", app="nonexistent")
        creds = {}
        with pytest.raises(ConfigError, match="unknown app"):
            resolve_platform_creds(account, creds)

    def test_default_first_matching_platform(self):
        account = AccountConfig(platform="linkedin")
        creds = {
            "x-app": PlatformCredentialConfig(
                platform="x", client_id="x-cid", client_secret="x-csec"
            ),
            "li-app": PlatformCredentialConfig(
                platform="linkedin", client_id="li-cid", client_secret="li-csec"
            ),
        }
        result = resolve_platform_creds(account, creds)
        assert result.client_id == "li-cid"

    def test_no_matching_platform(self):
        account = AccountConfig(platform="mastodon")
        creds = {
            "x-app": PlatformCredentialConfig(platform="x", client_id="cid", client_secret="csec"),
        }
        with pytest.raises(ConfigError, match="No platform_credentials"):
            resolve_platform_creds(account, creds)


class TestCreateAdapterFromAccount:
    def test_x_adapter_created(self, db_path):
        """X adapter is created with correct tier from AccountConfig."""
        save_tokens(db_path, "my-x", "x", "access_tok", "refresh_tok", _future())
        account = AccountConfig(platform="x", tier="basic")
        creds = PlatformCredentialConfig(platform="x", client_id="cid", client_secret="csec")

        adapter = create_adapter_from_account("my-x", account, creds, {}, db_path)

        from social_hook.adapters.platform.x import XAdapter

        assert isinstance(adapter, XAdapter)
        assert adapter.tier == "basic"
        assert adapter.access_token == "access_tok"

    def test_x_adapter_default_tier(self, db_path):
        """X adapter defaults to 'free' tier when account.tier is None."""
        save_tokens(db_path, "my-x", "x", "access_tok", "refresh_tok", _future())
        account = AccountConfig(platform="x", tier=None)
        creds = PlatformCredentialConfig(platform="x", client_id="cid", client_secret="csec")

        adapter = create_adapter_from_account("my-x", account, creds, {}, db_path)

        assert adapter.tier == "free"

    def test_x_adapter_has_token_refresher(self, db_path):
        """X adapter gets a token_refresher closure."""
        save_tokens(db_path, "my-x", "x", "access_tok", "refresh_tok", _future())
        account = AccountConfig(platform="x", tier="free")
        creds = PlatformCredentialConfig(platform="x", client_id="cid", client_secret="csec")

        adapter = create_adapter_from_account("my-x", account, creds, {}, db_path)

        assert adapter._token_refresher is not None

    def test_x_adapter_missing_client_id(self, db_path):
        account = AccountConfig(platform="x")
        creds = PlatformCredentialConfig(platform="x", client_id="", client_secret="csec")

        with pytest.raises(ConfigError, match="client_id not configured"):
            create_adapter_from_account("my-x", account, creds, {}, db_path)

    def test_linkedin_adapter_created(self, db_path):
        """LinkedIn adapter is created with token_refresher."""
        save_tokens(db_path, "my-linkedin", "linkedin", "li_access", "li_refresh", _future())
        account = AccountConfig(platform="linkedin")
        creds = PlatformCredentialConfig(
            platform="linkedin", client_id="li-cid", client_secret="li-csec"
        )

        adapter = create_adapter_from_account("my-linkedin", account, creds, {}, db_path)

        from social_hook.adapters.platform.linkedin import LinkedInAdapter

        assert isinstance(adapter, LinkedInAdapter)
        assert adapter.access_token == "li_access"
        assert adapter._token_refresher is not None

    def test_linkedin_adapter_missing_client_id(self, db_path):
        account = AccountConfig(platform="linkedin")
        creds = PlatformCredentialConfig(platform="linkedin", client_id="", client_secret="csec")

        with pytest.raises(ConfigError, match="client_id not configured"):
            create_adapter_from_account("my-linkedin", account, creds, {}, db_path)

    def test_unknown_platform_raises(self, db_path):
        account = AccountConfig(platform="mastodon")
        creds = PlatformCredentialConfig(platform="mastodon", client_id="cid", client_secret="csec")

        with pytest.raises(ConfigError, match="Unknown platform"):
            create_adapter_from_account("my-mastodon", account, creds, {}, db_path)

    def test_on_error_accepted_without_error(self, db_path):
        """on_error callback is accepted by create_adapter_from_account (reserved for future use)."""
        save_tokens(db_path, "my-x", "x", "access_tok", "refresh_tok", _future())
        account = AccountConfig(platform="x", tier="free")
        creds = PlatformCredentialConfig(platform="x", client_id="cid", client_secret="csec")
        error_cb = MagicMock()

        with patch(
            "social_hook.adapters.platform.factory.auth.refresh_and_get_token",
            return_value="mocked_token",
        ) as mock_refresh:
            adapter = create_adapter_from_account(
                "my-x", account, creds, {}, db_path, on_error=error_cb
            )

            mock_refresh.assert_called_once()
            assert adapter is not None
