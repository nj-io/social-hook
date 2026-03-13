"""Tests for scheduler tick (T31)."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from social_hook.db import (
    get_connection,
    get_draft,
    init_database,
    insert_decision,
    insert_draft,
    insert_project,
    update_draft,
)
from social_hook.filesystem import generate_id
from social_hook.models import Decision, Draft, Project
from social_hook.notifications import send_notification
from social_hook.scheduler import (
    acquire_lock,
    get_lock_pid,
    is_lock_stale,
    promote_deferred_drafts,
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
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc123",
            decision="draft",
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

        mock_config.return_value = MagicMock(env={}, channels={})
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

        mock_config.return_value = MagicMock(env={}, channels={})
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
            id=generate_id("project"),
            name="test",
            repo_path="/tmp/test",
            paused=True,
        )
        insert_project(conn, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc123",
            decision="draft",
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

        mock_config.return_value = MagicMock(env={}, channels={})
        mock_db_path.return_value = db_path
        mock_init_db.return_value = conn

        lock_path = temp_dir / "scheduler.lock"
        scheduler_tick(dry_run=True, lock_path=lock_path)

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

        mock_config.return_value = MagicMock(env={}, channels={})
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

        mock_config.return_value = MagicMock(env={}, channels={})
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
    def test_max_retries_marks_failed(
        self, mock_config, mock_db_path, mock_init_db, mock_post, temp_dir
    ):
        """Draft marked failed after 3 retries."""
        from social_hook.adapters.models import PostResult

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        project, draft = self._setup_due_draft(conn)

        # Set retry_count to 2 (next failure = 3rd attempt)
        update_draft(conn, draft.id, retry_count=2)

        mock_config.return_value = MagicMock(env={}, channels={})
        mock_db_path.return_value = db_path
        mock_init_db.return_value = conn
        mock_post.return_value = PostResult(success=False, error="Persistent error")

        lock_path = temp_dir / "scheduler.lock"
        scheduler_tick(dry_run=False, lock_path=lock_path)

        # Re-open connection
        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.status == "failed"
        assert updated.retry_count == 3
        conn2.close()


class TestNotifications:
    """Tests for the shared notification helper."""

    def test_send_notification_web_and_telegram(self):
        """Notification sends to both web and telegram when configured."""
        from social_hook.config.yaml import ChannelConfig, Config

        config = Config(
            channels={"web": ChannelConfig(enabled=True)},
            env={
                "TELEGRAM_BOT_TOKEN": "fake-token",
                "TELEGRAM_ALLOWED_CHAT_IDS": "123,456",
            },
        )

        mock_web = MagicMock()
        mock_tg = MagicMock()
        mock_tg.send_message.return_value = MagicMock(success=True)

        with (
            patch("social_hook.filesystem.get_db_path", return_value=Path("/tmp/test.db")),
            patch("social_hook.messaging.web.WebAdapter", return_value=mock_web),
            patch("social_hook.messaging.telegram.TelegramAdapter", return_value=mock_tg),
        ):
            send_notification(config, "Test message")

        mock_web.send_message.assert_called_once()
        assert mock_tg.send_message.call_count == 2  # 2 chat IDs

    @patch("social_hook.scheduler.send_notification")
    @patch("social_hook.scheduler.init_database")
    @patch("social_hook.scheduler.get_db_path")
    @patch("social_hook.scheduler.load_full_config")
    def test_scheduler_tick_success_notification(
        self, mock_config, mock_db_path, mock_init_db, mock_notify, temp_dir
    ):
        """Successful post triggers notification via send_notification."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)
        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc123",
            decision="draft",
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
        conn.execute(
            "UPDATE drafts SET scheduled_time = datetime('now', '-1 hour') WHERE id = ?",
            (draft.id,),
        )
        conn.commit()

        mock_config.return_value = MagicMock(env={}, channels={})
        mock_db_path.return_value = db_path
        mock_init_db.return_value = conn

        lock_path = temp_dir / "scheduler.lock"
        scheduler_tick(dry_run=True, lock_path=lock_path)

        # dry_run=True passed to send_notification, so it's called with dry_run=True
        mock_notify.assert_called_once()
        call_kwargs = mock_notify.call_args
        assert call_kwargs[1]["dry_run"] is True

    @patch("social_hook.scheduler.send_notification")
    @patch("social_hook.scheduler._post_draft")
    @patch("social_hook.scheduler.init_database")
    @patch("social_hook.scheduler.get_db_path")
    @patch("social_hook.scheduler.load_full_config")
    def test_scheduler_tick_failure_notification(
        self, mock_config, mock_db_path, mock_init_db, mock_post, mock_notify, temp_dir
    ):
        """Failed post (max retries) triggers failure notification."""
        from social_hook.adapters.models import PostResult

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)
        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc123",
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Test content",
            status="scheduled",
        )
        insert_draft(conn, draft)
        update_draft(conn, draft.id, retry_count=2)
        conn.execute(
            "UPDATE drafts SET scheduled_time = datetime('now', '-1 hour') WHERE id = ?",
            (draft.id,),
        )
        conn.commit()

        mock_config.return_value = MagicMock(env={}, channels={})
        mock_db_path.return_value = db_path
        mock_init_db.return_value = conn
        mock_post.return_value = PostResult(success=False, error="API down")

        lock_path = temp_dir / "scheduler.lock"
        scheduler_tick(dry_run=False, lock_path=lock_path)

        mock_notify.assert_called_once()
        msg = mock_notify.call_args[0][1]
        assert "Post failed" in msg
        assert "API down" in msg


