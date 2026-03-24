"""Tests for XAdapter (T2, T3, T4).

Source: WS3_ADAPTERS.md T2 (lines 130-137), T3 (lines 139-146), T4 (lines 148-155)
Source: TECHNICAL_ARCHITECTURE.md lines 1057-1110 (thread logic)
Source: WS3_ASSUMPTIONS.md A1-A4 (API details)
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from social_hook.adapters.models import (
    QUOTE,
    REPLY,
    SINGLE_POST,
    THREAD,
    PostReference,
    ReferenceType,
)
from social_hook.adapters.platform.x import XAdapter
from social_hook.errors import ConfigError, ErrorType, classify_x_error

# =============================================================================
# Helpers: X API v2 response factories
# =============================================================================


def _x_error_response(status_code, type_uri="", title="", detail=""):
    """Create a mock response matching X API v2 error format.

    Real X API v2 errors use: {"type": "uri", "title": "...", "detail": "..."}
    """
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {
        "type": type_uri,
        "title": title,
        "detail": detail,
    }
    resp.text = detail or title
    resp.headers = {}
    return resp


def _x_success_response(tweet_id):
    """Create a mock X API v2 success response."""
    resp = MagicMock()
    resp.status_code = 201
    resp.json.return_value = {"data": {"id": tweet_id}}
    return resp


# =============================================================================
# T2: XAdapter - Authentication
# =============================================================================


class TestXAdapterAuth:
    """T2: XAdapter authentication and credential validation."""

    def test_missing_credentials_raises_config_error(self):
        """Missing credentials raises ConfigError."""
        with pytest.raises(ConfigError):
            XAdapter("")

    @patch("social_hook.adapters.platform.x.requests.get")
    def test_valid_credentials(self, mock_get):
        """Valid credentials: validate() returns (True, "@username")."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": {"username": "testuser"}}
        mock_get.return_value = mock_resp

        adapter = XAdapter("test-token")
        success, info = adapter.validate()

        assert success is True
        assert info == "@testuser"

    @patch("social_hook.adapters.platform.x.requests.get")
    def test_invalid_credentials(self, mock_get):
        """Invalid credentials: validate() returns (False, error) with X API v2 format."""
        mock_get.return_value = _x_error_response(
            401,
            type_uri="https://api.x.com/2/problems/not-authorized-for-resource",
            title="Unauthorized",
            detail="Your account is not authorized to access this resource.",
        )

        adapter = XAdapter("test-token")
        success, info = adapter.validate()

        assert success is False
        assert "auth_expired" in info

    @patch("social_hook.adapters.platform.x.requests.get")
    def test_validate_network_error(self, mock_get):
        """Network error during validate returns (False, error)."""
        mock_get.side_effect = requests.RequestException("Connection refused")

        adapter = XAdapter("test-token")
        success, info = adapter.validate()

        assert success is False
        assert "Request failed" in info


# =============================================================================
# T2b: XAdapter - 401 Retry with token_refresher
# =============================================================================


