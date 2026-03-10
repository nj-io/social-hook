"""Tests for LinkedInAdapter (T5).

Source: WS3_ADAPTERS.md T5 (lines 157-166)
Source: WS3_ASSUMPTIONS.md A5-A6 (OAuth, endpoint)
"""

from unittest.mock import MagicMock, patch

from social_hook.adapters.models import PostReference, ReferenceType
from social_hook.adapters.platform.linkedin import (
    LinkedInAdapter,
)

# =============================================================================
# Helpers: LinkedIn response factories
# =============================================================================


def _li_userinfo_response(sub, name):
    """Create a mock LinkedIn /v2/userinfo success response."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"sub": sub, "name": name}
    return resp


def _li_post_success_response(post_id):
    """Create a mock LinkedIn /rest/posts success response."""
    resp = MagicMock()
    resp.status_code = 201
    resp.headers = {"x-restli-id": post_id}
    resp.json.return_value = {}
    return resp


def _li_error_response(status_code, message):
    """Create a mock LinkedIn error response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {"message": message}
    resp.text = message
    return resp


# =============================================================================
# T5: LinkedInAdapter - Authentication
# =============================================================================


class TestLinkedInAdapterAuth:
    """T5: LinkedInAdapter credential validation."""

    @patch("social_hook.adapters.platform.linkedin.requests.get")
    def test_valid_credentials(self, mock_get):
        """Valid credentials: validate() returns (True, "profile_name")."""
        mock_get.return_value = _li_userinfo_response("782bbtaQ", "John Doe")

        adapter = LinkedInAdapter("valid_token")
        success, info = adapter.validate()

        assert success is True
        assert info == "John Doe"
        assert adapter.author_urn == "urn:li:person:782bbtaQ"

    @patch("social_hook.adapters.platform.linkedin.requests.get")
    def test_invalid_credentials(self, mock_get):
        """Invalid credentials: validate() returns (False, error)."""
        mock_get.return_value = _li_error_response(401, "Invalid token")

        adapter = LinkedInAdapter("bad_token")
        success, info = adapter.validate()

        assert success is False
        assert "auth_expired" in info


# =============================================================================
# T5: LinkedInAdapter - Posting
# =============================================================================


class TestLinkedInAdapterPost:
    """T5: LinkedInAdapter posting."""

    @patch("social_hook.adapters.platform.linkedin.requests.post")
    @patch("social_hook.adapters.platform.linkedin.requests.get")
    def test_post_text_content(self, mock_get, mock_post):
        """Post text content returns PostResult(success=True)."""
        mock_get.return_value = _li_userinfo_response("abc123", "Test")
        mock_post.return_value = _li_post_success_response("urn:li:share:12345")

        adapter = LinkedInAdapter("valid_token")
        result = adapter.post("Hello LinkedIn!")

        assert result.success is True
        assert result.external_id == "urn:li:share:12345"
        assert "linkedin.com" in result.external_url

    def test_post_dry_run(self):
        """dry_run=True returns simulated success, no API call."""
        adapter = LinkedInAdapter("token")

        with patch("social_hook.adapters.platform.linkedin.requests.post") as mock_post:
            result = adapter.post("test content", dry_run=True)
            mock_post.assert_not_called()

        assert result.success is True

    @patch("social_hook.adapters.platform.linkedin.requests.post")
    def test_post_content_too_long(self, mock_post):
        """Content exceeding 3000 chars returns PostResult(success=False)."""
        adapter = LinkedInAdapter("token")
        result = adapter.post("x" * 3001)

        assert result.success is False
        assert "3000" in result.error
        mock_post.assert_not_called()

    @patch("social_hook.adapters.platform.linkedin.requests.post")
    @patch("social_hook.adapters.platform.linkedin.requests.get")
    def test_post_includes_required_headers(self, mock_get, mock_post):
        """POST /rest/posts includes X-Restli-Protocol-Version and LinkedIn-Version."""
        mock_get.return_value = _li_userinfo_response("abc123", "Test")
        mock_post.return_value = _li_post_success_response("urn:li:share:123")

        adapter = LinkedInAdapter("token")
        adapter.post("Hello")

        # Check headers in the post call
        call_kwargs = mock_post.call_args
        headers = call_kwargs.kwargs.get("headers", {})
        assert headers.get("X-Restli-Protocol-Version") == "2.0.0"
        assert headers.get("LinkedIn-Version") == "202501"


# =============================================================================
# T5: LinkedInAdapter - Author URN Prefetch & Caching
# =============================================================================


