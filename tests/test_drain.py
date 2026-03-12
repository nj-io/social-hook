"""Tests for deferred eval drain (Chunk 4)."""

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

from social_hook.config.yaml import Config, RateLimitsConfig
from social_hook.db import operations as ops
from social_hook.db.connection import init_database
from social_hook.filesystem import generate_id
from social_hook.models import Decision, Project
from social_hook.scheduler import (
    _drain_batch,
    _drain_deferred_evaluations,
    _drain_individual,
)


@dataclass
class _GateResult:
    blocked: bool
    reason: str


def _make_config(batch_throttled=False):
    """Build a Config with rate limits."""
    return Config(
        rate_limits=RateLimitsConfig(
            max_evaluations_per_day=15,
            min_evaluation_gap_minutes=10,
            batch_throttled=batch_throttled,
        ),
        channels={},
    )


def _seed_project(conn, paused=False):
    """Insert a project and return it."""
    project = Project(
        id=generate_id("project"),
        name="drain-test",
        repo_path="/tmp/drain-test",
        paused=paused,
    )
    ops.insert_project(conn, project)
    return project


def _seed_deferred(conn, project_id, count=2):
    """Insert deferred_eval decisions and return them."""
    decisions = []
    for i in range(count):
        d = Decision(
            id=generate_id("decision"),
            project_id=project_id,
            commit_hash=f"deadbeef{i:04d}",
            decision="deferred_eval",
            reasoning="Rate limited",
            trigger_source="commit",
        )
        ops.insert_decision(conn, d)
        decisions.append(d)
    return decisions


