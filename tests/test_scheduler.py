"""Tests for scheduler tick (T31)."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from social_hook.db import (
    get_connection,
    init_database,
    insert_decision,
    insert_draft,
    insert_project,
    get_draft,
    update_draft,
)
from social_hook.filesystem import generate_id
from social_hook.models import Decision, Draft, Project
from social_hook.scheduler import (
    acquire_lock,
    get_lock_path,
    get_lock_pid,
    is_lock_stale,
    release_lock,
    scheduler_tick,
)


class TestLockManagement:
    """Tests for lock file lifecycle."""

    def test_acquire_and_release(self, temp_dir):
        lock_path = temp_dir / "scheduler.lock"
        assert acquire_lock(lock_path) is True
        assert lock_path.exists()

        pid = get_lock_pid(lock_path)
        assert pid == os.getpid()

        release_lock(lock_path)
        assert not lock_path.exists()

    def test_acquire_fails_if_held(self, temp_dir):
        lock_path = temp_dir / "scheduler.lock"
        lock_path.write_text(str(os.getpid()))

        # Our own PID is alive, so lock should fail
        assert acquire_lock(lock_path) is False

    def test_stale_lock_cleaned_up(self, temp_dir):
        lock_path = temp_dir / "scheduler.lock"
        # Write a PID that doesn't exist
        lock_path.write_text("99999999")

        assert is_lock_stale(lock_path) is True
        assert acquire_lock(lock_path) is True

    def test_no_lock_file_is_stale(self, temp_dir):
        lock_path = temp_dir / "nonexistent.lock"
        assert is_lock_stale(lock_path) is True

    def test_get_lock_pid_invalid_content(self, temp_dir):
        lock_path = temp_dir / "scheduler.lock"
        lock_path.write_text("not_a_number")
        assert get_lock_pid(lock_path) is None

    def test_release_only_own_lock(self, temp_dir):
        lock_path = temp_dir / "scheduler.lock"
        # Write a different PID
        lock_path.write_text("12345")
        release_lock(lock_path)
        # Lock should still exist (not our PID)
        assert lock_path.exists()


class TestSchedulerTick:
    """Tests for scheduler_tick."""

    def _setup_due_draft(self, conn):
        """Create a project with a due draft."""
        project = Project(
            id=generate_id("project"), name="test", repo_path="/tmp/test"
        )
        insert_project(conn, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc123",
            decision="post_worthy",
            reasoning="test",
        )
        insert_decision(conn, decision)

        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Test post content",
            status="scheduled",
        )
        insert_draft(conn, draft)
        # Set scheduled_time to the past
        conn.execute(
            "UPDATE drafts SET scheduled_time = datetime('now', '-1 hour') WHERE id = ?",
            (draft.id,),
        )
        conn.commit()
        return project, draft

    @patch("social_hook.scheduler.init_database")
    @patch("social_hook.scheduler.get_db_path")
    @patch("social_hook.scheduler.load_full_config")
    def test_tick_dry_run_posts_due_drafts(self, mock_config, mock_db_path, mock_init_db, temp_dir):
        """Dry-run tick processes due drafts."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        project, draft = self._setup_due_draft(conn)

        mock_config.return_value = MagicMock(env={})
        mock_db_path.return_value = db_path
        mock_init_db.return_value = conn

        lock_path = temp_dir / "scheduler.lock"
        processed = scheduler_tick(dry_run=True, lock_path=lock_path)

        assert processed == 1

        # Re-open connection (scheduler_tick closes it)
        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.status == "posted"
        conn2.close()

    @patch("social_hook.scheduler.init_database")
    @patch("social_hook.scheduler.get_db_path")
    @patch("social_hook.scheduler.load_full_config")
    def test_tick_no_due_drafts(self, mock_config, mock_db_path, mock_init_db, temp_dir):
        """Tick with no due drafts returns 0."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)

        mock_config.return_value = MagicMock(env={})
        mock_db_path.return_value = db_path
        mock_init_db.return_value = conn

        lock_path = temp_dir / "scheduler.lock"
        processed = scheduler_tick(dry_run=True, lock_path=lock_path)
        assert processed == 0
        conn.close()

    def test_tick_skips_when_locked(self, temp_dir):
        """Tick returns 0 when lock is held."""
        lock_path = temp_dir / "scheduler.lock"
        lock_path.write_text(str(os.getpid()))

        processed = scheduler_tick(dry_run=True, lock_path=lock_path)
        assert processed == 0

    @patch("social_hook.scheduler.init_database")
    @patch("social_hook.scheduler.get_db_path")
    @patch("social_hook.scheduler.load_full_config")
    def test_tick_skips_paused_project(self, mock_config, mock_db_path, mock_init_db, temp_dir):
        """Tick skips drafts for paused projects."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)

        # Create paused project with due draft
        project = Project(
            id=generate_id("project"), name="test", repo_path="/tmp/test",
            paused=True,
        )
        insert_project(conn, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc123",
            decision="post_worthy",
            reasoning="test",
        )
        insert_decision(conn, decision)

        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="paused content",
            status="scheduled",
        )
        insert_draft(conn, draft)
        conn.execute(
            "UPDATE drafts SET scheduled_time = datetime('now', '-1 hour') WHERE id = ?",
            (draft.id,),
        )
        conn.commit()

        mock_config.return_value = MagicMock(env={})
        mock_db_path.return_value = db_path
        mock_init_db.return_value = conn

        lock_path = temp_dir / "scheduler.lock"
        processed = scheduler_tick(dry_run=True, lock_path=lock_path)

        # Re-open connection (scheduler_tick closes it)
        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.status == "scheduled"
        conn2.close()

    @patch("social_hook.scheduler.init_database")
    @patch("social_hook.scheduler.get_db_path")
    @patch("social_hook.scheduler.load_full_config")
    def test_lock_released_after_tick(self, mock_config, mock_db_path, mock_init_db, temp_dir):
        """Lock file is released after tick completes."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)

        mock_config.return_value = MagicMock(env={})
        mock_db_path.return_value = db_path
        mock_init_db.return_value = conn

        lock_path = temp_dir / "scheduler.lock"
        scheduler_tick(dry_run=True, lock_path=lock_path)

        assert not lock_path.exists()
        conn.close()

    @patch("social_hook.scheduler._post_draft")
    @patch("social_hook.scheduler.init_database")
    @patch("social_hook.scheduler.get_db_path")
    @patch("social_hook.scheduler.load_full_config")
    def test_retry_on_failure(self, mock_config, mock_db_path, mock_init_db, mock_post, temp_dir):
        """Failed post schedules retry with backoff."""
        from social_hook.adapters.models import PostResult

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        project, draft = self._setup_due_draft(conn)

        mock_config.return_value = MagicMock(env={})
        mock_db_path.return_value = db_path
        mock_init_db.return_value = conn
        mock_post.return_value = PostResult(success=False, error="Rate limited")

        lock_path = temp_dir / "scheduler.lock"
        processed = scheduler_tick(dry_run=False, lock_path=lock_path)

        assert processed == 1

        # Re-open connection
        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.status == "scheduled"
        assert updated.retry_count == 1
        assert updated.last_error == "Rate limited"
        conn2.close()

    @patch("social_hook.scheduler._post_draft")
    @patch("social_hook.scheduler.init_database")
    @patch("social_hook.scheduler.get_db_path")
    @patch("social_hook.scheduler.load_full_config")
    def test_max_retries_marks_failed(self, mock_config, mock_db_path, mock_init_db, mock_post, temp_dir):
        """Draft marked failed after 3 retries."""
        from social_hook.adapters.models import PostResult

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        project, draft = self._setup_due_draft(conn)

        # Set retry_count to 2 (next failure = 3rd attempt)
        update_draft(conn, draft.id, retry_count=2)

        mock_config.return_value = MagicMock(env={})
        mock_db_path.return_value = db_path
        mock_init_db.return_value = conn
        mock_post.return_value = PostResult(success=False, error="Persistent error")

        lock_path = temp_dir / "scheduler.lock"
        processed = scheduler_tick(dry_run=False, lock_path=lock_path)

        # Re-open connection
        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.status == "failed"
        assert updated.retry_count == 3
        conn2.close()
