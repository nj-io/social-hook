"""Tests for VCR configuration and credential filtering."""


class TestCredentialFilter:
    def test_scrub_bearer_token(self):
        from unittest.mock import MagicMock

        from scripts.e2e.vcr_config import _scrub_request_headers

        request = MagicMock()
        request.headers = {"Authorization": "Bearer sk-secret-token-123"}

        result = _scrub_request_headers(request)
        assert "sk-secret" not in result.headers["Authorization"]
        assert "REDACTED" in result.headers["Authorization"]

    def test_scrub_oauth_headers(self):
        from unittest.mock import MagicMock

        from scripts.e2e.vcr_config import _scrub_request_headers

        request = MagicMock()
        request.headers = {
            "Authorization": 'OAuth oauth_consumer_key="real_key", oauth_token="real_token", oauth_signature="real_sig"'
        }

        result = _scrub_request_headers(request)
        assert "real_key" not in result.headers["Authorization"]
        assert "real_token" not in result.headers["Authorization"]
        assert "REDACTED" in result.headers["Authorization"]

    def test_scrub_response_body_tokens(self):
        from scripts.e2e.vcr_config import _scrub_response_body

        response = {"body": {"string": b'{"access_token": "secret_value_123", "expires_in": 3600}'}}

        result = _scrub_response_body(response)
        body = result["body"]["string"]
        if isinstance(body, bytes):
            body = body.decode()
        assert "secret_value_123" not in body
        assert "REDACTED" in body

    def test_vcr_context_no_live_no_vcr(self):
        """vcr_context should yield None when vcrpy not installed and not live."""
        import scripts.e2e.vcr_config as vcr_mod

        original = vcr_mod.vcr
        try:
            vcr_mod.vcr = None
            with vcr_mod.vcr_context("x", "test_scenario", live=False) as cass:
                assert cass is None
        finally:
            vcr_mod.vcr = original

    def test_get_record_mode(self):
        from scripts.e2e.vcr_config import get_record_mode

        assert get_record_mode(live=True) == "new_episodes"
        assert get_record_mode(live=False) == "none"

    def test_test_png_exists(self):
        """Test PNG fixture should exist and be valid."""
        from pathlib import Path

        png_path = (
            Path(__file__).parent.parent / "scripts" / "e2e" / "fixtures" / "media" / "test.png"
        )
        assert png_path.exists()
        data = png_path.read_bytes()
        assert data[:4] == b"\x89PNG"
