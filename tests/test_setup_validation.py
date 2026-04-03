"""Tests for setup validation (T23)."""

from unittest.mock import MagicMock, patch

from social_hook.setup.validation import (
    exchange_linkedin_code,
    get_linkedin_auth_url,
    validate_anthropic_key,
    validate_media_gen,
    validate_telegram_bot,
    validate_x_api,
)


class TestValidateAnthropicKey:
    """Tests for validate_anthropic_key."""

    @patch("social_hook.setup.validation.requests.post")
    def test_valid_key(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        success, msg = validate_anthropic_key("sk-ant-valid-key")
        assert success is True
        assert "valid" in msg.lower()

    @patch("social_hook.setup.validation.requests.post")
    def test_invalid_key(self, mock_post):
        mock_post.return_value = MagicMock(status_code=401)
        success, msg = validate_anthropic_key("sk-ant-invalid")
        assert success is False
        assert "invalid" in msg.lower()

    @patch("social_hook.setup.validation.requests.post")
    def test_server_error(self, mock_post):
        mock_post.return_value = MagicMock(status_code=500)
        success, msg = validate_anthropic_key("sk-ant-key")
        assert success is False

    @patch("social_hook.setup.validation.requests.post")
    def test_network_error(self, mock_post):
        import requests

        mock_post.side_effect = requests.RequestException("timeout")
        success, msg = validate_anthropic_key("sk-ant-key")
        assert success is False
        assert "connection" in msg.lower() or "error" in msg.lower()


class TestValidateTelegramBot:
    """Tests for validate_telegram_bot."""

    @patch("social_hook.setup.validation.requests.get")
    def test_valid_bot(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"result": {"username": "test_bot"}},
        )
        success, msg = validate_telegram_bot("123:ABC")
        assert success is True
        assert "test_bot" in msg

    @patch("social_hook.setup.validation.requests.get")
    def test_invalid_token(self, mock_get):
        mock_get.return_value = MagicMock(status_code=401)
        success, msg = validate_telegram_bot("invalid")
        assert success is False

    @patch("social_hook.setup.validation.requests.get")
    def test_network_error(self, mock_get):
        import requests

        mock_get.side_effect = requests.RequestException()
        success, msg = validate_telegram_bot("123:ABC")
        assert success is False


class TestValidateXApi:
    """Tests for validate_x_api."""

    @patch("social_hook.setup.validation.requests.get")
    def test_valid_credentials(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"data": {"username": "testuser"}},
        )
        success, msg = validate_x_api("test-access-token")
        assert success is True
        assert "testuser" in msg

    @patch("social_hook.setup.validation.requests.get")
    def test_invalid_credentials(self, mock_get):
        mock_get.return_value = MagicMock(status_code=401)
        success, msg = validate_x_api("bad-token")
        assert success is False


class TestLinkedInAuth:
    """Tests for LinkedIn OAuth helpers."""

    def test_auth_url_format(self):
        url = get_linkedin_auth_url("client123", "http://localhost:8080")
        assert "linkedin.com/oauth/v2/authorization" in url
        assert "client123" in url
        assert "localhost" in url

    @patch("social_hook.setup.validation.requests.post")
    def test_exchange_code_success(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"access_token": "token_abc"},
        )
        success, token = exchange_linkedin_code("id", "secret", "code", "http://localhost")
        assert success is True
        assert token == "token_abc"

    @patch("social_hook.setup.validation.requests.post")
    def test_exchange_code_failure(self, mock_post):
        mock_post.return_value = MagicMock(status_code=400)
        success, msg = exchange_linkedin_code("id", "secret", "code", "http://localhost")
        assert success is False


class TestValidateMediaGen:
    """Tests for validate_media_gen."""

    @patch("social_hook.setup.validation.requests.post")
    def test_nano_banana_pro_valid(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        success, msg = validate_media_gen("nano_banana_pro", "valid-key")
        assert success is True
        assert "Connected" in msg

    @patch("social_hook.setup.validation.requests.post")
    def test_nano_banana_pro_invalid_key(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=400,
            text="API_KEY_INVALID",
        )
        success, msg = validate_media_gen("nano_banana_pro", "bad-key")
        assert success is False
        assert "Invalid" in msg

    @patch("social_hook.setup.validation.requests.post")
    def test_nano_banana_pro_forbidden(self, mock_post):
        mock_post.return_value = MagicMock(status_code=403)
        success, msg = validate_media_gen("nano_banana_pro", "key")
        assert success is False
        assert "not authorized" in msg.lower()

    @patch("social_hook.setup.validation.requests.post")
    def test_nano_banana_pro_network_error(self, mock_post):
        import requests

        mock_post.side_effect = requests.RequestException("timeout")
        success, msg = validate_media_gen("nano_banana_pro", "key")
        assert success is False
        assert "connection" in msg.lower() or "error" in msg.lower()

    def test_unknown_service(self):
        success, msg = validate_media_gen("nonexistent", "key")
        assert success is False
        assert "Unknown" in msg
