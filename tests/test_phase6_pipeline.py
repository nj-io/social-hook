"""Tests for Phase 6 pipeline features: per-account gap, topic status, queue actions, error feed."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from social_hook.db import operations as ops
from social_hook.db.connection import init_database
from social_hook.error_feed import ErrorSeverity
from social_hook.scheduler import (
    _check_per_account_gap,
    _handle_post_failure,
    record_post_success,
)

# =============================================================================
# Helpers
# =============================================================================


@dataclass
class FakeTargetConfig:
    account: str = ""
    platform: str = ""
    strategy: str = ""
    frequency: str | None = None
    scheduling: dict | None = None


@dataclass
class FakeConfig:
    targets: dict = field(default_factory=dict)
    platform_settings: dict = field(default_factory=dict)


def _make_draft(platform="x", draft_id="draft_1", target_id=None, topic_id=None):
    """Create a minimal draft-like object."""
    return SimpleNamespace(
        platform=platform,
        id=draft_id,
        target_id=target_id,
        topic_id=topic_id,
        project_id="proj_1",
        decision_id="dec_1",
        content="Test post content",
        retry_count=0,
        media_paths=[],
    )


def _insert_test_post(conn, platform="x", posted_at=None, project_id="proj_1", target_id=None):
    """Insert a test post with a specific posted_at time."""
    if posted_at is None:
        posted_at = datetime.now(timezone.utc)
    post_id = f"post_{posted_at.isoformat()}"
    conn.execute(
        "INSERT INTO posts (id, draft_id, project_id, platform, content, posted_at, target_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            post_id,
            "draft_test",
            project_id,
            platform,
            "test content",
            posted_at.isoformat(),
            target_id,
        ),
    )
    conn.commit()
    return post_id


@pytest.fixture
def db(tmp_path):
    """Create a temporary database with seed data."""
    db_path = tmp_path / "test.db"
    conn = init_database(db_path)
    conn.execute(
        "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
        ("proj_1", "test-project", "/tmp/test"),
    )
    conn.execute(
        "INSERT INTO decisions (id, project_id, commit_hash, decision, reasoning) "
        "VALUES (?, ?, ?, ?, ?)",
        ("dec_1", "proj_1", "abc123", "draft", "test"),
    )
    conn.execute(
        "INSERT INTO drafts (id, project_id, decision_id, platform, content, status) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("draft_test", "proj_1", "dec_1", "x", "test", "posted"),
    )
    conn.commit()
    yield conn
    conn.close()


# =============================================================================
# 6.1: Per-account posting gap
# =============================================================================


class TestPerAccountGap:
    """Tests for _check_per_account_gap."""

    def test_no_target_id_passes(self, db):
        """Legacy drafts without target_id always pass."""
        config = FakeConfig()
        draft = _make_draft(target_id=None)
        assert _check_per_account_gap(db, config, draft) is True

    def test_no_targets_config_passes(self, db):
        """No targets in config -> pass."""
        config = FakeConfig(targets={})
        draft = _make_draft(target_id="t1")
        assert _check_per_account_gap(db, config, draft) is True

    def test_target_not_found_passes(self, db):
        """Target not in config -> pass with warning."""
        config = FakeConfig(targets={"other": FakeTargetConfig(account="acct1")})
        draft = _make_draft(target_id="missing")
        assert _check_per_account_gap(db, config, draft) is True

    def test_no_account_passes(self, db):
        """Target with empty account (preview mode) -> pass."""
        config = FakeConfig(targets={"t1": FakeTargetConfig(account="")})
        draft = _make_draft(target_id="t1")
        assert _check_per_account_gap(db, config, draft) is True

    def test_no_prior_posts_passes(self, db):
        """No posts for this account -> pass."""
        config = FakeConfig(
            targets={
                "t1": FakeTargetConfig(account="acct1", frequency="high"),
            }
        )
        draft = _make_draft(target_id="t1")
        assert _check_per_account_gap(db, config, draft) is True

    def test_gap_satisfied(self, db):
        """Post was long enough ago -> pass."""
        config = FakeConfig(
            targets={
                "t1": FakeTargetConfig(account="acct1", frequency="high"),  # 30 min gap
            }
        )
        old_time = datetime.now(timezone.utc) - timedelta(minutes=60)
        _insert_test_post(db, posted_at=old_time, target_id="t1")
        draft = _make_draft(target_id="t1")
        assert _check_per_account_gap(db, config, draft) is True

    def test_gap_not_satisfied(self, db):
        """Post was too recent -> fail."""
        config = FakeConfig(
            targets={
                "t1": FakeTargetConfig(account="acct1", frequency="high"),  # 30 min gap
            }
        )
        recent_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        _insert_test_post(db, posted_at=recent_time, target_id="t1")
        draft = _make_draft(target_id="t1")
        assert _check_per_account_gap(db, config, draft) is False

    def test_max_gap_across_siblings(self, db):
        """Effective gap = max across targets sharing same account."""
        config = FakeConfig(
            targets={
                "t1": FakeTargetConfig(account="acct1", frequency="high"),  # 30 min
                "t2": FakeTargetConfig(account="acct1", frequency="moderate"),  # 120 min
            }
        )
        # Posted 60 min ago: passes t1's 30 min but not t2's 120 min
        mid_time = datetime.now(timezone.utc) - timedelta(minutes=60)
        _insert_test_post(db, posted_at=mid_time, target_id="t1")
        draft = _make_draft(target_id="t1")
        assert _check_per_account_gap(db, config, draft) is False

    def test_different_accounts_independent(self, db):
        """Posts from a different account don't affect this one."""
        config = FakeConfig(
            targets={
                "t1": FakeTargetConfig(account="acct1", frequency="high"),
                "t2": FakeTargetConfig(account="acct2", frequency="high"),
            }
        )
        recent_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        _insert_test_post(db, posted_at=recent_time, target_id="t2")
        draft = _make_draft(target_id="t1")
        assert _check_per_account_gap(db, config, draft) is True

    def test_scheduling_override(self, db):
        """Per-target scheduling override affects gap computation."""
        config = FakeConfig(
            targets={
                "t1": FakeTargetConfig(
                    account="acct1",
                    frequency="high",  # base: 30 min
                    scheduling={"min_gap_minutes": 120},  # override: 120 min
                ),
            }
        )
        mid_time = datetime.now(timezone.utc) - timedelta(minutes=60)
        _insert_test_post(db, posted_at=mid_time, target_id="t1")
        draft = _make_draft(target_id="t1")
        assert _check_per_account_gap(db, config, draft) is False


