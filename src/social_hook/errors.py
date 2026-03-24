"""Error taxonomy and classification for API error handling."""

from enum import Enum
from typing import Any


class ErrorType(Enum):
    """Classification of API errors for appropriate handling."""

    RATE_LIMITED = "rate_limited"  # 429 - retry with backoff
    AUTH_EXPIRED = "auth_expired"  # 401, 403 - alert human, halt
    CONTENT_INVALID = "content_invalid"  # 400 with content error - alert human for edit
    DUPLICATE = "duplicate"  # Content already posted - log and skip
    TRANSIENT = "transient"  # 500, 502, 503 - retry immediately
    UNKNOWN = "unknown"  # Unexpected - log, alert human


class ConfigError(Exception):
    """Raised when configuration is invalid or missing."""

    pass


class DatabaseError(Exception):
    """Raised when database operations fail."""

    pass


class AuthError(Exception):
    """Raised when authentication/authorization fails (LLM or platform)."""

    pass


class MalformedResponseError(Exception):
    """Raised when LLM response has no tool call or invalid tool args."""

    pass


class MaxArcsError(Exception):
    """Raised when attempting to create a 4th active arc."""

    pass


class PromptNotFoundError(Exception):
    """Raised when a prompt file is missing."""

    pass


def classify_x_error(response: Any) -> ErrorType:
    """Classify X API v2 error response.

    X API v2 returns errors in the format:
        {"type": "https://api.x.com/2/problems/...", "title": "...", "detail": "..."}

    The 'type' URI determines the error category.

    Args:
        response: HTTP response object with status_code and json() method

    Returns:
        ErrorType indicating how to handle the error
    """
    status = response.status_code

    if status == 429:
        return ErrorType.RATE_LIMITED
    elif status in (401, 403):
        return ErrorType.AUTH_EXPIRED
    elif status >= 500:
        return ErrorType.TRANSIENT

    # Parse X API v2 error body for 400-level errors
    try:
        body = response.json() if hasattr(response, "json") else {}
    except Exception:
        body = {}

    type_uri = body.get("type", "").lower()
    detail = body.get("detail", "").lower()

    # Check for duplicate before invalid (duplicate may have invalid-request type URI)
    if "duplicate" in type_uri or "duplicate" in detail:
        return ErrorType.DUPLICATE
    elif any(kw in type_uri for kw in ("invalid-request", "invalid")) or any(
        kw in detail for kw in ("too long", "character limit")
    ):
        return ErrorType.CONTENT_INVALID

    return ErrorType.UNKNOWN


def classify_error(response: Any) -> ErrorType:
    """Classify API error response for appropriate handling.

    Args:
        response: HTTP response object with status_code and optional json() method

    Returns:
        ErrorType indicating how to handle the error
    """
    status = response.status_code

    if status == 429:
        return ErrorType.RATE_LIMITED
    elif status in (401, 403):
        return ErrorType.AUTH_EXPIRED
    elif status == 400:
        # Check for specific content errors
        try:
            body = response.json() if hasattr(response, "json") else {}
        except Exception:
            body = {}

        error_code = body.get("error", {}).get("code", "")
        if error_code in ("duplicate_content", "status_duplicate"):
            return ErrorType.DUPLICATE
        elif error_code in ("invalid_text", "text_too_long", "invalid_media"):
            return ErrorType.CONTENT_INVALID
        return ErrorType.UNKNOWN
    elif status >= 500:
        return ErrorType.TRANSIENT
    else:
        return ErrorType.UNKNOWN
