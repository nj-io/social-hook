"""Tests for social_hook.setup.oauth — PKCE flow, token exchange, save, validate."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from social_hook.setup.oauth import (
    OAUTH_PLATFORMS,
    _build_auth_url,
    _CallbackHandler,
    _exchange_code,
    _generate_pkce,
    _save_tokens,
    run_pkce_flow,
    validate_token,
)


class TestOAuthPlatformConfigRegistry:
    def test_x_in_registry(self):
        assert "x" in OAUTH_PLATFORMS

    def test_linkedin_in_registry(self):
        assert "linkedin" in OAUTH_PLATFORMS

    def test_x_has_required_fields(self):
        cfg = OAUTH_PLATFORMS["x"]
        assert cfg.auth_url
        assert cfg.token_url
        assert cfg.scopes
        assert cfg.default_port > 0

    def test_linkedin_has_required_fields(self):
        cfg = OAUTH_PLATFORMS["linkedin"]
        assert cfg.auth_url
        assert cfg.token_url
        assert cfg.scopes
        assert cfg.default_port > 0


class TestGeneratePkce:
    def test_returns_non_empty_strings(self):
        verifier, challenge = _generate_pkce()
        assert isinstance(verifier, str) and len(verifier) > 0
        assert isinstance(challenge, str) and len(challenge) > 0

    def test_verifier_length(self):
        verifier, _ = _generate_pkce()
        # RFC 7636: verifier must be 43-128 chars
        assert 43 <= len(verifier) <= 128

    def test_challenge_is_base64url(self):
        _, challenge = _generate_pkce()
        # base64url characters only (no padding)
        import re

        assert re.fullmatch(r"[A-Za-z0-9_-]+", challenge)


class TestBuildAuthUrl:
    def test_contains_expected_params(self):
        url = _build_auth_url(
            client_id="test_client_id",
            state="test_state",
            code_challenge="test_challenge",
            redirect_uri="http://localhost:4000/callback",
            platform="x",
        )
        assert "client_id=test_client_id" in url
        assert "redirect_uri=" in url
        assert "scope=" in url
        assert "state=test_state" in url
        assert "code_challenge=test_challenge" in url
        assert url.startswith(OAUTH_PLATFORMS["x"].auth_url)

    def test_linkedin_url_uses_linkedin_base(self):
        url = _build_auth_url(
            client_id="li_client",
            state="s",
            code_challenge="c",
            redirect_uri="http://localhost:4001/callback",
            platform="linkedin",
        )
        assert url.startswith(OAUTH_PLATFORMS["linkedin"].auth_url)


class TestValidateToken:
    @patch("social_hook.setup.oauth.requests.get")
    def test_validate_token_x(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": {"username": "testuser"}}
        mock_get.return_value = mock_resp

        result = validate_token("x", "fake_token")
        assert result == "testuser"
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args
        assert "Bearer fake_token" in call_kwargs[1]["headers"]["Authorization"]

    @patch("social_hook.setup.oauth.requests.get")
    def test_validate_token_linkedin(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"name": "LinkedIn User", "email": "user@example.com"}
        mock_get.return_value = mock_resp

        result = validate_token("linkedin", "fake_token")
        assert result == "LinkedIn User"
        mock_get.assert_called_once()

    def test_validate_token_unknown_platform(self):
        result = validate_token("bluesky", "fake_token")
        assert result == ""

    @patch("social_hook.setup.oauth.requests.get")
    def test_validate_token_non_200(self, mock_get):
        """Non-200 response returns empty string."""
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_get.return_value = mock_resp

        result = validate_token("x", "bad_token")
        assert result == ""

    @patch("social_hook.setup.oauth.requests.get")
    def test_validate_token_exception_returns_empty(self, mock_get):
        """Network exception returns empty string (non-fatal)."""
        mock_get.side_effect = Exception("connection error")

        result = validate_token("x", "tok")
        assert result == ""


# =============================================================================
# _exchange_code
# =============================================================================


class TestExchangeCode:
    @patch("social_hook.setup.oauth.requests.post")
    def test_exchange_code_with_secret(self, mock_post):
        """With client_secret, uses HTTP Basic Auth (client_id, client_secret)."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        resp = _exchange_code(
            code="auth_code",
            code_verifier="verifier123",
            client_id="cid",
            client_secret="csec",
            redirect_uri="http://localhost:4000/callback",
            platform="x",
        )

        assert resp.status_code == 200
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        # Should use Basic Auth tuple
        assert call_kwargs[1]["auth"] == ("cid", "csec")
        # Data should NOT include client_id (it's in auth)
        data = call_kwargs[1]["data"]
        assert "client_id" not in data
        assert data["code"] == "auth_code"
        assert data["code_verifier"] == "verifier123"
        assert data["grant_type"] == "authorization_code"

    @patch("social_hook.setup.oauth.requests.post")
    def test_exchange_code_without_secret(self, mock_post):
        """Without client_secret, sends client_id in POST body, no auth."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        _exchange_code(
            code="code",
            code_verifier="v",
            client_id="cid",
            client_secret="",
            redirect_uri="http://localhost:4000/callback",
            platform="x",
        )

        call_kwargs = mock_post.call_args
        assert call_kwargs[1]["auth"] is None
        assert call_kwargs[1]["data"]["client_id"] == "cid"

    def test_exchange_code_unknown_platform(self):
        """Unknown platform raises ValueError."""
        with pytest.raises(ValueError, match="Unknown OAuth platform"):
            _exchange_code("c", "v", "cid", "cs", "http://x/cb", platform="bluesky")

    @patch("social_hook.setup.oauth.requests.post")
    def test_exchange_code_linkedin(self, mock_post):
        """LinkedIn exchange posts to LinkedIn token URL."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        _exchange_code(
            code="li_code",
            code_verifier="v",
            client_id="li_cid",
            client_secret="li_csec",
            redirect_uri="http://localhost:4001/callback",
            platform="linkedin",
        )

        call_url = mock_post.call_args[0][0]
        assert "linkedin.com" in call_url


