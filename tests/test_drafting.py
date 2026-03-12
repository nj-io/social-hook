"""Tests for the shared drafting pipeline (draft_for_platforms)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from social_hook.db import operations as ops
from social_hook.db.connection import init_database
from social_hook.drafting import (
    DraftResult,
    _draft_for_resolved_platforms,
    draft_for_platforms,
)
from social_hook.filesystem import generate_id
from social_hook.models import CommitInfo, Decision, Draft, Post, Project
from social_hook.scheduling import ScheduleResult

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
            config,
            conn,
            db,
            project,
            decision_id="decision-001",
            evaluation=evaluation,
            context=context,
            commit=commit,
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
        self,
        mock_schedule,
        mock_create,
        mock_filter,
        mock_resolve,
        tmp_path,
    ):
        db_path = tmp_path / "test.db"
        conn = init_database(db_path)
        project = _make_project(conn)

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(conn, dry_run=True)

        # Two enabled platforms
        config = _make_config(
            platforms={
                "x": _make_platform_config("x"),
                "linkedin": _make_platform_config("linkedin"),
            }
        )

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
        draft_result_mock.media_type = None
        draft_result_mock.media_spec = None
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
                config,
                conn,
                db,
                project,
                decision_id="decision-001",
                evaluation=evaluation,
                context=context,
                commit=commit,
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

        config = _make_config(
            platforms={
                "x": _make_platform_config("x"),
            }
        )
        resolved = MagicMock()
        resolved.filter = "significant"
        mock_resolve.return_value = resolved

        commit = _make_commit()
        evaluation = _make_evaluation()
        context = _make_context(project)

        results = draft_for_platforms(
            config,
            conn,
            db,
            project,
            decision_id="decision-001",
            evaluation=evaluation,
            context=context,
            commit=commit,
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
        self,
        mock_schedule,
        mock_create,
        mock_filter,
        mock_resolve,
        tmp_path,
    ):
        db_path = tmp_path / "test.db"
        conn = init_database(db_path)
        project = _make_project(conn)

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(conn, dry_run=True)

        config = _make_config(
            platforms={
                "linkedin": _make_platform_config("linkedin"),
            }
        )

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
        draft_result_mock.media_type = None
        draft_result_mock.media_spec = None
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
                config,
                conn,
                db,
                project,
                decision_id="decision-001",
                evaluation=_make_evaluation(),
                context=_make_context(project),
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
        self,
        mock_schedule,
        mock_create,
        mock_filter,
        mock_resolve,
        tmp_path,
    ):
        db_path = tmp_path / "test.db"
        conn = init_database(db_path)
        project = _make_project(conn)

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(conn, dry_run=True)

        config = _make_config(
            platforms={
                "x": _make_platform_config("x"),
                "linkedin": _make_platform_config("linkedin"),
            }
        )

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
            result.media_type = None
            result.media_spec = None
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
                config,
                conn,
                db,
                project,
                decision_id="decision-001",
                evaluation=_make_evaluation(),
                context=_make_context(project),
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
        self,
        mock_schedule,
        mock_create,
        mock_filter,
        mock_resolve,
        tmp_path,
    ):
        db_path = tmp_path / "test.db"
        conn = init_database(db_path)
        project = _make_project(conn)

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(conn, dry_run=True)

        config = _make_config(
            platforms={
                "x": _make_platform_config("x"),
            }
        )

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
        draft_result_mock.media_type = None
        draft_result_mock.media_spec = None
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
                config,
                conn,
                db,
                project,
                decision_id=custom_decision_id,
                evaluation=_make_evaluation(),
                context=_make_context(project),
                commit=_make_commit(),
                project_config=None,
            )

        assert len(results) == 1
        assert results[0].draft.decision_id == custom_decision_id
        conn.close()


class TestDraftMediaSpecGuards:
    """Tests for media spec guard logic in draft_for_platforms()."""

    @patch("social_hook.drafting.resolve_platform")
    @patch("social_hook.drafting.passes_content_filter", return_value=True)
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.drafting.calculate_optimal_time")
    @patch("social_hook.drafting._generate_media")
    def test_empty_spec_skipped_in_caller(
        self,
        mock_gen_media,
        mock_schedule,
        mock_create,
        mock_filter,
        mock_resolve,
        tmp_path,
    ):
        """When drafter returns media_type but empty media_spec, _generate_media is NOT called."""
        db_path = tmp_path / "test.db"
        conn = init_database(db_path)
        project = _make_project(conn)

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(conn, dry_run=True)

        config = _make_config(platforms={"x": _make_platform_config("x")})

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
        draft_result_mock.media_type = "ray_so"
        draft_result_mock.media_spec = {}  # Empty spec
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
            results = draft_for_platforms(
                config,
                conn,
                db,
                project,
                decision_id="decision-001",
                evaluation=_make_evaluation(),
                context=_make_context(project),
                commit=_make_commit(),
            )

        # _generate_media should NOT have been called because media_spec was empty
        mock_gen_media.assert_not_called()
        assert len(results) == 1
        conn.close()

    @patch("social_hook.drafting.resolve_platform")
    @patch("social_hook.drafting.passes_content_filter", return_value=True)
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.drafting.calculate_optimal_time")
    @patch("social_hook.drafting._generate_media")
    def test_none_spec_skipped_in_caller(
        self,
        mock_gen_media,
        mock_schedule,
        mock_create,
        mock_filter,
        mock_resolve,
        tmp_path,
    ):
        """When drafter returns media_type but None media_spec, _generate_media is NOT called."""
        db_path = tmp_path / "test.db"
        conn = init_database(db_path)
        project = _make_project(conn)

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(conn, dry_run=True)

        config = _make_config(platforms={"x": _make_platform_config("x")})

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
        draft_result_mock.media_type = "ray_so"
        draft_result_mock.media_spec = None  # None spec
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
            results = draft_for_platforms(
                config,
                conn,
                db,
                project,
                decision_id="decision-001",
                evaluation=_make_evaluation(),
                context=_make_context(project),
                commit=_make_commit(),
            )

        # _generate_media should NOT have been called because media_spec was None
        mock_gen_media.assert_not_called()
        assert len(results) == 1
        conn.close()

    @patch("social_hook.drafting.resolve_platform")
    @patch("social_hook.drafting.passes_content_filter", return_value=True)
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.drafting.calculate_optimal_time")
    @patch(
        "social_hook.drafting._generate_media",
        return_value=(["/tmp/media/code.png"], "ray_so", {"code": "x=1"}, None),
    )
    def test_valid_spec_triggers_media(
        self,
        mock_gen_media,
        mock_schedule,
        mock_create,
        mock_filter,
        mock_resolve,
        tmp_path,
    ):
        """When drafter returns media_type and valid media_spec, _generate_media IS called."""
        db_path = tmp_path / "test.db"
        conn = init_database(db_path)
        project = _make_project(conn)

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(conn, dry_run=True)

        config = _make_config(platforms={"x": _make_platform_config("x")})

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
        draft_result_mock.media_type = "ray_so"
        draft_result_mock.media_spec = {"code": "x=1"}  # Valid spec
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
            results = draft_for_platforms(
                config,
                conn,
                db,
                project,
                decision_id="decision-001",
                evaluation=_make_evaluation(),
                context=_make_context(project),
                commit=_make_commit(),
            )

        # _generate_media SHOULD have been called
        mock_gen_media.assert_called_once()
        assert len(results) == 1
        conn.close()


class TestDeferredDraftCreation:
    """Deferred scheduling creates a draft with status='deferred' and skips the results list."""

    @patch("social_hook.drafting.resolve_platform")
    @patch("social_hook.drafting.passes_content_filter", return_value=True)
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.drafting.calculate_optimal_time")
    @patch("social_hook.notifications.send_notification")
    def test_deferred_draft_inserted_not_in_results(
        self,
        mock_send_notif,
        mock_schedule,
        mock_create,
        mock_filter,
        mock_resolve,
        tmp_path,
    ):
        """When schedule.deferred=True, draft is inserted with status='deferred'
        and suggested_time=None, but is NOT in the returned results list."""
        db_path = tmp_path / "test.db"
        conn = init_database(db_path)
        project = _make_project(conn)

        # Insert a decision so foreign key constraint is satisfied
        decision_id = generate_id("decision")
        decision = Decision(
            id=decision_id,
            project_id=project.id,
            commit_hash="abc123def456",
            decision="draft",
            reasoning="test",
        )
        ops.insert_decision(conn, decision)

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(conn, dry_run=False)

        config = _make_config(
            platforms={
                "x": _make_platform_config("x"),
            }
        )

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
        draft_result_mock.content = "Deferred test content"
        draft_result_mock.reasoning = "Deferred reasoning"
        draft_result_mock.platform = "x"
        draft_result_mock.format_hint = "single"
        draft_result_mock.media_type = None
        draft_result_mock.media_spec = None
        mock_drafter_instance.create_draft.return_value = draft_result_mock

        mock_schedule.return_value = ScheduleResult(
            datetime=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
            is_optimal_day=False,
            day_reason="Weekly limit (5/5) reached",
            time_reason="deferred",
            deferred=True,
        )

        with patch("social_hook.llm.drafter.Drafter", return_value=mock_drafter_instance):
            results = draft_for_platforms(
                config,
                conn,
                db,
                project,
                decision_id=decision_id,
                evaluation=_make_evaluation(),
                context=_make_context(project),
                commit=_make_commit(),
                project_config=None,
                dry_run=False,
            )

        # Deferred drafts are NOT in the results list
        assert results == []

        # But draft WAS inserted into DB with correct status and no suggested_time
        drafts = ops.get_pending_drafts(conn, project.id)
        deferred = [d for d in drafts if d.status == "deferred"]
        assert len(deferred) == 1
        assert deferred[0].suggested_time is None
        assert deferred[0].content == "Deferred test content"

        # Notification was sent
        mock_send_notif.assert_called_once()
        call_args = mock_send_notif.call_args
        assert call_args[0][0] is config
        assert "Draft deferred" in call_args[0][1]
        assert call_args[1]["dry_run"] is False

        conn.close()

    @patch("social_hook.drafting.resolve_platform")
    @patch("social_hook.drafting.passes_content_filter", return_value=True)
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.drafting.calculate_optimal_time")
    @patch("social_hook.notifications.send_notification")
    def test_deferred_notification_uses_dry_run(
        self,
        mock_send_notif,
        mock_schedule,
        mock_create,
        mock_filter,
        mock_resolve,
        tmp_path,
    ):
        """send_notification receives dry_run=True when drafting in dry-run mode."""
        db_path = tmp_path / "test.db"
        conn = init_database(db_path)
        project = _make_project(conn)

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(conn, dry_run=True)

        config = _make_config(
            platforms={
                "x": _make_platform_config("x"),
            }
        )

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
        draft_result_mock.content = "Dry run deferred"
        draft_result_mock.reasoning = "reason"
        draft_result_mock.platform = "x"
        draft_result_mock.format_hint = "single"
        draft_result_mock.media_type = None
        draft_result_mock.media_spec = None
        mock_drafter_instance.create_draft.return_value = draft_result_mock

        mock_schedule.return_value = ScheduleResult(
            datetime=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
            is_optimal_day=False,
            day_reason="Weekly limit reached",
            time_reason="deferred",
            deferred=True,
        )

        with patch("social_hook.llm.drafter.Drafter", return_value=mock_drafter_instance):
            results = draft_for_platforms(
                config,
                conn,
                db,
                project,
                decision_id="decision-002",
                evaluation=_make_evaluation(),
                context=_make_context(project),
                commit=_make_commit(),
                project_config=None,
                dry_run=True,
            )

        assert results == []
        mock_send_notif.assert_called_once()
        assert mock_send_notif.call_args[1]["dry_run"] is True
        conn.close()


class TestDraftReferencePostResolution:
    """Tests for reference post resolution and reference_post_id on Draft."""

    @patch("social_hook.drafting.resolve_platform")
    @patch("social_hook.drafting.passes_content_filter", return_value=True)
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.drafting.calculate_optimal_time")
    def test_reference_posts_resolved_and_set_on_draft(
        self,
        mock_schedule,
        mock_create,
        mock_filter,
        mock_resolve,
        tmp_path,
    ):
        """When evaluation has reference_posts with a valid published post,
        the draft gets reference_post_id set and drafter gets referenced_posts."""
        db_path = tmp_path / "test.db"
        conn = init_database(db_path)
        project = _make_project(conn)

        # Insert a decision so foreign key constraint is satisfied
        decision_id = generate_id("decision")
        decision = Decision(
            id=decision_id,
            project_id=project.id,
            commit_hash="abc123def456",
            decision="draft",
            reasoning="test",
        )
        ops.insert_decision(conn, decision)

        # Insert a published post that the evaluation references
        ref_draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision_id,
            platform="x",
            content="Previous post",
            status="posted",
        )
        ops.insert_draft(conn, ref_draft)
        ref_post = Post(
            id=generate_id("post"),
            draft_id=ref_draft.id,
            project_id=project.id,
            platform="x",
            content="Previous post",
            external_id="tweet_123",
            external_url="https://x.com/user/status/tweet_123",
        )
        ops.insert_post(conn, ref_post)

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(conn, dry_run=False)

        config = _make_config(platforms={"x": _make_platform_config("x")})

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
        draft_result_mock.content = "Referencing previous post"
        draft_result_mock.reasoning = "Continues the thread"
        draft_result_mock.platform = "x"
        draft_result_mock.format_hint = "single"
        draft_result_mock.media_type = None
        draft_result_mock.media_spec = None
        mock_drafter_instance.create_draft.return_value = draft_result_mock

        mock_schedule.return_value = ScheduleResult(
            datetime=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
            is_optimal_day=True,
            day_reason="weekday",
            time_reason="optimal hour",
            deferred=False,
        )

        # Build evaluation with reference_posts pointing to our post
        eval_with_refs = _make_evaluation()
        eval_with_refs.reference_posts = [ref_post.id]

        with patch("social_hook.llm.drafter.Drafter", return_value=mock_drafter_instance):
            results = draft_for_platforms(
                config,
                conn,
                db,
                project,
                decision_id=decision_id,
                evaluation=eval_with_refs,
                context=_make_context(project),
                commit=_make_commit(),
                project_config=None,
                dry_run=False,
            )

        assert len(results) == 1
        draft = results[0].draft

        # reference_post_id should be set to the referenced post
        assert draft.reference_post_id == ref_post.id

        # Same platform = quote format
        assert draft.post_format == "quote"

        # Drafter should have received referenced_posts
        call_kwargs = mock_drafter_instance.create_draft.call_args
        ref_posts_arg = call_kwargs[1]["referenced_posts"]
        assert ref_posts_arg is not None
        assert len(ref_posts_arg) == 1
        assert ref_posts_arg[0].id == ref_post.id

        conn.close()

    @patch("social_hook.drafting.resolve_platform")
    @patch("social_hook.drafting.passes_content_filter", return_value=True)
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.drafting.calculate_optimal_time")
    def test_no_reference_posts_leaves_draft_unchanged(
        self,
        mock_schedule,
        mock_create,
        mock_filter,
        mock_resolve,
        tmp_path,
    ):
        """When evaluation has no reference_posts, draft has no reference_post_id."""
        db_path = tmp_path / "test.db"
        conn = init_database(db_path)
        project = _make_project(conn)

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(conn, dry_run=True)

        config = _make_config(platforms={"x": _make_platform_config("x")})

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
        draft_result_mock.content = "Normal post"
        draft_result_mock.reasoning = "Standalone"
        draft_result_mock.platform = "x"
        draft_result_mock.format_hint = "single"
        draft_result_mock.media_type = None
        draft_result_mock.media_spec = None
        mock_drafter_instance.create_draft.return_value = draft_result_mock

        mock_schedule.return_value = ScheduleResult(
            datetime=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
            is_optimal_day=True,
            day_reason="weekday",
            time_reason="optimal hour",
            deferred=False,
        )

        eval_no_refs = _make_evaluation()
        eval_no_refs.reference_posts = None

        with patch("social_hook.llm.drafter.Drafter", return_value=mock_drafter_instance):
            results = draft_for_platforms(
                config,
                conn,
                db,
                project,
                decision_id="decision-001",
                evaluation=eval_no_refs,
                context=_make_context(project),
                commit=_make_commit(),
                project_config=None,
            )

        assert len(results) == 1
        assert results[0].draft.reference_post_id is None
        assert results[0].draft.post_format is None

        # Drafter should have received referenced_posts=None
        call_kwargs = mock_drafter_instance.create_draft.call_args
        assert call_kwargs[1]["referenced_posts"] is None

        conn.close()

    @patch("social_hook.drafting.resolve_platform")
    @patch("social_hook.drafting.passes_content_filter", return_value=True)
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.drafting.calculate_optimal_time")
    def test_cross_platform_reference_no_quote_format(
        self,
        mock_schedule,
        mock_create,
        mock_filter,
        mock_resolve,
        tmp_path,
    ):
        """When reference post is on a different platform, post_format stays None (LINK fallback)."""
        db_path = tmp_path / "test.db"
        conn = init_database(db_path)
        project = _make_project(conn)

        decision_id = generate_id("decision")
        decision = Decision(
            id=decision_id,
            project_id=project.id,
            commit_hash="cross123plat456",
            decision="draft",
            reasoning="test",
        )
        ops.insert_decision(conn, decision)

        # Reference post is on linkedin, but we're drafting for x
        ref_draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision_id,
            platform="linkedin",
            content="Previous linkedin post",
            status="posted",
        )
        ops.insert_draft(conn, ref_draft)
        ref_post = Post(
            id=generate_id("post"),
            draft_id=ref_draft.id,
            project_id=project.id,
            platform="linkedin",
            content="Previous linkedin post",
            external_id="urn:li:share:123",
            external_url="https://linkedin.com/feed/update/urn:li:share:123",
        )
        ops.insert_post(conn, ref_post)

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(conn, dry_run=False)

        config = _make_config(platforms={"x": _make_platform_config("x")})

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
        draft_result_mock.content = "Cross-platform reference"
        draft_result_mock.reasoning = "References linkedin post"
        draft_result_mock.platform = "x"
        draft_result_mock.format_hint = "single"
        draft_result_mock.media_type = None
        draft_result_mock.media_spec = None
        mock_drafter_instance.create_draft.return_value = draft_result_mock

        mock_schedule.return_value = ScheduleResult(
            datetime=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
            is_optimal_day=True,
            day_reason="weekday",
            time_reason="optimal hour",
            deferred=False,
        )

        eval_with_refs = _make_evaluation()
        eval_with_refs.reference_posts = [ref_post.id]

        with patch("social_hook.llm.drafter.Drafter", return_value=mock_drafter_instance):
            results = draft_for_platforms(
                config,
                conn,
                db,
                project,
                decision_id=decision_id,
                evaluation=eval_with_refs,
                context=_make_context(project),
                commit=_make_commit(),
                project_config=None,
                dry_run=False,
            )

        assert len(results) == 1
        draft = results[0].draft

        # reference_post_id should be set
        assert draft.reference_post_id == ref_post.id
        # Cross-platform: post_format should NOT be "quote" (LINK fallback in scheduler)
        assert draft.post_format is None

        conn.close()


# =============================================================================
# Tests for _draft_for_resolved_platforms (two-layer split)
# =============================================================================


class TestDraftForResolvedPlatforms:
    """_draft_for_resolved_platforms drafts for exactly the platforms passed in."""

    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.drafting.calculate_optimal_time")
    def test_drafts_only_passed_platforms(
        self,
        mock_schedule,
        mock_create,
        tmp_path,
    ):
        """Only the platforms in the dict are drafted (no resolution or filtering)."""
        db_path = tmp_path / "test.db"
        conn = init_database(db_path)
        project = _make_project(conn)

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(conn, dry_run=True)

        config = _make_config(platforms={"x": _make_platform_config("x")})

        # Build a resolved platform config mock directly
        resolved_linkedin = MagicMock()
        resolved_linkedin.filter = "all"
        resolved_linkedin.account_tier = "free"
        resolved_linkedin.max_posts_per_day = 3
        resolved_linkedin.min_gap_minutes = 30
        resolved_linkedin.optimal_days = []
        resolved_linkedin.optimal_hours = []

        mock_drafter_instance = MagicMock()
        draft_result_mock = MagicMock()
        draft_result_mock.content = "Resolved platform test"
        draft_result_mock.reasoning = "Test reasoning"
        draft_result_mock.platform = "linkedin"
        draft_result_mock.format_hint = "single"
        draft_result_mock.media_type = None
        draft_result_mock.media_spec = None
        mock_drafter_instance.create_draft.return_value = draft_result_mock

        mock_schedule.return_value = ScheduleResult(
            datetime=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
            is_optimal_day=True,
            day_reason="weekday",
            time_reason="optimal hour",
            deferred=False,
        )

        with patch("social_hook.llm.drafter.Drafter", return_value=mock_drafter_instance):
            # Pass only "linkedin" — even though config only has "x"
            results = _draft_for_resolved_platforms(
                {"linkedin": resolved_linkedin},
                config,
                conn,
                db,
                project,
                decision_id="decision-001",
                evaluation=_make_evaluation(),
                context=_make_context(project),
                commit=_make_commit(),
                project_config=None,
            )

        assert len(results) == 1
        assert results[0].draft.platform == "linkedin"
        # Drafter was called exactly once (for linkedin only)
        assert mock_drafter_instance.create_draft.call_count == 1
        conn.close()


class TestDraftForPlatformsPublicApiUnchanged:
    """draft_for_platforms public API still works after the two-layer split."""

    @patch("social_hook.drafting.resolve_platform")
    @patch("social_hook.drafting.passes_content_filter", return_value=True)
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.drafting.calculate_optimal_time")
    def test_public_api_delegates_to_resolved(
        self,
        mock_schedule,
        mock_create,
        mock_filter,
        mock_resolve,
        tmp_path,
    ):
        db_path = tmp_path / "test.db"
        conn = init_database(db_path)
        project = _make_project(conn)

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(conn, dry_run=True)

        config = _make_config(platforms={"x": _make_platform_config("x")})

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
        draft_result_mock.content = "Public API test"
        draft_result_mock.reasoning = "reasoning"
        draft_result_mock.platform = "x"
        draft_result_mock.format_hint = "single"
        draft_result_mock.media_type = None
        draft_result_mock.media_spec = None
        mock_drafter_instance.create_draft.return_value = draft_result_mock

        mock_schedule.return_value = ScheduleResult(
            datetime=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
            is_optimal_day=True,
            day_reason="weekday",
            time_reason="optimal hour",
            deferred=False,
        )

        with patch("social_hook.llm.drafter.Drafter", return_value=mock_drafter_instance):
            results = draft_for_platforms(
                config,
                conn,
                db,
                project,
                decision_id="decision-001",
                evaluation=_make_evaluation(),
                context=_make_context(project),
                commit=_make_commit(),
            )

        assert len(results) == 1
        assert results[0].draft.platform == "x"
        conn.close()
