"""Tests for suggestions.py coverage: create, evaluate, dismiss, strategy wiring."""

from unittest.mock import MagicMock, patch

from social_hook.models.core import Project
from social_hook.suggestions import create_suggestion, dismiss_suggestion, evaluate_suggestion

# =============================================================================
# create_suggestion
# =============================================================================


class TestCreateSuggestion:
    """Tests for create_suggestion."""

    def test_creates_pending_suggestion(self, temp_db):
        from social_hook.db import operations as ops

        project = Project(id="proj-sug1", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        suggestion = create_suggestion(
            conn=temp_db,
            project_id="proj-sug1",
            idea="Write about new auth system",
            strategy="building-public",
            source="operator",
        )
        assert suggestion.id.startswith("suggestion_")
        assert suggestion.status == "pending"
        assert suggestion.idea == "Write about new auth system"
        assert suggestion.strategy == "building-public"
        assert suggestion.source == "operator"

    def test_creates_with_media_refs(self, temp_db):
        from social_hook.db import operations as ops

        project = Project(id="proj-sug2", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        suggestion = create_suggestion(
            conn=temp_db,
            project_id="proj-sug2",
            idea="Screenshot post",
            media_refs=["img1.png", "img2.png"],
        )
        assert suggestion.media_refs == ["img1.png", "img2.png"]

    def test_creates_with_no_strategy(self, temp_db):
        """strategy=None is valid (evaluator will choose)."""
        from social_hook.db import operations as ops

        project = Project(id="proj-sug3", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        suggestion = create_suggestion(
            conn=temp_db,
            project_id="proj-sug3",
            idea="General idea",
        )
        assert suggestion.strategy is None


# =============================================================================
# dismiss_suggestion
# =============================================================================


class TestDismissSuggestion:
    """Tests for dismiss_suggestion."""

    def test_dismiss_existing_suggestion(self, temp_db):
        from social_hook.db import operations as ops

        project = Project(id="proj-dis1", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        suggestion = create_suggestion(
            conn=temp_db,
            project_id="proj-dis1",
            idea="Dismiss me",
        )
        result = dismiss_suggestion(temp_db, suggestion.id)
        assert result is True

    def test_dismiss_nonexistent_returns_false(self, temp_db):
        result = dismiss_suggestion(temp_db, "nonexistent-id")
        assert result is False


# =============================================================================
# evaluate_suggestion: dry run
# =============================================================================


class TestEvaluateSuggestionDryRun:
    """evaluate_suggestion in dry_run mode."""

    def test_dry_run_returns_cycle_id(self, temp_db):
        from social_hook.db import operations as ops

        project = Project(id="proj-evdry", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        suggestion = create_suggestion(
            conn=temp_db,
            project_id="proj-evdry",
            idea="Draft something about auth",
        )

        result = evaluate_suggestion(
            conn=temp_db,
            config=None,
            project_id="proj-evdry",
            suggestion_id=suggestion.id,
            dry_run=True,
        )
        assert result is not None
        assert result.startswith("cycle_")


# =============================================================================
# evaluate_suggestion: no config -> early return
# =============================================================================


class TestEvaluateSuggestionNoConfig:
    """evaluate_suggestion with config=None returns cycle_id without LLM."""

    def test_none_config_returns_cycle_id(self, temp_db):
        from social_hook.db import operations as ops

        project = Project(id="proj-evnoc", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        suggestion = create_suggestion(
            conn=temp_db,
            project_id="proj-evnoc",
            idea="Some idea",
        )

        result = evaluate_suggestion(
            conn=temp_db,
            config=None,
            project_id="proj-evnoc",
            suggestion_id=suggestion.id,
            dry_run=False,
        )
        assert result is not None
        # Status should be updated to "evaluated"
        suggestions = ops.get_suggestions_by_project(temp_db, "proj-evnoc")
        evaluated = [s for s in suggestions if s.id == suggestion.id]
        assert len(evaluated) == 1
        assert evaluated[0].status == "evaluated"


# =============================================================================
# evaluate_suggestion: wrong status
# =============================================================================


class TestEvaluateSuggestionWrongStatus:
    """evaluate_suggestion rejects non-pending suggestions."""

    def test_evaluated_suggestion_returns_none(self, temp_db):
        from social_hook.db import operations as ops

        project = Project(id="proj-evwrong", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        suggestion = create_suggestion(
            conn=temp_db,
            project_id="proj-evwrong",
            idea="Already done",
        )
        # Manually set status to evaluated
        ops.update_suggestion_status(temp_db, suggestion.id, "evaluated")

        result = evaluate_suggestion(
            conn=temp_db,
            config=None,
            project_id="proj-evwrong",
            suggestion_id=suggestion.id,
        )
        assert result is None


# =============================================================================
# evaluate_suggestion: not found
# =============================================================================


class TestEvaluateSuggestionNotFound:
    """evaluate_suggestion returns None for nonexistent suggestion."""

    def test_missing_suggestion_returns_none(self, temp_db):
        from social_hook.db import operations as ops

        project = Project(id="proj-evnf", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        result = evaluate_suggestion(
            conn=temp_db,
            config=None,
            project_id="proj-evnf",
            suggestion_id="nonexistent",
        )
        assert result is None


# =============================================================================
# evaluate_suggestion: strategy wiring (targets path)
# =============================================================================


class TestEvaluateSuggestionStrategyWiring:
    """evaluate_suggestion passes strategies to evaluator."""

    def test_strategies_passed_to_evaluator(self, temp_db):
        from social_hook.db import operations as ops
        from social_hook.llm.schemas import (
            CommitAnalysis,
            LogEvaluationInput,
            StrategyDecisionInput,
            TargetAction,
        )

        project = Project(id="proj-evstrat", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        suggestion = create_suggestion(
            conn=temp_db,
            project_id="proj-evstrat",
            idea="Write about auth",
            strategy="building-public",
        )

        evaluation = LogEvaluationInput(
            commit_analysis=CommitAnalysis(summary="suggestion", episode_tags=[]),
            strategies={
                "building-public": StrategyDecisionInput(
                    action=TargetAction.draft,
                    reason="great idea",
                ),
            },
        )
        mock_evaluator = MagicMock()
        mock_evaluator.evaluate.return_value = evaluation

        config = MagicMock()
        config.models.evaluator = "anthropic/claude-sonnet-4-5"
        config.targets = {"main-feed": MagicMock(strategy="building-public")}
        config.content_strategies = {"building-public": MagicMock()}

        mock_routed = MagicMock()
        mock_routed.action = "draft"

        with (
            patch("social_hook.db.operations.get_project", return_value=project),
            patch("social_hook.config.project.load_project_config", return_value=None),
            patch("social_hook.llm.prompts.assemble_evaluator_context", return_value=MagicMock()),
            patch("social_hook.llm.factory.create_client", return_value=MagicMock()),
            patch("social_hook.llm.evaluator.Evaluator", return_value=mock_evaluator),
            patch("social_hook.routing.route_to_targets", return_value=[mock_routed]),
            patch("social_hook.drafting.draft_for_targets"),
        ):
            result = evaluate_suggestion(
                conn=temp_db,
                config=config,
                project_id="proj-evstrat",
                suggestion_id=suggestion.id,
            )

        assert result is not None
        # Verify strategies kwarg was passed to evaluator
        call_kwargs = mock_evaluator.evaluate.call_args[1]
        assert "strategies" in call_kwargs
        assert call_kwargs["strategies"] == config.content_strategies


# =============================================================================
# evaluate_suggestion: legacy path (no targets)
# =============================================================================


class TestEvaluateSuggestionLegacyPath:
    """evaluate_suggestion uses legacy draft_for_platforms when no targets."""

    def test_legacy_path_with_draft_action(self, temp_db):
        from social_hook.db import operations as ops
        from social_hook.llm.schemas import (
            CommitAnalysis,
            LogEvaluationInput,
            StrategyDecisionInput,
            TargetAction,
        )

        project = Project(id="proj-evleg", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        suggestion = create_suggestion(
            conn=temp_db,
            project_id="proj-evleg",
            idea="Write about feature X",
        )

        evaluation = LogEvaluationInput(
            commit_analysis=CommitAnalysis(summary="suggestion", episode_tags=[]),
            strategies={
                "default": StrategyDecisionInput(
                    action=TargetAction.draft,
                    reason="worth drafting",
                ),
            },
        )
        mock_evaluator = MagicMock()
        mock_evaluator.evaluate.return_value = evaluation

        config = MagicMock()
        config.models.evaluator = "anthropic/claude-sonnet-4-5"
        config.targets = {}  # No targets -> legacy path
        config.content_strategies = None

        with (
            patch("social_hook.db.operations.get_project", return_value=project),
            patch("social_hook.config.project.load_project_config", return_value=None),
            patch("social_hook.llm.prompts.assemble_evaluator_context", return_value=MagicMock()),
            patch("social_hook.llm.factory.create_client", return_value=MagicMock()),
            patch("social_hook.llm.evaluator.Evaluator", return_value=mock_evaluator),
            patch("social_hook.drafting.draft_for_platforms") as mock_legacy_draft,
        ):
            result = evaluate_suggestion(
                conn=temp_db,
                config=config,
                project_id="proj-evleg",
                suggestion_id=suggestion.id,
            )

        assert result is not None
        mock_legacy_draft.assert_called_once()