class TestXAdapter401Retry:
    """Token refresh on 401 responses."""

    @patch("social_hook.adapters.platform.x.requests.post")
    def test_401_retry_with_refresher(self, mock_post):
        """401 triggers refresher, retry succeeds with new token."""
        first_resp = _x_error_response(401, title="Unauthorized")
        second_resp = _x_success_response("tweet_refreshed")
        mock_post.side_effect = [first_resp, second_resp]

        refresher = MagicMock(return_value="new-token")
        adapter = XAdapter("old-token", token_refresher=refresher)
        result = adapter.post("Hello")

        assert result.success is True
        assert result.external_id == "tweet_refreshed"
        refresher.assert_called_once()
        assert adapter.access_token == "new-token"

    @patch("social_hook.adapters.platform.x.requests.post")
    def test_401_no_refresher(self, mock_post):
        """401 without refresher returns error immediately (no retry)."""
        mock_post.return_value = _x_error_response(401, title="Unauthorized")

        adapter = XAdapter("some-token")
        result = adapter.post("Hello")

        assert result.success is False
        assert "auth_expired" in result.error
        assert mock_post.call_count == 1

    @patch("social_hook.adapters.platform.x.requests.post")
    def test_401_retry_fails(self, mock_post):
        """401 triggers refresher, but retry also returns 401 -> error."""
        first_resp = _x_error_response(401, title="Unauthorized")
        second_resp = _x_error_response(401, title="Still Unauthorized")
        mock_post.side_effect = [first_resp, second_resp]

        refresher = MagicMock(return_value="new-token")
        adapter = XAdapter("old-token", token_refresher=refresher)
        result = adapter.post("Hello")

        assert result.success is False
        assert "auth_expired" in result.error
        refresher.assert_called_once()

    @patch("social_hook.adapters.platform.x.requests.get")
    def test_validate_401_refresh_success(self, mock_get):
        """Validate: 401 triggers refresh, retry succeeds."""
        first_resp = _x_error_response(401, title="Unauthorized")
        second_resp = MagicMock()
        second_resp.status_code = 200
        second_resp.json.return_value = {"data": {"username": "refreshed_user"}}
        mock_get.side_effect = [first_resp, second_resp]

        refresher = MagicMock(return_value="fresh-token")
        adapter = XAdapter("stale-token", token_refresher=refresher)
        success, info = adapter.validate()

        assert success is True
        assert info == "@refreshed_user"
        refresher.assert_called_once()
        assert adapter.access_token == "fresh-token"
        assert mock_get.call_count == 2

    @patch("social_hook.adapters.platform.x.requests.delete")
    def test_delete_401_refresh_success(self, mock_delete):
        """Delete: 401 triggers refresh, retry succeeds."""
        first_resp = _x_error_response(401, title="Unauthorized")
        second_resp = MagicMock()
        second_resp.status_code = 200
        mock_delete.side_effect = [first_resp, second_resp]

        refresher = MagicMock(return_value="fresh-token")
        adapter = XAdapter("stale-token", token_refresher=refresher)
        result = adapter.delete("tweet_999")

        assert result is True
        refresher.assert_called_once()
        assert adapter.access_token == "fresh-token"
        assert mock_delete.call_count == 2

    @patch("social_hook.adapters.platform.x.requests.post")
    def test_upload_media_401_refresh_success(self, mock_post, tmp_path):
        """Media upload: 401 triggers refresh, retry succeeds."""
        img_file = tmp_path / "test.png"
        img_file.write_bytes(b"\x89PNG" + b"\x00" * 50)

        upload_401 = _x_error_response(401, title="Unauthorized")
        upload_ok = MagicMock()
        upload_ok.status_code = 200
        upload_ok.json.return_value = {"data": {"id": "media_refreshed"}}

        tweet_ok = _x_success_response("tweet_after_refresh")

        mock_post.side_effect = [upload_401, upload_ok, tweet_ok]

        refresher = MagicMock(return_value="fresh-token")
        adapter = XAdapter("stale-token", token_refresher=refresher)
        result = adapter.post("hello media", media_paths=[str(img_file)])

        assert result.success is True
        refresher.assert_called_once()
        # 3 calls: first upload (401), retry upload (200), tweet post
        assert mock_post.call_count == 3


# =============================================================================
# T3: XAdapter - Single Post
# =============================================================================


