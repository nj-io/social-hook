"""Tests for OAuth 2.0 token management (adapters/auth.py)."""

import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests as requests_lib

from social_hook.adapters.auth import (
    _DT_FORMAT,
    TokenRefreshError,
    get_tokens,
    is_expired,
    refresh_and_get_token,
    save_tokens,
)


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


def _future(seconds=3600):
    """Return an ISO 8601 UTC timestamp in the future."""
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).strftime(_DT_FORMAT)


def _past(seconds=3600):
    """Return an ISO 8601 UTC timestamp in the past."""
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).strftime(_DT_FORMAT)


class TestSaveAndGetTokens:
    def test_round_trip(self, db_path):
        save_tokens(db_path, "x", "x", "access123", "refresh456", "2026-03-23T15:00:00Z")
        result = get_tokens(db_path, "x")
        assert result is not None
        assert result["access_token"] == "access123"
        assert result["refresh_token"] == "refresh456"
        assert result["expires_at"] == "2026-03-23T15:00:00Z"

    def test_get_tokens_missing(self, db_path):
        result = get_tokens(db_path, "nonexistent")
        assert result is None

    def test_save_updates_existing(self, db_path):
        save_tokens(db_path, "x", "x", "old_access", "old_refresh", "2026-03-23T15:00:00Z")
        save_tokens(db_path, "x", "x", "new_access", "new_refresh", "2026-03-23T16:00:00Z")
        result = get_tokens(db_path, "x")
        assert result["access_token"] == "new_access"
        assert result["refresh_token"] == "new_refresh"

    def test_save_sets_updated_at(self, db_path):
        save_tokens(db_path, "x", "x", "access", "refresh", "2026-03-23T15:00:00Z")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT updated_at FROM oauth_tokens WHERE account_name = 'x'"
        ).fetchone()
        conn.close()
        assert row["updated_at"] is not None
        # Should be a valid ISO 8601 timestamp
        datetime.strptime(row["updated_at"], _DT_FORMAT)

    def test_platform_field_stored(self, db_path):
        save_tokens(db_path, "my-account", "linkedin", "access", "refresh", "2026-03-23T15:00:00Z")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT platform FROM oauth_tokens WHERE account_name = 'my-account'"
        ).fetchone()
        conn.close()
        assert row["platform"] == "linkedin"


class TestIsExpired:
    def test_future_not_expired(self):
        assert not is_expired(_future(3600))

    def test_past_expired(self):
        assert is_expired(_past(3600))

    def test_buffer(self):
        # 30 seconds from now with 60 second buffer = expired
        almost_expired = _future(30)
        assert is_expired(almost_expired, buffer_seconds=60)

    def test_no_buffer(self):
        # 30 seconds from now with 0 buffer = not expired
        almost_expired = _future(30)
        assert not is_expired(almost_expired, buffer_seconds=0)

    def test_invalid_format_treated_as_expired(self):
        assert is_expired("not-a-date")


class TestRefreshAndGetToken:
    def test_valid_token_returned_without_http(self, db_path):
        save_tokens(db_path, "x", "x", "valid_token", "refresh_tok", _future(3600))
        token = refresh_and_get_token(
            db_path,
            "x",
            "x",
            client_id="client_id",
            client_secret="client_secret",
            token_url="https://example.com/token",
        )
        assert token == "valid_token"

    @patch("social_hook.adapters.auth.requests.post")
    def test_expired_token_refreshed(self, mock_post, db_path):
        save_tokens(db_path, "x", "x", "old_token", "refresh_tok", _past(3600))

        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "access_token": "new_token",
                "refresh_token": "new_refresh",
                "expires_in": 7200,
            },
        )

        token = refresh_and_get_token(
            db_path,
            "x",
            "x",
            client_id="client_id",
            client_secret="client_secret",
            token_url="https://api.x.com/2/oauth2/token",
        )
        assert token == "new_token"

        # Verify saved to DB
        result = get_tokens(db_path, "x")
        assert result["access_token"] == "new_token"
        assert result["refresh_token"] == "new_refresh"

        # Verify correct request
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[1]["data"]["grant_type"] == "refresh_token"
        assert call_kwargs[1]["data"]["refresh_token"] == "refresh_tok"

    def test_no_tokens_raises(self, db_path):
        with pytest.raises(TokenRefreshError, match="No tokens found"):
            refresh_and_get_token(
                db_path,
                "x",
                "x",
                client_id="cid",
                client_secret="csec",
                token_url="https://example.com/token",
            )

    @patch("social_hook.adapters.auth.requests.post")
    def test_invalid_grant_deletes_tokens(self, mock_post, db_path):
        save_tokens(db_path, "x", "x", "old_token", "refresh_tok", _past(3600))

        mock_post.return_value = MagicMock(
            status_code=400,
            json=lambda: {"error": "invalid_grant"},
            text='{"error": "invalid_grant"}',
        )

        with pytest.raises(TokenRefreshError, match="Token revoked"):
            refresh_and_get_token(
                db_path,
                "x",
                "x",
                client_id="cid",
                client_secret="csec",
                token_url="https://example.com/token",
            )

        # Tokens should be deleted
        assert get_tokens(db_path, "x") is None

    @patch("social_hook.adapters.auth.requests.post")
    def test_network_error_preserves_tokens(self, mock_post, db_path):
        save_tokens(db_path, "x", "x", "old_token", "refresh_tok", _past(3600))
        mock_post.side_effect = requests_lib.ConnectionError("network down")

        with pytest.raises(TokenRefreshError, match="Network error"):
            refresh_and_get_token(
                db_path,
                "x",
                "x",
                client_id="cid",
                client_secret="csec",
                token_url="https://example.com/token",
            )

        # Tokens should NOT be deleted
        assert get_tokens(db_path, "x") is not None

    @patch("social_hook.adapters.auth.requests.post")
    def test_5xx_preserves_tokens(self, mock_post, db_path):
        save_tokens(db_path, "x", "x", "old_token", "refresh_tok", _past(3600))

        mock_post.return_value = MagicMock(
            status_code=500,
            text="Internal Server Error",
        )

        with pytest.raises(TokenRefreshError, match="HTTP 500"):
            refresh_and_get_token(
                db_path,
                "x",
                "x",
                client_id="cid",
                client_secret="csec",
                token_url="https://example.com/token",
            )

        # Tokens should NOT be deleted
        assert get_tokens(db_path, "x") is not None
