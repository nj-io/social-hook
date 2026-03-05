"""Tests for consolidation processing system."""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from social_hook.config.yaml import Config, ConsolidationConfig
from social_hook.consolidation import consolidation_tick, get_consolidation_lock_path
from social_hook.db import operations as ops
from social_hook.db.connection import init_database
from social_hook.filesystem import generate_id
from social_hook.models import Decision, Project


# =============================================================================
# Helpers
# =============================================================================


def _make_project(conn: sqlite3.Connection, name: str = "test-project") -> Project:
    """Create and insert a test project."""
    project = Project(
        id=generate_id("project"),
        name=name,
        repo_path="/tmp/test-repo",
    )
    ops.insert_project(conn, project)
    return project


def _make_decision(
    conn: sqlite3.Connection,
    project_id: str,
    decision_type: str = "hold",
    commit_hash: str = None,
    commit_summary: str = None,
) -> Decision:
    """Create and insert a consolidate/deferred decision."""
    if commit_hash is None:
        commit_hash = generate_id("commit")[:12]
    d = Decision(
        id=generate_id("decision"),
        project_id=project_id,
        commit_hash=commit_hash,
        decision=decision_type,
        reasoning=f"Test {decision_type} decision",
        commit_message=f"Test commit {commit_hash[:8]}",
        commit_summary=commit_summary or f"Summary for {commit_hash[:8]}",
    )
    ops.insert_decision(conn, d)
    return d


def _make_config(enabled=True, mode="notify_only", batch_size=20) -> Config:
    """Create a Config with consolidation settings."""
    config = Config()
    config.consolidation = ConsolidationConfig(
        enabled=enabled,
        mode=mode,
        batch_size=batch_size,
    )
    config.env = {}
    return config


# =============================================================================
# DB operations
# =============================================================================


class TestConsolidationDBOps:
    """Test the 3 new DB operations for consolidation."""

    @pytest.fixture
    def conn(self, tmp_path):
        db_path = tmp_path / "test.db"
        c = init_database(db_path)
        yield c
        c.close()

    def test_get_unprocessed_returns_hold_decisions(self, conn):
        project = _make_project(conn)
        d1 = _make_decision(conn, project.id, "hold")
        d2 = _make_decision(conn, project.id, "hold")
        # skip should NOT be returned
        _make_decision(conn, project.id, "skip",
                       commit_hash=generate_id("c")[:12], commit_summary=None)

        results = ops.get_held_decisions(conn, project.id)
        ids = [r.id for r in results]
        assert d1.id in ids
        assert d2.id in ids
        assert len(results) == 2

    def test_get_unprocessed_respects_limit(self, conn):
        project = _make_project(conn)
        for _ in range(5):
            _make_decision(conn, project.id)

        results = ops.get_held_decisions(conn, project.id, limit=3)
        assert len(results) == 3

    def test_get_unprocessed_excludes_processed(self, conn):
        project = _make_project(conn)
        d1 = _make_decision(conn, project.id)
        d2 = _make_decision(conn, project.id)

        ops.mark_decisions_processed(conn, [d1.id], "batch-001")

        results = ops.get_held_decisions(conn, project.id)
        assert len(results) == 1
        assert results[0].id == d2.id

    def test_mark_decisions_processed(self, conn):
        project = _make_project(conn)
        d1 = _make_decision(conn, project.id)
        d2 = _make_decision(conn, project.id)

        count = ops.mark_decisions_processed(conn, [d1.id, d2.id], "batch-test")
        assert count == 2

        # Verify they are processed
        row = conn.execute(
            "SELECT processed, batch_id, processed_at FROM decisions WHERE id = ?",
            (d1.id,),
        ).fetchone()
        assert row[0] == 1
        assert row[1] == "batch-test"
        assert row[2] is not None

    def test_mark_decisions_processed_empty_list(self, conn):
        count = ops.mark_decisions_processed(conn, [], "batch-empty")
        assert count == 0

    def test_update_decision(self, conn):
        project = _make_project(conn)
        d = _make_decision(conn, project.id)

        updated = ops.update_decision(
            conn, d.id,
            decision="draft",
            reasoning="Re-evaluated as draftable",
            angle="New angle",
            episode_type="milestone",
        )
        assert updated is True

        row = conn.execute(
            "SELECT decision, reasoning, angle, episode_type FROM decisions WHERE id = ?",
            (d.id,),
        ).fetchone()
        assert row[0] == "draft"
        assert row[1] == "Re-evaluated as draftable"
        assert row[2] == "New angle"
        assert row[3] == "milestone"

    def test_update_decision_no_changes(self, conn):
        project = _make_project(conn)
        d = _make_decision(conn, project.id)
        updated = ops.update_decision(conn, d.id)
        assert updated is False


# =============================================================================
# Consolidation tick: disabled
# =============================================================================