class TestXAdapterPost:
    """T3: XAdapter single post functionality."""

    @patch("social_hook.adapters.platform.x.requests.post")
    def test_post_valid_content(self, mock_post):
        """Post valid content returns PostResult(success=True, external_id)."""
        mock_post.return_value = _x_success_response("1234567890")

        adapter = XAdapter("test-token")
        result = adapter.post("Hello world!")

        assert result.success is True
        assert result.external_id == "1234567890"
        assert result.external_url is not None

    @patch("social_hook.adapters.platform.x.requests.post")
    def test_post_content_too_long(self, mock_post):
        """Content exceeding 280 chars returns PostResult(success=False)."""
        adapter = XAdapter("test-token")
        result = adapter.post("x" * 300)

        assert result.success is False
        assert "280" in result.error
        # No API call should be made
        mock_post.assert_not_called()

    def test_post_at_char_limit(self):
        """Content exactly at 280 chars is accepted (dry-run)."""
        adapter = XAdapter("test-token")
        result = adapter.post("x" * 280, dry_run=True)
        assert result.success is True

    @patch("social_hook.adapters.platform.x.requests.post")
    def test_post_dry_run_no_api_call(self, mock_post):
        """dry_run=True returns simulated success without API call."""
        adapter = XAdapter("test-token")
        result = adapter.post("test", dry_run=True)
        mock_post.assert_not_called()

        assert result.success is True

    @patch("social_hook.adapters.platform.x.requests.post")
    def test_post_api_error_real_format(self, mock_post):
        """API error uses X API v2 format with type/title/detail."""
        mock_post.return_value = _x_error_response(
            403,
            type_uri="https://api.x.com/2/problems/not-authorized-for-resource",
            title="Forbidden",
            detail="You are not permitted to perform this action.",
        )

        adapter = XAdapter("test-token")
        result = adapter.post("Hello")

        assert result.success is False
        assert "auth_expired" in result.error

    @patch("social_hook.adapters.platform.x.requests.post")
    def test_post_rate_limited_real_format(self, mock_post):
        """Rate limit error with x-rate-limit-reset header."""
        resp = _x_error_response(
            429,
            type_uri="https://api.x.com/2/problems/rate-limit",
            title="Too Many Requests",
            detail="Rate limit exceeded.",
        )
        resp.headers = {"x-rate-limit-reset": "1700000000"}
        mock_post.return_value = resp

        adapter = XAdapter("test-token")
        result = adapter.post("Hello")

        assert result.success is False
        assert "rate_limited" in result.error

    @patch("social_hook.adapters.platform.x.requests.post")
    def test_post_with_media(self, mock_post, tmp_path):
        """Post with media_paths uploads files and attaches media_ids."""
        img_file = tmp_path / "test.png"
        img_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        upload_resp = MagicMock()
        upload_resp.status_code = 200
        upload_resp.json.return_value = {"data": {"id": "media_001"}}

        tweet_resp = _x_success_response("tweet_123")

        # First call is media upload, second is tweet post
        mock_post.side_effect = [upload_resp, tweet_resp]

        adapter = XAdapter("test-token")
        result = adapter.post("Check this out!", media_paths=[str(img_file)])

        assert result.success is True
        assert result.external_id == "tweet_123"
        # Verify 2 POST calls: upload + tweet
        assert mock_post.call_count == 2
        # Verify tweet body includes media_ids
        tweet_call = mock_post.call_args_list[1]
        tweet_body = tweet_call.kwargs.get("json", {})
        assert tweet_body.get("media", {}).get("media_ids") == ["media_001"]

    @patch("social_hook.adapters.platform.x.requests.post")
    def test_post_with_media_upload_failure(self, mock_post, tmp_path):
        """Failed media upload still posts tweet without media."""
        img_file = tmp_path / "test.png"
        img_file.write_bytes(b"\x89PNG" + b"\x00" * 50)

        upload_resp = MagicMock()
        upload_resp.status_code = 400
        upload_resp.text = "Bad image"

        tweet_resp = _x_success_response("tweet_456")

        mock_post.side_effect = [upload_resp, tweet_resp]

        adapter = XAdapter("test-token")
        result = adapter.post("Still posting", media_paths=[str(img_file)])

        assert result.success is True
        # Tweet body should NOT have media since upload failed
        tweet_call = mock_post.call_args_list[1]
        tweet_body = tweet_call.kwargs.get("json", {})
        assert "media" not in tweet_body


# =============================================================================
# T4: XAdapter - Thread Posting
# =============================================================================


