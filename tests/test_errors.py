"""Tests for error taxonomy and classification (T7).

NOTE: The classify_error() function is a PLACEHOLDER implementation.
It uses a generic {"error": {"code": "..."}} format that does NOT match
X API v2's actual format ({"type": "...", "title": "...", "detail": "..."}).

WS3 must implement platform-specific classifiers:
- classify_x_error() for X API v2 format
- classify_linkedin_error() for LinkedIn format

See docs/research/WS1_ASSUMPTIONS.md (A1) for details.
"""

from dataclasses import dataclass
from typing import Any, Optional

import pytest

from social_hook.errors import ErrorType, classify_error, ConfigError, DatabaseError


# Mock response class for testing
@dataclass
class MockResponse:
    status_code: int
    _json: Optional[dict] = None

    def json(self) -> dict:
        return self._json or {}


# =============================================================================
# T7: Error Classification (Placeholder Implementation)
# =============================================================================


class TestErrorClassification:
    """T7: Error classification tests for placeholder implementation.

    These tests verify the current placeholder behavior. The placeholder
    uses a generic format that won't work with real X API v2 responses.
    """

    def test_classify_rate_limit(self):
        """429 response returns RATE_LIMITED."""
        response = MockResponse(status_code=429)
        error_type = classify_error(response)
        assert error_type == ErrorType.RATE_LIMITED

    def test_classify_auth_error_401(self):
        """401 response returns AUTH_EXPIRED."""
        response = MockResponse(status_code=401)
        error_type = classify_error(response)
        assert error_type == ErrorType.AUTH_EXPIRED

    def test_classify_auth_error_403(self):
        """403 response returns AUTH_EXPIRED."""
        response = MockResponse(status_code=403)
        error_type = classify_error(response)
        assert error_type == ErrorType.AUTH_EXPIRED

    def test_classify_content_invalid(self):
        """400 with content error returns CONTENT_INVALID."""
        response = MockResponse(
            status_code=400,
            _json={"error": {"code": "invalid_text"}},
        )
        error_type = classify_error(response)
        assert error_type == ErrorType.CONTENT_INVALID

    def test_classify_duplicate(self):
        """400 with duplicate_content returns DUPLICATE."""
        response = MockResponse(
            status_code=400,
            _json={"error": {"code": "duplicate_content"}},
        )
        error_type = classify_error(response)
        assert error_type == ErrorType.DUPLICATE

    def test_classify_transient_500(self):
        """500 response returns TRANSIENT."""
        response = MockResponse(status_code=500)
        error_type = classify_error(response)
        assert error_type == ErrorType.TRANSIENT

    def test_classify_transient_502(self):
        """502 response returns TRANSIENT."""
        response = MockResponse(status_code=502)
        error_type = classify_error(response)
        assert error_type == ErrorType.TRANSIENT

    def test_classify_transient_503(self):
        """503 response returns TRANSIENT."""
        response = MockResponse(status_code=503)
        error_type = classify_error(response)
        assert error_type == ErrorType.TRANSIENT

    def test_classify_unknown_418(self):
        """418 (I'm a teapot) returns UNKNOWN."""
        response = MockResponse(status_code=418)
        error_type = classify_error(response)
        assert error_type == ErrorType.UNKNOWN

    def test_classify_unknown_400_no_code(self):
        """400 without specific error code returns UNKNOWN."""
        response = MockResponse(status_code=400, _json={})
        error_type = classify_error(response)
        assert error_type == ErrorType.UNKNOWN

    def test_x_api_v2_format_returns_unknown(self):
        """X API v2 format returns UNKNOWN (placeholder doesn't understand it).

        This documents that the placeholder classifier does NOT handle
        X API v2's actual error format. WS3 must implement classify_x_error().

        Real X API v2 error format:
        {"type": "https://api.x.com/2/problems/...", "title": "...", "detail": "..."}
        """
        # X API v2 actual error format
        response = MockResponse(
            status_code=400,
            _json={
                "type": "https://api.x.com/2/problems/invalid-request",
                "title": "Invalid Request",
                "detail": "The 'query' parameter is required.",
            },
        )
        error_type = classify_error(response)
        # Placeholder returns UNKNOWN because it doesn't understand this format
        assert error_type == ErrorType.UNKNOWN

    def test_all_error_type_values(self):
        """ErrorType contains all expected values."""
        expected = {
            ErrorType.RATE_LIMITED,
            ErrorType.AUTH_EXPIRED,
            ErrorType.CONTENT_INVALID,
            ErrorType.DUPLICATE,
            ErrorType.TRANSIENT,
            ErrorType.UNKNOWN,
        }

        assert set(ErrorType) == expected

    def test_error_type_string_values(self):
        """ErrorType values have correct string representations."""
        assert ErrorType.RATE_LIMITED.value == "rate_limited"
        assert ErrorType.AUTH_EXPIRED.value == "auth_expired"
        assert ErrorType.CONTENT_INVALID.value == "content_invalid"
        assert ErrorType.DUPLICATE.value == "duplicate"
        assert ErrorType.TRANSIENT.value == "transient"
        assert ErrorType.UNKNOWN.value == "unknown"


class TestCustomExceptions:
    """Test custom exception classes."""

    def test_config_error(self):
        """ConfigError can be raised with message."""
        with pytest.raises(ConfigError) as exc_info:
            raise ConfigError("Missing required: ANTHROPIC_API_KEY")

        assert "ANTHROPIC_API_KEY" in str(exc_info.value)

    def test_database_error(self):
        """DatabaseError can be raised with message."""
        with pytest.raises(DatabaseError) as exc_info:
            raise DatabaseError("Failed to connect")

        assert "Failed to connect" in str(exc_info.value)
