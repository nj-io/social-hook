"""Tests for dry-run mode and error classification (T12).

Source: WS3_ADAPTERS.md T12 (lines 232-243)
"""

from dataclasses import dataclass
from unittest.mock import patch

from social_hook.adapters.dry_run import (
    dry_run_media_result,
    dry_run_post_result,
    dry_run_thread_result,
)
from social_hook.adapters.models import MediaResult, PostResult
from social_hook.errors import ErrorType, classify_error


# Mock response for error classification tests
@dataclass
class MockResponse:
    status_code: int
    _json: dict | None = None
    content: bytes = b"{}"

    def json(self) -> dict:
        return self._json or {}


# =============================================================================
# T12: Dry-Run Mode
# =============================================================================


class TestDryRunPlatform:
    """T12: Platform adapter dry-run returns simulated success."""

    def test_dry_run_post_result(self):
        """dry_run_post_result returns success with fake ID."""
        result = dry_run_post_result()
        assert isinstance(result, PostResult)
        assert result.success is True
        assert result.external_id is not None
        assert result.external_id.startswith("dry_run_")
        assert result.external_url is not None
        assert result.error is None

    def test_dry_run_thread_result(self):
        """dry_run_thread_result returns N simulated PostResults."""
        result = dry_run_thread_result(4)
        assert isinstance(result, PostResult)
        assert result.success is True
        assert len(result.part_results) == 4
        for tweet in result.part_results:
            assert tweet.success is True
            assert tweet.external_id is not None

    def test_dry_run_thread_result_single(self):
        """Single-tweet thread dry-run works."""
        result = dry_run_thread_result(1)
        assert len(result.part_results) == 1

    def test_xadapter_post_dry_run(self):
        """XAdapter.post(dry_run=True) returns simulated success, no API call."""
        from social_hook.adapters.platform.x import XAdapter

        adapter = XAdapter("test-token")
        with patch("social_hook.adapters.platform.x.requests") as mock_req:
            result = adapter.post("test content", dry_run=True)
            mock_req.post.assert_not_called()

        assert result.success is True

    def test_xadapter_thread_dry_run(self):
        """XAdapter.post_thread(dry_run=True) returns simulated PostResult."""
        from social_hook.adapters.platform.x import XAdapter

        adapter = XAdapter("test-token")
        tweets = [{"content": f"Tweet {i}"} for i in range(4)]

        with patch("social_hook.adapters.platform.x.requests") as mock_req:
            result = adapter.post_thread(tweets, dry_run=True)
            mock_req.post.assert_not_called()

        assert result.success is True
        assert len(result.part_results) == 4


class TestDryRunMedia:
    """T12: Media adapter dry-run returns placeholder path."""

    def test_dry_run_media_result(self):
        """dry_run_media_result returns placeholder path."""
        result = dry_run_media_result("mermaid")
        assert isinstance(result, MediaResult)
        assert result.success is True
        assert result.file_path is not None
        assert result.file_path.endswith(".png")
        assert result.error is None

    def test_dry_run_media_with_output_dir(self, tmp_path):
        """dry_run_media_result uses provided output_dir."""
        result = dry_run_media_result("image", output_dir=str(tmp_path))
        assert str(tmp_path) in result.file_path

    def test_mermaid_dry_run(self):
        """MermaidAdapter.generate(dry_run=True) returns placeholder."""
        from social_hook.adapters.media.mermaid import MermaidAdapter

        adapter = MermaidAdapter()
        result = adapter.generate({"diagram": "graph LR\n  A-->B"}, dry_run=True)
        assert result.success is True
        assert result.file_path is not None


# =============================================================================
# T12: Error Classification
# =============================================================================


class TestErrorClassification:
    """T12: classify_error returns correct ErrorType for status codes."""

    def test_429_rate_limited(self):
        """429 response -> ErrorType.RATE_LIMITED."""
        assert classify_error(MockResponse(429)) == ErrorType.RATE_LIMITED

    def test_401_auth_expired(self):
        """401 response -> ErrorType.AUTH_EXPIRED."""
        assert classify_error(MockResponse(401)) == ErrorType.AUTH_EXPIRED

    def test_403_auth_expired(self):
        """403 response -> ErrorType.AUTH_EXPIRED."""
        assert classify_error(MockResponse(403)) == ErrorType.AUTH_EXPIRED

    def test_400_content_invalid(self):
        """400 with invalid_text -> ErrorType.CONTENT_INVALID."""
        resp = MockResponse(400, _json={"error": {"code": "invalid_text"}})
        assert classify_error(resp) == ErrorType.CONTENT_INVALID

    def test_400_text_too_long(self):
        """400 with text_too_long -> ErrorType.CONTENT_INVALID."""
        resp = MockResponse(400, _json={"error": {"code": "text_too_long"}})
        assert classify_error(resp) == ErrorType.CONTENT_INVALID

    def test_503_transient(self):
        """503 response -> ErrorType.TRANSIENT."""
        assert classify_error(MockResponse(503)) == ErrorType.TRANSIENT

    def test_500_transient(self):
        """500 response -> ErrorType.TRANSIENT."""
        assert classify_error(MockResponse(500)) == ErrorType.TRANSIENT

    def test_400_duplicate(self):
        """400 with duplicate_content -> ErrorType.DUPLICATE."""
        resp = MockResponse(400, _json={"error": {"code": "duplicate_content"}})
        assert classify_error(resp) == ErrorType.DUPLICATE

    def test_400_status_duplicate(self):
        """400 with status_duplicate -> ErrorType.DUPLICATE."""
        resp = MockResponse(400, _json={"error": {"code": "status_duplicate"}})
        assert classify_error(resp) == ErrorType.DUPLICATE