class TestXAdapterThread:
    """T4: XAdapter thread posting with atomic failure."""

    def test_empty_thread_raises_value_error(self):
        """Empty thread raises ValueError."""
        adapter = XAdapter("test-token")
        with pytest.raises(ValueError, match="at least one tweet"):
            adapter.post_thread([])

    @patch("social_hook.adapters.platform.x.requests.post")
    def test_valid_thread_4_tweets(self, mock_post):
        """4-tweet thread returns ThreadResult(success=True) with 4 results."""
        call_count = 0

        def mock_post_fn(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return _x_success_response(f"tweet_{call_count}")

        mock_post.side_effect = mock_post_fn

        adapter = XAdapter("test-token")
        tweets = [{"content": f"Tweet {i}"} for i in range(4)]
        result = adapter.post_thread(tweets)

        assert result.success is True
        assert len(result.tweet_results) == 4
        for i, tr in enumerate(result.tweet_results):
            assert tr.success is True
            assert tr.external_id == f"tweet_{i + 1}"

    @patch("social_hook.adapters.platform.x.requests.post")
    def test_atomic_failure_on_tweet_3(self, mock_post):
        """Failure on tweet 3: stops, returns partial results for 1-2."""
        call_count = 0

        def mock_post_fn(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 3:
                return _x_error_response(
                    500,
                    type_uri="https://api.x.com/2/problems/server-error",
                    title="Internal Server Error",
                    detail="An internal error occurred.",
                )
            return _x_success_response(f"tweet_{call_count}")

        mock_post.side_effect = mock_post_fn

        adapter = XAdapter("test-token")
        tweets = [{"content": f"Tweet {i}"} for i in range(4)]
        result = adapter.post_thread(tweets)

        assert result.success is False
        assert len(result.tweet_results) == 3  # 2 success + 1 failure
        assert result.tweet_results[0].success is True
        assert result.tweet_results[1].success is True
        assert result.tweet_results[2].success is False
        assert "Tweet 3 failed" in result.error

    @patch("social_hook.adapters.platform.x.requests.post")
    def test_thread_reply_chaining_format(self, mock_post):
        """Thread chaining uses reply.in_reply_to_tweet_id nested object."""
        captured_bodies = []
        call_count = 0

        def mock_post_fn(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            body = kwargs.get("json", {})
            captured_bodies.append(body)
            return _x_success_response(f"tweet_{call_count}")

        mock_post.side_effect = mock_post_fn

        adapter = XAdapter("test-token")
        tweets = [{"content": f"Tweet {i}"} for i in range(3)]
        adapter.post_thread(tweets)

        # First tweet has no reply field
        assert "reply" not in captured_bodies[0]

        # Second tweet replies to first
        assert captured_bodies[1]["reply"]["in_reply_to_tweet_id"] == "tweet_1"

        # Third tweet replies to second
        assert captured_bodies[2]["reply"]["in_reply_to_tweet_id"] == "tweet_2"

    @patch("social_hook.adapters.platform.x.requests.post")
    def test_thread_dry_run(self, mock_post):
        """Thread dry-run returns simulated results without API calls."""
        adapter = XAdapter("test-token")
        tweets = [{"content": f"Tweet {i}"} for i in range(4)]

        result = adapter.post_thread(tweets, dry_run=True)
        mock_post.assert_not_called()

        assert result.success is True
        assert len(result.tweet_results) == 4


# =============================================================================
# classify_x_error - X API v2 error classification
# =============================================================================


class TestClassifyXError:
    """X API v2 error classification using type URI format."""

    def test_rate_limited_429(self):
        """429 status code returns RATE_LIMITED."""
        resp = _x_error_response(
            429,
            type_uri="https://api.x.com/2/problems/rate-limit",
            detail="Rate limit exceeded.",
        )
        assert classify_x_error(resp) == ErrorType.RATE_LIMITED

    def test_auth_expired_401(self):
        """401 status code returns AUTH_EXPIRED."""
        resp = _x_error_response(
            401,
            type_uri="https://api.x.com/2/problems/not-authorized-for-resource",
            detail="Unauthorized.",
        )
        assert classify_x_error(resp) == ErrorType.AUTH_EXPIRED

    def test_auth_expired_403(self):
        """403 status code returns AUTH_EXPIRED."""
        resp = _x_error_response(
            403,
            type_uri="https://api.x.com/2/problems/not-authorized-for-resource",
            detail="Forbidden.",
        )
        assert classify_x_error(resp) == ErrorType.AUTH_EXPIRED

    def test_transient_500(self):
        """500 status code returns TRANSIENT."""
        resp = _x_error_response(
            500,
            type_uri="https://api.x.com/2/problems/server-error",
            detail="Internal server error.",
        )
        assert classify_x_error(resp) == ErrorType.TRANSIENT

    def test_transient_503(self):
        """503 status code returns TRANSIENT."""
        resp = _x_error_response(503, detail="Service unavailable.")
        assert classify_x_error(resp) == ErrorType.TRANSIENT

    def test_duplicate_via_type_uri(self):
        """400 with 'duplicate' in type URI returns DUPLICATE."""
        resp = _x_error_response(
            400,
            type_uri="https://api.x.com/2/problems/duplicate-content",
            title="Forbidden",
            detail="You are not allowed to create a Tweet with duplicate content.",
        )
        assert classify_x_error(resp) == ErrorType.DUPLICATE

    def test_duplicate_via_detail(self):
        """400 with 'duplicate' in detail returns DUPLICATE (even if type says invalid)."""
        resp = _x_error_response(
            400,
            type_uri="https://api.x.com/2/problems/invalid-request",
            title="Invalid Request",
            detail="Status is a duplicate.",
        )
        assert classify_x_error(resp) == ErrorType.DUPLICATE

    def test_content_invalid_via_type_uri(self):
        """400 with 'invalid-request' in type URI returns CONTENT_INVALID."""
        resp = _x_error_response(
            400,
            type_uri="https://api.x.com/2/problems/invalid-request",
            title="Invalid Request",
            detail="The 'text' parameter is required.",
        )
        assert classify_x_error(resp) == ErrorType.CONTENT_INVALID

    def test_content_invalid_too_long(self):
        """400 with 'too long' in detail returns CONTENT_INVALID."""
        resp = _x_error_response(
            400,
            type_uri="https://api.x.com/2/problems/invalid-request",
            title="Invalid Request",
            detail="Tweet text is too long.",
        )
        assert classify_x_error(resp) == ErrorType.CONTENT_INVALID

    def test_unknown_400(self):
        """400 without matching keywords returns UNKNOWN."""
        resp = _x_error_response(
            400,
            type_uri="https://api.x.com/2/problems/some-new-error",
            detail="Something unexpected happened.",
        )
        assert classify_x_error(resp) == ErrorType.UNKNOWN


# =============================================================================
# XAdapter - post_with_reference
# =============================================================================


class TestXAdapterPostWithReference:
    """XAdapter.post_with_reference() for quote tweets, replies, and link fallback."""

    def _make_ref(self, ref_type, ext_id="999", url="https://x.com/other/status/999"):
        return PostReference(external_id=ext_id, external_url=url, reference_type=ref_type)

    @patch("social_hook.adapters.platform.x.requests.post")
    def test_quote_tweet_builds_correct_body(self, mock_post):
        """QUOTE reference sends quote_tweet_id in request body."""
        mock_post.return_value = _x_success_response("new_tweet_1")
        adapter = XAdapter("test-token")
        ref = self._make_ref(ReferenceType.QUOTE)

        result = adapter.post_with_reference("Check this out", ref)

        assert result.success is True
        body = mock_post.call_args.kwargs["json"]
        assert body["text"] == "Check this out"
        assert body["quote_tweet_id"] == "999"
        assert "reply" not in body

    @patch("social_hook.adapters.platform.x.requests.post")
    def test_reply_builds_correct_body(self, mock_post):
        """REPLY reference sends reply.in_reply_to_tweet_id in request body."""
        mock_post.return_value = _x_success_response("new_tweet_2")
        adapter = XAdapter("test-token")
        ref = self._make_ref(ReferenceType.REPLY)

        result = adapter.post_with_reference("Great thread!", ref)

        assert result.success is True
        body = mock_post.call_args.kwargs["json"]
        assert body["text"] == "Great thread!"
        assert body["reply"]["in_reply_to_tweet_id"] == "999"
        assert "quote_tweet_id" not in body

    @patch("social_hook.adapters.platform.x.requests.post")
    def test_link_appends_url_to_content(self, mock_post):
        """LINK reference appends URL to content and uses post()."""
        mock_post.return_value = _x_success_response("new_tweet_3")
        adapter = XAdapter("test-token")
        ref = self._make_ref(ReferenceType.LINK)

        result = adapter.post_with_reference("Related post", ref)

        assert result.success is True
        body = mock_post.call_args.kwargs["json"]
        assert "https://x.com/other/status/999" in body["text"]
        assert "Related post" in body["text"]
        assert "quote_tweet_id" not in body
        assert "reply" not in body

    def test_quote_dry_run_no_api_call(self):
        """QUOTE dry_run returns success without API call."""
        adapter = XAdapter("test-token")
        ref = self._make_ref(ReferenceType.QUOTE)

        with patch("social_hook.adapters.platform.x.requests.post") as mock_post:
            result = adapter.post_with_reference("Quote this", ref, dry_run=True)
            mock_post.assert_not_called()

        assert result.success is True

    def test_reply_dry_run_no_api_call(self):
        """REPLY dry_run returns success without API call."""
        adapter = XAdapter("test-token")
        ref = self._make_ref(ReferenceType.REPLY)

        with patch("social_hook.adapters.platform.x.requests.post") as mock_post:
            result = adapter.post_with_reference("Replying", ref, dry_run=True)
            mock_post.assert_not_called()

        assert result.success is True

    def test_link_dry_run_no_api_call(self):
        """LINK dry_run returns success without API call."""
        adapter = XAdapter("test-token")
        ref = self._make_ref(ReferenceType.LINK)

        with patch("social_hook.adapters.platform.x.requests.post") as mock_post:
            result = adapter.post_with_reference("Link post", ref, dry_run=True)
            mock_post.assert_not_called()

        assert result.success is True


# =============================================================================
# XAdapter - supports_reference_type
# =============================================================================


class TestXAdapterSupportsReferenceType:
    """XAdapter.supports_reference_type() returns True for all types."""

    def test_supports_reply(self):
        adapter = XAdapter("test-token")
        assert adapter.supports_reference_type(ReferenceType.REPLY) is True

    def test_supports_quote(self):
        adapter = XAdapter("test-token")
        assert adapter.supports_reference_type(ReferenceType.QUOTE) is True

    def test_supports_link(self):
        adapter = XAdapter("test-token")
        assert adapter.supports_reference_type(ReferenceType.LINK) is True


# =============================================================================
# XAdapter - Capability Registry
# =============================================================================


class TestXAdapterCapabilities:
    """XAdapter capability registry methods."""

    def test_capabilities_contains_expected(self):
        """XAdapter.capabilities() returns SINGLE_POST, THREAD, QUOTE, REPLY."""
        adapter = XAdapter("test-token")
        caps = adapter.capabilities()
        assert SINGLE_POST in caps
        assert THREAD in caps
        assert QUOTE in caps
        assert REPLY in caps

    def test_capabilities_returns_list(self):
        """XAdapter.capabilities() returns a list."""
        adapter = XAdapter("test-token")
        assert isinstance(adapter.capabilities(), list)

    def test_supports_threads(self):
        """XAdapter.supports_threads() returns True."""
        adapter = XAdapter("test-token")
        assert adapter.supports_threads() is True

    def test_supports_media(self):
        """XAdapter.supports_media() returns True."""
        adapter = XAdapter("test-token")
        assert adapter.supports_media() is True
