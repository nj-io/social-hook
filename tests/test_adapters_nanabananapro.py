"""Tests for NanaBananaAdapter (T8).

Source: WS3_ADAPTERS.md T8 (lines 186-194)
Source: TECHNICAL_ARCHITECTURE.md lines 2074-2116
"""

import base64
from unittest.mock import MagicMock, patch

import pytest

from social_hook.adapters.media.nanabananapro import NanaBananaAdapter
from social_hook.adapters.models import MediaResult


# =============================================================================
# T8: NanaBananaAdapter
# =============================================================================


class TestNanaBananaAdapterSupports:
    """T8: NanaBananaAdapter supports() media types."""

    def test_supports_image(self):
        """supports('image') returns True."""
        adapter = NanaBananaAdapter(api_key="test_key")
        assert adapter.supports("image") is True

    def test_supports_ai_image(self):
        """supports('ai_image') returns True."""
        adapter = NanaBananaAdapter(api_key="test_key")
        assert adapter.supports("ai_image") is True

    def test_supports_nano_banana(self):
        """supports('nano_banana') returns True."""
        adapter = NanaBananaAdapter(api_key="test_key")
        assert adapter.supports("nano_banana") is True

    def test_supports_unknown(self):
        """supports('code') returns False."""
        adapter = NanaBananaAdapter(api_key="test_key")
        assert adapter.supports("code") is False


class TestNanaBananaAdapterGenerate:
    """T8: NanaBananaAdapter image generation."""

    def test_missing_prompt(self):
        """Missing 'prompt' in spec returns error."""
        adapter = NanaBananaAdapter(api_key="test_key")
        result = adapter.generate({})
        assert result.success is False
        assert "Missing" in result.error

    @patch("social_hook.adapters.media.nanabananapro.requests.post")
    def test_dry_run(self, mock_post):
        """dry_run=True returns placeholder path without API call."""
        adapter = NanaBananaAdapter(api_key="test_key")
        result = adapter.generate({"prompt": "a sunset"}, dry_run=True)
        mock_post.assert_not_called()

        assert result.success is True
        assert result.file_path is not None

    @patch("social_hook.adapters.media.nanabananapro.requests.post")
    def test_generate_success(self, mock_post, tmp_path):
        """Successful generation decodes base64 image and saves file."""
        fake_image = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        fake_b64 = base64.b64encode(fake_image).decode()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "inlineData": {
                                    "mimeType": "image/png",
                                    "data": fake_b64,
                                }
                            }
                        ]
                    }
                }
            ]
        }
        mock_post.return_value = mock_resp

        adapter = NanaBananaAdapter(api_key="test_key")
        result = adapter.generate(
            {"prompt": "a sunset over mountains"},
            output_dir=str(tmp_path),
        )

        assert result.success is True
        assert result.file_path is not None
        assert result.file_path.endswith(".png")

    @patch("social_hook.adapters.media.nanabananapro.requests.post")
    def test_generate_no_image_in_response(self, mock_post):
        """Response without image data returns error."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "I can't generate that image"}]
                    }
                }
            ]
        }
        mock_post.return_value = mock_resp

        adapter = NanaBananaAdapter(api_key="test_key")
        result = adapter.generate({"prompt": "test"})

        assert result.success is False
        assert "No image data" in result.error

    @patch("social_hook.adapters.media.nanabananapro.requests.post")
    def test_generate_api_error(self, mock_post):
        """API error returns MediaResult(success=False)."""
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.json.return_value = {
            "error": {"message": "Rate limit exceeded"}
        }
        mock_resp.text = "Rate limit exceeded"
        mock_post.return_value = mock_resp

        adapter = NanaBananaAdapter(api_key="test_key")
        result = adapter.generate({"prompt": "test"})

        assert result.success is False
        assert "Rate limit" in result.error

    @patch("social_hook.adapters.media.nanabananapro.requests.post")
    def test_generate_passes_api_key(self, mock_post):
        """API key is included in the request URL."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"candidates": []}
        mock_post.return_value = mock_resp

        adapter = NanaBananaAdapter(api_key="my_secret_key")
        adapter.generate({"prompt": "test"})

        url = mock_post.call_args.args[0]
        assert "key=my_secret_key" in url


class TestNanaBananaAdapterValidate:
    """T8: NanaBananaAdapter credential validation."""

    @patch("social_hook.adapters.media.nanabananapro.requests.post")
    def test_valid_api_key(self, mock_post):
        """Valid API key: validate() returns (True, 'connected')."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"candidates": []}
        mock_post.return_value = mock_resp

        adapter = NanaBananaAdapter(api_key="valid_key")
        success, info = adapter.validate()

        assert success is True
        assert info == "connected"

    @patch("social_hook.adapters.media.nanabananapro.requests.post")
    def test_invalid_api_key(self, mock_post):
        """Invalid API key: validate() returns (False, error)."""
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"error": {"message": "Invalid API key"}}
        mock_post.return_value = mock_resp

        adapter = NanaBananaAdapter(api_key="bad_key")
        success, info = adapter.validate()

        assert success is False
        assert "Invalid API key" in info