class TestConsolidationDisabled:
    """Consolidation tick when disabled should do nothing."""

    @patch("social_hook.consolidation.load_full_config")
    @patch("social_hook.consolidation.acquire_lock", return_value=True)
    @patch("social_hook.consolidation.release_lock")
    def test_disabled_returns_zero(self, mock_release, mock_lock, mock_config):
        config = _make_config(enabled=False)
        mock_config.return_value = config

        result = consolidation_tick(lock_path=Path("/tmp/test-consolidation.lock"))
        assert result == 0


# =============================================================================
# Consolidation tick: notify_only
# =============================================================================


class TestConsolidationNotifyOnly:
    """Test notify_only mode."""

    @patch("social_hook.notifications.send_notification")
    @patch("social_hook.consolidation.load_full_config")
    @patch("social_hook.consolidation.acquire_lock", return_value=True)
    @patch("social_hook.consolidation.release_lock")
    @patch("social_hook.consolidation.get_db_path")
    @patch("social_hook.consolidation.init_database")
    def test_notify_only_sends_notification(
        self, mock_init_db, mock_db_path, mock_release, mock_lock,
        mock_config, mock_notify, tmp_path,
    ):
        db_path = tmp_path / "test.db"
        conn = init_database(db_path)
        mock_db_path.return_value = db_path

        config = _make_config(enabled=True, mode="notify_only")
        mock_config.return_value = config

        project = _make_project(conn)
        _make_decision(conn, project.id, "hold", commit_summary="Added logging")
        _make_decision(conn, project.id, "hold", commit_summary="Fixed typo")

        # Return a fresh connection each call (consolidation_tick closes it)
        mock_init_db.return_value = init_database(db_path)

        result = consolidation_tick(lock_path=tmp_path / "test.lock")
        assert result == 2
        mock_notify.assert_called_once()

        # Verify decisions are marked processed (use original conn which is still open)
        unprocessed = ops.get_held_decisions(conn, project.id)
        assert len(unprocessed) == 0

        conn.close()


# =============================================================================
# Consolidation tick: locking
# =============================================================================


class TestConsolidationLocking:
    """Test lock file behavior."""

    @patch("social_hook.consolidation.acquire_lock", return_value=False)
    def test_lock_held_returns_zero(self, mock_lock):
        result = consolidation_tick()
        assert result == 0


# =============================================================================
# Consolidation tick: idempotent
# =============================================================================


class TestConsolidationIdempotent:
    """Test that re-running does not reprocess."""

    @patch("social_hook.notifications.send_notification")
    @patch("social_hook.consolidation.load_full_config")
    @patch("social_hook.consolidation.acquire_lock", return_value=True)
    @patch("social_hook.consolidation.release_lock")
    @patch("social_hook.consolidation.get_db_path")
    @patch("social_hook.consolidation.init_database")
    def test_second_run_processes_nothing(
        self, mock_init_db, mock_db_path, mock_release, mock_lock,
        mock_config, mock_notify, tmp_path,
    ):
        db_path = tmp_path / "test.db"
        # Set up shared DB
        setup_conn = init_database(db_path)
        mock_db_path.return_value = db_path

        config = _make_config(enabled=True, mode="notify_only")
        mock_config.return_value = config

        project = _make_project(setup_conn)
        _make_decision(setup_conn, project.id, "hold")
        setup_conn.close()

        # First run - provide fresh conn
        mock_init_db.return_value = init_database(db_path)
        result1 = consolidation_tick(lock_path=tmp_path / "test.lock")
        assert result1 == 1

        # Second run - provide fresh conn
        mock_notify.reset_mock()
        mock_init_db.return_value = init_database(db_path)
        result2 = consolidation_tick(lock_path=tmp_path / "test.lock")
        assert result2 == 0
        mock_notify.assert_not_called()


# =============================================================================
# Decision model: commit_summary field
# =============================================================================


class TestDecisionCommitSummary:
    """Test commit_summary field on Decision model."""

    def test_to_dict_includes_commit_summary(self):
        d = Decision(
            id="d1", project_id="p1", commit_hash="abc",
            decision="hold", reasoning="test",
            commit_summary="Added logging feature",
        )
        data = d.to_dict()
        assert data["commit_summary"] == "Added logging feature"
        assert data["processed"] is False
        assert data["processed_at"] is None
        assert data["batch_id"] is None

    def test_from_dict_parses_commit_summary(self):
        data = {
            "id": "d1", "project_id": "p1", "commit_hash": "abc",
            "decision": "hold", "reasoning": "test",
            "commit_summary": "Fixed bug",
            "processed": 1,
            "batch_id": "batch-001",
        }
        d = Decision.from_dict(data)
        assert d.commit_summary == "Fixed bug"
        assert d.processed is True
        assert d.batch_id == "batch-001"

    def test_to_row_includes_commit_summary(self):
        d = Decision(
            id="d1", project_id="p1", commit_hash="abc",
            decision="hold", reasoning="test",
            commit_summary="New feature",
        )
        row = d.to_row()
        # 16-element tuple; commit_summary is at index 14
        assert len(row) == 16
        assert row[14] == "New feature"
