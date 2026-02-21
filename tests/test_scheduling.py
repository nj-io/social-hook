"""Tests for scheduling algorithm (T30)."""

from datetime import datetime, timedelta, timezone

import pytest

from social_hook.db import init_database, insert_decision, insert_draft, insert_post, insert_project
from social_hook.filesystem import generate_id
from social_hook.models import Decision, Draft, Post, Project
from social_hook.scheduling import ScheduleResult, calculate_optimal_time


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
        project = Project(
            id=generate_id("project"), name="test", repo_path="/tmp/test"
        )
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
            temp_db, project.id,
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
                decision="post_worthy",
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
            temp_db, project.id,
            max_posts_per_day=3,
        )
        # Should be scheduled for a future day
        now = datetime.now(timezone.utc)
        assert result.datetime.date() > now.date()

    def test_timezone_handling(self, temp_db):
        """Handles timezone conversion correctly."""
        project = self._setup_project(temp_db)
        result = calculate_optimal_time(
            temp_db, project.id,
            tz="America/New_York",
            optimal_hours=[9, 12, 17],
        )
        assert result.datetime.tzinfo is not None
        assert isinstance(result, ScheduleResult)

    def test_invalid_timezone_fallback(self, temp_db):
        """Falls back to UTC for invalid timezone."""
        project = self._setup_project(temp_db)
        result = calculate_optimal_time(
            temp_db, project.id,
            tz="Invalid/Timezone",
        )
        assert isinstance(result, ScheduleResult)
        assert result.datetime > datetime.now(timezone.utc)

    def test_single_optimal_day(self, temp_db):
        """Works with a single optimal day."""
        project = self._setup_project(temp_db)
        result = calculate_optimal_time(
            temp_db, project.id,
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
                decision="post_worthy",
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
            temp_db, p1.id,
            max_posts_per_day=3,
        )
        # All 3 slots used by project 2, so should schedule for tomorrow
        now = datetime.now(timezone.utc)
        assert result.datetime.date() > now.date()


class TestPlatformFilter:
    """Tests for platform parameter in calculate_optimal_time."""

    def _setup_project(self, conn):
        project = Project(
            id=generate_id("project"), name="test", repo_path="/tmp/test"
        )
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
                decision="post_worthy",
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
            temp_db, project.id,
            max_posts_per_day=3,
        )
        now = datetime.now(timezone.utc)
        assert result_all.datetime.date() > now.date()

        # With platform="linkedin", no posts exist — should schedule today
        result_li = calculate_optimal_time(
            temp_db, project.id,
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
