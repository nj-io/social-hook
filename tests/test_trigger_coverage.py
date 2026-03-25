"""Additional trigger.py coverage: strategy wiring, legacy path deprecation, _run_targets_path paths."""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from social_hook.llm.schemas import (
    CommitAnalysis,
    LogEvaluationInput,
    StrategyDecisionInput,
    TargetAction,
)
from social_hook.models import CommitInfo, Project
from social_hook.rate_limits import GateResult
from social_hook.trigger import (
    _run_targets_path,
)


@pytest.fixture(autouse=True)
def _allow_rate_limit():
    with patch(
        "social_hook.trigger.check_rate_limit",
        return_value=GateResult(blocked=False, reason=""),
    ):
        yield


def _make_evaluation(strategies=None):
    if strategies is None:
        strategies = {
            "building-public": StrategyDecisionInput(
                action=TargetAction.draft,
                reason="Good commit",
                angle="show the work",
            ),
        }
    return LogEvaluationInput(
        commit_analysis=CommitAnalysis(
            summary="Refactored module",
            episode_tags=["refactor"],
        ),
        strategies=strategies,
    )


# =============================================================================
# Strategy wiring: strategies passed to evaluator
# =============================================================================


class TestStrategyWiring:
    """Verify strategies are forwarded from config to evaluator.evaluate()."""

    @patch("social_hook.trigger.assemble_evaluator_context")
    @patch("social_hook.config.project.load_project_config", return_value=None)
    @patch("social_hook.trigger.parse_commit_info")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.get_db_path", return_value="/tmp/test.db")
    @patch("social_hook.trigger.load_full_config")
    def test_strategies_passed_to_evaluator(
        self,
        mock_load_config,
        mock_db_path,
        mock_init_db,
        mock_parse_commit,
        mock_load_project_config,
        mock_assemble_context,
    ):
        """config.content_strategies is forwarded to evaluator.evaluate()."""
        from social_hook.trigger import run_trigger

        # Setup config with content_strategies
        config = MagicMock()
        config.content_strategies = {
            "building-public": MagicMock(),
            "brand": MagicMock(),
        }
        config.targets = {}  # Empty targets = legacy path
        config.platforms = {
            "x": MagicMock(enabled=True, priority="primary", type="builtin", description=None)
        }
        config.rate_limits = MagicMock()
        config.notification_level = "drafts_only"
        mock_load_config.return_value = config

        # Setup DB
        conn = MagicMock()
        mock_init_db.return_value = conn

        project = Project(id="proj-1", name="test", repo_path="/tmp/test")
        conn.execute.return_value = MagicMock()

        # Mock ops
        with patch("social_hook.trigger.ops") as mock_ops:
            mock_ops.get_project_by_path.return_value = project
            mock_ops.get_held_decisions.return_value = []

            mock_parse_commit.return_value = CommitInfo(hash="abc", message="test", diff="")
            mock_assemble_context.return_value = MagicMock(
                project_summary="summary",
                held_decisions=[],
            )

            # Mock evaluator — patch at source since trigger.py uses lazy imports
            evaluation = _make_evaluation(
                {"default": StrategyDecisionInput(action=TargetAction.skip, reason="not worthy")}
            )
            mock_evaluator = MagicMock()
            mock_evaluator.evaluate.return_value = evaluation

            with (
                patch("social_hook.llm.factory.create_client", return_value=MagicMock()),
                patch("social_hook.llm.evaluator.Evaluator", return_value=mock_evaluator),
                patch("social_hook.scheduling.get_scheduling_state", return_value=None),
                patch("social_hook.trigger._get_current_branch", return_value="main"),
                patch("social_hook.trigger._send_decision_notification"),
            ):
                run_trigger("abc", "/tmp/test", verbose=False)

                # Verify strategies kwarg was passed
                call_kwargs = mock_evaluator.evaluate.call_args[1]
                assert "strategies" in call_kwargs
                assert call_kwargs["strategies"] == config.content_strategies


# =============================================================================
# Legacy path deprecation warning
# =============================================================================


