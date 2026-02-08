#!/usr/bin/env python3
"""WS3 Adapters verification script.

Runs 16 checks covering all adapter components using dry-run mode
and dummy credentials. No real API calls are made.

Usage:
    python scripts/verify_ws3_adapters.py
"""

import sys
import time

passed = 0
failed = 0


def check(name: str, fn):
    """Run a single check and report pass/fail."""
    global passed, failed
    print(f"  [{passed + failed + 1:2d}] {name}...", end=" ", flush=True)
    try:
        fn()
        print("PASS")
        passed += 1
    except Exception as e:
        print(f"FAIL: {e}")
        failed += 1


# ── Check 1: PlatformAdapter ABC enforcement ──────────────────────────


def check_platform_abc():
    from social_hook.adapters.platform.base import PlatformAdapter

    try:
        PlatformAdapter()
        raise AssertionError("Should not instantiate ABC")
    except TypeError:
        pass


# ── Check 2: Dataclass creation and field access ──────────────────────


def check_dataclasses():
    from social_hook.adapters.models import MediaResult, PostResult, ThreadResult

    pr = PostResult(success=True, external_id="123", external_url="https://example.com/123")
    assert pr.success is True
    assert pr.external_id == "123"

    tr = ThreadResult(success=True, tweet_results=[pr])
    assert len(tr.tweet_results) == 1

    mr = MediaResult(success=True, file_path="/tmp/test.png")
    assert mr.file_path is not None


# ── Check 3: ThreadResult default (no explicit tweet_results) ─────────


def check_thread_result_default():
    from social_hook.adapters.models import ThreadResult

    tr = ThreadResult(success=False, error="test error")
    assert tr.tweet_results == [], f"Expected empty list, got {tr.tweet_results}"
    assert tr.error == "test error"


# ── Check 4: XAdapter dry-run post ────────────────────────────────────


def check_x_adapter_dry_run_post():
    from social_hook.adapters.platform.x import XAdapter

    adapter = XAdapter("dummy_key", "dummy_secret", "dummy_token", "dummy_token_secret")
    result = adapter.post("Test post", [], dry_run=True)
    assert result.success is True
    assert result.external_id is not None, "Dry-run should return a fake ID"
    assert result.external_url is not None


# ── Check 5: XAdapter thread dry-run ──────────────────────────────────


def check_x_adapter_dry_run_thread():
    from social_hook.adapters.platform.x import XAdapter

    adapter = XAdapter("k", "s", "t", "ts")
    tweets = [
        {"content": f"Tweet {i}", "media_paths": []}
        for i in range(1, 5)
    ]
    result = adapter.post_thread(tweets, dry_run=True)
    assert result.success is True
    assert len(result.tweet_results) == 4, f"Expected 4, got {len(result.tweet_results)}"


# ── Check 6: LinkedInAdapter dry-run post ─────────────────────────────


def check_linkedin_dry_run_post():
    from social_hook.adapters.platform.linkedin import LinkedInAdapter

    adapter = LinkedInAdapter(access_token="dummy_token")
    result = adapter.post("LinkedIn test", [], dry_run=True)
    assert result.success is True
    assert result.external_id is not None


# ── Check 7: MediaAdapter ABC enforcement ─────────────────────────────


def check_media_abc():
    from social_hook.adapters.media.base import MediaAdapter

    try:
        MediaAdapter()
        raise AssertionError("Should not instantiate ABC")
    except TypeError:
        pass


# ── Check 8: MermaidAdapter supports() and dry-run ────────────────────


def check_mermaid_dry_run():
    from social_hook.adapters.media.mermaid import MermaidAdapter

    adapter = MermaidAdapter()
    assert adapter.supports("mermaid") is True
    assert adapter.supports("diagram") is True
    assert adapter.supports("unknown") is False

    result = adapter.generate({"diagram": "graph LR\n    A-->B"}, dry_run=True)
    assert result.success is True
    assert result.file_path is not None


# ── Check 9: PlaywrightAdapter dry-run ────────────────────────────────


def check_playwright_dry_run():
    from social_hook.adapters.media.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter()
    result = adapter.generate({"url": "https://example.com"}, dry_run=True)
    assert result.success is True
    assert result.file_path is not None


# ── Check 10: RaySoAdapter dry-run ────────────────────────────────────


def check_rayso_dry_run():
    from social_hook.adapters.media.rayso import RaySoAdapter

    adapter = RaySoAdapter()
    result = adapter.generate(
        {"code": "print('hello')", "language": "python"}, dry_run=True
    )
    assert result.success is True
    assert result.file_path is not None


# ── Check 11: Rate limiting ───────────────────────────────────────────


def check_rate_limiting():
    from social_hook.adapters.rate_limit import (
        RateLimitState,
        calculate_backoff,
        should_retry,
    )

    # calculate_backoff: attempts=1 → base 60*2^1 = 120s + jitter
    backoff = calculate_backoff(1)
    assert backoff.total_seconds() >= 120, f"Expected >= 120s, got {backoff.total_seconds()}"

    # calculate_backoff: cap at 1 hour
    backoff_high = calculate_backoff(10)
    assert backoff_high.total_seconds() <= 3960, f"Expected <= 3960s, got {backoff_high.total_seconds()}"

    # should_retry
    state = RateLimitState(attempts=0)
    assert should_retry(state, max_attempts=3) is True

    state.attempts = 3
    assert should_retry(state, max_attempts=3) is False


# ── Check 12: Error classification (WS1) ─────────────────────────────