class TestPromoteDeferredDrafts:
    """Tests for promote_deferred_drafts."""

    def _make_config(self, platform_enabled=True):
        """Build a Config with an X platform."""
        from social_hook.config.platforms import OutputPlatformConfig
        from social_hook.config.yaml import Config, SchedulingConfig

        platforms = {}
        if platform_enabled:
            platforms["x"] = OutputPlatformConfig(enabled=True, priority="primary")
        else:
            platforms["x"] = OutputPlatformConfig(enabled=False, priority="primary")
        return Config(
            platforms=platforms,
            scheduling=SchedulingConfig(),
            channels={},
        )

    def _insert_deferred_draft(self, conn):
        """Insert a project + deferred draft, return (project, draft)."""
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)
        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc123",
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Deferred content here",
            status="deferred",
        )
        insert_draft(conn, draft)
        return project, draft

    @patch("social_hook.scheduler.calculate_optimal_time")
    def test_still_deferred_guard(self, mock_calc, temp_dir):
        """Draft stays deferred when calculate_optimal_time returns deferred=True."""
        from social_hook.scheduling import ScheduleResult

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        project, draft = self._insert_deferred_draft(conn)
        config = self._make_config()

        mock_calc.return_value = ScheduleResult(
            datetime=MagicMock(),
            deferred=True,
            is_optimal_day=False,
            day_reason="Weekly limit reached",
            time_reason="deferred",
        )

        promoted = promote_deferred_drafts(conn, config)
        assert promoted == 0

        updated = get_draft(conn, draft.id)
        assert updated.status == "deferred"
        conn.close()

    def test_disabled_platform_cancellation(self, temp_dir):
        """Deferred draft is cancelled when its platform is disabled."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        _project, draft = self._insert_deferred_draft(conn)
        config = self._make_config(platform_enabled=False)

        promoted = promote_deferred_drafts(conn, config)
        assert promoted == 0

        updated = get_draft(conn, draft.id)
        assert updated.status == "cancelled"
        conn.close()

    def test_disabled_platform_missing(self, temp_dir):
        """Deferred draft is cancelled when its platform is missing from config."""
        from social_hook.config.yaml import Config, SchedulingConfig

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        _project, draft = self._insert_deferred_draft(conn)
        # Config with no platforms at all
        config = Config(platforms={}, scheduling=SchedulingConfig(), channels={})

        promoted = promote_deferred_drafts(conn, config)
        assert promoted == 0

        updated = get_draft(conn, draft.id)
        assert updated.status == "cancelled"
        conn.close()

    @patch("social_hook.scheduler.send_notification")
    @patch("social_hook.scheduler.calculate_optimal_time")
    def test_successful_promotion(self, mock_calc, mock_notify, temp_dir):
        """Deferred draft is promoted to scheduled when a slot is available."""
        from datetime import datetime, timezone

        from social_hook.scheduling import ScheduleResult

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        project, draft = self._insert_deferred_draft(conn)
        config = self._make_config()

        scheduled_dt = datetime(2026, 3, 10, 14, 0, 0, tzinfo=timezone.utc)
        mock_calc.return_value = ScheduleResult(
            datetime=scheduled_dt,
            deferred=False,
            is_optimal_day=True,
            day_reason="Optimal day",
            time_reason="Optimal hour",
        )

        promoted = promote_deferred_drafts(conn, config)
        assert promoted == 1

        updated = get_draft(conn, draft.id)
        assert updated.status == "scheduled"
        # scheduled_time may be returned as datetime or string depending on DB layer
        st = updated.scheduled_time
        if isinstance(st, str):
            assert st == scheduled_dt.isoformat()
        else:
            assert st == scheduled_dt

        # Notification was sent
        mock_notify.assert_called_once()
        msg = mock_notify.call_args[0][1]
        assert "Deferred draft promoted" in msg
        assert "2026-03-10 14:00 UTC" in msg
        conn.close()

    @patch("social_hook.scheduler.promote_deferred_drafts")
    @patch("social_hook.scheduler.init_database")
    @patch("social_hook.scheduler.get_db_path")
    @patch("social_hook.scheduler.load_full_config")
    def test_promotion_runs_before_early_return(
        self, mock_config, mock_db_path, mock_init_db, mock_promote, temp_dir
    ):
        """promote_deferred_drafts is called even when get_due_drafts returns empty."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)

        mock_config.return_value = MagicMock(env={}, channels={})
        mock_db_path.return_value = db_path
        mock_init_db.return_value = conn

        lock_path = temp_dir / "scheduler.lock"
        result = scheduler_tick(dry_run=True, lock_path=lock_path)

        assert result == 0
        # promote_deferred_drafts must have been called
        mock_promote.assert_called_once()
        conn.close()