class TestLegacyPathDeprecation:
    """No targets configured -> legacy path logs deprecation warning."""

    @patch("social_hook.trigger.assemble_evaluator_context")
    @patch("social_hook.config.project.load_project_config", return_value=None)
    @patch("social_hook.trigger.parse_commit_info")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.get_db_path", return_value="/tmp/test.db")
    @patch("social_hook.trigger.load_full_config")
    def test_legacy_path_logs_warning(
        self,
        mock_load_config,
        mock_db_path,
        mock_init_db,
        mock_parse_commit,
        mock_load_project_config,
        mock_assemble_context,
        caplog,
    ):
        """When config.targets is empty, the legacy warning is logged."""
        from social_hook.trigger import run_trigger

        config = MagicMock()
        config.content_strategies = None
        config.targets = {}  # Empty = legacy
        config.platforms = {
            "x": MagicMock(enabled=True, priority="primary", type="builtin", description=None)
        }
        config.rate_limits = MagicMock()
        config.notification_level = "drafts_only"
        mock_load_config.return_value = config

        conn = MagicMock()
        mock_init_db.return_value = conn

        project = Project(id="proj-1", name="test", repo_path="/tmp/test")
        with patch("social_hook.trigger.ops") as mock_ops:
            mock_ops.get_project_by_path.return_value = project
            mock_ops.get_held_decisions.return_value = []

            mock_parse_commit.return_value = CommitInfo(hash="abc", message="test", diff="")
            mock_assemble_context.return_value = MagicMock(
                project_summary="summary",
                held_decisions=[],
            )

            evaluation = _make_evaluation(
                {"default": StrategyDecisionInput(action=TargetAction.skip, reason="nah")}
            )
            mock_evaluator = MagicMock()
            mock_evaluator.evaluate.return_value = evaluation

            with (
                patch("social_hook.llm.factory.create_client", return_value=MagicMock()),
                patch("social_hook.llm.evaluator.Evaluator", return_value=mock_evaluator),
                patch("social_hook.scheduling.get_scheduling_state", return_value=None),
                patch("social_hook.trigger._get_current_branch", return_value="main"),
                patch("social_hook.trigger._send_decision_notification"),
            ):
                with caplog.at_level(logging.WARNING, logger="social_hook.trigger"):
                    run_trigger("abc", "/tmp/test", verbose=False)

                assert any(
                    "no targets configured" in r.message.lower()
                    or "legacy platform-based" in r.message.lower()
                    for r in caplog.records
                )


# =============================================================================
# _run_targets_path: notification on skip when all_decisions
# =============================================================================


