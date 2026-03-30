"""Tests for social_hook.scheduling.find_optimal_slot — pure scheduling algorithm."""

from datetime import datetime, timezone

from social_hook.scheduling import find_optimal_slot


class TestFindOptimalSlot:
    """Pure scheduling algorithm tests (no DB needed)."""

    def test_basic_slot_found(self):
        # Wednesday 8am UTC — should find 9am slot
        now = datetime(2026, 3, 25, 8, 0, tzinfo=timezone.utc)  # Wednesday
        result = find_optimal_slot(
            existing_post_times=[],
            scheduled_times=[],
            optimal_days=["Wed"],
            optimal_hours=[9, 12],
            now=now,
        )
        assert not result.deferred
        assert result.is_optimal_day
        assert result.datetime.hour == 9

    def test_weekly_limit_defers(self):
        now = datetime(2026, 3, 25, 8, 0, tzinfo=timezone.utc)
        result = find_optimal_slot(
            existing_post_times=[],
            scheduled_times=[],
            weekly_count=5,
            max_per_week=5,
            now=now,
        )
        assert result.deferred
        assert "Weekly limit" in result.day_reason

    def test_min_gap_enforced(self):
        now = datetime(2026, 3, 25, 8, 50, tzinfo=timezone.utc)
        recent = datetime(2026, 3, 25, 8, 45, tzinfo=timezone.utc)
        result = find_optimal_slot(
            existing_post_times=[recent],
            scheduled_times=[],
            min_gap_minutes=30,
            optimal_hours=[9, 12],
            optimal_days=["Wed"],
            now=now,
        )
        # 9am is only 15 min after 8:45, so should skip to 12pm
        assert result.datetime.hour == 12

    def test_skips_full_day(self):
        now = datetime(2026, 3, 25, 8, 0, tzinfo=timezone.utc)
        result = find_optimal_slot(
            existing_post_times=[],
            scheduled_times=[],
            posts_today_count=3,
            max_posts_per_day=3,
            optimal_hours=[9, 12],
            optimal_days=["Wed", "Thu"],
            now=now,
        )
        # Today (Wed) is full, should advance to Thu
        assert result.datetime.day == 26

    def test_scheduled_conflict_avoided(self):
        now = datetime(2026, 3, 25, 8, 0, tzinfo=timezone.utc)
        already_scheduled = datetime(2026, 3, 25, 9, 0, tzinfo=timezone.utc)
        result = find_optimal_slot(
            existing_post_times=[],
            scheduled_times=[already_scheduled],
            min_gap_minutes=30,
            optimal_hours=[9, 12],
            optimal_days=["Wed"],
            now=now,
        )
        # 9am conflicts with scheduled, should pick 12pm
        assert result.datetime.hour == 12

    def test_fallback_when_no_slots(self):
        now = datetime(2026, 3, 25, 23, 0, tzinfo=timezone.utc)
        result = find_optimal_slot(
            existing_post_times=[],
            scheduled_times=[],
            optimal_hours=[],  # No optimal hours
            optimal_days=[],
            now=now,
        )
        assert "Fallback" in result.time_reason

    def test_timezone_handling(self):
        # 6pm UTC = 11am Pacific — should find optimal hour in local time
        now = datetime(2026, 3, 25, 18, 0, tzinfo=timezone.utc)
        result = find_optimal_slot(
            existing_post_times=[],
            scheduled_times=[],
            tz="America/Los_Angeles",
            optimal_hours=[12, 17],
            optimal_days=["Wed"],
            now=now,
        )
        assert not result.deferred
        # Should pick 12pm Pacific = 19:00 UTC (PDT = UTC-7)
        assert result.datetime.hour == 19

    def test_no_weekly_limit(self):
        now = datetime(2026, 3, 25, 8, 0, tzinfo=timezone.utc)
        result = find_optimal_slot(
            existing_post_times=[],
            scheduled_times=[],
            weekly_count=100,
            max_per_week=None,
            optimal_hours=[9],
            optimal_days=["Wed"],
            now=now,
        )
        # No weekly limit, should still find a slot
        assert not result.deferred

    def test_invalid_timezone_falls_back_to_utc(self):
        now = datetime(2026, 3, 25, 8, 0, tzinfo=timezone.utc)
        result = find_optimal_slot(
            existing_post_times=[],
            scheduled_times=[],
            tz="Invalid/Timezone",
            optimal_hours=[9],
            optimal_days=["Wed"],
            now=now,
        )
        assert not result.deferred
        assert result.datetime.hour == 9
