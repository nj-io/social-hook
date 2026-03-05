"""Tests for the shared drafting pipeline (draft_for_platforms)."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from social_hook.db.connection import init_database
from social_hook.db import operations as ops
from social_hook.drafting import DraftResult, draft_for_platforms
from social_hook.filesystem import generate_id
from social_hook.models import CommitInfo, Project


# =============================================================================
# Helpers
# =============================================================================


def _make_project(conn, name="test-project") -> Project:
    """Create and insert a test project."""
    project = Project(
        id=generate_id("project"),
        name=name,
        repo_path="/tmp/test-repo",
    )
    ops.insert_project(conn, project)
    return project


def _make_commit() -> CommitInfo:
    return CommitInfo(
        hash="abc123def456",
        message="Add feature X",
        diff="diff --git a/foo.py b/foo.py\n+print('hello')",
        files_changed=["foo.py"],
    )


def _make_evaluation():
    """Build a minimal evaluation mock."""
    eval_mock = MagicMock()
    eval_mock.decision = "draft"
    eval_mock.reasoning = "Interesting feature"
    eval_mock.angle = "test angle"
    eval_mock.episode_type = "milestone"
    eval_mock.post_category = "standalone"
    eval_mock.media_tool = None
    eval_mock.arc_id = None
    eval_mock.platforms = {}
    return eval_mock


def _make_context(project):
    """Build a minimal context mock."""
    ctx = MagicMock()
    ctx.project = project
    return ctx


def _make_config(platforms=None):
    """Build a Config-like mock with platforms and scheduling."""
    config = MagicMock()

    # Default: no enabled platforms
    if platforms is None:
        platforms = {}
    config.platforms = platforms

    # Scheduling defaults
    config.scheduling.timezone = "UTC"
    config.scheduling.max_per_week = 10
    config.scheduling.thread_min_tweets = 4

    # Media generation disabled by default
    config.media_generation.enabled = False

    # Models
    config.models.drafter = "anthropic/claude-sonnet-4-5"

    # Env
    config.env = {}

    return config


def _make_platform_config(name="x", enabled=True, priority="primary"):
    """Build a mock OutputPlatformConfig."""
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


# =============================================================================
# Tests
# =============================================================================


class TestDraftForPlatformsNoEnabledPlatforms:
    """No enabled platforms returns empty list."""

    def test_no_platforms_with_target_filter_returns_empty(self, tmp_path):
        """When target_platform_names is set but no platforms match, returns empty."""
        db_path = tmp_path / "test.db"
        conn = init_database(db_path)
        project = _make_project(conn)

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(conn, dry_run=True)

        config = _make_config(platforms={})
        commit = _make_commit()
        evaluation = _make_evaluation()
        context = _make_context(project)

        # With explicit target_platform_names, no preview fallback
        results = draft_for_platforms(
            config, conn, db, project, decision_id="decision-001",
            evaluation=evaluation, context=context, commit=commit,
            target_platform_names=["x"],
        )

        assert results == []
        conn.close()


class TestDraftForPlatformsTargetFilter:
    """target_platform_names filters to specified platforms only."""

    @patch("social_hook.drafting.resolve_platform")
    @patch("social_hook.drafting.passes_content_filter", return_value=True)
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.drafting.calculate_optimal_time")
    def test_target_filter_excludes_unspecified(
        self, mock_schedule, mock_create, mock_filter, mock_resolve, tmp_path,
    ):
        db_path = tmp_path / "test.db"
        conn = init_database(db_path)
        project = _make_project(conn)

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(conn, dry_run=True)

        # Two enabled platforms
        config = _make_config(platforms={
            "x": _make_platform_config("x"),
            "linkedin": _make_platform_config("linkedin"),
        })

        # resolve_platform returns something with a filter that passes "all"
        resolved = MagicMock()
        resolved.filter = "all"
        resolved.account_tier = "free"
        resolved.max_posts_per_day = 3
        resolved.min_gap_minutes = 30
        resolved.optimal_days = []
        resolved.optimal_hours = []
        mock_resolve.return_value = resolved

        commit = _make_commit()
        evaluation = _make_evaluation()
        context = _make_context(project)

        # Mock drafter
        mock_drafter_instance = MagicMock()
        draft_result_mock = MagicMock()
        draft_result_mock.content = "Test content"
        draft_result_mock.reasoning = "Test reasoning"
        draft_result_mock.platform = "linkedin"
        draft_result_mock.format_hint = "single"
        mock_drafter_instance.create_draft.return_value = draft_result_mock

        from social_hook.scheduling import ScheduleResult

        mock_schedule.return_value = ScheduleResult(
            datetime=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
            is_optimal_day=True,
            day_reason="weekday",
            time_reason="optimal hour",
            deferred=False,
        )

        with patch("social_hook.llm.drafter.Drafter", return_value=mock_drafter_instance):
            # Only target "linkedin" -- "x" should be excluded
            results = draft_for_platforms(
                config, conn, db, project, decision_id="decision-001",
                evaluation=evaluation, context=context, commit=commit,
                target_platform_names=["linkedin"],
            )

        # Only linkedin should have been drafted
        assert len(results) == 1
        assert results[0].draft.platform == "linkedin"
        conn.close()


class TestDraftForPlatformsContentFilterExcludes:
    """Content filter excludes all platforms returns empty list."""

    @patch("social_hook.drafting.resolve_platform")
    @patch("social_hook.drafting.passes_content_filter", return_value=False)
    def test_all_filtered_returns_empty(self, mock_filter, mock_resolve, tmp_path):
        db_path = tmp_path / "test.db"
        conn = init_database(db_path)
        project = _make_project(conn)

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(conn, dry_run=True)

        config = _make_config(platforms={
            "x": _make_platform_config("x"),
        })
        resolved = MagicMock()
        resolved.filter = "significant"
        mock_resolve.return_value = resolved

        commit = _make_commit()
        evaluation = _make_evaluation()
        context = _make_context(project)

        results = draft_for_platforms(
            config, conn, db, project, decision_id="decision-001",
            evaluation=evaluation, context=context, commit=commit,
        )

        assert results == []
        conn.close()


class TestDraftForPlatformsProjectConfigNone:
    """project_config=None path doesn't crash."""

    @patch("social_hook.drafting.resolve_platform")
    @patch("social_hook.drafting.passes_content_filter", return_value=True)
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.drafting.calculate_optimal_time")
    def test_none_project_config(
        self, mock_schedule, mock_create, mock_filter, mock_resolve, tmp_path,
    ):
        db_path = tmp_path / "test.db"
        conn = init_database(db_path)
        project = _make_project(conn)

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(conn, dry_run=True)

        config = _make_config(platforms={
            "linkedin": _make_platform_config("linkedin"),
        })

        resolved = MagicMock()
        resolved.filter = "all"
        resolved.account_tier = None
        resolved.max_posts_per_day = 3
        resolved.min_gap_minutes = 30
        resolved.optimal_days = []
        resolved.optimal_hours = []
        mock_resolve.return_value = resolved

        # Mock drafter
        mock_drafter_instance = MagicMock()
        draft_result_mock = MagicMock()
        draft_result_mock.content = "Test content"
        draft_result_mock.reasoning = "Test reasoning"
        draft_result_mock.platform = "linkedin"
        draft_result_mock.format_hint = "single"
        mock_drafter_instance.create_draft.return_value = draft_result_mock

        with patch("social_hook.llm.drafter.Drafter", return_value=mock_drafter_instance):
            from social_hook.scheduling import ScheduleResult

            mock_schedule.return_value = ScheduleResult(
                datetime=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
                is_optimal_day=True,
                day_reason="weekday",
                time_reason="optimal hour",
                deferred=False,
            )

            results = draft_for_platforms(
                config, conn, db, project, decision_id="decision-001",
                evaluation=_make_evaluation(), context=_make_context(project),
                commit=_make_commit(),
                project_config=None,  # Explicitly None
            )

        assert len(results) == 1
        assert isinstance(results[0], DraftResult)
        # Verify drafter.create_draft was called with config=None (not project_config.context)
        call_kwargs = mock_drafter_instance.create_draft.call_args
        assert call_kwargs[1]["config"] is None
        assert call_kwargs[1]["media_guidance"] is None
        conn.close()


