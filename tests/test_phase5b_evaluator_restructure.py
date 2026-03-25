"""Tests for Phase 5b: Evaluator Restructure.

Tests that:
1. Trivial commits skip stage 2 (decision created as "skip")
2. Non-trivial commits pass analysis to evaluator
3. Backward compat: evaluator works without analysis parameter
4. Prompt assembly includes pre-computed analysis section when provided
5. Prompt assembly works without analysis (backward compat)
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from social_hook.llm.schemas import (
    BriefUpdateInstructions,
    CommitAnalysis,
    CommitAnalysisResult,
    CommitClassification,
    TargetAction,
)
from social_hook.models import CommitInfo, Project

# =============================================================================
# _is_trivial_classification
# =============================================================================


class TestIsTrivialClassification:
    """Test the _is_trivial_classification helper."""

    def test_trivial_returns_true(self):
        from social_hook.trigger import _is_trivial_classification

        result = CommitAnalysisResult(
            commit_analysis=CommitAnalysis(
                summary="Fix typo",
                classification=CommitClassification.trivial,
                episode_tags=["typo"],
            ),
            brief_update=BriefUpdateInstructions(),
        )
        assert _is_trivial_classification(result) is True

    def test_routine_returns_false(self):
        from social_hook.trigger import _is_trivial_classification

        result = CommitAnalysisResult(
            commit_analysis=CommitAnalysis(
                summary="Refactor module",
                classification=CommitClassification.routine,
                episode_tags=["refactor"],
            ),
            brief_update=BriefUpdateInstructions(),
        )
        assert _is_trivial_classification(result) is False

    def test_notable_returns_false(self):
        from social_hook.trigger import _is_trivial_classification

        result = CommitAnalysisResult(
            commit_analysis=CommitAnalysis(
                summary="New feature",
                classification=CommitClassification.notable,
                episode_tags=["feature"],
            ),
            brief_update=BriefUpdateInstructions(),
        )
        assert _is_trivial_classification(result) is False

    def test_significant_returns_false(self):
        from social_hook.trigger import _is_trivial_classification

        result = CommitAnalysisResult(
            commit_analysis=CommitAnalysis(
                summary="Architecture change",
                classification=CommitClassification.significant,
                episode_tags=["architecture"],
            ),
            brief_update=BriefUpdateInstructions(),
        )
        assert _is_trivial_classification(result) is False

    def test_none_returns_false(self):
        from social_hook.trigger import _is_trivial_classification

        assert _is_trivial_classification(None) is False

    def test_no_classification_returns_false(self):
        from social_hook.trigger import _is_trivial_classification

        result = CommitAnalysisResult(
            commit_analysis=CommitAnalysis(
                summary="Something",
                episode_tags=[],
            ),
            brief_update=BriefUpdateInstructions(),
        )
        assert _is_trivial_classification(result) is False


# =============================================================================
# _run_trivial_skip
# =============================================================================


class TestRunTrivialSkip:
    """Test that trivial commits produce a skip decision without stage 2."""

    def _make_trivial_result(self):
        return CommitAnalysisResult(
            commit_analysis=CommitAnalysis(
                summary="Fix whitespace in README",
                classification=CommitClassification.trivial,
                episode_tags=["docs", "formatting"],
            ),
            brief_update=BriefUpdateInstructions(),
        )

    def _make_ctx(self, temp_db, project, commit):
        from social_hook.llm.dry_run import DryRunContext
        from social_hook.trigger import TriggerContext

        config = MagicMock()
        config.notification_level = "drafts_only"
        return TriggerContext(
            config=config,
            conn=temp_db,
            db=DryRunContext(temp_db, dry_run=False),
            project=project,
            commit=commit,
            project_config=None,
            current_branch="main",
            dry_run=False,
            verbose=False,
            show_prompt=False,
        )

    def test_creates_skip_decision(self, temp_db):
        """Trivial commits create a skip decision."""
        from social_hook.db import operations as ops
        from social_hook.trigger import _run_trivial_skip

        project = Project(id="proj-trivial-1", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        commit = CommitInfo(hash="aaa111", message="fix whitespace", diff="")
        ctx = self._make_ctx(temp_db, project, commit)
        result = _run_trivial_skip(
            ctx=ctx,
            analyzer_result=self._make_trivial_result(),
            commit_hash="aaa111",
        )

        assert result == 0

        # Verify decision was created as skip
        decisions = ops.get_recent_decisions(temp_db, "proj-trivial-1")
        assert len(decisions) == 1
        assert decisions[0].decision == "skip"
        assert "Trivial commit" in decisions[0].reasoning
        assert decisions[0].commit_summary == "Fix whitespace in README"

    def test_creates_evaluation_cycle(self, temp_db):
        """Trivial skip still creates an evaluation cycle record."""
        from social_hook.db import operations as ops
        from social_hook.trigger import _run_trivial_skip

        project = Project(id="proj-trivial-2", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        commit = CommitInfo(hash="bbb222", message="fix typo", diff="")
        ctx = self._make_ctx(temp_db, project, commit)
        _run_trivial_skip(
            ctx=ctx,
            analyzer_result=self._make_trivial_result(),
            commit_hash="bbb222",
        )

        cycles = ops.get_recent_cycles(temp_db, "proj-trivial-2")
        assert len(cycles) == 1
        assert cycles[0].trigger_type == "commit"
        assert cycles[0].trigger_ref == "bbb222"

    def test_stores_analysis_json_on_cycle(self, temp_db):
        """Trivial skip stores the analysis JSON on the cycle for caching."""
        from social_hook.db import operations as ops
        from social_hook.trigger import _run_trivial_skip

        project = Project(id="proj-trivial-3", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        commit = CommitInfo(hash="ccc333", message="fix typo", diff="")
        ctx = self._make_ctx(temp_db, project, commit)
        _run_trivial_skip(
            ctx=ctx,
            analyzer_result=self._make_trivial_result(),
            commit_hash="ccc333",
        )

        cycle = ops.get_latest_cycle_with_analysis(temp_db, "proj-trivial-3")
        assert cycle is not None
        assert cycle.commit_analysis_json is not None
        assert "trivial" in cycle.commit_analysis_json

    def test_preserves_episode_tags(self, temp_db):
        """Trivial skip preserves the episode tags from the analyzer."""
        from social_hook.db import operations as ops
        from social_hook.trigger import _run_trivial_skip

        project = Project(id="proj-trivial-4", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        commit = CommitInfo(hash="ddd444", message="fix formatting", diff="")
        ctx = self._make_ctx(temp_db, project, commit)
        _run_trivial_skip(
            ctx=ctx,
            analyzer_result=self._make_trivial_result(),
            commit_hash="ddd444",
        )

        decisions = ops.get_recent_decisions(temp_db, "proj-trivial-4")
        assert decisions[0].episode_tags == ["docs", "formatting"]


# =============================================================================
# Evaluator backward compatibility
# =============================================================================


class TestEvaluatorBackwardCompat:
    """Evaluator.evaluate() works with and without analysis parameter."""

    def test_evaluate_without_analysis(self):
        """Backward compat: evaluator works without analysis parameter."""
        from social_hook.llm.evaluator import Evaluator

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.usage = MagicMock()
        mock_response.tool_calls = [
            MagicMock(
                name="log_evaluation",
                input={
                    "commit_analysis": {
                        "summary": "Added feature",
                        "episode_tags": ["feature"],
                    },
                    "targets": {
                        "default": {
                            "action": "draft",
                            "reason": "Worth posting",
                        },
                    },
                },
            )
        ]
        mock_client.complete.return_value = mock_response

        evaluator = Evaluator(mock_client)

        context = SimpleNamespace(
            project=SimpleNamespace(id="p1", summary="", repo_path="", prompt_docs=None),
            social_context="",
            lifecycle=None,
            narrative_debt=0,
            platform_introduced=None,
            all_introduced=True,
            active_arcs=[],
            arc_posts={},
            pending_drafts=[],
            held_decisions=[],
            recent_decisions=[],
            recent_posts=[],
            project_summary="",
            file_summaries=[],
            milestone_summaries=[],
            session_narratives=[],
            memories=[],
            context_notes=[],
        )

        db = MagicMock()
        db.get_summary_freshness = MagicMock(return_value=None)
        commit = CommitInfo(hash="abc123", message="test commit", diff="some diff")

        # Should work without analysis parameter
        with patch("social_hook.llm.evaluator.extract_tool_call") as mock_extract:
            mock_extract.return_value = {
                "commit_analysis": {
                    "summary": "Added feature",
                    "episode_tags": ["feature"],
                },
                "targets": {
                    "default": {"action": "draft", "reason": "Worth posting"},
                },
            }
            result = evaluator.evaluate(commit, context, db)
            assert result.strategies["default"].action == TargetAction.draft

    def test_evaluate_with_analysis(self):
        """Evaluator accepts analysis parameter and passes it to prompt assembly."""
        from social_hook.llm.evaluator import Evaluator

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.usage = MagicMock()
        mock_client.complete.return_value = mock_response

        evaluator = Evaluator(mock_client)

        context = SimpleNamespace(
            project=SimpleNamespace(id="p1", summary="", repo_path="", prompt_docs=None),
            social_context="",
            lifecycle=None,
            narrative_debt=0,
            platform_introduced=None,
            all_introduced=True,
            active_arcs=[],
            arc_posts={},
            pending_drafts=[],
            held_decisions=[],
            recent_decisions=[],
            recent_posts=[],
            project_summary="",
            file_summaries=[],
            milestone_summaries=[],
            session_narratives=[],
            memories=[],
            context_notes=[],
        )

        db = MagicMock()
        db.get_summary_freshness = MagicMock(return_value=None)
        commit = CommitInfo(hash="abc123", message="test commit", diff="some diff")

        analysis = CommitAnalysisResult(
            commit_analysis=CommitAnalysis(
                summary="Added auth feature",
                classification=CommitClassification.notable,
                episode_tags=["feature", "auth"],
            ),
            brief_update=BriefUpdateInstructions(),
        )

        with patch("social_hook.llm.evaluator.extract_tool_call") as mock_extract:
            mock_extract.return_value = {
                "commit_analysis": {
                    "summary": "Added auth feature",
                    "episode_tags": ["feature", "auth"],
                },
                "targets": {
                    "default": {"action": "draft", "reason": "Notable feature"},
                },
            }
            result = evaluator.evaluate(commit, context, db, analysis=analysis)
            assert result.strategies["default"].action == TargetAction.draft

            # Verify the prompt included the analysis section
            call_args = mock_client.complete.call_args
            system_prompt = call_args.kwargs.get("system", "")
            assert "Pre-Computed Commit Analysis" in system_prompt
            assert "notable" in system_prompt
            assert "Added auth feature" in system_prompt


# =============================================================================
# Prompt assembly with analysis
# =============================================================================


class TestAssembleEvaluatorPromptWithAnalysis:
    """Test that assemble_evaluator_prompt includes analysis section."""

    def _make_context(self):
        return SimpleNamespace(
            project=SimpleNamespace(id="p1", summary="", repo_path="", prompt_docs=None),
            social_context="",
            lifecycle=None,
            narrative_debt=0,
            platform_introduced=None,
            all_introduced=True,
            active_arcs=[],
            arc_posts={},
            pending_drafts=[],
            held_decisions=[],
            recent_decisions=[],
            recent_posts=[],
            project_summary="",
            file_summaries=[],
            milestone_summaries=[],
            session_narratives=[],
            memories=[],
            context_notes=[],
        )

    def test_without_analysis(self):
        """Prompt assembly works without analysis (no pre-computed section)."""
        from social_hook.llm.prompts import assemble_evaluator_prompt

        commit = CommitInfo(hash="abc123", message="test", diff="diff here")
        result = assemble_evaluator_prompt(
            prompt="# Evaluator",
            project_context=self._make_context(),
            commit=commit,
        )
        assert "Pre-Computed Commit Analysis" not in result
        assert "diff here" in result

    def test_with_analysis(self):
        """Prompt includes pre-computed analysis section when provided."""
        from social_hook.llm.prompts import assemble_evaluator_prompt

        analysis = CommitAnalysisResult(
            commit_analysis=CommitAnalysis(
                summary="Implemented OAuth 2.0 flow",
                classification=CommitClassification.significant,
                episode_tags=["security", "auth"],
                technical_detail="Added PKCE flow for X platform",
            ),
            brief_update=BriefUpdateInstructions(),
        )

        commit = CommitInfo(hash="abc123", message="feat: oauth2", diff="diff here")
        result = assemble_evaluator_prompt(
            prompt="# Evaluator",
            project_context=self._make_context(),
            commit=commit,
            analysis=analysis,
        )
        assert "Pre-Computed Commit Analysis" in result
        assert "significant" in result
        assert "security, auth" in result
        assert "Implemented OAuth 2.0 flow" in result
        assert "Added PKCE flow for X platform" in result

    def test_with_analysis_reduces_diff_budget(self):
        """When analysis is provided, diff is truncated more aggressively."""
        from social_hook.llm.prompts import assemble_evaluator_prompt

        analysis = CommitAnalysisResult(
            commit_analysis=CommitAnalysis(
                summary="Large change",
                classification=CommitClassification.notable,
                episode_tags=["feature"],
            ),
            brief_update=BriefUpdateInstructions(),
        )

        # Create a large diff
        large_diff = "x" * 100000
        commit = CommitInfo(hash="abc123", message="test", diff=large_diff)
        result = assemble_evaluator_prompt(
            prompt="# Evaluator",
            project_context=self._make_context(),
            commit=commit,
            analysis=analysis,
        )
        assert "see Pre-Computed Commit Analysis above" in result

    def test_analysis_without_classification(self):
        """Analysis with no classification still renders without error."""
        from social_hook.llm.prompts import assemble_evaluator_prompt

        analysis = CommitAnalysisResult(
            commit_analysis=CommitAnalysis(
                summary="Some commit",
                episode_tags=["misc"],
            ),
            brief_update=BriefUpdateInstructions(),
        )

        commit = CommitInfo(hash="abc123", message="test", diff="diff")
        result = assemble_evaluator_prompt(
            prompt="# Evaluator",
            project_context=self._make_context(),
            commit=commit,
            analysis=analysis,
        )
        assert "Pre-Computed Commit Analysis" in result
        assert "Some commit" in result
        # No classification line rendered
        assert "Classification" not in result or "None" not in result