# =============================================================================
# _save_tokens
# =============================================================================


class TestSaveTokens:
    @patch("social_hook.setup.oauth.save_tokens_to_db")
    @patch("social_hook.setup.oauth.init_database")
    @patch("social_hook.setup.oauth.get_db_path")
    def test_save_tokens_calls_db(self, mock_get_path, mock_init_db, mock_save):
        """_save_tokens initializes DB and saves tokens with computed expires_at."""
        mock_get_path.return_value = "/tmp/test.db"

        _save_tokens("access123", "refresh456", expires_in=3600, platform="x")

        mock_get_path.assert_called_once()
        mock_init_db.assert_called_once_with("/tmp/test.db")
        mock_save.assert_called_once()

        args = mock_save.call_args[0]
        assert args[0] == "/tmp/test.db"  # db_path
        assert args[1] == "x"  # account_name (== platform for now)
        assert args[2] == "x"  # platform
        assert args[3] == "access123"  # access_token
        assert args[4] == "refresh456"  # refresh_token
        # expires_at is a datetime string — just check it's non-empty
        assert len(args[5]) > 0

    @patch("social_hook.setup.oauth.save_tokens_to_db")
    @patch("social_hook.setup.oauth.init_database")
    @patch("social_hook.setup.oauth.get_db_path")
    def test_save_tokens_no_refresh_token(self, mock_get_path, mock_init_db, mock_save):
        """Missing refresh_token defaults to empty string."""
        mock_get_path.return_value = "/tmp/t.db"

        _save_tokens("access", None, platform="linkedin")

        args = mock_save.call_args[0]
        assert args[4] == ""  # refresh_token should be ""


# =============================================================================
# run_pkce_flow — happy path
# =============================================================================