class TestLinkedInAuthorUrn:
    """T5: LinkedIn author URN prefetch and caching."""

    @patch("social_hook.adapters.platform.linkedin.requests.post")
    @patch("social_hook.adapters.platform.linkedin.requests.get")
    def test_post_calls_validate_when_no_urn(self, mock_get, mock_post):
        """post() fetches author URN via validate() when not cached."""
        mock_get.return_value = _li_userinfo_response("abc123", "Test User")
        mock_post.return_value = _li_post_success_response("urn:li:share:12345")

        adapter = LinkedInAdapter("token")
        assert adapter.author_urn is None

        adapter.post("Hello")

        mock_get.assert_called_once()  # validate was called
        assert adapter.author_urn == "urn:li:person:abc123"

    @patch("social_hook.adapters.platform.linkedin.requests.post")
    @patch("social_hook.adapters.platform.linkedin.requests.get")
    def test_author_urn_cached_on_second_post(self, mock_get, mock_post):
        """Author URN is cached - validate() not called on second post."""
        mock_get.return_value = _li_userinfo_response("abc123", "Test User")
        mock_post.return_value = _li_post_success_response("urn:li:share:12345")

        adapter = LinkedInAdapter("token")
        adapter.post("First post")
        adapter.post("Second post")

        # validate (GET) should only be called once
        assert mock_get.call_count == 1
        # post should be called twice
        assert mock_post.call_count == 2

    @patch("social_hook.adapters.platform.linkedin.requests.get")
    def test_post_fails_when_validate_fails(self, mock_get):
        """post() returns error when validate() fails (no author URN)."""
        mock_get.return_value = _li_error_response(401, "Invalid token")

        adapter = LinkedInAdapter("bad_token")
        result = adapter.post("Hello")

        assert result.success is False
        assert "Failed to get author URN" in result.error

    @patch("social_hook.adapters.platform.linkedin.requests.post")
    @patch("social_hook.adapters.platform.linkedin.requests.get")
    def test_pre_set_author_urn_skips_validate(self, mock_get, mock_post):
        """When author_urn is pre-set, validate() is not called during post()."""
        mock_post.return_value = _li_post_success_response("urn:li:share:789")

        adapter = LinkedInAdapter("token")
        adapter.author_urn = "urn:li:person:pre_set"

        adapter.post("Hello")

        mock_get.assert_not_called()  # validate was NOT called
        mock_post.assert_called_once()


# =============================================================================
# T5: LinkedInAdapter - Thread
# =============================================================================


class TestLinkedInAdapterThread:
    """T5: LinkedInAdapter thread behavior."""

    def test_post_thread_unsupported(self):
        """LinkedIn doesn't support threads - returns error."""
        adapter = LinkedInAdapter("token")
        result = adapter.post_thread([{"content": "test"}])

        assert result.success is False
        assert "does not support threads" in result.error
        assert result.tweet_results == []


# =============================================================================
# T5: LinkedInAdapter - OAuth Helpers
# =============================================================================


