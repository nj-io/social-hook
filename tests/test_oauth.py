"""Tests for non-HTTP parts of social_hook.setup.oauth."""

from unittest.mock import MagicMock, patch

from social_hook.setup.oauth import (
    OAUTH_PLATFORMS,
    _build_auth_url,
    _generate_pkce,
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
