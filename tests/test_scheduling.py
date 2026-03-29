"""Tests for scheduling algorithm (T30)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from social_hook.db import insert_decision, insert_draft, insert_post, insert_project
from social_hook.filesystem import generate_id
from social_hook.models.core import Decision, Draft, Post, Project
from social_hook.scheduling import (
    ProjectSchedulingState,
    ScheduleResult,
    _is_today,
    calculate_optimal_time,
    get_scheduling_state,
)


class TestScheduleResult:
    """Tests for ScheduleResult dataclass."""

    def test_create_schedule_result(self):
        dt = datetime(2026, 2, 10, 17, 0, tzinfo=timezone.utc)
        result = ScheduleResult(
            datetime=dt,
            is_optimal_day=True,
            day_reason="Optimal day",
            time_reason="Optimal hour (17:00)",
        )
        assert result.datetime == dt
        assert result.is_optimal_day is True


class TestCalculateOptimalTime:
    """Tests for calculate_optimal_time."""

    def _setup_project(self, conn):
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)
        return project

    def test_basic_scheduling(self, temp_db):
        """Returns a ScheduleResult with a future datetime."""
        project = self._setup_project(temp_db)
        result = calculate_optimal_time(temp_db, project.id)
        assert isinstance(result, ScheduleResult)
        assert result.datetime > datetime.now(timezone.utc)

    def test_respects_optimal_hours(self, temp_db):
        """Scheduled time uses one of the optimal hours."""
        project = self._setup_project(temp_db)
        result = calculate_optimal_time(
            temp_db,
            project.id,
            tz="UTC",
            optimal_hours=[9, 12, 17],
        )
        # The hour should be one of the optimal hours
        assert result.datetime.hour in [9, 12, 17]

    def test_respects_max_posts_per_day(self, temp_db):
        """Advances to next day when max_posts_per_day reached."""
        project = self._setup_project(temp_db)

        # Create decisions and drafts, then posts for today
        for i in range(3):
            d = Decision(
                id=generate_id("decision"),
                project_id=project.id,
                commit_hash=f"hash{i}",
                decision="draft",
                reasoning="test",
            )
            insert_decision(temp_db, d)
            dr = Draft(
                id=generate_id("draft"),
                project_id=project.id,
                decision_id=d.id,
                platform="x",
                content=f"content {i}",
            )
            insert_draft(temp_db, dr)
            post = Post(
                id=generate_id("post"),
                draft_id=dr.id,
                project_id=project.id,
                platform="x",
                content=f"posted {i}",
            )
            insert_post(temp_db, post)

        result = calculate_optimal_time(
            temp_db,
            project.id,
            max_posts_per_day=3,
        )
        # Should be scheduled for a future day
        now = datetime.now(timezone.utc)
        assert result.datetime.date() > now.date()

    def test_timezone_handling(self, temp_db):
        """Handles timezone conversion correctly."""
        project = self._setup_project(temp_db)
        result = calculate_optimal_time(
            temp_db,
            project.id,
            tz="America/New_York",
            optimal_hours=[9, 12, 17],
        )
        assert result.datetime.tzinfo is not None
        assert isinstance(result, ScheduleResult)

    def test_invalid_timezone_fallback(self, temp_db):
        """Falls back to UTC for invalid timezone."""
        project = self._setup_project(temp_db)
        result = calculate_optimal_time(
            temp_db,
            project.id,
            tz="Invalid/Timezone",
        )
        assert isinstance(result, ScheduleResult)
        assert result.datetime > datetime.now(timezone.utc)

    def test_single_optimal_day(self, temp_db):
        """Works with a single optimal day."""
        project = self._setup_project(temp_db)
        result = calculate_optimal_time(
            temp_db,
            project.id,
            optimal_days=["Mon"],
            optimal_hours=[9],
        )
        assert isinstance(result, ScheduleResult)

    def test_cross_project_coordination(self, temp_db):
        """Posts from other projects count toward max_posts_per_day."""
        p1 = self._setup_project(temp_db)
        p2 = Project(id=generate_id("project"), name="other", repo_path="/tmp/other")
        insert_project(temp_db, p2)

        # Create posts for project 2 today
        for i in range(3):
            d = Decision(
                id=generate_id("decision"),
                project_id=p2.id,
                commit_hash=f"hash{i}",
                decision="draft",
                reasoning="test",
            )
            insert_decision(temp_db, d)
            dr = Draft(
                id=generate_id("draft"),
                project_id=p2.id,
                decision_id=d.id,
                platform="x",
                content=f"c{i}",
            )
            insert_draft(temp_db, dr)
            post = Post(
                id=generate_id("post"),
                draft_id=dr.id,
                project_id=p2.id,
                platform="x",
                content=f"posted {i}",
            )
            insert_post(temp_db, post)

        result = calculate_optimal_time(
            temp_db,
            p1.id,
            max_posts_per_day=3,
        )
        # All 3 slots used by project 2, so should schedule for tomorrow
        now = datetime.now(timezone.utc)
        assert result.datetime.date() > now.date()


class TestPlatformFilter:
    """Tests for platform parameter in calculate_optimal_time."""

    def _setup_project(self, conn):
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)
        return project

    def test_platform_filter_posts(self, temp_db):
        """Platform param filters today's posts by platform."""
        project = self._setup_project(temp_db)

        # Create 3 posts for X today
        for i in range(3):
            d = Decision(
                id=generate_id("decision"),
                project_id=project.id,
                commit_hash=f"hash{i}",
                decision="draft",
                reasoning="test",
            )
            insert_decision(temp_db, d)
            dr = Draft(
                id=generate_id("draft"),
                project_id=project.id,
                decision_id=d.id,
                platform="x",
                content=f"content {i}",
            )
            insert_draft(temp_db, dr)
            post = Post(
                id=generate_id("post"),
                draft_id=dr.id,
                project_id=project.id,
                platform="x",
                content=f"posted {i}",
            )
            insert_post(temp_db, post)

        # With platform=None (cross-platform), max reached
        result_all = calculate_optimal_time(
            temp_db,
            project.id,
            max_posts_per_day=3,
        )
        now = datetime.now(timezone.utc)
        assert result_all.datetime.date() > now.date()

        # With platform="linkedin", no posts exist — should schedule today
        result_li = calculate_optimal_time(
            temp_db,
            project.id,
            platform="linkedin",
            max_posts_per_day=3,
        )
        # LinkedIn has no posts today, can schedule today
        assert isinstance(result_li, ScheduleResult)

    def test_no_platform_filter_backward_compat(self, temp_db):
        """Platform=None preserves existing cross-platform behavior."""
        project = self._setup_project(temp_db)
        result = calculate_optimal_time(temp_db, project.id)
        assert isinstance(result, ScheduleResult)
        assert result.datetime > datetime.now(timezone.utc)