class TestDraftForPlatformsPerPlatformError:
    """Per-platform LLM error is caught and skipped (other platforms still draft)."""

    @patch("social_hook.drafting.resolve_platform")
    @patch("social_hook.drafting.passes_content_filter", return_value=True)
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.drafting.calculate_optimal_time")
    def test_error_skips_platform(
        self, mock_schedule, mock_create, mock_filter, mock_resolve, tmp_path,
    ):
        db_path = tmp_path / "test.db"
        conn = init_database(db_path)
        project = _make_project(conn)

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(conn, dry_run=True)

        config = _make_config(platforms={
            "x": _make_platform_config("x"),
            "linkedin": _make_platform_config("linkedin"),
        })

        resolved = MagicMock()
        resolved.filter = "all"
        resolved.account_tier = "free"
        resolved.max_posts_per_day = 3
        resolved.min_gap_minutes = 30
        resolved.optimal_days = []
        resolved.optimal_hours = []
        mock_resolve.return_value = resolved

        mock_drafter_instance = MagicMock()
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("LLM API failed for x")
            # Second call succeeds (linkedin)
            result = MagicMock()
            result.content = "LinkedIn post"
            result.reasoning = "Reasoning"
            result.platform = "linkedin"
            result.format_hint = "single"
            return result

        mock_drafter_instance.create_draft.side_effect = side_effect

        with patch("social_hook.llm.drafter.Drafter", return_value=mock_drafter_instance):
            from social_hook.scheduling import ScheduleResult

            mock_schedule.return_value = ScheduleResult(
                datetime=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
                is_optimal_day=True,
                day_reason="weekday",
                time_reason="optimal hour",
                deferred=False,
            )

            results = draft_for_platforms(
                config, conn, db, project, decision_id="decision-001",
                evaluation=_make_evaluation(), context=_make_context(project),
                commit=_make_commit(),
                project_config=None,
            )

        # Only the second platform succeeded
        assert len(results) == 1
        assert results[0].draft.platform == "linkedin"
        conn.close()


