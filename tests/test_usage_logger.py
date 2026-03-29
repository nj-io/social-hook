"""Tests for LLM usage logging helper."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from social_hook.db import operations as ops
from social_hook.llm._usage_logger import log_usage
from social_hook.llm.dry_run import DryRunContext
from social_hook.models.core import Project


def _make_usage(**kwargs):
    """Create a mock usage object."""
    defaults = {
        "input_tokens": 100,
        "output_tokens": 50,
        "cache_read_input_tokens": 10,
        "cache_creation_input_tokens": 5,
        "cost_cents": 0.0,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestLogUsage:
    def test_log_usage_with_db_and_operation_type(self):
        mock_db = MagicMock()
        mock_db.insert_usage = MagicMock()
        usage = _make_usage()

        log_usage(
            mock_db,
            "evaluate",
            "anthropic/claude-opus-4-5",
            usage,
            project_id="proj-123",
            commit_hash="abc123",
        )

        mock_db.insert_usage.assert_called_once()
        usage_log = mock_db.insert_usage.call_args[0][0]
        assert usage_log.model == "anthropic/claude-opus-4-5"
        assert usage_log.input_tokens == 100
        assert usage_log.output_tokens == 50
        assert usage_log.project_id == "proj-123"
        assert usage_log.commit_hash == "abc123"

    def test_log_usage_no_op_without_db(self):
        # Should not raise
        log_usage(None, "evaluate", "model/id", _make_usage())

    def test_log_usage_no_op_without_operation_type(self):
        mock_db = MagicMock()
        mock_db.insert_usage = MagicMock()

        log_usage(mock_db, "", "model/id", _make_usage())
        mock_db.insert_usage.assert_not_called()

    def test_log_usage_auto_extracts_cost_cents(self):
        mock_db = MagicMock()
        mock_db.insert_usage = MagicMock()
        usage = _make_usage(cost_cents=5.25)

        log_usage(mock_db, "evaluate", "model/id", usage)

        usage_log = mock_db.insert_usage.call_args[0][0]
        assert usage_log.cost_cents == 5.25

    def test_log_usage_explicit_cost_overrides(self):
        mock_db = MagicMock()
        mock_db.insert_usage = MagicMock()
        usage = _make_usage(cost_cents=5.25)

        log_usage(mock_db, "evaluate", "model/id", usage, cost_cents=10.0)

        usage_log = mock_db.insert_usage.call_args[0][0]
        assert usage_log.cost_cents == 10.0

    def test_log_usage_with_dry_run_context_suppressed(self, temp_db):
        """DryRunContext(dry_run=True) suppresses writes."""
        project = Project(id="proj_test1", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        db = DryRunContext(temp_db, dry_run=True)
        usage = _make_usage()

        log_usage(db, "evaluate", "anthropic/claude-opus-4-5", usage, project_id="proj_test1")

        summary = ops.get_usage_summary(temp_db)
        assert len(summary) == 0

    def test_log_usage_with_dry_run_context_live(self, temp_db):
        """DryRunContext(dry_run=False) persists writes."""
        project = Project(id="proj_test1", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        db = DryRunContext(temp_db, dry_run=False)
        usage = _make_usage()

        log_usage(db, "evaluate", "anthropic/claude-opus-4-5", usage, project_id="proj_test1")

        summary = ops.get_usage_summary(temp_db)
        assert len(summary) == 1
        assert summary[0]["model"] == "anthropic/claude-opus-4-5"

    def test_log_usage_with_sqlite_connection(self, temp_db):
        """Falls back to ops.insert_usage for raw sqlite3.Connection."""
        project = Project(id="proj_test1", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        usage = _make_usage()
        log_usage(temp_db, "evaluate", "anthropic/claude-opus-4-5", usage, project_id="proj_test1")

        summary = ops.get_usage_summary(temp_db)
        assert len(summary) == 1

    def test_trigger_source_defaults_to_auto(self):
        """Without trigger_source on db, usage log defaults to 'auto'."""
        mock_db = MagicMock()
        mock_db.insert_usage = MagicMock()
        # No trigger_source attr set
        del mock_db.trigger_source
        usage = _make_usage()

        log_usage(mock_db, "evaluate", "model/id", usage)

        usage_log = mock_db.insert_usage.call_args[0][0]
        assert usage_log.trigger_source == "auto"

    def test_trigger_source_manual_flows_through(self):
        """Manual trigger_source on db flows through to UsageLog."""
        mock_db = MagicMock()
        mock_db.insert_usage = MagicMock()
        mock_db.trigger_source = "manual"
        usage = _make_usage()

        log_usage(mock_db, "evaluate", "model/id", usage)

        usage_log = mock_db.insert_usage.call_args[0][0]
        assert usage_log.trigger_source == "manual"

    def test_trigger_source_commit_maps_to_auto(self):
        """Commit trigger_source maps to 'auto' in UsageLog."""
        mock_db = MagicMock()
        mock_db.insert_usage = MagicMock()
        mock_db.trigger_source = "commit"
        usage = _make_usage()

        log_usage(mock_db, "evaluate", "model/id", usage)

        usage_log = mock_db.insert_usage.call_args[0][0]
        assert usage_log.trigger_source == "auto"