class TestMaxPerWeekDeferral:
    """Tests for max_per_week weekly deferral in calculate_optimal_time."""

    def _setup_project(self, conn):
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)
        return project

    def test_defers_when_weekly_limit_reached(self, temp_db):
        """When max_per_week posts exist in last 7 days, result is deferred."""
        project = self._setup_project(temp_db)

        # Create 5 posts (to hit max_per_week=5)
        for i in range(5):
            d = Decision(
                id=generate_id("decision"),
                project_id=project.id,
                commit_hash=f"hash{i}",
                decision="draft",
                reasoning="test",
            )
            insert_decision(temp_db, d)
            dr = Draft(
                id=generate_id("draft"),
                project_id=project.id,
                decision_id=d.id,
                platform="x",
                content=f"content {i}",
            )
            insert_draft(temp_db, dr)
            post = Post(
                id=generate_id("post"),
                draft_id=dr.id,
                project_id=project.id,
                platform="x",
                content=f"posted {i}",
            )
            insert_post(temp_db, post)

        result = calculate_optimal_time(
            temp_db,
            project.id,
            max_per_week=5,
        )
        assert result.deferred is True
        assert "Weekly limit" in result.day_reason

    def test_no_deferral_when_under_limit(self, temp_db):
        """When max_per_week is not reached, result is not deferred."""
        project = self._setup_project(temp_db)

        result = calculate_optimal_time(
            temp_db,
            project.id,
            max_per_week=10,
        )
        assert result.deferred is False

    def test_no_deferral_when_max_per_week_none(self, temp_db):
        """When max_per_week is None (default), no deferral logic runs."""
        project = self._setup_project(temp_db)

        result = calculate_optimal_time(temp_db, project.id)
        assert result.deferred is False