class TestSchedulerTickDraftId:
    """Tests for scheduler_tick with draft_id parameter (post-now mode)."""

    @patch("social_hook.scheduler.init_database")
    @patch("social_hook.scheduler.load_full_config")
    @patch("social_hook.scheduler.get_db_path")
    @patch("social_hook.scheduler.get_base_path")
    def test_draft_id_uses_separate_lock(
        self, mock_base, mock_db_path, mock_config, mock_init_db, temp_dir
    ):
        """scheduler_tick with draft_id should use a per-draft lock path."""
        mock_base.return_value = Path(temp_dir)
        mock_db_path.return_value = temp_dir / "test.db"

        draft = MagicMock()
        draft.id = "draft_123"
        draft.status = "scheduled"
        draft.platform = "x"
        draft.content = "test"
        draft.project_id = "proj_1"
        draft.decision_id = None
        draft.media_paths = None
        draft.retry_count = 0

        conn = MagicMock()
        mock_init_db.return_value = conn
        mock_config.return_value = MagicMock(env={}, channels={})

        with (
            patch("social_hook.scheduler.ops.get_draft", return_value=draft),
            patch("social_hook.scheduler._post_draft") as mock_post,
            patch("social_hook.scheduler.ops.update_draft"),
            patch("social_hook.scheduler.ops.insert_post"),
            patch("social_hook.scheduler.ops.emit_data_event"),
            patch("social_hook.scheduler.ops.get_project") as mock_proj,
            patch("social_hook.scheduler.send_notification"),
        ):
            mock_post.return_value = MagicMock(
                success=True, external_id="ext_1", external_url="https://x.com/test/1"
            )
            mock_proj.return_value = MagicMock(name="test", paused=False)
            result = scheduler_tick(draft_id="draft_123")

        assert result == 1

    @patch("social_hook.scheduler.init_database")
    @patch("social_hook.scheduler.load_full_config")
    @patch("social_hook.scheduler.get_db_path")
    @patch("social_hook.scheduler.get_base_path")
    def test_draft_id_skips_promote_and_drain(
        self, mock_base, mock_db_path, mock_config, mock_init_db, temp_dir
    ):
        """scheduler_tick with draft_id should NOT call promote_deferred_drafts or drain."""
        mock_base.return_value = Path(temp_dir)
        mock_db_path.return_value = temp_dir / "test.db"

        draft = MagicMock()
        draft.id = "draft_123"
        draft.status = "not_scheduled"  # Wrong status — should return 0

        conn = MagicMock()
        mock_init_db.return_value = conn
        mock_config.return_value = MagicMock(env={}, channels={})

        with (
            patch("social_hook.scheduler.ops.get_draft", return_value=draft),
            patch("social_hook.scheduler.promote_deferred_drafts") as mock_promote,
            patch("social_hook.scheduler._drain_deferred_evaluations") as mock_drain,
        ):
            result = scheduler_tick(draft_id="draft_123")

        mock_promote.assert_not_called()
        mock_drain.assert_not_called()
        assert result == 0