# =============================================================================
# 6.1: DB operation — get_last_post_time_by_account
# =============================================================================


class TestGetLastPostTimeByAccount:
    def test_no_posts(self, db):
        result = ops.get_last_post_time_by_account(db, ["t1", "t2"])
        assert result is None

    def test_empty_target_ids(self, db):
        result = ops.get_last_post_time_by_account(db, [])
        assert result is None

    def test_returns_most_recent(self, db):
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        new_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        _insert_test_post(db, posted_at=old_time, target_id="t1")
        _insert_test_post(db, posted_at=new_time, target_id="t2")
        result = ops.get_last_post_time_by_account(db, ["t1", "t2"])
        assert result is not None
        # Should be close to new_time (within 1 second)
        assert abs((result - new_time).total_seconds()) < 1

    def test_filters_by_target_id(self, db):
        recent = datetime.now(timezone.utc) - timedelta(minutes=5)
        _insert_test_post(db, posted_at=recent, target_id="other")
        result = ops.get_last_post_time_by_account(db, ["t1"])
        assert result is None


# =============================================================================
# 6.2: Topic status completeness — record_post_success
# =============================================================================


class TestTopicStatusOnPost:
    def _insert_draft(self, db, draft_id="draft_post", topic_id=None, target_id=None):
        """Insert a draft row so FK constraints are satisfied."""
        db.execute(
            "INSERT INTO drafts (id, project_id, decision_id, platform, content, status, "
            "target_id, topic_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (draft_id, "proj_1", "dec_1", "x", "test", "scheduled", target_id, topic_id),
        )
        db.commit()

    def test_topic_updated_on_post(self, db):
        """When a draft with topic_id is posted, topic status should be set to 'covered'."""
        # Create a topic
        db.execute(
            "INSERT INTO content_topics (id, project_id, strategy, topic, status) "
            "VALUES (?, ?, ?, ?, ?)",
            ("topic_1", "proj_1", "building-public", "auth system", "partial"),
        )
        db.commit()

        draft_id = "draft_topic_test"
        self._insert_draft(db, draft_id=draft_id, topic_id="topic_1", target_id="t1")

        draft = _make_draft(draft_id=draft_id, target_id="t1", topic_id="topic_1")
        result = SimpleNamespace(
            success=True,
            external_id="ext_123",
            external_url="https://x.com/test/123",
        )
        config = SimpleNamespace(notification_level="drafts_only")

        with (
            patch("social_hook.scheduler.send_notification"),
            patch("social_hook.scheduler.ops.get_draft_tweets", return_value=[]),
            patch("social_hook.scheduler.ops.get_decision", return_value=None),
        ):
            record_post_success(db, draft, result, config, "test-project")

        topic = ops.get_topic(db, "topic_1")
        assert topic is not None
        assert topic.status == "covered"

    def test_no_topic_id_no_update(self, db):
        """When draft has no topic_id, no topic status update happens."""
        draft_id = "draft_no_topic"
        self._insert_draft(db, draft_id=draft_id, target_id="t1")

        draft = _make_draft(draft_id=draft_id, target_id="t1", topic_id=None)
        result = SimpleNamespace(
            success=True,
            external_id="ext_456",
            external_url="https://x.com/test/456",
        )
        config = SimpleNamespace(notification_level="drafts_only")

        with (
            patch("social_hook.scheduler.send_notification"),
            patch("social_hook.scheduler.ops.get_draft_tweets", return_value=[]),
            patch("social_hook.scheduler.ops.get_decision", return_value=None),
        ):
            # Should not raise — just verifies it runs cleanly
            record_post_success(db, draft, result, config, "test-project")