class TestRunPkceFlow:
    """Tests for run_pkce_flow.

    Since sys/termios/tty are imported locally inside run_pkce_flow, we patch
    sys.stdin at the global sys module level and use the non-TTY code path
    (stdin.isatty() returns False).
    """

    def _run_with_mocks(self, *, exchange_resp=None, extra_patches=None):
        """Helper: run run_pkce_flow with heavy mocking.

        Returns (result_or_exception, mock_exchange, mock_save, mock_validate).
        """
        extra_patches = extra_patches or {}

        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False

        mock_exchange = MagicMock()
        if exchange_resp is not None:
            mock_exchange.return_value = exchange_resp

        mock_save = MagicMock()
        mock_validate = MagicMock(return_value=extra_patches.get("username", ""))

        mock_thread_inst = MagicMock()
        mock_thread_inst.is_alive.return_value = False

        with (
            patch.object(sys, "stdin", mock_stdin),
            patch("social_hook.setup.oauth.http.server.HTTPServer", return_value=MagicMock()),
            patch("social_hook.setup.oauth.threading.Thread", return_value=mock_thread_inst),
            patch("social_hook.setup.oauth.secrets.token_urlsafe", return_value="fixed_state"),
            patch("social_hook.setup.oauth._exchange_code", mock_exchange),
            patch("social_hook.setup.oauth._save_tokens", mock_save),
            patch("social_hook.setup.oauth.validate_token", mock_validate),
        ):
            return mock_exchange, mock_save, mock_validate

    def test_unknown_platform_raises(self):
        """Unknown platform raises ValueError immediately."""
        with pytest.raises(ValueError, match="Unknown OAuth platform"):
            run_pkce_flow("bluesky", "cid", "csec")

    def test_happy_path(self):
        """Happy path: PKCE generated, code exchanged, tokens saved, username returned."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "at_abc",
            "refresh_token": "rt_xyz",
            "expires_in": 7200,
        }

        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False

        # Simulate the callback arriving during server_thread.join()
        def simulate_callback(**kwargs):
            _CallbackHandler.code = "auth_code_123"
            _CallbackHandler.state = "fixed_state"
            _CallbackHandler.error = None

        mock_thread_inst = MagicMock()
        mock_thread_inst.is_alive.return_value = False
        mock_thread_inst.join.side_effect = simulate_callback

        mock_exchange = MagicMock(return_value=mock_resp)
        mock_save = MagicMock()
        mock_validate = MagicMock(return_value="testuser")

        with (
            patch.object(sys, "stdin", mock_stdin),
            patch("social_hook.setup.oauth.http.server.HTTPServer", return_value=MagicMock()),
            patch("social_hook.setup.oauth.threading.Thread", return_value=mock_thread_inst),
            patch("social_hook.setup.oauth.secrets.token_urlsafe", return_value="fixed_state"),
            patch("social_hook.setup.oauth._exchange_code", mock_exchange),
            patch("social_hook.setup.oauth._save_tokens", mock_save),
            patch("social_hook.setup.oauth.validate_token", mock_validate),
        ):
            result = run_pkce_flow("x", "client_id", "client_secret", port=4000)

        assert result["access_token"] == "at_abc"
        assert result["refresh_token"] == "rt_xyz"
        assert result["expires_in"] == 7200
        assert result["username"] == "testuser"

        mock_exchange.assert_called_once()
        mock_save.assert_called_once_with("at_abc", "rt_xyz", 7200, platform="x")
        mock_validate.assert_called_once_with("x", "at_abc")

    def test_exchange_non_200_raises(self):
        """Token exchange returning non-200 raises RuntimeError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "invalid_grant"

        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False

        def simulate_callback(**kwargs):
            _CallbackHandler.code = "some_code"
            _CallbackHandler.state = "fixed_state"
            _CallbackHandler.error = None

        mock_thread_inst = MagicMock()
        mock_thread_inst.is_alive.return_value = False
        mock_thread_inst.join.side_effect = simulate_callback

        with (
            patch.object(sys, "stdin", mock_stdin),
            patch("social_hook.setup.oauth.http.server.HTTPServer", return_value=MagicMock()),
            patch("social_hook.setup.oauth.threading.Thread", return_value=mock_thread_inst),
            patch("social_hook.setup.oauth.secrets.token_urlsafe", return_value="fixed_state"),
            patch("social_hook.setup.oauth._exchange_code", return_value=mock_resp),
            pytest.raises(RuntimeError, match="Token exchange failed"),
        ):
            run_pkce_flow("x", "cid", "csec", port=4000)

    def test_missing_code_raises(self):
        """No authorization code received raises RuntimeError."""
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False
        mock_thread_inst = MagicMock()
        mock_thread_inst.is_alive.return_value = False

        _CallbackHandler.code = None
        _CallbackHandler.state = None
        _CallbackHandler.error = None

        with (
            patch.object(sys, "stdin", mock_stdin),
            patch("social_hook.setup.oauth.http.server.HTTPServer", return_value=MagicMock()),
            patch("social_hook.setup.oauth.threading.Thread", return_value=mock_thread_inst),
            pytest.raises(RuntimeError, match="No authorization code received"),
        ):
            run_pkce_flow("x", "cid", "csec", port=4000)

    def test_error_callback_raises(self):
        """Authorization error in callback raises RuntimeError."""
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False

        def simulate_error_callback(**kwargs):
            _CallbackHandler.code = None
            _CallbackHandler.state = None
            _CallbackHandler.error = "access_denied"

        mock_thread_inst = MagicMock()
        mock_thread_inst.is_alive.return_value = False
        mock_thread_inst.join.side_effect = simulate_error_callback

        with (
            patch.object(sys, "stdin", mock_stdin),
            patch("social_hook.setup.oauth.http.server.HTTPServer", return_value=MagicMock()),
            patch("social_hook.setup.oauth.threading.Thread", return_value=mock_thread_inst),
            pytest.raises(RuntimeError, match="Authorization failed"),
        ):
            run_pkce_flow("x", "cid", "csec", port=4000)

    def test_state_mismatch_raises(self):
        """State mismatch between callback and expected raises RuntimeError."""
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False

        def simulate_wrong_state(**kwargs):
            _CallbackHandler.code = "code"
            _CallbackHandler.state = "wrong_state"
            _CallbackHandler.error = None

        mock_thread_inst = MagicMock()
        mock_thread_inst.is_alive.return_value = False
        mock_thread_inst.join.side_effect = simulate_wrong_state

        with (
            patch.object(sys, "stdin", mock_stdin),
            patch("social_hook.setup.oauth.http.server.HTTPServer", return_value=MagicMock()),
            patch("social_hook.setup.oauth.threading.Thread", return_value=mock_thread_inst),
            patch("social_hook.setup.oauth.secrets.token_urlsafe", return_value="expected_state"),
            pytest.raises(RuntimeError, match="State mismatch"),
        ):
            run_pkce_flow("x", "cid", "csec", port=4000)


# =============================================================================
# _build_auth_url — unknown platform
# =============================================================================


class TestBuildAuthUrlErrors:
    def test_unknown_platform_raises(self):
        with pytest.raises(ValueError, match="Unknown OAuth platform"):
            _build_auth_url("cid", "state", "challenge", "http://x/cb", platform="foo")
