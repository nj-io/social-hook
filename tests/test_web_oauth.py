"""Tests for OAuth web endpoints in social_hook.web.server.

These tests use FastAPI's TestClient to exercise the OAuth API endpoints
with mocked dependencies (credentials, token storage, validation).
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from social_hook.web.server import app


async def _noop_bridge_loop():
    """No-op replacement for _event_bridge_loop during tests."""


@pytest.fixture
def client():
    """Create a TestClient, mocking the lifespan DB/background-task deps."""
    with (
        patch("social_hook.web.server.get_db_path", return_value="/tmp/test_oauth.db"),
        patch("social_hook.web.server.init_database"),
        patch("social_hook.web.server._cleanup_stale_tasks"),
        patch("social_hook.web.server._event_bridge_loop", _noop_bridge_loop),
        TestClient(app) as c,
    ):
        yield c


class TestAuthorizeEndpoint:
    @patch(
        "social_hook.web.server._get_oauth_credentials",
        return_value=("test_client_id", "test_secret"),
    )
    def test_authorize_returns_auth_url(self, _mock_creds, client):
        resp = client.get("/api/oauth/x/authorize")
        assert resp.status_code == 200
        data = resp.json()
        assert "auth_url" in data
        assert "state" in data
        assert "callback_url" in data
        assert "test_client_id" in data["auth_url"]

    def test_authorize_unknown_platform(self, client):
        resp = client.get("/api/oauth/bluesky/authorize")
        assert resp.status_code == 400


class TestStatusEndpoint:
    @patch("social_hook.web.server.get_db_path", return_value="/tmp/test_oauth.db")
    @patch("social_hook.setup.oauth.validate_token", return_value="")
    @patch("social_hook.adapters.auth.get_tokens", return_value=None)
    def test_status_not_connected(self, _mock_get, _mock_validate, _mock_db, client):
        resp = client.get("/api/oauth/x/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is False

    @patch("social_hook.web.server.get_db_path", return_value="/tmp/test_oauth.db")
    @patch("social_hook.setup.oauth.validate_token", return_value="testuser")
    @patch(
        "social_hook.adapters.auth.get_tokens",
        return_value={
            "access_token": "tok",
            "refresh_token": "ref",
            "expires_at": "2099-01-01T00:00:00Z",
        },
    )
    def test_status_connected(self, _mock_get, _mock_validate, _mock_db, client):
        resp = client.get("/api/oauth/x/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is True
        assert data["username"] == "testuser"


class TestDisconnectEndpoint:
    @patch("social_hook.web.server.get_db_path", return_value="/tmp/test_oauth.db")
    @patch("social_hook.adapters.auth.delete_tokens", return_value=True)
    @patch("social_hook.scheduler._registry")
    def test_disconnect(self, _mock_registry, _mock_delete, _mock_db, client):
        resp = client.delete("/api/oauth/x/disconnect")
        assert resp.status_code == 200
        data = resp.json()
        assert data["disconnected"] is True
