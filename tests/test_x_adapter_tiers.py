"""Tests for XAdapter tier-aware character limits (Phase A)."""

from unittest.mock import patch

import pytest

from social_hook.adapters.platform.x import XAdapter
from social_hook.errors import ConfigError


class TestXAdapterTierInit:
    """Tier parameter on XAdapter."""

    def test_default_tier_is_free(self):
        adapter = XAdapter("k", "s", "t", "ts")
        assert adapter.tier == "free"
        assert adapter.char_limit == 280

    def test_basic_tier(self):
        adapter = XAdapter("k", "s", "t", "ts", tier="basic")
        assert adapter.tier == "basic"
        assert adapter.char_limit == 25_000

    def test_premium_tier(self):
        adapter = XAdapter("k", "s", "t", "ts", tier="premium")
        assert adapter.tier == "premium"
        assert adapter.char_limit == 25_000

    def test_premium_plus_tier(self):
        adapter = XAdapter("k", "s", "t", "ts", tier="premium_plus")
        assert adapter.tier == "premium_plus"
        assert adapter.char_limit == 25_000

    def test_invalid_tier_raises(self):
        with pytest.raises(ConfigError, match="Invalid tier"):
            XAdapter("k", "s", "t", "ts", tier="ultra")

    def test_keyword_only_tier(self):
        """Tier must be keyword-only — can't be passed positionally."""
        with pytest.raises(TypeError):
            XAdapter("k", "s", "t", "ts", "premium")


class TestXAdapterTierPost:
    """Tier-aware post() character validation."""

    @patch("social_hook.adapters.platform.x.requests.post")
    def test_free_tier_rejects_over_280(self, mock_post):
        adapter = XAdapter("k", "s", "t", "ts", tier="free")
        result = adapter.post("x" * 300)
        assert result.success is False
        assert "280" in result.error
        mock_post.assert_not_called()

    @patch("social_hook.adapters.platform.x.requests.post")
    def test_free_tier_accepts_280(self, mock_post):
        adapter = XAdapter("k", "s", "t", "ts", tier="free")
        result = adapter.post("x" * 280, dry_run=True)
        assert result.success is True

    @patch("social_hook.adapters.platform.x.requests.post")
    def test_premium_tier_accepts_long_post(self, mock_post):
        """Premium tier accepts posts up to 25K chars."""
        adapter = XAdapter("k", "s", "t", "ts", tier="premium")
        result = adapter.post("x" * 1000, dry_run=True)
        assert result.success is True

    @patch("social_hook.adapters.platform.x.requests.post")
    def test_basic_tier_accepts_long_post(self, mock_post):
        """Basic tier accepts posts up to 25K chars."""
        adapter = XAdapter("k", "s", "t", "ts", tier="basic")
        result = adapter.post("x" * 5000, dry_run=True)
        assert result.success is True

    @patch("social_hook.adapters.platform.x.requests.post")
    def test_premium_plus_accepts_long_post(self, mock_post):
        adapter = XAdapter("k", "s", "t", "ts", tier="premium_plus")
        result = adapter.post("x" * 10000, dry_run=True)
        assert result.success is True

    @patch("social_hook.adapters.platform.x.requests.post")
    def test_premium_rejects_over_25k(self, mock_post):
        adapter = XAdapter("k", "s", "t", "ts", tier="premium")
        result = adapter.post("x" * 26000)
        assert result.success is False
        assert "25000" in result.error
        mock_post.assert_not_called()


class TestXAdapterThreadTierIndependent:
    """Thread tweets are always 280 chars regardless of tier."""

    def test_thread_rejects_long_tweet_on_premium(self):
        """Even on premium tier, thread tweets are capped at 280."""
        adapter = XAdapter("k", "s", "t", "ts", tier="premium")
        tweets = [{"content": "x" * 300}]
        result = adapter.post_thread(tweets, dry_run=False)
        # Should fail validation before hitting API
        assert result.success is False
        assert "280" in result.tweet_results[0].error

    def test_thread_accepts_280_per_tweet_on_premium(self):
        """Premium tier thread with 280-char tweets works."""
        adapter = XAdapter("k", "s", "t", "ts", tier="premium")
        tweets = [{"content": "x" * 280} for _ in range(4)]
        result = adapter.post_thread(tweets, dry_run=True)
        assert result.success is True
        assert len(result.tweet_results) == 4
