"""Tests for rate limit gate."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from social_hook.rate_limits import GateResult, check_rate_limit


def _make_rate_config(max_per_day=15, min_gap=10):
    return SimpleNamespace(
        max_evaluations_per_day=max_per_day,
        min_evaluation_gap_minutes=min_gap,
    )


class TestGateResult:
    def test_blocked(self):
        r = GateResult(blocked=True, reason="cap hit")
        assert r.blocked is True
        assert r.reason == "cap hit"

    def test_allowed(self):
        r = GateResult(blocked=False, reason="")
        assert r.blocked is False
        assert r.reason == ""


class TestCheckRateLimit:
    @patch("social_hook.rate_limits.ops.get_last_auto_evaluation_time")
    @patch("social_hook.rate_limits.ops.get_today_auto_evaluation_count")
    def test_allows_when_under_cap_and_gap_elapsed(self, mock_count, mock_time):
        mock_count.return_value = 5
        # Last eval was 30 minutes ago
        mock_time.return_value = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()

        result = check_rate_limit(None, _make_rate_config(max_per_day=15, min_gap=10))
        assert result.blocked is False
        assert result.reason == ""

    @patch("social_hook.rate_limits.ops.get_last_auto_evaluation_time")
    @patch("social_hook.rate_limits.ops.get_today_auto_evaluation_count")
    def test_blocks_when_daily_cap_reached(self, mock_count, mock_time):
        mock_count.return_value = 15

        result = check_rate_limit(None, _make_rate_config(max_per_day=15, min_gap=10))
        assert result.blocked is True
        assert "Daily limit reached" in result.reason
        assert "15/15" in result.reason

    @patch("social_hook.rate_limits.ops.get_last_auto_evaluation_time")
    @patch("social_hook.rate_limits.ops.get_today_auto_evaluation_count")
    def test_blocks_when_gap_not_elapsed(self, mock_count, mock_time):
        mock_count.return_value = 2
        # Last eval was 3 minutes ago, gap is 10
        mock_time.return_value = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()

        result = check_rate_limit(None, _make_rate_config(max_per_day=15, min_gap=10))
        assert result.blocked is True
        assert "Gap not elapsed" in result.reason
        assert "remaining" in result.reason

    @patch("social_hook.rate_limits.ops.get_last_auto_evaluation_time")
    @patch("social_hook.rate_limits.ops.get_today_auto_evaluation_count")
    def test_allows_with_zero_gap(self, mock_count, mock_time):
        mock_count.return_value = 2
        # Last eval was 0 seconds ago
        mock_time.return_value = datetime.now(timezone.utc).isoformat()

        result = check_rate_limit(None, _make_rate_config(max_per_day=15, min_gap=0))
        assert result.blocked is False

    @patch("social_hook.rate_limits.ops.get_last_auto_evaluation_time")
    @patch("social_hook.rate_limits.ops.get_today_auto_evaluation_count")
    def test_allows_when_no_previous_evaluations(self, mock_count, mock_time):
        mock_count.return_value = 0
        mock_time.return_value = None

        result = check_rate_limit(None, _make_rate_config(max_per_day=15, min_gap=10))
        assert result.blocked is False

    @patch("social_hook.rate_limits.ops.get_last_auto_evaluation_time")
    @patch("social_hook.rate_limits.ops.get_today_auto_evaluation_count")
    def test_daily_cap_checked_before_gap(self, mock_count, mock_time):
        """Daily cap is checked first; gap is not even consulted."""
        mock_count.return_value = 15

        result = check_rate_limit(None, _make_rate_config(max_per_day=15, min_gap=10))
        assert result.blocked is True
        assert "Daily limit" in result.reason
        mock_time.assert_not_called()
