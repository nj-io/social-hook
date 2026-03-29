"""Tests for deferred eval drain (Chunk 4)."""

from dataclasses import dataclass
from unittest.mock import patch

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

        # run_trigger called twice with correct kwargs
        assert mock_trigger.call_count == 2
        for i, call in enumerate(mock_trigger.call_args_list):
            assert call.kwargs.get("trigger_source") == "drain"
            assert call.kwargs.get("existing_decision_id") == deferred[i].id
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

        # Only 1 trigger call; remaining 2 deferred rows untouched
        assert mock_trigger.call_count == 1
        remaining = ops.get_deferred_eval_decisions(conn, project.id)
        assert len(remaining) == 3  # all rows still in DB (upsert pattern)
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
    def test_error_upserts_deferred_back(self, mock_gate, mock_trigger, temp_dir):
        """On exception, upsert_decision restores deferred_eval with error reason."""
        mock_gate.return_value = _GateResult(blocked=False, reason="")

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        project = _seed_project(conn)
        deferred = _seed_deferred(conn, project.id, count=1)
        decision_id = deferred[0].id

        def trigger_that_upserts_then_fails(**kwargs):
            # Simulate run_trigger upserting the row to "skip" before failing
            ops.upsert_decision(
                conn,
                Decision(
                    id=decision_id,
                    project_id=project.id,
                    commit_hash=deferred[0].commit_hash,
                    decision="skip",
                    reasoning="evaluated",
                    trigger_source="drain",
                ),
            )
            raise RuntimeError("late failure")

        mock_trigger.side_effect = trigger_that_upserts_then_fails
        config = _make_config()

        _drain_individual(conn, config, project, deferred)

        # Error handler upserts deferred_eval back over the "skip" row
        remaining = ops.get_deferred_eval_decisions(conn, project.id)
        assert len(remaining) == 1
        assert remaining[0].id == decision_id
        assert "Drain failed" in remaining[0].reasoning
        conn.close()

    @patch("social_hook.scheduler.run_trigger")
    @patch("social_hook.scheduler.check_rate_limit")
    def test_passes_existing_decision_id(self, mock_gate, mock_trigger, temp_dir):
        """run_trigger receives existing_decision_id so it upserts over the deferred row."""
        mock_gate.return_value = _GateResult(blocked=False, reason="")
        mock_trigger.return_value = 0

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        project = _seed_project(conn)
        deferred = _seed_deferred(conn, project.id, count=1)
        config = _make_config()

        _drain_individual(conn, config, project, deferred)

        assert mock_trigger.call_count == 1
        assert mock_trigger.call_args.kwargs["existing_decision_id"] == deferred[0].id
        conn.close()


class TestDrainBatch:
    """Tests for batch drain mode (batch_throttled=True)."""

    @patch("social_hook.trigger.evaluate_batch")
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.scheduler.check_rate_limit")
    def test_batch_combines_deferred(self, mock_gate, _mock_client, mock_eval, temp_dir):
        """Batch mode calls evaluate_batch with all deferred decisions."""
        mock_gate.return_value = _GateResult(blocked=False, reason="")

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        project = _seed_project(conn)
        deferred = _seed_deferred(conn, project.id, count=3)
        config = _make_config(batch_throttled=True)

        _drain_batch(conn, config, project, deferred)

        # evaluate_batch called once with all deferred commits
        mock_eval.assert_called_once()
        conn.close()

    @patch("social_hook.trigger.evaluate_batch")
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

    @patch("social_hook.trigger.evaluate_batch")
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.scheduler.check_rate_limit")
    def test_dispatches_batch_mode(self, mock_gate, _mock_client, mock_eval, temp_dir):
        """With batch_throttled=True, dispatches to batch drain via evaluate_batch."""
        mock_gate.return_value = _GateResult(blocked=False, reason="")

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        project = _seed_project(conn)
        _seed_deferred(conn, project.id, count=2)
        config = _make_config(batch_throttled=True)

        _drain_deferred_evaluations(conn, config, dry_run=False)

        mock_eval.assert_called_once()
        conn.close()