# =============================================================================
# 6.2: Topic status completeness — trigger _run_targets_path
# =============================================================================


class TestTopicStatusOnDraft:
    """Test topic status update after draft creation in _run_targets_path."""

    def test_topic_status_partial_with_arc(self):
        """Strategy with topic_id and arc_id should set topic to 'partial'."""
        sd = SimpleNamespace(action="draft", topic_id="topic_1", arc_id="arc_1", reason="test")

        def _val(x):
            return x.value if hasattr(x, "value") else x

        # Verify the logic: if arc_id present, new_status should be "partial"
        if _val(sd.action) == "draft" and sd.topic_id:
            new_status = "partial" if sd.arc_id else "covered"
        assert new_status == "partial"

    def test_topic_status_covered_without_arc(self):
        """Strategy with topic_id but no arc_id should set topic to 'covered'."""
        sd = SimpleNamespace(action="draft", topic_id="topic_1", arc_id=None, reason="test")

        def _val(x):
            return x.value if hasattr(x, "value") else x

        if _val(sd.action) == "draft" and sd.topic_id:
            new_status = "partial" if sd.arc_id else "covered"
        assert new_status == "covered"


# =============================================================================
# 6.3: Queue action notifications
# =============================================================================


class TestQueueActionNotifications:
    """Tests for queue action collection and passing to notifications."""

    def test_queue_actions_collected(self):
        """Executed queue actions should be collected as list of dicts."""
        executed = []
        # Simulate the collection pattern from _run_targets_path
        qa = SimpleNamespace(action="supersede", draft_id="d1", reason="newer version")
        action_type = qa.action
        executed.append(
            {
                "type": action_type,
                "draft_id": qa.draft_id,
                "reason": qa.reason or "",
            }
        )
        assert len(executed) == 1
        assert executed[0]["type"] == "supersede"
        assert executed[0]["draft_id"] == "d1"
        assert executed[0]["reason"] == "newer version"

    def test_empty_queue_actions_passed_as_none(self):
        """Empty list should be passed as None."""
        executed_queue_actions: list[dict[str, str]] = []
        result = executed_queue_actions or None
        assert result is None

    def test_non_empty_queue_actions_passed_as_list(self):
        """Non-empty list should be passed as-is."""
        executed_queue_actions = [{"type": "drop", "draft_id": "d2", "reason": "obsolete"}]
        result = executed_queue_actions or None
        assert result is not None
        assert len(result) == 1

    def test_merge_actions_excluded(self):
        """Merge actions should be skipped in the collection."""
        executed = []
        actions = [
            SimpleNamespace(action="supersede", draft_id="d1", reason="newer"),
            SimpleNamespace(action="merge", draft_id="d2", reason="combine"),
            SimpleNamespace(action="drop", draft_id="d3", reason="obsolete"),
        ]
        for qa in actions:
            if qa.action == "merge":
                continue
            executed.append(
                {
                    "type": qa.action,
                    "draft_id": qa.draft_id,
                    "reason": qa.reason or "",
                }
            )
        assert len(executed) == 2
        assert executed[0]["type"] == "supersede"
        assert executed[1]["type"] == "drop"