class TestDraftResultDecisionId:
    """DraftResult contains correct decision_id from caller."""

    @patch("social_hook.drafting.resolve_platform")
    @patch("social_hook.drafting.passes_content_filter", return_value=True)
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.drafting.calculate_optimal_time")
    def test_decision_id_propagated(
        self, mock_schedule, mock_create, mock_filter, mock_resolve, tmp_path,
    ):
        db_path = tmp_path / "test.db"
        conn = init_database(db_path)
        project = _make_project(conn)

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(conn, dry_run=True)

        config = _make_config(platforms={
            "x": _make_platform_config("x"),
        })

        resolved = MagicMock()
        resolved.filter = "all"
        resolved.account_tier = "free"
        resolved.max_posts_per_day = 3
        resolved.min_gap_minutes = 30
        resolved.optimal_days = []
        resolved.optimal_hours = []
        mock_resolve.return_value = resolved

        mock_drafter_instance = MagicMock()
        draft_result_mock = MagicMock()
        draft_result_mock.content = "Test content"
        draft_result_mock.reasoning = "Test reasoning"
        draft_result_mock.platform = "x"
        draft_result_mock.format_hint = "single"
        mock_drafter_instance.create_draft.return_value = draft_result_mock

        with patch("social_hook.llm.drafter.Drafter", return_value=mock_drafter_instance):
            from social_hook.scheduling import ScheduleResult

            mock_schedule.return_value = ScheduleResult(
                datetime=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
                is_optimal_day=True,
                day_reason="weekday",
                time_reason="optimal hour",
                deferred=False,
            )

            custom_decision_id = "decision-custom-42"
            results = draft_for_platforms(
                config, conn, db, project, decision_id=custom_decision_id,
                evaluation=_make_evaluation(), context=_make_context(project),
                commit=_make_commit(),
                project_config=None,
            )

        assert len(results) == 1
        assert results[0].draft.decision_id == custom_decision_id
        conn.close()
