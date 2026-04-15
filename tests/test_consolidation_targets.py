"""Tests for consolidation.py targets pipeline path (Chunk 4)."""

from unittest.mock import MagicMock, patch

from social_hook.llm.schemas import (
    CommitAnalysis,
    LogEvaluationInput,
    StrategyDecisionInput,
    TargetAction,
)


class TestConsolidationTargetsPath:
    """Consolidation with targets config -> per-strategy re-evaluation."""

    def _mock_evaluator(self, evaluation):
        """Create a mock evaluator that returns the given evaluation."""
        mock = MagicMock()
        mock.evaluate.return_value = evaluation
        return mock

    def _base_config(self, with_targets=True):
        config = MagicMock()
        if with_targets:
            config.targets = {"main-feed": MagicMock(strategy="building-public")}
        else:
            config.targets = {}
        config.models = MagicMock()
        config.platforms = {
            "x": MagicMock(enabled=True, type="standard", description=None, priority="primary")
        }
        config.media_generation = MagicMock()
        return config

    def test_targets_path_routes_and_drafts(self):
        """When config.targets exists, consolidation uses route_to_targets."""
        from social_hook.consolidation import _process_re_evaluate

        evaluation = LogEvaluationInput(
            commit_analysis=CommitAnalysis(summary="Batch", episode_tags=[]),
            strategies={
                "building-public": StrategyDecisionInput(
                    action=TargetAction.draft,
                    reason="Batch is worth posting",
                    angle="batch insight",
                ),
            },
        )

        config = self._base_config(with_targets=True)

        mock_routed = MagicMock()
        mock_routed.action = "draft"

        with (
            patch("social_hook.llm.factory.create_client", return_value=MagicMock()),
            patch(
                "social_hook.llm.evaluator.Evaluator",
                return_value=self._mock_evaluator(evaluation),
            ),
            patch("social_hook.routing.route_to_targets", return_value=[mock_routed]),
            patch("social_hook.drafting.draft", return_value=[]) as mock_dft,
            patch("social_hook.consolidation.ops"),
        ):
            decisions = [MagicMock(id="d1", commit_summary="test")]
            _process_re_evaluate(
                config=config,
                conn=MagicMock(),
                db=MagicMock(),
                project=MagicMock(name="test", id="proj-1", repo_path="/tmp"),
                decisions=decisions,
                batch_id="batch-123",
                dry_run=False,
            )

            mock_dft.assert_called_once()

    def test_legacy_path_when_no_targets(self):
        """When config.targets is empty, consolidation uses legacy path."""
        from social_hook.consolidation import _process_re_evaluate

        evaluation = LogEvaluationInput(
            commit_analysis=CommitAnalysis(summary="Batch", episode_tags=[]),
            strategies={
                "default": StrategyDecisionInput(
                    action=TargetAction.draft,
                    reason="Batch is worth posting",
                    angle="batch insight",
                ),
            },
        )

        config = self._base_config(with_targets=False)

        with (
            patch("social_hook.llm.factory.create_client", return_value=MagicMock()),
            patch(
                "social_hook.llm.evaluator.Evaluator",
                return_value=self._mock_evaluator(evaluation),
            ),
            patch("social_hook.drafting.draft", return_value=[]) as mock_dfp,
            patch("social_hook.drafting_intents.intent_from_platforms") as mock_compat,
            patch("social_hook.consolidation.ops"),
        ):
            decisions = [MagicMock(id="d1", commit_summary="test")]
            _process_re_evaluate(
                config=config,
                conn=MagicMock(),
                db=MagicMock(),
                project=MagicMock(name="test", id="proj-1", repo_path="/tmp"),
                decisions=decisions,
                batch_id="batch-456",
                dry_run=False,
            )

            mock_compat.assert_called_once()
            mock_dfp.assert_called_once()

    def test_skip_result_does_not_draft(self):
        """When all strategies skip, consolidation doesn't draft."""
        from social_hook.consolidation import _process_re_evaluate

        evaluation = LogEvaluationInput(
            commit_analysis=CommitAnalysis(summary="Batch", episode_tags=[]),
            strategies={
                "building-public": StrategyDecisionInput(
                    action=TargetAction.skip,
                    reason="Not enough for a post",
                ),
            },
        )

        config = self._base_config(with_targets=True)

        with (
            patch("social_hook.llm.factory.create_client", return_value=MagicMock()),
            patch(
                "social_hook.llm.evaluator.Evaluator",
                return_value=self._mock_evaluator(evaluation),
            ),
            patch("social_hook.consolidation.ops") as mock_ops,
        ):
            decisions = [MagicMock(id="d1", commit_summary="test")]
            _process_re_evaluate(
                config=config,
                conn=MagicMock(),
                db=MagicMock(),
                project=MagicMock(name="test", id="proj-1", repo_path="/tmp"),
                decisions=decisions,
                batch_id="batch-789",
                dry_run=False,
            )

            mock_ops.update_decision.assert_not_called()