class TestDrainDryRun:
    """Drain is skipped entirely in dry_run mode."""

    def test_drain_noop_in_dry_run(self, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        project = _seed_project(conn)
        _seed_deferred(conn, project.id, count=2)
        config = _make_config()

        _drain_deferred_evaluations(conn, config, dry_run=True)

        # Decisions should still exist
        remaining = ops.get_deferred_eval_decisions(conn, project.id)
        assert len(remaining) == 2
        conn.close()


class TestDrainSkipsPaused:
    """Drain skips paused projects."""

    @patch("social_hook.rate_limits.check_rate_limit")
    def test_paused_project_skipped(self, mock_gate, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        project = _seed_project(conn, paused=True)
        _seed_deferred(conn, project.id, count=2)
        config = _make_config()

        _drain_deferred_evaluations(conn, config, dry_run=False)

        # Rate limit should never be checked for paused projects
        mock_gate.assert_not_called()

        # Decisions still exist
        remaining = ops.get_deferred_eval_decisions(conn, project.id)
        assert len(remaining) == 2
        conn.close()


class TestDrainIndividual:
    """Tests for individual drain mode (batch_throttled=False)."""

    @patch("social_hook.scheduler.run_trigger")
    @patch("social_hook.scheduler.check_rate_limit")
    def test_drains_all_deferred(self, mock_gate, mock_trigger, temp_dir):
        """All deferred decisions are drained when rate limit allows."""
        mock_gate.return_value = _GateResult(blocked=False, reason="")
        mock_trigger.return_value = 0

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        project = _seed_project(conn)
        deferred = _seed_deferred(conn, project.id, count=2)
        config = _make_config()

        _drain_individual(conn, config, project, deferred)

        # Both decisions should be deleted
        remaining = ops.get_deferred_eval_decisions(conn, project.id)
        assert len(remaining) == 0

        # run_trigger called twice with trigger_source="drain"
        assert mock_trigger.call_count == 2
        for call in mock_trigger.call_args_list:
            assert call.kwargs.get("trigger_source") == "drain"
        conn.close()

    @patch("social_hook.scheduler.run_trigger")
    @patch("social_hook.scheduler.check_rate_limit")
    def test_stops_when_rate_limited(self, mock_gate, mock_trigger, temp_dir):
        """Drain stops after rate limit blocks."""
        # Allow first, block second
        mock_gate.side_effect = [
            _GateResult(blocked=False, reason=""),
            _GateResult(blocked=True, reason="Daily limit reached"),
        ]
        mock_trigger.return_value = 0

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        project = _seed_project(conn)
        deferred = _seed_deferred(conn, project.id, count=3)
        config = _make_config()

        _drain_individual(conn, config, project, deferred)

        # Only 1 processed, 2 remain
        remaining = ops.get_deferred_eval_decisions(conn, project.id)
        assert len(remaining) == 2
        assert mock_trigger.call_count == 1
        conn.close()

    @patch("social_hook.scheduler.run_trigger")
    @patch("social_hook.scheduler.check_rate_limit")
    def test_error_reinserts_deferred(self, mock_gate, mock_trigger, temp_dir):
        """On exception, deferred_eval decision is re-inserted if no real decision exists."""
        mock_gate.return_value = _GateResult(blocked=False, reason="")
        mock_trigger.side_effect = RuntimeError("git failed")

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        project = _seed_project(conn)
        deferred = _seed_deferred(conn, project.id, count=1)
        config = _make_config()

        _drain_individual(conn, config, project, deferred)

        # deferred_eval should be re-inserted
        remaining = ops.get_deferred_eval_decisions(conn, project.id)
        assert len(remaining) == 1
        assert "Drain failed" in remaining[0].reasoning
        conn.close()

    @patch("social_hook.scheduler.run_trigger")
    @patch("social_hook.scheduler.check_rate_limit")
    def test_error_no_reinsert_if_real_decision_exists(self, mock_gate, mock_trigger, temp_dir):
        """On exception, no re-insert if run_trigger already created a real decision."""
        mock_gate.return_value = _GateResult(blocked=False, reason="")

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        project = _seed_project(conn)
        deferred = _seed_deferred(conn, project.id, count=1)
        commit_hash = deferred[0].commit_hash

        def trigger_that_inserts_then_fails(**kwargs):
            # Simulate run_trigger creating a decision before failing
            real = Decision(
                id=generate_id("decision"),
                project_id=project.id,
                commit_hash=commit_hash,
                decision="skip",
                reasoning="evaluated",
                trigger_source="drain",
            )
            ops.insert_decision(conn, real)
            raise RuntimeError("late failure")

        mock_trigger.side_effect = trigger_that_inserts_then_fails
        config = _make_config()

        _drain_individual(conn, config, project, deferred)

        # Should NOT re-insert deferred_eval because a real decision exists
        remaining = ops.get_deferred_eval_decisions(conn, project.id)
        assert len(remaining) == 0

        # The real decision should be there
        all_decisions = conn.execute(
            "SELECT * FROM decisions WHERE project_id = ? AND commit_hash = ?",
            (project.id, commit_hash),
        ).fetchall()
        assert len(all_decisions) == 1
        assert dict(all_decisions[0])["decision"] == "skip"
        conn.close()

    @patch("social_hook.scheduler.run_trigger")
    @patch("social_hook.scheduler.check_rate_limit")
    def test_unique_constraint_freed(self, mock_gate, mock_trigger, temp_dir):
        """Deferred_eval is deleted before run_trigger so UNIQUE constraint is free."""
        mock_gate.return_value = _GateResult(blocked=False, reason="")

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        project = _seed_project(conn)
        deferred = _seed_deferred(conn, project.id, count=1)
        commit_hash = deferred[0].commit_hash

        call_order = []

        def check_deleted_before_trigger(**kwargs):
            # At this point the deferred_eval should already be deleted
            existing = conn.execute(
                "SELECT * FROM decisions WHERE project_id = ? AND commit_hash = ? AND decision = 'deferred_eval'",
                (project.id, commit_hash),
            ).fetchone()
            call_order.append(("trigger_called", existing is None))
            return 0

        mock_trigger.side_effect = check_deleted_before_trigger
        config = _make_config()

        _drain_individual(conn, config, project, deferred)

        assert call_order == [("trigger_called", True)]
        conn.close()


class TestDrainBatch:
    """Tests for batch drain mode (batch_throttled=True)."""

    @patch("social_hook.scheduler._run_batch_evaluation")
    @patch("social_hook.trigger.parse_commit_info")
    @patch("social_hook.scheduler.check_rate_limit")
    def test_batch_combines_deferred(self, mock_gate, mock_parse, mock_eval, temp_dir):
        """Batch mode deletes all deferred and calls evaluator once."""
        mock_gate.return_value = _GateResult(blocked=False, reason="")
        mock_parse.return_value = MagicMock(message="test commit msg")

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        project = _seed_project(conn)
        deferred = _seed_deferred(conn, project.id, count=3)
        config = _make_config(batch_throttled=True)

        _drain_batch(conn, config, project, deferred)

        # All deferred decisions should be deleted
        remaining = ops.get_deferred_eval_decisions(conn, project.id)
        assert len(remaining) == 0

        # Evaluator called once
        mock_eval.assert_called_once()
        # The commit arg should have combined message
        call_args = mock_eval.call_args
        commit_arg = call_args[0][3]  # positional: conn, config, project, commit, deferred
        assert "Batch of 3" in commit_arg.message
        conn.close()

    @patch("social_hook.scheduler._run_batch_evaluation")
    @patch("social_hook.scheduler.check_rate_limit")
    def test_batch_blocked_skips(self, mock_gate, mock_eval, temp_dir):
        """Batch mode skips when rate limited."""
        mock_gate.return_value = _GateResult(blocked=True, reason="Daily limit")

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        project = _seed_project(conn)
        deferred = _seed_deferred(conn, project.id, count=2)
        config = _make_config(batch_throttled=True)

        _drain_batch(conn, config, project, deferred)

        # Decisions should still exist
        remaining = ops.get_deferred_eval_decisions(conn, project.id)
        assert len(remaining) == 2

        # Evaluator not called
        mock_eval.assert_not_called()
        conn.close()


class TestDrainIntegration:
    """Integration tests through _drain_deferred_evaluations."""

    @patch("social_hook.scheduler.run_trigger")
    @patch("social_hook.scheduler.check_rate_limit")
    def test_dispatches_individual_mode(self, mock_gate, mock_trigger, temp_dir):
        """With batch_throttled=False, dispatches to individual drain."""
        mock_gate.return_value = _GateResult(blocked=False, reason="")
        mock_trigger.return_value = 0

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        project = _seed_project(conn)
        _seed_deferred(conn, project.id, count=2)
        config = _make_config(batch_throttled=False)

        _drain_deferred_evaluations(conn, config, dry_run=False)

        assert mock_trigger.call_count == 2
        conn.close()

    @patch("social_hook.scheduler._run_batch_evaluation")
    @patch("social_hook.scheduler.parse_commit_info")
    @patch("social_hook.scheduler.check_rate_limit")
    def test_dispatches_batch_mode(self, mock_gate, mock_parse, mock_eval, temp_dir):
        """With batch_throttled=True, dispatches to batch drain."""
        mock_gate.return_value = _GateResult(blocked=False, reason="")
        mock_parse.return_value = MagicMock(message="commit msg")

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        project = _seed_project(conn)
        _seed_deferred(conn, project.id, count=2)
        config = _make_config(batch_throttled=True)

        _drain_deferred_evaluations(conn, config, dry_run=False)

        mock_eval.assert_called_once()
        conn.close()
