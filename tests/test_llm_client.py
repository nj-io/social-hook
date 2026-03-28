"""Tests for LLM client and DryRunContext (T11)."""

from unittest.mock import MagicMock, patch

import pytest

from social_hook.db import operations as ops
from social_hook.errors import AuthError
from social_hook.llm.client import ClaudeClient, _calculate_cost_cents
from social_hook.llm.dry_run import DryRunContext
from social_hook.models import (
    Decision,
    Draft,
    Project,
    UsageLog,
)

# =============================================================================
# T11: Cost Calculation Tests
# =============================================================================


class TestCostCalculation:
    """T11: Token cost estimation."""

    def test_opus_cost(self):
        cost = _calculate_cost_cents(
            "claude-opus-4-5",
            input_tokens=1000,
            output_tokens=500,
        )
        # 1000/1M * 1500 cents + 500/1M * 7500 cents = 1.5 + 3.75 = 5.25
        assert abs(cost - 5.25) < 0.01

    def test_haiku_cost(self):
        cost = _calculate_cost_cents(
            "claude-haiku-4-5",
            input_tokens=10000,
            output_tokens=1000,
        )
        # 10000/1M * 80 + 1000/1M * 400 = 0.8 + 0.4 = 1.2
        assert abs(cost - 1.2) < 0.01

    def test_with_cache_tokens(self):
        cost = _calculate_cost_cents(
            "claude-opus-4-5",
            input_tokens=1000,
            output_tokens=500,
            cache_read_tokens=5000,
            cache_creation_tokens=2000,
        )
        # input: 1.5, output: 3.75, cache_read: 5000/1M*150=0.75, cache_write: 2000/1M*1875=3.75
        expected = 1.5 + 3.75 + 0.75 + 3.75
        assert abs(cost - expected) < 0.01

    def test_unknown_model_returns_zero(self):
        cost = _calculate_cost_cents("unknown-model", 1000, 500)
        assert cost == 0.0

    def test_sonnet_cost(self):
        cost = _calculate_cost_cents(
            "claude-sonnet-4-5",
            input_tokens=10000,
            output_tokens=1000,
        )
        # 10000/1M * 300 + 1000/1M * 1500 = 3.0 + 1.5 = 4.5
        assert abs(cost - 4.5) < 0.01

    def test_zero_tokens(self):
        cost = _calculate_cost_cents("claude-opus-4-5", 0, 0)
        assert cost == 0.0


# =============================================================================
# T11: ClaudeClient Tests (mocked)
# =============================================================================