class TestLinkedInOAuthHelpers:
    """T5: LinkedIn OAuth static helper methods."""

    def test_get_auth_url(self):
        """get_auth_url returns valid authorization URL."""
        url = LinkedInAdapter.get_auth_url(
            client_id="test_client",
            redirect_uri="https://example.com/callback",
            state="csrf_token_123",
        )

        assert "linkedin.com/oauth/v2/authorization" in url
        assert "client_id=test_client" in url
        assert "redirect_uri=" in url
        assert "state=csrf_token_123" in url
        assert "response_type=code" in url
        assert "scope=" in url

    @patch("social_hook.adapters.platform.linkedin.requests.post")
    def test_exchange_code(self, mock_post):
        """exchange_code returns access token dict."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "new_token",
            "expires_in": 5184000,
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = LinkedInAdapter.exchange_code(
            client_id="test_client",
            client_secret="test_secret",
            code="auth_code_123",
            redirect_uri="https://example.com/callback",
        )

        assert result["access_token"] == "new_token"
        assert result["expires_in"] == 5184000


# =============================================================================
# LinkedInAdapter - post_with_reference
# =============================================================================


class TestLinkedInAdapterPostWithReference:
    """LinkedInAdapter.post_with_reference() for reshares, replies, and links."""

    def _make_ref(
        self,
        ref_type,
        ext_id="urn:li:share:12345",
        url="https://www.linkedin.com/feed/update/urn:li:share:12345",
    ):
        return PostReference(external_id=ext_id, external_url=url, reference_type=ref_type)

    @patch("social_hook.adapters.platform.linkedin.requests.post")
    @patch("social_hook.adapters.platform.linkedin.requests.get")
    def test_quote_linkedin_reshare(self, mock_get, mock_post):
        """QUOTE with LinkedIn URN uses reshare API with reshareContext."""
        mock_get.return_value = _li_userinfo_response("abc123", "Test")
        mock_post.return_value = _li_post_success_response("urn:li:share:99999")

        adapter = LinkedInAdapter("token")
        ref = self._make_ref(ReferenceType.QUOTE)
        result = adapter.post_with_reference("Great insight!", ref)

        assert result.success is True
        assert result.external_id == "urn:li:share:99999"

        body = mock_post.call_args.kwargs["json"]
        assert body["reshareContext"]["parent"] == "urn:li:share:12345"
        assert body["commentary"] == "Great insight!"
        assert body["visibility"] == "PUBLIC"

    @patch("social_hook.adapters.platform.linkedin.requests.post")
    @patch("social_hook.adapters.platform.linkedin.requests.get")
    def test_quote_cross_platform_falls_back_to_link(self, mock_get, mock_post):
        """QUOTE with non-LinkedIn external_id falls back to LINK behavior."""
        mock_get.return_value = _li_userinfo_response("abc123", "Test")
        mock_post.return_value = _li_post_success_response("urn:li:share:88888")

        adapter = LinkedInAdapter("token")
        # Cross-platform reference (X tweet ID, not a LinkedIn URN)
        ref = PostReference(
            external_id="tweet_12345",
            external_url="https://x.com/user/status/12345",
            reference_type=ReferenceType.QUOTE,
        )
        result = adapter.post_with_reference("From X", ref)

        assert result.success is True
        # Should embed the URL in commentary, not use reshareContext
        body = mock_post.call_args.kwargs["json"]
        assert "reshareContext" not in body
        assert "https://x.com/user/status/12345" in body["commentary"]

    @patch("social_hook.adapters.platform.linkedin.requests.post")
    @patch("social_hook.adapters.platform.linkedin.requests.get")
    def test_reply_embeds_url_in_content(self, mock_get, mock_post):
        """REPLY embeds reference URL in commentary text."""
        mock_get.return_value = _li_userinfo_response("abc123", "Test")
        mock_post.return_value = _li_post_success_response("urn:li:share:77777")

        adapter = LinkedInAdapter("token")
        ref = self._make_ref(ReferenceType.REPLY)
        result = adapter.post_with_reference("Responding to this", ref)

        assert result.success is True
        body = mock_post.call_args.kwargs["json"]
        assert "https://www.linkedin.com/feed/update/urn:li:share:12345" in body["commentary"]
        assert "reshareContext" not in body

    @patch("social_hook.adapters.platform.linkedin.requests.post")
    @patch("social_hook.adapters.platform.linkedin.requests.get")
    def test_link_embeds_url_in_content(self, mock_get, mock_post):
        """LINK embeds reference URL in commentary text."""
        mock_get.return_value = _li_userinfo_response("abc123", "Test")
        mock_post.return_value = _li_post_success_response("urn:li:share:66666")

        adapter = LinkedInAdapter("token")
        ref = self._make_ref(ReferenceType.LINK)
        result = adapter.post_with_reference("Check this out", ref)

        assert result.success is True
        body = mock_post.call_args.kwargs["json"]
        assert "https://www.linkedin.com/feed/update/urn:li:share:12345" in body["commentary"]
        assert "reshareContext" not in body

    def test_dry_run_no_api_call(self):
        """dry_run returns success without API call."""
        adapter = LinkedInAdapter("token")
        ref = self._make_ref(ReferenceType.QUOTE)

        with patch("social_hook.adapters.platform.linkedin.requests.post") as mock_post:
            result = adapter.post_with_reference("Test", ref, dry_run=True)
            mock_post.assert_not_called()

        assert result.success is True

    def test_dry_run_link_no_api_call(self):
        """LINK dry_run also returns success without API call."""
        adapter = LinkedInAdapter("token")
        ref = self._make_ref(ReferenceType.LINK)

        with patch("social_hook.adapters.platform.linkedin.requests.post") as mock_post:
            result = adapter.post_with_reference("Test", ref, dry_run=True)
            mock_post.assert_not_called()

        assert result.success is True


# =============================================================================
# LinkedInAdapter - supports_reference_type
# =============================================================================


class TestLinkedInSupportsReferenceType:
    """LinkedInAdapter.supports_reference_type() capabilities."""

    def test_supports_quote(self):
        adapter = LinkedInAdapter("token")
        assert adapter.supports_reference_type(ReferenceType.QUOTE) is True

    def test_supports_link(self):
        adapter = LinkedInAdapter("token")
        assert adapter.supports_reference_type(ReferenceType.LINK) is True

    def test_does_not_support_reply(self):
        adapter = LinkedInAdapter("token")
        assert adapter.supports_reference_type(ReferenceType.REPLY) is False