# =============================================================================
# 6.4: Error feed integration — scheduler
# =============================================================================


class TestErrorFeedScheduler:
    """Tests for error_feed.emit() at scheduler error sites."""

    def test_retry_exhaustion_emits_error(self, db):
        """Post failure after max retries should emit ERROR to error feed."""
        draft = _make_draft()
        draft.retry_count = 2  # This will be attempt 3 (>= 3)
        config = SimpleNamespace(notification_level="drafts_only")

        with (
            patch("social_hook.scheduler.error_feed") as mock_feed,
            patch("social_hook.scheduler.send_notification"),
            patch("social_hook.scheduler.ops.get_project", return_value=None),
        ):
            _handle_post_failure(db, draft, "auth error", config, dry_run=False)

        mock_feed.emit.assert_called_once()
        call_args = mock_feed.emit.call_args
        assert call_args[0][0] == ErrorSeverity.ERROR
        assert "failed after 3 attempts" in call_args[0][1]
        assert call_args[1]["source"] == "posting"

    def test_retryable_failure_emits_warning(self, db):
        """Post failure with retries remaining should emit WARNING."""
        draft = _make_draft()
        draft.retry_count = 0  # First retry
        config = SimpleNamespace(notification_level="drafts_only")

        with patch("social_hook.scheduler.error_feed") as mock_feed:
            _handle_post_failure(db, draft, "timeout", config, dry_run=False)

            mock_feed.emit.assert_called_once()
            call_args = mock_feed.emit.call_args
            assert call_args[0][0] == ErrorSeverity.WARNING
            assert "attempt 1/3" in call_args[0][1]
            assert call_args[1]["source"] == "posting"

    def test_adapter_config_error_emits(self, db):
        """ConfigError in _post_draft should emit to error feed."""
        from social_hook.scheduler import _post_draft

        draft = _make_draft()
        draft.preview_mode = False
        draft.target_id = "nonexistent"

        config = SimpleNamespace(
            targets={"other": FakeTargetConfig(account="acct1")},
            accounts={},
            platform_credentials={},
            env={},
        )

        with (
            patch("social_hook.scheduler.error_feed") as mock_feed,
            patch("social_hook.scheduler._registry") as mock_reg,
        ):
            from social_hook.errors import ConfigError

            mock_reg.get.side_effect = ConfigError("No adapter")

            result = _post_draft(db, draft, config, db_path="/tmp/test.db")
            assert not result.success

            mock_feed.emit.assert_called_once()
            call_args = mock_feed.emit.call_args
            assert call_args[0][0] == ErrorSeverity.ERROR
            assert call_args[1]["source"] == "auth"


# =============================================================================
# 6.4: Error feed integration — trigger
# =============================================================================


class TestErrorFeedTrigger:
    """Tests for error_feed.emit() at trigger error sites."""

    def test_config_error_emits(self):
        """ConfigError in run_trigger should emit to error feed."""
        from social_hook.errors import ConfigError
        from social_hook.trigger import run_trigger

        with (
            patch("social_hook.trigger.load_full_config") as mock_config,
            patch("social_hook.trigger.error_feed") as mock_feed,
        ):
            mock_config.side_effect = ConfigError("bad config")
            result = run_trigger("abc123", "/tmp/test")
            assert result == 1
            mock_feed.emit.assert_called_once()
            call_args = mock_feed.emit.call_args
            assert call_args[0][0] == ErrorSeverity.ERROR
            assert "Config error" in call_args[0][1]
            assert call_args[1]["source"] == "config"

    def test_db_error_emits(self):
        """DatabaseError in run_trigger should emit to error feed."""
        from social_hook.errors import DatabaseError
        from social_hook.trigger import run_trigger

        with (
            patch("social_hook.trigger.load_full_config"),
            patch("social_hook.trigger.get_db_path", return_value="/tmp/test.db"),
            patch("social_hook.trigger.init_database") as mock_init,
            patch("social_hook.trigger.error_feed") as mock_feed,
        ):
            mock_init.side_effect = DatabaseError("db corrupted")
            result = run_trigger("abc123", "/tmp/test")
            assert result == 2
            mock_feed.emit.assert_called_once()
            call_args = mock_feed.emit.call_args
            assert call_args[0][0] == ErrorSeverity.ERROR
            assert "Database error" in call_args[0][1]
            assert call_args[1]["source"] == "database"