class TestClaudeClient:
    """T11: ClaudeClient with mocked Anthropic SDK."""

    def _make_mock_response(self, input_tokens=100, output_tokens=50):
        """Create a mock API response."""
        response = MagicMock()
        response.usage.input_tokens = input_tokens
        response.usage.output_tokens = output_tokens
        response.usage.cache_read_input_tokens = 0
        response.usage.cache_creation_input_tokens = 0
        response.content = [
            MagicMock(
                type="tool_use",
                name="log_decision",
                input={"decision": "post_worthy", "reasoning": "test"},
            )
        ]
        return response

    @patch("social_hook.llm.client.anthropic.Anthropic")
    def test_complete_basic(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = self._make_mock_response()

        client = ClaudeClient(api_key="sk-test", model="claude-opus-4-5")
        response = client.complete(
            messages=[{"role": "user", "content": "test"}],
            tools=[{"name": "test"}],
        )

        mock_client.messages.create.assert_called_once()
        assert response is not None

        # Verify correct kwargs passed to SDK
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-opus-4-5"
        assert call_kwargs["max_tokens"] == 4096
        assert call_kwargs["messages"] == [{"role": "user", "content": "test"}]

    @patch("social_hook.llm.client.anthropic.Anthropic")
    def test_complete_with_system(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = self._make_mock_response()

        client = ClaudeClient(api_key="sk-test", model="claude-opus-4-5")
        client.complete(
            messages=[{"role": "user", "content": "test"}],
            tools=[{"name": "test"}],
            system="You are an evaluator.",
        )

        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["system"] == "You are an evaluator."

    @patch("social_hook.llm.client.anthropic.Anthropic")
    def test_auth_error_wrapped(self, mock_anthropic_cls):
        import anthropic as anthropic_module

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.side_effect = anthropic_module.AuthenticationError(
            message="Invalid API key",
            response=MagicMock(status_code=401),
            body={"error": {"message": "Invalid API key"}},
        )

        client = ClaudeClient(api_key="sk-bad", model="claude-opus-4-5")
        with pytest.raises(AuthError):
            client.complete(
                messages=[{"role": "user", "content": "test"}],
                tools=[{"name": "test"}],
            )

    @patch("social_hook.llm.client.anthropic.Anthropic")
    def test_cost_cents_in_usage(self, mock_anthropic_cls):
        """ClaudeClient populates cost_cents on NormalizedUsage for known models."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = self._make_mock_response(
            input_tokens=1000, output_tokens=500
        )

        client = ClaudeClient(api_key="sk-test", model="claude-opus-4-5")
        response = client.complete(
            messages=[{"role": "user", "content": "test"}],
            tools=[{"name": "test"}],
        )

        assert response.usage.cost_cents > 0


# =============================================================================
# T11: DryRunContext Tests
# =============================================================================


class TestDryRunContext:
    """T11: DryRunContext delegates reads and skips writes."""

    def _setup_project(self, conn):
        """Insert a test project."""
        project = Project(id="proj_test1", name="test", repo_path="/tmp/test")
        ops.insert_project(conn, project)
        return project

    # --- Read operations pass through ---

    def test_get_project_passthrough(self, temp_db):
        self._setup_project(temp_db)
        db = DryRunContext(temp_db, dry_run=True)
        project = db.get_project("proj_test1")
        assert project is not None
        assert project.name == "test"

    def test_get_all_projects_passthrough(self, temp_db):
        self._setup_project(temp_db)
        db = DryRunContext(temp_db, dry_run=True)
        projects = db.get_all_projects()
        assert len(projects) == 1

    def test_get_recent_decisions_passthrough(self, temp_db):
        self._setup_project(temp_db)
        db = DryRunContext(temp_db, dry_run=True)
        decisions = db.get_recent_decisions("proj_test1")
        assert decisions == []

    def test_get_pending_drafts_passthrough(self, temp_db):
        self._setup_project(temp_db)
        db = DryRunContext(temp_db, dry_run=True)
        drafts = db.get_pending_drafts("proj_test1")
        assert drafts == []

    def test_get_lifecycle_passthrough(self, temp_db):
        self._setup_project(temp_db)
        db = DryRunContext(temp_db, dry_run=True)
        lifecycle = db.get_lifecycle("proj_test1")
        assert lifecycle is None

    def test_get_active_arcs_passthrough(self, temp_db):
        self._setup_project(temp_db)
        db = DryRunContext(temp_db, dry_run=True)
        arcs = db.get_active_arcs("proj_test1")
        assert arcs == []

    def test_get_narrative_debt_passthrough(self, temp_db):
        self._setup_project(temp_db)
        db = DryRunContext(temp_db, dry_run=True)
        debt = db.get_narrative_debt("proj_test1")
        assert debt is None

    def test_get_recent_posts_passthrough(self, temp_db):
        self._setup_project(temp_db)
        db = DryRunContext(temp_db, dry_run=True)
        posts = db.get_recent_posts("proj_test1")
        assert posts == []

    def test_get_recent_posts_for_context_passthrough(self, temp_db):
        self._setup_project(temp_db)
        db = DryRunContext(temp_db, dry_run=True)
        posts = db.get_recent_posts_for_context("proj_test1")
        assert posts == []

    def test_get_project_summary_passthrough(self, temp_db):
        self._setup_project(temp_db)
        db = DryRunContext(temp_db, dry_run=True)
        summary = db.get_project_summary("proj_test1")
        assert summary is None

    def test_get_summary_freshness_passthrough(self, temp_db):
        self._setup_project(temp_db)
        db = DryRunContext(temp_db, dry_run=True)
        freshness = db.get_summary_freshness("proj_test1")
        assert "commits_since_summary" in freshness

    def test_get_usage_summary_passthrough(self, temp_db):
        db = DryRunContext(temp_db, dry_run=True)
        summary = db.get_usage_summary()
        assert summary == []

    def test_get_milestone_summaries_passthrough(self, temp_db):
        self._setup_project(temp_db)
        db = DryRunContext(temp_db, dry_run=True)
        summaries = db.get_milestone_summaries("proj_test1")
        assert summaries == []

    def test_get_arc_passthrough(self, temp_db):
        db = DryRunContext(temp_db, dry_run=True)
        arc = db.get_arc("nonexistent")
        assert arc is None

    def test_get_audience_introduced_passthrough(self, temp_db):
        self._setup_project(temp_db)
        db = DryRunContext(temp_db, dry_run=True)
        result = db.get_audience_introduced("proj_test1")
        assert result is False

    # --- Write operations skipped in dry-run ---

    def test_insert_decision_skipped(self, temp_db):
        self._setup_project(temp_db)
        db = DryRunContext(temp_db, dry_run=True)
        decision = Decision(
            id="dec_test1",
            project_id="proj_test1",
            commit_hash="abc123",
            decision="draft",
            reasoning="Test",
        )
        result = db.insert_decision(decision)
        assert result == "dec_test1"  # Returns ID
        # Verify not persisted
        assert db.get_recent_decisions("proj_test1") == []

    def test_insert_draft_skipped(self, temp_db):
        self._setup_project(temp_db)
        db = DryRunContext(temp_db, dry_run=True)
        # Need a decision first for FK — but in dry-run, reads only
        # Just verify the no-op behavior
        draft = Draft(
            id="draft_test1",
            project_id="proj_test1",
            decision_id="dec_test1",
            platform="x",
            content="Test",
        )
        result = db.insert_draft(draft)
        assert result == "draft_test1"

    def test_insert_usage_skipped(self, temp_db):
        db = DryRunContext(temp_db, dry_run=True)
        usage = UsageLog(
            id="usage_test1",
            operation_type="evaluate",
            model="claude-opus-4-5",
            input_tokens=100,
            output_tokens=50,
        )
        result = db.insert_usage(usage)
        assert result == "usage_test1"
        assert db.get_usage_summary() == []

    def test_update_draft_skipped(self, temp_db):
        db = DryRunContext(temp_db, dry_run=True)
        result = db.update_draft("draft_test1", status="approved")
        assert result is False

    def test_supersede_draft_skipped(self, temp_db):
        db = DryRunContext(temp_db, dry_run=True)
        result = db.supersede_draft("old_draft", "new_draft")
        assert result is False

    def test_update_lifecycle_skipped(self, temp_db):
        db = DryRunContext(temp_db, dry_run=True)
        result = db.update_lifecycle("proj_test1", phase="build")
        assert result is False

    def test_update_arc_skipped(self, temp_db):
        db = DryRunContext(temp_db, dry_run=True)
        result = db.update_arc("arc_test1", status="completed")
        assert result is False

    def test_increment_narrative_debt_skipped(self, temp_db):
        db = DryRunContext(temp_db, dry_run=True)
        result = db.increment_narrative_debt("proj_test1")
        assert result == 0

    def test_reset_narrative_debt_skipped(self, temp_db):
        db = DryRunContext(temp_db, dry_run=True)
        result = db.reset_narrative_debt("proj_test1")
        assert result is False

    def test_set_audience_introduced_skipped(self, temp_db):
        self._setup_project(temp_db)
        db = DryRunContext(temp_db, dry_run=True)
        result = db.set_audience_introduced("proj_test1", True)
        assert result is False
        # Verify not changed
        assert db.get_audience_introduced("proj_test1") is False

    def test_update_project_summary_skipped(self, temp_db):
        db = DryRunContext(temp_db, dry_run=True)
        result = db.update_project_summary("proj_test1", "New summary")
        assert result is False

    def test_insert_milestone_summary_skipped(self, temp_db):
        db = DryRunContext(temp_db, dry_run=True)
        result = db.insert_milestone_summary(
            {
                "id": "ms_test1",
                "project_id": "proj_test1",
                "milestone_type": "post",
                "summary": "Test",
                "items_covered": [],
                "token_count": 10,
                "period_start": "2026-01-01",
                "period_end": "2026-01-15",
            }
        )
        assert result == "ms_test1"

    # --- Write operations pass through when not dry-run ---

    def test_insert_decision_passthrough_live(self, temp_db):
        self._setup_project(temp_db)
        db = DryRunContext(temp_db, dry_run=False)
        decision = Decision(
            id="dec_test1",
            project_id="proj_test1",
            commit_hash="abc123",
            decision="draft",
            reasoning="Test",
        )
        result = db.insert_decision(decision)
        assert result == "dec_test1"
        # Verify persisted
        decisions = db.get_recent_decisions("proj_test1")
        assert len(decisions) == 1

    def test_nonexistent_operation_raises(self, temp_db):
        db = DryRunContext(temp_db, dry_run=True)
        with pytest.raises(AttributeError, match="not found in"):
            db.nonexistent_operation()
