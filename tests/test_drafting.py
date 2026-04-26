"""Tests for the shared drafting pipeline (draft)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from social_hook.db import operations as ops
from social_hook.db.connection import init_database
from social_hook.drafting import (
    DraftingIntent,
    DraftResult,
    PlatformSpec,
    draft,
)
from social_hook.filesystem import generate_id
from social_hook.models.core import CommitInfo, Decision, Draft, Post, Project
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


def _make_intent(
    decision_id="decision-001",
    platforms=None,
    platform_names=None,
    angle="test angle",
    reasoning="Interesting feature",
    post_category="standalone",
    include_project_docs=False,
    arc_id=None,
    reference_posts=None,
):
    """Build a DraftingIntent for tests.

    If platform_names is provided, creates PlatformSpec entries with mock resolved configs.
    If platforms is provided as a list of PlatformSpec, uses those directly.
    """
    if platforms is None:
        if platform_names is None:
            platform_names = ["x"]
        platforms = []
        for pname in platform_names:
            resolved = MagicMock()
            resolved.name = pname
            resolved.account_tier = "free"
            resolved.max_posts_per_day = 3
            resolved.min_gap_minutes = 30
            resolved.optimal_days = []
            resolved.optimal_hours = []
            resolved.filter = "all"
            platforms.append(PlatformSpec(platform=pname, resolved=resolved))

    return DraftingIntent(
        decision_id=decision_id,
        decision="draft",
        angle=angle,
        reasoning=reasoning,
        post_category=post_category,
        include_project_docs=include_project_docs,
        arc_id=arc_id,
        reference_posts=reference_posts,
        platforms=platforms,
    )


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
        context = _make_context(project)

        # No platforms in intent -> empty results
        intent = _make_intent(decision_id="decision-001", platforms=[])
        results = draft(
            intent,
            config,
            conn,
            db,
            project,
            context,
            commit,
        )

        assert results == []
        conn.close()


class TestDraftForPlatformsTargetFilter:
    """target_platform_names filters to specified platforms only."""

    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.drafting.calculate_optimal_time")
    def test_target_filter_excludes_unspecified(
        self,
        mock_schedule,
        mock_create,
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

        # Build a resolved platform config mock
        resolved = MagicMock()
        resolved.filter = "all"
        resolved.account_tier = "free"
        resolved.max_posts_per_day = 3
        resolved.min_gap_minutes = 30
        resolved.optimal_days = []
        resolved.optimal_hours = []

        commit = _make_commit()
        context = _make_context(project)

        # Mock drafter
        mock_drafter_instance = MagicMock()
        draft_result_mock = MagicMock()
        draft_result_mock.content = "Test content"
        draft_result_mock.reasoning = "Test reasoning"
        draft_result_mock.platform = "linkedin"
        draft_result_mock.vehicle = "single"
        draft_result_mock.media_specs = []
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
            # Only target "linkedin" via intent platforms
            intent = _make_intent(decision_id="decision-001", platform_names=["linkedin"])
            intent.platforms[0].resolved = resolved
            results = draft(
                intent,
                config,
                conn,
                db,
                project,
                context,
                commit,
            )

        # Only linkedin should have been drafted
        assert len(results) == 1
        assert results[0].draft.platform == "linkedin"
        conn.close()


class TestDraftForPlatformsProjectConfigNone:
    """project_config=None path doesn't crash."""

    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.drafting.calculate_optimal_time")
    def test_none_project_config(
        self,
        mock_schedule,
        mock_create,
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

        # Mock drafter
        mock_drafter_instance = MagicMock()
        draft_result_mock = MagicMock()
        draft_result_mock.content = "Test content"
        draft_result_mock.reasoning = "Test reasoning"
        draft_result_mock.platform = "linkedin"
        draft_result_mock.vehicle = "single"
        draft_result_mock.media_specs = []
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

            intent = _make_intent(decision_id="decision-001")
            results = draft(
                intent,
                config,
                conn,
                db,
                project,
                _make_context(project),
                _make_commit(),
                project_config=None,
            )

        assert len(results) == 1
        assert isinstance(results[0], DraftResult)
        # Verify drafter.create_draft was called with config=None (not project_config.context)
        call_kwargs = mock_drafter_instance.create_draft.call_args
        assert call_kwargs[1]["config"] is None
        assert call_kwargs[1]["media_guidance"] is None
        conn.close()


class TestDraftResultDecisionId:
    """DraftResult contains correct decision_id from caller."""

    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.drafting.calculate_optimal_time")
    def test_decision_id_propagated(
        self,
        mock_schedule,
        mock_create,
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

        mock_drafter_instance = MagicMock()
        draft_result_mock = MagicMock()
        draft_result_mock.content = "Test content"
        draft_result_mock.reasoning = "Test reasoning"
        draft_result_mock.platform = "x"
        draft_result_mock.vehicle = "single"
        draft_result_mock.media_specs = []
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
            intent = _make_intent(decision_id=custom_decision_id)
            results = draft(
                intent,
                config,
                conn,
                db,
                project,
                _make_context(project),
                _make_commit(),
                project_config=None,
            )

        assert len(results) == 1
        assert results[0].draft.decision_id == custom_decision_id
        conn.close()


class TestDraftMediaSpecGuards:
    """Tests for media spec flow through draft() via the new parallel-array pipeline.

    ``_generate_all_media`` is the sole entry into per-item generation now;
    these tests verify that an empty media_specs list short-circuits and
    that populated specs are forwarded to the parallel executor.
    """

    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.drafting.calculate_optimal_time")
    @patch("social_hook.drafting._generate_all_media", return_value=([], []))
    def test_empty_specs_calls_generator_with_empty_list(
        self,
        mock_gen_all,
        mock_schedule,
        mock_create,
        tmp_path,
    ):
        """When drafter returns an empty media_specs, generator runs with [] and returns ([], [])."""
        db_path = tmp_path / "test.db"
        conn = init_database(db_path)
        project = _make_project(conn)

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(conn, dry_run=True)

        config = _make_config(platforms={"x": _make_platform_config("x")})

        mock_drafter_instance = MagicMock()
        draft_result_mock = MagicMock()
        draft_result_mock.content = "Test content"
        draft_result_mock.reasoning = "Test reasoning"
        draft_result_mock.platform = "x"
        draft_result_mock.vehicle = "single"
        draft_result_mock.media_specs = []  # drafter emitted no media
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
            intent = _make_intent(decision_id="decision-001")

            results = draft(
                intent,
                config,
                conn,
                db,
                project,
                _make_context(project),
                _make_commit(),
            )

        assert mock_gen_all.call_count == 1
        # Second positional arg is the specs list.
        assert mock_gen_all.call_args.args[1] == []
        assert len(results) == 1
        assert results[0].draft.media_specs == []
        assert results[0].draft.media_paths == []
        assert results[0].draft.media_errors == []
        conn.close()

    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.drafting.calculate_optimal_time")
    @patch(
        "social_hook.drafting._generate_all_media",
        return_value=(["/tmp/media/code.png"], [None]),
    )
    def test_populated_specs_forwarded_to_generator(
        self,
        mock_gen_all,
        mock_schedule,
        mock_create,
        tmp_path,
    ):
        """A populated media_specs list flows into _generate_all_media and back onto the Draft."""
        db_path = tmp_path / "test.db"
        conn = init_database(db_path)
        project = _make_project(conn)

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(conn, dry_run=True)

        config = _make_config(platforms={"x": _make_platform_config("x")})

        mock_drafter_instance = MagicMock()
        draft_result_mock = MagicMock()
        draft_result_mock.content = "Test content"
        draft_result_mock.reasoning = "Test reasoning"
        draft_result_mock.platform = "x"
        draft_result_mock.vehicle = "single"
        spec = {"id": "media_abc123def456", "tool": "ray_so", "spec": {"code": "x=1"}}
        draft_result_mock.media_specs = [spec]
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
            intent = _make_intent(decision_id="decision-001")

            results = draft(
                intent,
                config,
                conn,
                db,
                project,
                _make_context(project),
                _make_commit(),
            )

        assert mock_gen_all.call_count == 1
        forwarded_specs = mock_gen_all.call_args.args[1]
        assert forwarded_specs == [spec]
        assert len(results) == 1
        d = results[0].draft
        assert d.media_specs == [spec]
        assert d.media_paths == ["/tmp/media/code.png"]
        assert d.media_errors == [None]
        # Spec-unchanged invariant at creation time.
        assert d.media_specs_used == [spec]
        conn.close()

    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.drafting.calculate_optimal_time")
    @patch(
        "social_hook.drafting._generate_all_media",
        return_value=(["/tmp/ok.png", ""], [None, "Gemini timeout"]),
    )
    def test_partial_failure_records_errors_and_summary(
        self,
        mock_gen_all,
        mock_schedule,
        mock_create,
        tmp_path,
    ):
        """Per-item errors are written to the draft and summarized in last_error."""
        db_path = tmp_path / "test.db"
        conn = init_database(db_path)
        project = _make_project(conn)

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(conn, dry_run=True)

        config = _make_config(platforms={"x": _make_platform_config("x")})

        mock_drafter_instance = MagicMock()
        draft_result_mock = MagicMock()
        draft_result_mock.content = "Test content"
        draft_result_mock.reasoning = "Test reasoning"
        draft_result_mock.platform = "x"
        draft_result_mock.vehicle = "single"
        specs = [
            {"id": "media_aaaaaaaaaaaa", "tool": "mermaid", "spec": {"diagram": "A-->B"}},
            {
                "id": "media_bbbbbbbbbbbb",
                "tool": "nano_banana_pro",
                "spec": {"prompt": "a cat"},
            },
        ]
        draft_result_mock.media_specs = specs
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
            intent = _make_intent(decision_id="decision-001")

            results = draft(
                intent,
                config,
                conn,
                db,
                project,
                _make_context(project),
                _make_commit(),
            )

        assert len(results) == 1
        d = results[0].draft
        assert d.media_errors == [None, "Gemini timeout"]
        assert d.media_paths == ["/tmp/ok.png", ""]
        assert d.last_error is not None
        assert "1 of 2" in d.last_error
        assert "Gemini timeout" in d.last_error
        conn.close()


class TestDeferredDraftCreation:
    """Deferred scheduling creates a draft with status='deferred' and skips the results list."""

    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.drafting.calculate_optimal_time")
    @patch("social_hook.notifications.send_notification")
    def test_deferred_draft_inserted_not_in_results(
        self,
        mock_send_notif,
        mock_schedule,
        mock_create,
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

        mock_drafter_instance = MagicMock()
        draft_result_mock = MagicMock()
        draft_result_mock.content = "Deferred test content"
        draft_result_mock.reasoning = "Deferred reasoning"
        draft_result_mock.platform = "x"
        draft_result_mock.vehicle = "single"
        draft_result_mock.media_specs = []
        mock_drafter_instance.create_draft.return_value = draft_result_mock

        mock_schedule.return_value = ScheduleResult(
            datetime=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
            is_optimal_day=False,
            day_reason="Weekly limit (5/5) reached",
            time_reason="deferred",
            deferred=True,
        )

        with patch("social_hook.llm.drafter.Drafter", return_value=mock_drafter_instance):
            intent = _make_intent(decision_id=decision_id)
            results = draft(
                intent,
                config,
                conn,
                db,
                project,
                _make_context(project),
                _make_commit(),
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

    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.drafting.calculate_optimal_time")
    @patch("social_hook.notifications.send_notification")
    def test_deferred_notification_uses_dry_run(
        self,
        mock_send_notif,
        mock_schedule,
        mock_create,
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

        mock_drafter_instance = MagicMock()
        draft_result_mock = MagicMock()
        draft_result_mock.content = "Dry run deferred"
        draft_result_mock.reasoning = "reason"
        draft_result_mock.platform = "x"
        draft_result_mock.vehicle = "single"
        draft_result_mock.media_specs = []
        mock_drafter_instance.create_draft.return_value = draft_result_mock

        mock_schedule.return_value = ScheduleResult(
            datetime=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
            is_optimal_day=False,
            day_reason="Weekly limit reached",
            time_reason="deferred",
            deferred=True,
        )

        with patch("social_hook.llm.drafter.Drafter", return_value=mock_drafter_instance):
            intent = _make_intent(decision_id="decision-002")
            results = draft(
                intent,
                config,
                conn,
                db,
                project,
                _make_context(project),
                _make_commit(),
                project_config=None,
                dry_run=True,
            )

        assert results == []
        mock_send_notif.assert_called_once()
        assert mock_send_notif.call_args[1]["dry_run"] is True
        conn.close()


class TestDraftReferencePostResolution:
    """Tests for reference post resolution and reference_post_id on Draft."""

    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.drafting.calculate_optimal_time")
    def test_reference_posts_resolved_and_set_on_draft(
        self,
        mock_schedule,
        mock_create,
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

        mock_drafter_instance = MagicMock()
        draft_result_mock = MagicMock()
        draft_result_mock.content = "Referencing previous post"
        draft_result_mock.reasoning = "Continues the thread"
        draft_result_mock.platform = "x"
        draft_result_mock.vehicle = "single"
        draft_result_mock.media_specs = []
        mock_drafter_instance.create_draft.return_value = draft_result_mock

        mock_schedule.return_value = ScheduleResult(
            datetime=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
            is_optimal_day=True,
            day_reason="weekday",
            time_reason="optimal hour",
            deferred=False,
        )

        # Build intent with reference_posts pointing to our post
        intent = _make_intent(decision_id=decision_id, reference_posts=[ref_post.id])

        with patch("social_hook.llm.drafter.Drafter", return_value=mock_drafter_instance):
            results = draft(
                intent,
                config,
                conn,
                db,
                project,
                _make_context(project),
                _make_commit(),
                project_config=None,
                dry_run=False,
            )

        assert len(results) == 1
        draft_obj = results[0].draft

        # reference_post_id should be set to the referenced post
        assert draft_obj.reference_post_id == ref_post.id

        # Same platform = quote format
        assert draft_obj.reference_type == "quote"

        # Drafter should have received referenced_posts
        call_kwargs = mock_drafter_instance.create_draft.call_args
        ref_posts_arg = call_kwargs[1]["referenced_posts"]
        assert ref_posts_arg is not None
        assert len(ref_posts_arg) == 1
        assert ref_posts_arg[0].id == ref_post.id

        conn.close()

    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.drafting.calculate_optimal_time")
    def test_no_reference_posts_leaves_draft_unchanged(
        self,
        mock_schedule,
        mock_create,
        tmp_path,
    ):
        """When evaluation has no reference_posts, draft has no reference_post_id."""
        db_path = tmp_path / "test.db"
        conn = init_database(db_path)
        project = _make_project(conn)

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(conn, dry_run=True)

        config = _make_config(platforms={"x": _make_platform_config("x")})

        mock_drafter_instance = MagicMock()
        draft_result_mock = MagicMock()
        draft_result_mock.content = "Normal post"
        draft_result_mock.reasoning = "Standalone"
        draft_result_mock.platform = "x"
        draft_result_mock.vehicle = "single"
        draft_result_mock.media_specs = []
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
            intent = _make_intent(decision_id="decision-001")
            results = draft(
                intent,
                config,
                conn,
                db,
                project,
                _make_context(project),
                _make_commit(),
                project_config=None,
            )

        assert len(results) == 1
        assert results[0].draft.reference_post_id is None
        assert results[0].draft.reference_type is None

        # Drafter should have received referenced_posts=None
        call_kwargs = mock_drafter_instance.create_draft.call_args
        assert call_kwargs[1]["referenced_posts"] is None

        conn.close()

    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.drafting.calculate_optimal_time")
    def test_cross_platform_reference_no_quote_format(
        self,
        mock_schedule,
        mock_create,
        tmp_path,
    ):
        """When reference post is on a different platform, reference_type stays None (LINK fallback)."""
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

        mock_drafter_instance = MagicMock()
        draft_result_mock = MagicMock()
        draft_result_mock.content = "Cross-platform reference"
        draft_result_mock.reasoning = "References linkedin post"
        draft_result_mock.platform = "x"
        draft_result_mock.vehicle = "single"
        draft_result_mock.media_specs = []
        mock_drafter_instance.create_draft.return_value = draft_result_mock

        mock_schedule.return_value = ScheduleResult(
            datetime=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
            is_optimal_day=True,
            day_reason="weekday",
            time_reason="optimal hour",
            deferred=False,
        )

        intent = _make_intent(decision_id=decision_id, reference_posts=[ref_post.id])

        with patch("social_hook.llm.drafter.Drafter", return_value=mock_drafter_instance):
            results = draft(
                intent,
                config,
                conn,
                db,
                project,
                _make_context(project),
                _make_commit(),
                project_config=None,
                dry_run=False,
            )

        assert len(results) == 1
        draft_obj = results[0].draft

        # reference_post_id should be set
        assert draft_obj.reference_post_id == ref_post.id
        # Cross-platform: reference_type should NOT be "quote" (LINK fallback in scheduler)
        assert draft_obj.reference_type is None

        conn.close()


# =============================================================================
# Tests for draft (two-layer split)
# =============================================================================


class TestDraftForResolvedPlatforms:
    """draft drafts for exactly the platforms passed in."""

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
        draft_result_mock.vehicle = "single"
        draft_result_mock.media_specs = []
        mock_drafter_instance.create_draft.return_value = draft_result_mock

        mock_schedule.return_value = ScheduleResult(
            datetime=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
            is_optimal_day=True,
            day_reason="weekday",
            time_reason="optimal hour",
            deferred=False,
        )

        with patch("social_hook.llm.drafter.Drafter", return_value=mock_drafter_instance):
            # Pass only "linkedin" via intent — even though config only has "x"
            intent = _make_intent(
                decision_id="decision-001",
                platforms=[PlatformSpec(platform="linkedin", resolved=resolved_linkedin)],
            )
            results = draft(
                intent,
                config,
                conn,
                db,
                project,
                _make_context(project),
                _make_commit(),
                project_config=None,
            )

        assert len(results) == 1
        assert results[0].draft.platform == "linkedin"
        # Drafter was called exactly once (for linkedin only)
        assert mock_drafter_instance.create_draft.call_count == 1
        conn.close()


class TestDraftPublicApi:
    """draft() public API works with DraftingIntent."""

    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.drafting.calculate_optimal_time")
    def test_public_api_delegates_to_resolved(
        self,
        mock_schedule,
        mock_create,
        tmp_path,
    ):
        db_path = tmp_path / "test.db"
        conn = init_database(db_path)
        project = _make_project(conn)

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(conn, dry_run=True)

        config = _make_config(platforms={"x": _make_platform_config("x")})

        mock_drafter_instance = MagicMock()
        draft_result_mock = MagicMock()
        draft_result_mock.content = "Public API test"
        draft_result_mock.reasoning = "reasoning"
        draft_result_mock.platform = "x"
        draft_result_mock.vehicle = "single"
        draft_result_mock.media_specs = []
        mock_drafter_instance.create_draft.return_value = draft_result_mock

        mock_schedule.return_value = ScheduleResult(
            datetime=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
            is_optimal_day=True,
            day_reason="weekday",
            time_reason="optimal hour",
            deferred=False,
        )

        with patch("social_hook.llm.drafter.Drafter", return_value=mock_drafter_instance):
            intent = _make_intent(decision_id="decision-001")

            results = draft(
                intent,
                config,
                conn,
                db,
                project,
                _make_context(project),
                _make_commit(),
            )

        assert len(results) == 1
        assert results[0].draft.platform == "x"
        conn.close()


# ---------------------------------------------------------------------------
# _generate_all_media — parallel generator under test
# ---------------------------------------------------------------------------


class TestGenerateAllMedia:
    """Parallel media generation: happy path, partial failure, user-uploaded passthrough."""

    @patch("social_hook.drafting._generate_one_media_guarded")
    def test_happy_path_returns_aligned_arrays(self, mock_one, tmp_path):
        from social_hook.drafting import _generate_all_media

        config = _make_config()
        config.media_generation.enabled = True
        specs = [
            {"id": "media_aaaaaaaaaaaa", "tool": "mermaid", "spec": {"diagram": "A"}},
            {"id": "media_bbbbbbbbbbbb", "tool": "nano_banana_pro", "spec": {"prompt": "x"}},
        ]
        mock_one.side_effect = ["/out/a.png", "/out/b.png"]

        paths, errors = _generate_all_media(config, specs, dry_run=True, verbose=False)

        assert len(paths) == 2
        assert len(errors) == 2
        assert errors == [None, None]
        # Set comparison — ThreadPoolExecutor order is not deterministic.
        assert set(paths) == {"/out/a.png", "/out/b.png"}

    @patch("social_hook.drafting._generate_one_media_guarded")
    def test_partial_failure_other_items_still_generated(self, mock_one, tmp_path):
        from social_hook.drafting import _generate_all_media

        config = _make_config()
        config.media_generation.enabled = True
        specs = [
            {"id": "media_aaaaaaaaaaaa", "tool": "mermaid", "spec": {"diagram": "A"}},
            {"id": "media_bbbbbbbbbbbb", "tool": "nano_banana_pro", "spec": {"prompt": "x"}},
        ]

        # Item 1 raises, item 0 succeeds.
        def side_effect(config_, spec, tool, dry_run, verbose, project_config):
            if spec["id"] == "media_bbbbbbbbbbbb":
                raise RuntimeError("Gemini timeout")
            return "/out/a.png"

        mock_one.side_effect = side_effect

        paths, errors = _generate_all_media(config, specs, dry_run=True, verbose=False)

        assert paths[0] == "/out/a.png"
        assert paths[1] == ""
        assert errors[0] is None
        assert errors[1] == "Gemini timeout"

    def test_user_uploaded_passthrough_no_adapter_call(self, tmp_path):
        from social_hook.drafting import _generate_all_media

        config = _make_config()
        config.media_generation.enabled = True
        upload_path = tmp_path / "ref.png"
        upload_path.write_bytes(b"\x89PNG")
        specs = [
            {
                "id": "media_upl000000ab",
                "tool": "legacy_upload",
                "spec": {"path": str(upload_path)},
                "user_uploaded": True,
            },
        ]

        with patch("social_hook.drafting._generate_one_media_guarded") as mock_one:
            paths, errors = _generate_all_media(config, specs, dry_run=False, verbose=False)

        assert paths == [str(upload_path)]
        assert errors == [None]
        mock_one.assert_not_called()

    @patch("social_hook.drafting._generate_one_media_guarded")
    def test_empty_specs_returns_empty_arrays(self, mock_one, tmp_path):
        from social_hook.drafting import _generate_all_media

        config = _make_config()
        config.media_generation.enabled = True
        paths, errors = _generate_all_media(config, [], dry_run=True)
        assert paths == []
        assert errors == []
        mock_one.assert_not_called()

    @patch("social_hook.drafting._generate_one_media_guarded")
    def test_task_stage_emitted_per_item(self, mock_one, tmp_path):
        """emit_task_stage is called once per item when task_id + db are provided."""
        from social_hook.drafting import _generate_all_media

        config = _make_config()
        config.media_generation.enabled = True
        specs = [
            {"id": "media_aaaaaaaaaaaa", "tool": "mermaid", "spec": {"diagram": "A"}},
            {"id": "media_bbbbbbbbbbbb", "tool": "mermaid", "spec": {"diagram": "B"}},
        ]
        mock_one.side_effect = ["/out/a.png", "/out/b.png"]
        fake_db = MagicMock()

        paths, errors = _generate_all_media(
            config,
            specs,
            task_id="task-1",
            project_id="proj-1",
            db=fake_db,
            dry_run=True,
        )

        assert fake_db.emit_task_stage.call_count == 2
        # The stage label format is "Media N of M".
        labels = {c.args[2] for c in fake_db.emit_task_stage.call_args_list}
        assert labels == {"Media 1 of 2", "Media 2 of 2"}


class TestGenerateOneMediaGuarded:
    """Thread-safety gate: non-thread-safe adapters serialize via with_adapter_lock."""

    @patch("social_hook.drafting._generate_one_media")
    def test_playwright_uses_pre_populated_lock(self, mock_inner):
        """The lock for ``playwright`` is pre-populated at module import."""
        from social_hook.adapters.registry import _ADAPTER_LOCKS
        from social_hook.drafting import _generate_one_media_guarded

        assert "playwright" in _ADAPTER_LOCKS
        assert "ray_so" in _ADAPTER_LOCKS

        mock_inner.return_value = "/out/a.png"
        spec = {"id": "media_aaaaaaaaaaaa", "tool": "playwright", "spec": {"url": "https://ex.com"}}

        result = _generate_one_media_guarded(
            config=MagicMock(),
            spec=spec,
            tool="playwright",
            dry_run=True,
            verbose=False,
            project_config=None,
        )
        assert result == "/out/a.png"
        mock_inner.assert_called_once()


# ---------------------------------------------------------------------------
# DraftingIntent.uploads threads through all 4 builders
# ---------------------------------------------------------------------------


class TestDraftingIntentUploads:
    """uploads field on DraftingIntent: default None for 3 builders; threaded by intent_from_decision."""

    def test_uploads_default_none_on_drafting_intent(self):
        from social_hook.drafting import DraftingIntent

        intent = DraftingIntent()
        assert intent.uploads is None

    def test_intent_from_decision_threads_uploads(self, tmp_path):
        """intent_from_decision forwards its uploads kwarg onto the returned DraftingIntent."""
        from social_hook.db.connection import init_database
        from social_hook.drafting import MediaUpload
        from social_hook.drafting_intents import intent_from_decision

        db_path = tmp_path / "t.db"
        conn = init_database(db_path)

        config = _make_config(platforms={"x": _make_platform_config("x")})
        decision = MagicMock()
        decision.id = "d1"
        decision.decision = "draft"
        decision.angle = "test"
        decision.reasoning = "r"
        decision.post_category = "standalone"
        decision.targets = {}

        uploads = [MediaUpload(path="/tmp/a.png", context="desk")]
        intent = intent_from_decision(decision, config, conn, target_platform="x", uploads=uploads)
        assert intent.uploads == uploads
        conn.close()

    def test_intent_from_platforms_never_has_uploads(self):
        """Auto-triggered intents never carry operator uploads."""
        from social_hook.drafting_intents import intent_from_platforms

        config = _make_config(platforms={"x": _make_platform_config("x")})
        evaluation = MagicMock()
        evaluation.strategies = {}
        evaluation.targets = {}
        evaluation.commit_analysis = MagicMock()
        evaluation.commit_analysis.summary = "s"
        intent = intent_from_platforms(evaluation, "d1", config)
        assert intent.uploads is None