class TestRunTargetsPathNotification:
    """_run_targets_path sends notification for non-draftable when all_decisions."""

    def test_skip_with_all_decisions_sends_notification(self, temp_db):
        from social_hook.db import operations as ops

        project = Project(id="proj-notif", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        strategies = {
            "s1": StrategyDecisionInput(action=TargetAction.skip, reason="not worthy"),
        }
        evaluation = _make_evaluation(strategies)
        commit = CommitInfo(hash="notif123", message="test", diff="")
        context = SimpleNamespace(held_decisions=[])

        config = MagicMock()
        config.targets = {"main-feed": MagicMock(strategy="s1")}
        config.notification_level = "all_decisions"

        with (
            patch("social_hook.routing.route_to_targets", return_value=[]),
            patch("social_hook.db.operations.get_held_decisions", return_value=[]),
            patch("social_hook.trigger._send_decision_notification") as mock_notify,
        ):
            from social_hook.llm.dry_run import DryRunContext

            db = DryRunContext(temp_db, dry_run=False)
            _run_targets_path(
                evaluation=evaluation,
                analysis=evaluation.commit_analysis,
                config=config,
                conn=temp_db,
                db=db,
                project=project,
                commit=commit,
                commit_hash="notif123",
                context=context,
                project_config=None,
                current_branch="main",
                evaluator_client=MagicMock(),
                dry_run=False,
                verbose=False,
            )
            mock_notify.assert_called_once()

    def test_skip_with_drafts_only_no_notification(self, temp_db):
        """Skip with drafts_only notification_level does NOT notify."""
        from social_hook.db import operations as ops

        project = Project(id="proj-quiet", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        strategies = {
            "s1": StrategyDecisionInput(action=TargetAction.skip, reason="not worthy"),
        }
        evaluation = _make_evaluation(strategies)
        commit = CommitInfo(hash="quiet123", message="test", diff="")
        context = SimpleNamespace(held_decisions=[])

        config = MagicMock()
        config.targets = {"main-feed": MagicMock(strategy="s1")}
        config.notification_level = "drafts_only"

        with (
            patch("social_hook.routing.route_to_targets", return_value=[]),
            patch("social_hook.db.operations.get_held_decisions", return_value=[]),
            patch("social_hook.trigger._send_decision_notification") as mock_notify,
        ):
            from social_hook.llm.dry_run import DryRunContext

            db = DryRunContext(temp_db, dry_run=False)
            _run_targets_path(
                evaluation=evaluation,
                analysis=evaluation.commit_analysis,
                config=config,
                conn=temp_db,
                db=db,
                project=project,
                commit=commit,
                commit_hash="quiet123",
                context=context,
                project_config=None,
                current_branch="main",
                evaluator_client=MagicMock(),
                dry_run=False,
                verbose=False,
            )
            mock_notify.assert_not_called()


# =============================================================================
# _run_targets_path: hold count enforcement
# =============================================================================


class TestRunTargetsPathHoldEnforcement:
    """Hold limit causes forced skip."""

    def test_hold_limit_forces_skip(self, temp_db):
        from social_hook.db import operations as ops

        project = Project(id="proj-hold", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        strategies = {
            "s1": StrategyDecisionInput(action=TargetAction.hold, reason="needs more"),
        }
        evaluation = _make_evaluation(strategies)
        commit = CommitInfo(hash="hold123", message="test", diff="")
        context = SimpleNamespace(held_decisions=[])

        config = MagicMock()
        config.targets = {"main-feed": MagicMock(strategy="s1")}
        config.notification_level = "all_decisions"

        # Pre-fill held decisions to exceed limit
        held = [MagicMock(id=f"held-{i}") for i in range(6)]

        with (
            patch("social_hook.routing.route_to_targets", return_value=[]),
            patch("social_hook.db.operations.get_held_decisions", return_value=held),
            patch("social_hook.trigger._send_decision_notification"),
        ):
            from social_hook.llm.dry_run import DryRunContext

            db = DryRunContext(temp_db, dry_run=False)
            _run_targets_path(
                evaluation=evaluation,
                analysis=evaluation.commit_analysis,
                config=config,
                conn=temp_db,
                db=db,
                project=project,
                commit=commit,
                commit_hash="hold123",
                context=context,
                project_config=None,  # default max_hold = 5
                current_branch="main",
                evaluator_client=MagicMock(),
                dry_run=False,
                verbose=False,
            )

        decisions = ops.get_recent_decisions(temp_db, "proj-hold")
        assert len(decisions) == 1
        # Should be forced to "skip" because hold limit reached
        assert decisions[0].decision == "skip"


# =============================================================================
# _run_targets_path: draftable -> routes and drafts
# =============================================================================


class TestRunTargetsPathDrafting:
    """Draftable decision triggers routing + drafting."""

    def test_draft_calls_route_and_draft(self, temp_db):
        from social_hook.db import operations as ops

        project = Project(id="proj-draft", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        strategies = {
            "building-public": StrategyDecisionInput(
                action=TargetAction.draft,
                reason="Good for building in public",
            ),
        }
        evaluation = _make_evaluation(strategies)
        commit = CommitInfo(hash="draft123", message="test", diff="")
        context = SimpleNamespace(held_decisions=[])

        config = MagicMock()
        config.targets = {"main-feed": MagicMock(strategy="building-public")}
        config.notification_level = "drafts_only"

        mock_routed = MagicMock()
        mock_routed.action = "draft"

        with (
            patch("social_hook.routing.route_to_targets", return_value=[mock_routed]) as mock_route,
            patch("social_hook.drafting.draft_for_targets", return_value=[]) as mock_draft,
            patch("social_hook.db.operations.get_held_decisions", return_value=[]),
        ):
            from social_hook.llm.dry_run import DryRunContext

            db = DryRunContext(temp_db, dry_run=False)
            _run_targets_path(
                evaluation=evaluation,
                analysis=evaluation.commit_analysis,
                config=config,
                conn=temp_db,
                db=db,
                project=project,
                commit=commit,
                commit_hash="draft123",
                context=context,
                project_config=None,
                current_branch="main",
                evaluator_client=MagicMock(),
                dry_run=False,
                verbose=False,
            )

            mock_route.assert_called_once()
            mock_draft.assert_called_once()
