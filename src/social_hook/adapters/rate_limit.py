"""Rate limiting utilities with exponential backoff."""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


@dataclass
class RateLimitState:
    """Tracks rate limit state for retry logic."""

    attempts: int = 0
    last_attempt: datetime | None = None
    backoff_until: datetime | None = None


def calculate_backoff(attempts: int) -> timedelta:
    """Calculate exponential backoff with jitter.

    Formula: base 60s * 2^attempts, capped at 1 hour, with 10% jitter.

    Args:
        attempts: Number of retry attempts so far

    Returns:
        Backoff duration as timedelta
    """
    base_seconds = min(60 * (2**attempts), 3600)  # Cap at 1 hour
    jitter = random.uniform(0, base_seconds * 0.1)
    return timedelta(seconds=base_seconds + jitter)


def should_retry(state: RateLimitState, max_attempts: int = 3) -> bool:
    """Check if retry is allowed based on current state.

    Args:
        state: Current rate limit state
        max_attempts: Maximum number of attempts allowed

    Returns:
        True if retry is allowed, False otherwise
    """
    if state.attempts >= max_attempts:
        return False
    return not (state.backoff_until and datetime.now() < state.backoff_until)


def handle_rate_limit(
    response: Any, state: RateLimitState, platform: str = "generic"
) -> RateLimitState:
    """Update state based on rate limit response.

    Platform-specific header handling:
    - X API: Uses x-rate-limit-reset (Unix timestamp)
    - LinkedIn/others: Uses retry-after (seconds to wait)

    Args:
        response: HTTP response object with headers
        state: Current rate limit state to update
        platform: Platform identifier ("x", "linkedin", "generic")

    Returns:
        Updated rate limit state
    """
    headers = getattr(response, "headers", {})

    if platform == "x" and "x-rate-limit-reset" in headers:
        # X API uses Unix timestamp
        reset_timestamp = int(headers["x-rate-limit-reset"])
        state.backoff_until = datetime.fromtimestamp(reset_timestamp)
    elif "retry-after" in headers:
        # Standard retry-after header (LinkedIn, others)
        wait_seconds = int(headers["retry-after"])
        state.backoff_until = datetime.now() + timedelta(seconds=wait_seconds)
    else:
        # Fall back to exponential backoff
        state.backoff_until = datetime.now() + calculate_backoff(state.attempts)

    state.attempts += 1
    state.last_attempt = datetime.now()

    return state