class TestPostDraftReferencePosting:
    """Tests for _post_draft reference posting via abstract adapter interface."""

    def _setup_with_reference(self, conn, post_format="quote"):
        """Create project, decision, draft with reference_post_id, and referenced post."""
        from social_hook.db import operations as db_ops

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc123",
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)

        # Create a "previous" draft and post (the referenced post)
        ref_draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Previous post",
            status="posted",
        )
        insert_draft(conn, ref_draft)

        from social_hook.models import Post

        ref_post = Post(
            id=generate_id("post"),
            draft_id=ref_draft.id,
            project_id=project.id,
            platform="x",
            content="Previous post",
            external_id="ext_tweet_999",
            external_url="https://x.com/user/status/ext_tweet_999",
        )
        db_ops.insert_post(conn, ref_post)

        # Create the draft that references the previous post
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="New quote post",
            status="scheduled",
            post_format=post_format,
            reference_post_id=ref_post.id,
        )
        insert_draft(conn, draft)

        return project, draft, ref_post

    @patch("social_hook.adapters.platform.factory.create_adapter")
    def test_quote_uses_post_with_reference(self, mock_create_adapter, temp_dir):
        """Quote draft calls adapter.post_with_reference() with ReferenceType.QUOTE."""
        from social_hook.adapters.models import PostResult, ReferenceType
        from social_hook.scheduler import _post_draft

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        project, draft, ref_post = self._setup_with_reference(conn, post_format="quote")

        mock_adapter = MagicMock()
        mock_adapter.supports_reference_type.return_value = True
        mock_adapter.post_with_reference.return_value = PostResult(
            success=True,
            external_id="new_tweet_1",
            external_url="https://x.com/u/status/new_tweet_1",
        )
        mock_create_adapter.return_value = mock_adapter

        config = MagicMock()
        result = _post_draft(conn, draft, config)

        assert result.success is True
        mock_adapter.post_with_reference.assert_called_once()
        call_args = mock_adapter.post_with_reference.call_args
        reference = call_args[0][1]
        assert reference.reference_type == ReferenceType.QUOTE
        assert reference.external_id == "ext_tweet_999"
        conn.close()

    @patch("social_hook.adapters.platform.factory.create_adapter")
    def test_reply_uses_post_with_reference(self, mock_create_adapter, temp_dir):
        """Reply draft calls adapter.post_with_reference() with ReferenceType.REPLY."""
        from social_hook.adapters.models import PostResult, ReferenceType
        from social_hook.scheduler import _post_draft

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        project, draft, ref_post = self._setup_with_reference(conn, post_format="reply")

        mock_adapter = MagicMock()
        mock_adapter.supports_reference_type.return_value = True
        mock_adapter.post_with_reference.return_value = PostResult(
            success=True,
            external_id="new_tweet_2",
            external_url="https://x.com/u/status/new_tweet_2",
        )
        mock_create_adapter.return_value = mock_adapter

        config = MagicMock()
        result = _post_draft(conn, draft, config)

        assert result.success is True
        call_args = mock_adapter.post_with_reference.call_args
        reference = call_args[0][1]
        assert reference.reference_type == ReferenceType.REPLY
        conn.close()

    @patch("social_hook.adapters.platform.factory.create_adapter")
    def test_unsupported_ref_type_falls_back_to_link(self, mock_create_adapter, temp_dir):
        """When adapter doesn't support QUOTE, falls back to LINK."""
        from social_hook.adapters.models import PostResult, ReferenceType
        from social_hook.scheduler import _post_draft

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        project, draft, ref_post = self._setup_with_reference(conn, post_format="quote")

        mock_adapter = MagicMock()
        mock_adapter.supports_reference_type.return_value = False  # Doesn't support QUOTE
        mock_adapter.post_with_reference.return_value = PostResult(
            success=True, external_id="new_post_3"
        )
        mock_create_adapter.return_value = mock_adapter

        config = MagicMock()
        result = _post_draft(conn, draft, config)

        assert result.success is True
        call_args = mock_adapter.post_with_reference.call_args
        reference = call_args[0][1]
        assert reference.reference_type == ReferenceType.LINK
        conn.close()

    @patch("social_hook.adapters.platform.factory.create_adapter")
    def test_non_reference_draft_uses_standard_post(self, mock_create_adapter, temp_dir):
        """Draft without reference_post_id uses standard adapter.post()."""
        from social_hook.adapters.models import PostResult
        from social_hook.scheduler import _post_draft

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)
        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc123",
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Standard post",
            status="scheduled",
        )
        insert_draft(conn, draft)

        mock_adapter = MagicMock()
        mock_adapter.post.return_value = PostResult(success=True, external_id="standard_1")
        mock_create_adapter.return_value = mock_adapter

        config = MagicMock()
        result = _post_draft(conn, draft, config)

        assert result.success is True
        # post_with_reference should NOT be called
        mock_adapter.post_with_reference.assert_not_called()
        # Standard post() should be called
        mock_adapter.post.assert_called_once()
        conn.close()