def check_classify_error():
    from social_hook.errors import ErrorType, classify_error

    class MockResponse:
        def __init__(self, status_code, body=None):
            self.status_code = status_code
            self._body = body or {}

        def json(self):
            return self._body

    assert classify_error(MockResponse(429)) == ErrorType.RATE_LIMITED
    assert classify_error(MockResponse(401)) == ErrorType.AUTH_EXPIRED
    assert classify_error(MockResponse(503)) == ErrorType.TRANSIENT
    assert classify_error(MockResponse(400)) == ErrorType.UNKNOWN


# ── Check 13: X-specific error classification (WS3) ──────────────────


def check_classify_x_error():
    from social_hook.errors import ErrorType, classify_x_error

    class MockResponse:
        def __init__(self, status_code, body=None):
            self.status_code = status_code
            self._body = body or {}

        def json(self):
            return self._body

    assert classify_x_error(MockResponse(429)) == ErrorType.RATE_LIMITED
    assert classify_x_error(MockResponse(401)) == ErrorType.AUTH_EXPIRED
    assert classify_x_error(MockResponse(503)) == ErrorType.TRANSIENT

    # X API v2 duplicate error
    dup_body = {
        "type": "https://api.x.com/2/problems/duplicate",
        "title": "Duplicate",
        "detail": "duplicate content",
    }
    assert classify_x_error(MockResponse(400, dup_body)) == ErrorType.DUPLICATE

    # X API v2 invalid request
    invalid_body = {
        "type": "https://api.x.com/2/problems/invalid-request",
        "title": "Invalid",
        "detail": "bad request",
    }
    assert classify_x_error(MockResponse(400, invalid_body)) == ErrorType.CONTENT_INVALID


# ── Check 14: Registry — MEDIA_ADAPTER_NAMES ─────────────────────────


def check_registry_names():
    from social_hook.adapters.registry import MEDIA_ADAPTER_NAMES

    expected = {"mermaid", "nano_banana_pro", "playwright", "ray_so"}
    assert set(MEDIA_ADAPTER_NAMES) == expected, f"Expected {expected}, got {set(MEDIA_ADAPTER_NAMES)}"


# ── Check 15: Registry — get_media_adapter ────────────────────────────


def check_registry_get_adapter():
    from social_hook.adapters.media.mermaid import MermaidAdapter
    from social_hook.adapters.media.nanabananapro import NanaBananaAdapter
    from social_hook.adapters.registry import clear_adapter_cache, get_media_adapter

    # Clear cache so we get fresh instances
    clear_adapter_cache()

    mermaid = get_media_adapter("mermaid")
    assert isinstance(mermaid, MermaidAdapter)

    nano = get_media_adapter("nano_banana_pro", api_key="dummy_key")
    assert isinstance(nano, NanaBananaAdapter)

    # Missing api_key should raise ValueError
    clear_adapter_cache()
    try:
        get_media_adapter("nano_banana_pro")
        raise AssertionError("Should raise ValueError for missing api_key")
    except ValueError:
        pass

    # Invalid name returns None
    assert get_media_adapter("invalid") is None

    clear_adapter_cache()


# ── Check 16: handle_rate_limit ───────────────────────────────────────


def check_handle_rate_limit():
    from social_hook.adapters.rate_limit import RateLimitState, handle_rate_limit

    # X platform: x-rate-limit-reset (Unix timestamp)
    class MockXResponse:
        headers = {"x-rate-limit-reset": str(int(time.time()) + 60)}

    state = RateLimitState(attempts=0)
    new_state = handle_rate_limit(MockXResponse(), state, platform="x")
    assert new_state.attempts == 1
    assert new_state.backoff_until is not None

    # Generic/LinkedIn: retry-after (seconds)
    class MockGenericResponse:
        headers = {"retry-after": "60"}

    state2 = RateLimitState(attempts=0)
    new_state2 = handle_rate_limit(MockGenericResponse(), state2, platform="generic")
    assert new_state2.attempts == 1
    assert new_state2.backoff_until is not None


# ── Main ──────────────────────────────────────────────────────────────


def main():
    print("WS3 Adapters Verification")
    print("=" * 50)

    check("PlatformAdapter ABC enforcement", check_platform_abc)
    check("Dataclass creation and field access", check_dataclasses)
    check("ThreadResult default (no tweet_results)", check_thread_result_default)
    check("XAdapter dry-run post", check_x_adapter_dry_run_post)
    check("XAdapter thread dry-run (4 tweets)", check_x_adapter_dry_run_thread)
    check("LinkedInAdapter dry-run post", check_linkedin_dry_run_post)
    check("MediaAdapter ABC enforcement", check_media_abc)
    check("MermaidAdapter supports() + dry-run", check_mermaid_dry_run)
    check("PlaywrightAdapter dry-run", check_playwright_dry_run)
    check("RaySoAdapter dry-run", check_rayso_dry_run)
    check("Rate limiting (backoff, retry)", check_rate_limiting)
    check("Error classification (WS1)", check_classify_error)
    check("X-specific error classification (WS3)", check_classify_x_error)
    check("Registry: MEDIA_ADAPTER_NAMES", check_registry_names)
    check("Registry: get_media_adapter", check_registry_get_adapter)
    check("handle_rate_limit (X + generic)", check_handle_rate_limit)

    print("=" * 50)
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")

    if failed > 0:
        print("\nVerification FAILED")
        sys.exit(1)
    else:
        print("\nAll checks passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
