"""Tests for rate limiting (T11).

Source: WS3_ADAPTERS.md T11 (lines 215-230)
Source: TECHNICAL_ARCHITECTURE.md lines 1263-1331
"""

import time
from datetime import datetime, timedelta

from social_hook.adapters.rate_limit import (
    RateLimitState,
    calculate_backoff,
    handle_rate_limit,
    should_retry,
)

# =============================================================================
# T11: Rate Limiting
# =============================================================================


class TestCalculateBackoff:
    """T11: calculate_backoff() exponential growth with jitter."""

    def test_attempts_1(self):
        """attempts=1: base 60*2^1=120s, jitter up to 10% -> 120-132s."""
        backoff = calculate_backoff(1)
        seconds = backoff.total_seconds()
        assert 120 <= seconds <= 132, f"Expected 120-132s, got {seconds}s"

    def test_attempts_2(self):
        """attempts=2: base 60*2^2=240s, jitter up to 10% -> 240-264s."""
        backoff = calculate_backoff(2)
        seconds = backoff.total_seconds()
        assert 240 <= seconds <= 264, f"Expected 240-264s, got {seconds}s"

    def test_attempts_3(self):
        """attempts=3: base 60*2^3=480s, jitter up to 10% -> 480-528s."""
        backoff = calculate_backoff(3)
        seconds = backoff.total_seconds()
        assert 480 <= seconds <= 528, f"Expected 480-528s, got {seconds}s"

    def test_cap_at_1_hour(self):
        """attempts=10: capped at 3600s (1 hour) + jitter."""
        backoff = calculate_backoff(10)
        seconds = backoff.total_seconds()
        # Cap is 3600 + up to 10% jitter = max 3960
        assert seconds <= 3960, f"Expected <= 3960s, got {seconds}s"
        # Should be at least 3600 (the cap)
        assert seconds >= 3600, f"Expected >= 3600s, got {seconds}s"

    def test_attempts_0(self):
        """attempts=0: base 60*2^0=60s, jitter up to 10% -> 60-66s."""
        backoff = calculate_backoff(0)
        seconds = backoff.total_seconds()
        assert 60 <= seconds <= 66, f"Expected 60-66s, got {seconds}s"


class TestShouldRetry:
    """T11: should_retry() logic."""

    def test_under_max_returns_true(self):
        """attempts=2, max=3: should retry."""
        state = RateLimitState(attempts=2)
        assert should_retry(state, max_attempts=3) is True

    def test_at_max_returns_false(self):
        """attempts=3, max=3: should not retry."""
        state = RateLimitState(attempts=3)
        assert should_retry(state, max_attempts=3) is False

    def test_over_max_returns_false(self):
        """attempts=5, max=3: should not retry."""
        state = RateLimitState(attempts=5)
        assert should_retry(state, max_attempts=3) is False

    def test_zero_attempts_returns_true(self):
        """Fresh state with 0 attempts: should retry."""
        state = RateLimitState(attempts=0)
        assert should_retry(state, max_attempts=3) is True

    def test_backoff_active_returns_false(self):
        """During backoff period: should not retry even if under max."""
        state = RateLimitState(
            attempts=1,
            backoff_until=datetime.now() + timedelta(minutes=5),
        )
        assert should_retry(state, max_attempts=3) is False

    def test_backoff_expired_returns_true(self):
        """After backoff period: should retry."""
        state = RateLimitState(
            attempts=1,
            backoff_until=datetime.now() - timedelta(minutes=1),
        )
        assert should_retry(state, max_attempts=3) is True


class TestHandleRateLimit:
    """T11: handle_rate_limit() platform-specific header parsing."""

    def test_x_rate_limit_reset_header(self):
        """X platform: uses x-rate-limit-reset Unix timestamp."""
        future_ts = int(time.time()) + 120
        state = RateLimitState(attempts=0)

        class MockXResp:
            headers = {"x-rate-limit-reset": str(future_ts)}

        new_state = handle_rate_limit(MockXResp(), state, platform="x")
        assert new_state.attempts == 1
        assert new_state.backoff_until is not None
        # backoff_until should be close to the timestamp we set
        expected = datetime.fromtimestamp(future_ts)
        diff = abs((new_state.backoff_until - expected).total_seconds())
        assert diff < 2, f"backoff_until off by {diff}s"

    def test_generic_retry_after_header(self):
        """Generic/LinkedIn: uses retry-after seconds."""
        state = RateLimitState(attempts=0)

        class MockResp:
            headers = {"retry-after": "120"}

        before = datetime.now()
        new_state = handle_rate_limit(MockResp(), state, platform="generic")
        assert new_state.attempts == 1
        assert new_state.backoff_until is not None
        # Should be ~120 seconds from now
        expected_min = before + timedelta(seconds=119)
        assert new_state.backoff_until >= expected_min

    def test_linkedin_retry_after_header(self):
        """LinkedIn platform: also uses retry-after."""
        state = RateLimitState(attempts=0)

        class MockResp:
            headers = {"retry-after": "60"}

        new_state = handle_rate_limit(MockResp(), state, platform="linkedin")
        assert new_state.attempts == 1
        assert new_state.backoff_until is not None

    def test_no_header_falls_back_to_exponential(self):
        """No rate limit header: falls back to exponential backoff."""
        state = RateLimitState(attempts=2)

        class MockResp:
            headers = {}

        before = datetime.now()
        new_state = handle_rate_limit(MockResp(), state, platform="generic")
        assert new_state.attempts == 3
        assert new_state.backoff_until is not None
        # Should use calculate_backoff(2) which is ~240s
        diff = (new_state.backoff_until - before).total_seconds()
        assert diff >= 240, f"Fallback backoff too short: {diff}s"

    def test_increments_attempts(self):
        """Each call increments attempts counter."""
        state = RateLimitState(attempts=0)

        class MockResp:
            headers = {"retry-after": "60"}

        state = handle_rate_limit(MockResp(), state, platform="generic")
        assert state.attempts == 1
        state = handle_rate_limit(MockResp(), state, platform="generic")
        assert state.attempts == 2

    def test_sets_last_attempt(self):
        """handle_rate_limit sets last_attempt timestamp."""
        state = RateLimitState(attempts=0)

        class MockResp:
            headers = {"retry-after": "60"}

        before = datetime.now()
        new_state = handle_rate_limit(MockResp(), state, platform="generic")
        assert new_state.last_attempt is not None
        assert new_state.last_attempt >= before