class TestIsToday:
    """Tests for the _is_today helper."""

    def test_today_utc(self):
        """A datetime from now is today in UTC."""
        now = datetime.now(timezone.utc)
        assert _is_today(now, ZoneInfo("UTC")) is True

    def test_yesterday_utc(self):
        """A datetime from yesterday is not today."""
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        assert _is_today(yesterday, ZoneInfo("UTC")) is False

    def test_naive_datetime_treated_as_utc(self):
        """A naive datetime is treated as UTC."""
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        assert _is_today(now_naive, ZoneInfo("UTC")) is True

    def test_timezone_boundary(self):
        """A UTC time near midnight may be a different day in another timezone."""
        # 2026-03-08 01:00 UTC = 2026-03-07 20:00 in America/New_York (EST, UTC-5)
        dt = datetime(2026, 3, 8, 1, 0, tzinfo=timezone.utc)
        ny_tz = ZoneInfo("America/New_York")
        # _is_today compares to "now", so we only check consistency
        result = _is_today(dt, ny_tz)
        assert isinstance(result, bool)


class TestGetSchedulingState:
    """Tests for get_scheduling_state."""

    def _setup_project(self, conn):
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)
        return project

    def _make_config(self, platforms=None):
        """Build a Config-like mock."""
        config = MagicMock()
        config.scheduling.timezone = "UTC"
        config.scheduling.max_per_week = 10
        if platforms is None:
            platforms = {}
        config.platforms = platforms
        return config

    def _make_platform_config(self, enabled=True, priority="primary"):
        pcfg = MagicMock()
        pcfg.enabled = enabled
        pcfg.priority = priority
        pcfg.type = "builtin"
        pcfg.description = None
        pcfg.account_tier = "free"
        pcfg.filter = None
        pcfg.frequency = None
        pcfg.format = None
        pcfg.max_length = None
        return pcfg

    def _make_resolved(self, max_posts_per_day=3):
        """Build a mock ResolvedPlatformConfig."""
        resolved = MagicMock()
        resolved.max_posts_per_day = max_posts_per_day
        return resolved

    @patch("social_hook.config.platforms.resolve_platform")
    def test_empty_state(self, mock_resolve, temp_db):
        """No posts, no drafts -> zeros everywhere."""
        project = self._setup_project(temp_db)
        config = self._make_config(platforms={"x": self._make_platform_config()})
        mock_resolve.return_value = self._make_resolved(max_posts_per_day=3)

        state = get_scheduling_state(temp_db, project.id, config)

        assert isinstance(state, ProjectSchedulingState)
        assert state.weekly_posts == 0
        assert state.max_per_week == 10
        assert len(state.platform_states) == 1
        ps = state.platform_states[0]
        assert ps.platform == "x"
        assert ps.posts_today == 0
        assert ps.pending_drafts == 0
        assert ps.deferred_drafts == 0
        assert ps.slots_remaining_today == 3

    @patch("social_hook.config.platforms.resolve_platform")
    def test_posts_reduce_slots(self, mock_resolve, temp_db):
        """Posts today reduce slots_remaining_today."""
        project = self._setup_project(temp_db)
        config = self._make_config(platforms={"x": self._make_platform_config()})
        mock_resolve.return_value = self._make_resolved(max_posts_per_day=3)

        # Create 2 posts for today
        for i in range(2):
            d = Decision(
                id=generate_id("decision"),
                project_id=project.id,
                commit_hash=f"hash{i}",
                decision="draft",
                reasoning="test",
            )
            insert_decision(temp_db, d)
            dr = Draft(
                id=generate_id("draft"),
                project_id=project.id,
                decision_id=d.id,
                platform="x",
                content=f"content {i}",
            )
            insert_draft(temp_db, dr)
            post = Post(
                id=generate_id("post"),
                draft_id=dr.id,
                project_id=project.id,
                platform="x",
                content=f"posted {i}",
            )
            insert_post(temp_db, post)

        state = get_scheduling_state(temp_db, project.id, config)
        ps = state.platform_states[0]
        assert ps.posts_today == 2
        assert ps.max_posts_per_day == 3
        assert ps.slots_remaining_today == 1

    @patch("social_hook.config.platforms.resolve_platform")
    def test_deferred_drafts_counted(self, mock_resolve, temp_db):
        """Deferred drafts are counted separately from pending."""
        project = self._setup_project(temp_db)
        config = self._make_config(platforms={"x": self._make_platform_config()})
        mock_resolve.return_value = self._make_resolved(max_posts_per_day=3)

        d = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="hash-def",
            decision="draft",
            reasoning="test",
        )
        insert_decision(temp_db, d)

        # Insert a deferred draft
        dr = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=d.id,
            platform="x",
            content="deferred content",
            status="deferred",
        )
        insert_draft(temp_db, dr)

        # Insert a normal pending draft
        dr2 = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=d.id,
            platform="x",
            content="pending content",
            status="draft",
        )
        insert_draft(temp_db, dr2)

        state = get_scheduling_state(temp_db, project.id, config)
        ps = state.platform_states[0]
        assert ps.deferred_drafts == 1
        assert ps.pending_drafts == 1

    @patch("social_hook.config.platforms.resolve_platform")
    def test_weekly_total(self, mock_resolve, temp_db):
        """Weekly posts are counted across all platforms."""
        project = self._setup_project(temp_db)
        config = self._make_config(platforms={"x": self._make_platform_config()})
        mock_resolve.return_value = self._make_resolved(max_posts_per_day=3)

        # Create a post
        d = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="hash-wk",
            decision="draft",
            reasoning="test",
        )
        insert_decision(temp_db, d)
        dr = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=d.id,
            platform="x",
            content="content",
        )
        insert_draft(temp_db, dr)
        post = Post(
            id=generate_id("post"),
            draft_id=dr.id,
            project_id=project.id,
            platform="x",
            content="posted",
        )
        insert_post(temp_db, post)

        state = get_scheduling_state(temp_db, project.id, config)
        assert state.weekly_posts == 1

    @patch("social_hook.config.platforms.resolve_platform")
    def test_disabled_platform_excluded(self, mock_resolve, temp_db):
        """Disabled platforms are not included in platform_states."""
        project = self._setup_project(temp_db)
        config = self._make_config(
            platforms={
                "x": self._make_platform_config(enabled=True),
                "linkedin": self._make_platform_config(enabled=False),
            }
        )
        mock_resolve.return_value = self._make_resolved(max_posts_per_day=3)

        state = get_scheduling_state(temp_db, project.id, config)
        assert len(state.platform_states) == 1
        assert state.platform_states[0].platform == "x"

    @patch("social_hook.config.platforms.resolve_platform")
    def test_multiple_platforms(self, mock_resolve, temp_db):
        """Multiple enabled platforms each get their own state."""
        project = self._setup_project(temp_db)
        config = self._make_config(
            platforms={
                "x": self._make_platform_config(),
                "linkedin": self._make_platform_config(),
            }
        )
        mock_resolve.return_value = self._make_resolved(max_posts_per_day=3)

        state = get_scheduling_state(temp_db, project.id, config)
        assert len(state.platform_states) == 2
        platform_names = {ps.platform for ps in state.platform_states}
        assert platform_names == {"x", "linkedin"}
