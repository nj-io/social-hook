"""Tests for the commit analyzer (Phase 5a)."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from social_hook.llm.schemas import (
    BriefUpdateInstructions,
    CommitAnalysis,
    CommitAnalysisResult,
    CommitClassification,
)
from social_hook.models.content import EvaluationCycle
from social_hook.models.core import CommitInfo, Project

# =============================================================================
# CommitClassification enum
# =============================================================================


class TestCommitClassification:
    """Verify CommitClassification enum values."""

    def test_enum_values(self):
        assert CommitClassification.trivial.value == "trivial"
        assert CommitClassification.routine.value == "routine"
        assert CommitClassification.notable.value == "notable"
        assert CommitClassification.significant.value == "significant"

    def test_all_values(self):
        values = [e.value for e in CommitClassification]
        assert values == ["trivial", "routine", "notable", "significant"]

    def test_string_enum(self):
        assert isinstance(CommitClassification.trivial, str)
        assert CommitClassification("routine") == CommitClassification.routine


# =============================================================================
# CommitAnalysisResult schema
# =============================================================================


class TestCommitAnalysisResult:
    """Test CommitAnalysisResult validation and tool schema."""

    def test_valid_result(self):
        result = CommitAnalysisResult(
            commit_analysis=CommitAnalysis(
                summary="Added auth module",
                episode_tags=["feature", "auth"],
                classification=CommitClassification.notable,
            ),
            brief_update=BriefUpdateInstructions(
                sections_to_update={"Features": "Added OAuth 2.0 auth module"},
                new_facts=["Project uses OAuth 2.0 for authentication"],
            ),
        )
        assert result.commit_analysis.classification == CommitClassification.notable
        assert len(result.brief_update.new_facts) == 1

    def test_validate_from_dict(self):
        data = {
            "commit_analysis": {
                "summary": "Fixed typo in readme",
                "episode_tags": ["docs"],
                "classification": "trivial",
            },
            "brief_update": {
                "sections_to_update": {},
                "new_facts": [],
            },
        }
        result = CommitAnalysisResult.validate(data)
        assert result.commit_analysis.classification == CommitClassification.trivial

    def test_validate_invalid_classification(self):
        from social_hook.errors import MalformedResponseError

        data = {
            "commit_analysis": {
                "summary": "test",
                "episode_tags": [],
                "classification": "super_important",
            },
            "brief_update": {"sections_to_update": {}, "new_facts": []},
        }
        with pytest.raises(MalformedResponseError):
            CommitAnalysisResult.validate(data)

    def test_tool_schema_structure(self):
        schema = CommitAnalysisResult.to_tool_schema()
        assert schema["name"] == "log_commit_analysis"
        props = schema["input_schema"]["properties"]
        assert "commit_analysis" in props
        assert "brief_update" in props
        # Classification enum values in schema
        cls_enum = props["commit_analysis"]["properties"]["classification"]["enum"]
        assert cls_enum == ["trivial", "routine", "notable", "significant"]

    def test_commit_analysis_classification_optional(self):
        """CommitAnalysis.classification is optional for backward compat with evaluator."""
        analysis = CommitAnalysis(summary="test", episode_tags=["feat"])
        assert analysis.classification is None


# =============================================================================
# CommitAnalyzer.analyze() with mock LLM
# =============================================================================


class TestCommitAnalyzer:
    """Test CommitAnalyzer with mocked LLM client."""

    def _make_mock_response(self, tool_data):
        """Create a mock LLM response with a tool call."""
        from social_hook.llm.base import NormalizedResponse, NormalizedToolCall, NormalizedUsage

        return NormalizedResponse(
            content=[
                NormalizedToolCall(
                    name="log_commit_analysis",
                    input=tool_data,
                )
            ],
            usage=NormalizedUsage(
                input_tokens=100,
                output_tokens=50,
            ),
            raw={},
        )

    def test_analyze_returns_result(self):
        from social_hook.llm.analyzer import CommitAnalyzer

        tool_data = {
            "commit_analysis": {
                "summary": "Refactored auth middleware to use JWT",
                "episode_tags": ["refactor", "auth", "security"],
                "classification": "notable",
            },
            "brief_update": {
                "sections_to_update": {"Architecture": "Auth now uses JWT tokens"},
                "new_facts": ["Switched from session-based to JWT authentication"],
            },
        }

        mock_client = MagicMock()
        mock_client.complete.return_value = self._make_mock_response(tool_data)

        analyzer = CommitAnalyzer(mock_client)
        commit = CommitInfo(
            hash="abc12345", message="refactor: auth middleware", diff="- old\n+ new"
        )
        project = Project(id="proj-1", name="test", repo_path="/tmp", summary="Test project")
        context = SimpleNamespace(project=project)

        mock_db = MagicMock()
        result = analyzer.analyze(commit, context, mock_db)

        assert isinstance(result, CommitAnalysisResult)
        assert result.commit_analysis.classification == CommitClassification.notable
        assert "auth" in result.commit_analysis.episode_tags
        assert result.brief_update.sections_to_update["Architecture"] == "Auth now uses JWT tokens"

    def test_analyze_calls_llm_with_correct_tool(self):
        from social_hook.llm.analyzer import CommitAnalyzer

        tool_data = {
            "commit_analysis": {
                "summary": "test",
                "episode_tags": [],
                "classification": "trivial",
            },
            "brief_update": {"sections_to_update": {}, "new_facts": []},
        }

        mock_client = MagicMock()
        mock_client.complete.return_value = self._make_mock_response(tool_data)

        analyzer = CommitAnalyzer(mock_client)
        commit = CommitInfo(hash="def456", message="fix typo", diff="")
        context = SimpleNamespace(project=Project(id="p1", name="t", repo_path="/tmp"))
        mock_db = MagicMock()

        analyzer.analyze(commit, context, mock_db)

        # Verify the tool schema was passed
        call_args = mock_client.complete.call_args
        tools = call_args.kwargs.get("tools") or call_args[1].get("tools")
        assert len(tools) == 1
        assert tools[0]["name"] == "log_commit_analysis"

    def test_analyze_logs_usage(self):
        from social_hook.llm.analyzer import CommitAnalyzer

        tool_data = {
            "commit_analysis": {
                "summary": "test",
                "episode_tags": [],
                "classification": "routine",
            },
            "brief_update": {"sections_to_update": {}, "new_facts": []},
        }

        mock_client = MagicMock()
        mock_client.full_id = "test/model"
        mock_client.complete.return_value = self._make_mock_response(tool_data)

        analyzer = CommitAnalyzer(mock_client)
        commit = CommitInfo(hash="ghi789", message="small fix", diff="")
        context = SimpleNamespace(project=Project(id="p1", name="t", repo_path="/tmp"))
        mock_db = MagicMock()

        with patch("social_hook.llm.analyzer.log_usage") as mock_log:
            analyzer.analyze(commit, context, mock_db)
            mock_log.assert_called_once()
            args = mock_log.call_args[0]
            assert args[1] == "analyze"
            assert args[2] == "test/model"

    def test_analyze_truncates_long_diff(self):
        from social_hook.llm.analyzer import CommitAnalyzer

        tool_data = {
            "commit_analysis": {
                "summary": "test",
                "episode_tags": [],
                "classification": "routine",
            },
            "brief_update": {"sections_to_update": {}, "new_facts": []},
        }

        mock_client = MagicMock()
        mock_client.complete.return_value = self._make_mock_response(tool_data)

        analyzer = CommitAnalyzer(mock_client)
        long_diff = "x" * 10000
        commit = CommitInfo(hash="jkl012", message="big change", diff=long_diff)
        context = SimpleNamespace(project=Project(id="p1", name="t", repo_path="/tmp"))
        mock_db = MagicMock()

        analyzer.analyze(commit, context, mock_db)

        call_args = mock_client.complete.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        user_msg = messages[0]["content"]
        assert "diff truncated" in user_msg


# =============================================================================
# DB operations for analysis_commit_count
# =============================================================================


class TestAnalysisCommitCountOps:
    """Test increment/reset/get operations for analysis_commit_count."""

    def test_increment_returns_new_count(self, temp_db):
        from social_hook.db import operations as ops

        project = Project(id="proj-count-1", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        count = ops.increment_analysis_commit_count(temp_db, "proj-count-1")
        assert count == 1

        count = ops.increment_analysis_commit_count(temp_db, "proj-count-1")
        assert count == 2

    def test_reset_sets_to_zero(self, temp_db):
        from social_hook.db import operations as ops

        project = Project(id="proj-count-2", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        ops.increment_analysis_commit_count(temp_db, "proj-count-2")
        ops.increment_analysis_commit_count(temp_db, "proj-count-2")
        ops.reset_analysis_commit_count(temp_db, "proj-count-2")

        count = ops.get_analysis_commit_count(temp_db, "proj-count-2")
        assert count == 0

    def test_get_returns_zero_for_new_project(self, temp_db):
        from social_hook.db import operations as ops

        project = Project(id="proj-count-3", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        count = ops.get_analysis_commit_count(temp_db, "proj-count-3")
        assert count == 0


# =============================================================================
# Cycle analysis JSON caching
# =============================================================================


class TestCycleAnalysisCaching:
    """Test storing and retrieving analysis JSON on evaluation cycles."""

    def test_store_and_retrieve_analysis(self, temp_db):
        from social_hook.db import operations as ops

        project = Project(id="proj-cache-1", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        cycle = EvaluationCycle(
            id="cycle-1",
            project_id="proj-cache-1",
            trigger_type="commit",
            trigger_ref="abc123",
        )
        ops.insert_evaluation_cycle(temp_db, cycle)

        analysis_data = {
            "commit_analysis": {
                "summary": "test",
                "episode_tags": ["feat"],
                "classification": "notable",
            },
            "brief_update": {"sections_to_update": {}, "new_facts": []},
        }
        analysis_json = json.dumps(analysis_data)
        ops.update_cycle_analysis_json(temp_db, "cycle-1", analysis_json)

        cached = ops.get_latest_cycle_with_analysis(temp_db, "proj-cache-1")
        assert cached is not None
        assert cached.id == "cycle-1"
        assert cached.commit_analysis_json == analysis_json

        # Validate round-trip
        loaded = json.loads(cached.commit_analysis_json)
        result = CommitAnalysisResult.model_validate(loaded)
        assert result.commit_analysis.classification == CommitClassification.notable

    def test_no_cached_analysis(self, temp_db):
        from social_hook.db import operations as ops

        project = Project(id="proj-cache-2", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        # Cycle without analysis JSON
        cycle = EvaluationCycle(
            id="cycle-2",
            project_id="proj-cache-2",
            trigger_type="commit",
        )
        ops.insert_evaluation_cycle(temp_db, cycle)

        cached = ops.get_latest_cycle_with_analysis(temp_db, "proj-cache-2")
        assert cached is None


# =============================================================================
# Interval gating logic (_run_commit_analyzer)
# =============================================================================


class TestCommitAnalyzerIntervalGating:
    """Test commit_analysis_interval gating: count < interval uses cache, >= runs fresh."""

    def _make_mock_analyzer_result(self):
        return CommitAnalysisResult(
            commit_analysis=CommitAnalysis(
                summary="Test commit",
                episode_tags=["test"],
                classification=CommitClassification.routine,
            ),
            brief_update=BriefUpdateInstructions(
                sections_to_update={},
                new_facts=[],
            ),
        )

    def _make_ctx(self, temp_db, project, commit, project_config=None):
        from social_hook.llm.dry_run import DryRunContext
        from social_hook.trigger import TriggerContext

        return TriggerContext(
            config=MagicMock(),
            conn=temp_db,
            db=DryRunContext(temp_db, dry_run=False),
            project=project,
            commit=commit,
            project_config=project_config,
            current_branch="main",
            dry_run=False,
            verbose=False,
            show_prompt=False,
        )

    def test_first_commit_defers_like_any_other(self, temp_db):
        """First commit (no cache) still defers when interval > 1."""
        from social_hook.db import operations as ops
        from social_hook.trigger import _run_commit_analyzer

        project = Project(id="proj-gate-1", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        commit = CommitInfo(hash="abc123", message="first commit", diff="")
        context = SimpleNamespace(project=project)

        mock_client = MagicMock()

        # Set interval to 3 — first commit should defer, not evaluate
        project_config = SimpleNamespace(context=SimpleNamespace(commit_analysis_interval=3))
        ctx = self._make_ctx(temp_db, project, commit, project_config)

        outcome = _run_commit_analyzer(
            ctx=ctx,
            context=context,
            evaluator_client=mock_client,
        )

        assert outcome.result is None
        assert outcome.should_evaluate is False
        # Counter incremented but not reset
        assert ops.get_analysis_commit_count(temp_db, "proj-gate-1") == 1

    def test_interval_not_met_uses_cache(self, temp_db):
        """When count < interval and cache exists, return cached result."""
        from social_hook.db import operations as ops
        from social_hook.trigger import _run_commit_analyzer

        project = Project(id="proj-gate-2", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        # Pre-populate a cached cycle
        cycle = EvaluationCycle(
            id="cycle-cached",
            project_id="proj-gate-2",
            trigger_type="commit",
            trigger_ref="prev123",
        )
        ops.insert_evaluation_cycle(temp_db, cycle)
        cached_data = self._make_mock_analyzer_result().model_dump()
        ops.update_cycle_analysis_json(
            temp_db, "cycle-cached", json.dumps(cached_data, default=str)
        )

        commit = CommitInfo(hash="def456", message="second commit", diff="")
        context = SimpleNamespace(project=project)
        mock_client = MagicMock()

        project_config = SimpleNamespace(context=SimpleNamespace(commit_analysis_interval=3))
        ctx = self._make_ctx(temp_db, project, commit, project_config)

        with patch("social_hook.llm.analyzer.CommitAnalyzer") as MockAnalyzer:
            outcome = _run_commit_analyzer(
                ctx=ctx,
                context=context,
                evaluator_client=mock_client,
            )
            # Analyzer should NOT be called — using cache
            MockAnalyzer.return_value.analyze.assert_not_called()

        assert outcome.result is not None
        assert outcome.should_evaluate is False
        assert outcome.result.commit_analysis.classification == CommitClassification.routine

    def test_interval_met_signals_evaluate_no_llm(self, temp_db):
        """When count >= interval, signal should_evaluate=True but do NOT run LLM."""
        from social_hook.db import operations as ops
        from social_hook.trigger import _run_commit_analyzer

        project = Project(id="proj-gate-3", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        # Set count to 2 so next increment hits interval of 3
        ops.increment_analysis_commit_count(temp_db, "proj-gate-3")
        ops.increment_analysis_commit_count(temp_db, "proj-gate-3")

        commit = CommitInfo(hash="ghi789", message="third commit", diff="")
        context = SimpleNamespace(project=project)
        mock_client = MagicMock()

        project_config = SimpleNamespace(context=SimpleNamespace(commit_analysis_interval=3))
        ctx = self._make_ctx(temp_db, project, commit, project_config)

        outcome = _run_commit_analyzer(
            ctx=ctx,
            context=context,
            evaluator_client=mock_client,
        )

        # Pure gating — no LLM called, result is None
        assert outcome.result is None
        assert outcome.should_evaluate is True
        # Counter reset to 0
        assert ops.get_analysis_commit_count(temp_db, "proj-gate-3") == 0

    def test_analyzer_failure_returns_none(self, temp_db):
        """Analyzer failure is non-fatal, returns None."""
        from social_hook.db import operations as ops
        from social_hook.trigger import _run_commit_analyzer

        project = Project(id="proj-gate-4", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        commit = CommitInfo(hash="jkl012", message="test", diff="")
        context = SimpleNamespace(project=project)
        ctx = self._make_ctx(temp_db, project, commit, project_config=None)

        with patch("social_hook.llm.analyzer.CommitAnalyzer") as MockAnalyzer:
            MockAnalyzer.return_value.analyze.side_effect = Exception("LLM error")
            outcome = _run_commit_analyzer(
                ctx=ctx,
                context=context,
                evaluator_client=MagicMock(),
            )

        assert outcome.result is None
        assert outcome.should_evaluate is True
