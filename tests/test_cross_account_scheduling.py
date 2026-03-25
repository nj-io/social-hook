"""Tests for cross-account scheduling with jitter (Phase 4, Chunk 2)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from social_hook.db import operations as ops
from social_hook.db.connection import init_database
from social_hook.models import Draft
from social_hook.scheduler import _check_cross_account_gap

# =============================================================================
# Helpers
# =============================================================================


def _make_config(platform="x", gap_minutes=30):
    """Create a minimal config with platform_settings."""
    from dataclasses import dataclass, field

    @dataclass
    class PlatformSettingsConfig:
        cross_account_gap_minutes: int = 0

    @dataclass
    class FakeConfig:
        platform_settings: dict = field(default_factory=dict)

    config = FakeConfig()
    if gap_minutes > 0:
        config.platform_settings[platform] = PlatformSettingsConfig(
            cross_account_gap_minutes=gap_minutes
        )
    return config


def _make_draft(platform="x", draft_id="draft_1"):
    """Create a minimal draft-like object."""
    from types import SimpleNamespace

    return SimpleNamespace(platform=platform, id=draft_id)


def _insert_test_post(conn, platform="x", posted_at=None, project_id="proj_1"):
    """Insert a test post with a specific posted_at time.

    Uses raw SQL to set posted_at explicitly since insert_post() relies on
    SQLite's DEFAULT (datetime('now')) and ignores the model's posted_at field.
    """
    if posted_at is None:
        posted_at = datetime.now(timezone.utc)
    post_id = f"post_{posted_at.isoformat()}"
    conn.execute(
        "INSERT INTO posts (id, draft_id, project_id, platform, content, posted_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (post_id, "draft_test", project_id, platform, "test content", posted_at.isoformat()),
    )
    conn.commit()
    return post_id


@pytest.fixture
def db(tmp_path):
    """Create a temporary database."""
    db_path = tmp_path / "test.db"
    conn = init_database(db_path)
    # Seed a project so FK constraints are satisfied
    conn.execute(
        "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
        ("proj_1", "test-project", "/tmp/test"),
    )
    # Seed a decision and draft for FK constraints on posts
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
# _check_cross_account_gap tests
# =============================================================================


class TestCheckCrossAccountGap:
    """Tests for _check_cross_account_gap."""

    def test_gap_disabled_no_platform_settings(self, db):
        """Gap = 0 or no config -> disabled, no check."""
        config = _make_config(gap_minutes=0)
        draft = _make_draft(platform="x")
        assert _check_cross_account_gap(db, config, draft) is True

    def test_gap_disabled_platform_not_configured(self, db):
        """Platform not in platform_settings -> disabled."""
        config = _make_config(platform="linkedin", gap_minutes=30)
        draft = _make_draft(platform="x")
        assert _check_cross_account_gap(db, config, draft) is True

    def test_no_prior_posts(self, db):
        """No posts on the platform -> gap satisfied."""
        config = _make_config(platform="x", gap_minutes=30)
        draft = _make_draft(platform="x")
        assert _check_cross_account_gap(db, config, draft) is True

    @patch("social_hook.scheduler.random.randint", return_value=0)
    def test_gap_enforced_too_soon(self, mock_randint, db):
        """Post 5 min ago, gap = 30 min -> should be deferred."""
        config = _make_config(platform="x", gap_minutes=30)
        draft = _make_draft(platform="x")

        # Post 5 minutes ago
        _insert_test_post(
            db,
            platform="x",
            posted_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )

        assert _check_cross_account_gap(db, config, draft) is False

    @patch("social_hook.scheduler.random.randint", return_value=0)
    def test_gap_satisfied(self, mock_randint, db):
        """Post 45 min ago, gap = 30 min -> OK to post."""
        config = _make_config(platform="x", gap_minutes=30)
        draft = _make_draft(platform="x")

        _insert_test_post(
            db,
            platform="x",
            posted_at=datetime.now(timezone.utc) - timedelta(minutes=45),
        )

        assert _check_cross_account_gap(db, config, draft) is True

    @patch("social_hook.scheduler.random.randint", return_value=10)
    def test_jitter_applied(self, mock_randint, db):
        """Jitter makes effective gap = base + jitter. Mock randint to verify."""
        config = _make_config(platform="x", gap_minutes=30)
        draft = _make_draft(platform="x")

        # Post 35 min ago: base gap (30) satisfied, but with jitter (10) = 40 min needed
        _insert_test_post(
            db,
            platform="x",
            posted_at=datetime.now(timezone.utc) - timedelta(minutes=35),
        )

        assert _check_cross_account_gap(db, config, draft) is False
        mock_randint.assert_called_once_with(0, 9)  # int(30 * 0.33) = 9

    def test_different_platforms_no_gap(self, db):
        """Post on linkedin 1 min ago, checking x -> no gap between them."""
        config = _make_config(platform="x", gap_minutes=30)
        draft = _make_draft(platform="x")

        _insert_test_post(
            db,
            platform="linkedin",
            posted_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )

        assert _check_cross_account_gap(db, config, draft) is True

    @patch("social_hook.scheduler.random.randint", return_value=0)
    def test_two_accounts_same_platform_gap_enforced(self, mock_randint, db):
        """Two accounts on same platform -> gap enforced across both."""
        config = _make_config(platform="x", gap_minutes=30)
        draft = _make_draft(platform="x")

        # Post from a different project (simulating different account) 5 min ago
        conn = db
        conn.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj_2", "other-project", "/tmp/other"),
        )
        conn.execute(
            "INSERT INTO decisions (id, project_id, commit_hash, decision, reasoning) "
            "VALUES (?, ?, ?, ?, ?)",
            ("dec_2", "proj_2", "def456", "draft", "test"),
        )
        conn.execute(
            "INSERT INTO drafts (id, project_id, decision_id, platform, content, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("draft_test2", "proj_2", "dec_2", "x", "test2", "posted"),
        )
        conn.commit()
        _insert_test_post(
            db,
            platform="x",
            posted_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            project_id="proj_2",
        )

        assert _check_cross_account_gap(db, config, draft) is False

    @patch("social_hook.scheduler.random.randint", return_value=0)
    def test_single_account_gap_is_noop(self, mock_randint, db):
        """Single account on platform -> gap check passes when no recent posts."""
        config = _make_config(platform="x", gap_minutes=30)
        draft = _make_draft(platform="x")

        # No posts at all
        assert _check_cross_account_gap(db, config, draft) is True


# =============================================================================
# get_last_post_time_by_platform tests
# =============================================================================


class TestGetLastPostTimeByPlatform:
    """Tests for ops.get_last_post_time_by_platform."""

    def test_no_posts_returns_none(self, db):
        """No posts -> None."""
        result = ops.get_last_post_time_by_platform(db, "x")
        assert result is None

    def test_returns_most_recent(self, db):
        """Returns the most recent post time."""
        old = datetime.now(timezone.utc) - timedelta(hours=2)
        recent = datetime.now(timezone.utc) - timedelta(minutes=5)
        _insert_test_post(db, platform="x", posted_at=old)
        _insert_test_post(db, platform="x", posted_at=recent)

        result = ops.get_last_post_time_by_platform(db, "x")
        assert result is not None
        # Should be close to 'recent'
        diff = abs((result - recent).total_seconds())
        assert diff < 2  # Within 2 seconds due to ISO formatting precision

    def test_handles_sqlite_text_format(self, db):
        """Handle SQLite TEXT format (YYYY-MM-DD HH:MM:SS without timezone)."""
        # Insert with SQLite default format directly
        db.execute(
            "INSERT INTO posts (id, draft_id, project_id, platform, content, posted_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("post_text", "draft_test", "proj_1", "x", "test", "2026-03-24 04:30:00"),
        )
        db.commit()

        result = ops.get_last_post_time_by_platform(db, "x")
        assert result is not None
        assert result.tzinfo is not None  # Should have timezone set

    def test_handles_iso_format_with_timezone(self, db):
        """Handle ISO format with timezone info."""
        dt = datetime(2026, 3, 24, 5, 0, 0, tzinfo=timezone.utc)
        _insert_test_post(db, platform="x", posted_at=dt)

        result = ops.get_last_post_time_by_platform(db, "x")
        assert result is not None
        assert result.tzinfo is not None

    def test_filters_by_platform(self, db):
        """Only returns posts for the requested platform."""
        _insert_test_post(
            db,
            platform="linkedin",
            posted_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )

        result = ops.get_last_post_time_by_platform(db, "x")
        assert result is None


# =============================================================================
# get_drafts_by_cycle tests
# =============================================================================


class TestGetDraftsByCycle:
    """Tests for ops.get_drafts_by_cycle."""

    def test_no_drafts_returns_empty(self, db):
        """No matching drafts -> empty list."""
        result = ops.get_drafts_by_cycle(db, "cycle_nonexistent")
        assert result == []

    def test_returns_matching_drafts(self, db):
        """Returns drafts with matching evaluation_cycle_id."""
        cycle_id = "cycle_123"
        # Insert drafts with cycle_id
        db.execute(
            "INSERT INTO drafts (id, project_id, decision_id, platform, content, "
            "status, evaluation_cycle_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("draft_c1", "proj_1", "dec_1", "x", "content1", "draft", cycle_id),
        )
        db.execute(
            "INSERT INTO drafts (id, project_id, decision_id, platform, content, "
            "status, evaluation_cycle_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("draft_c2", "proj_1", "dec_1", "linkedin", "content2", "draft", cycle_id),
        )
        # Insert draft with different cycle
        db.execute(
            "INSERT INTO drafts (id, project_id, decision_id, platform, content, "
            "status, evaluation_cycle_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("draft_other", "proj_1", "dec_1", "x", "other", "draft", "cycle_other"),
        )
        db.commit()

        result = ops.get_drafts_by_cycle(db, cycle_id)
        assert len(result) == 2
        assert {d.id for d in result} == {"draft_c1", "draft_c2"}

    def test_returns_draft_objects(self, db):
        """Returns proper Draft model instances."""
        cycle_id = "cycle_456"
        db.execute(
            "INSERT INTO drafts (id, project_id, decision_id, platform, content, "
            "status, evaluation_cycle_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("draft_typed", "proj_1", "dec_1", "x", "typed content", "approved", cycle_id),
        )
        db.commit()

        result = ops.get_drafts_by_cycle(db, cycle_id)
        assert len(result) == 1
        draft = result[0]
        assert isinstance(draft, Draft)
        assert draft.id == "draft_typed"
        assert draft.status == "approved"
        assert draft.platform == "x"


# =============================================================================
# Content sequencing verification (routing.py)
# =============================================================================


class TestContentSequencing:
    """Verify routing.py orders targets correctly: primary first, then independent, then dependent."""

    def test_primary_targets_first(self):
        """Primary targets should be routed before secondary targets."""
        import tempfile

        from social_hook.config.targets import AccountConfig, TargetConfig
        from social_hook.config.yaml import Config
        from social_hook.llm.schemas import StrategyDecisionInput
        from social_hook.routing import route_to_targets

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = f"{tmpdir}/test.db"
            conn = init_database(db_path)

            config = Config.__new__(Config)
            config.accounts = {
                "acct-primary": AccountConfig(platform="x"),
                "acct-secondary": AccountConfig(platform="linkedin"),
            }
            config.targets = {
                "secondary-target": TargetConfig(
                    account="acct-secondary",
                    strategy="building-public",
                    primary=False,
                ),
                "primary-target": TargetConfig(
                    account="acct-primary",
                    strategy="building-public",
                    primary=True,
                ),
            }
            config.scheduling = Config.__new__(Config)
            config.scheduling.timezone = "UTC"
            config.scheduling.optimal_days = []
            config.scheduling.optimal_hours = []
            config.scheduling.max_per_week = 100

            decisions = {
                "building-public": StrategyDecisionInput(
                    action="draft",
                    reason="Test",
                ),
            }

            result = route_to_targets(decisions, config, conn)
            conn.close()

            # Primary should come first
            assert len(result) == 2
            assert result[0].target_name == "primary-target"
            assert result[1].target_name == "secondary-target"

    def test_dependent_targets_after_independent(self):
        """Targets with source dependency come after independent targets."""
        import tempfile

        from social_hook.config.targets import AccountConfig, TargetConfig
        from social_hook.config.yaml import Config
        from social_hook.llm.schemas import StrategyDecisionInput
        from social_hook.routing import route_to_targets

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = f"{tmpdir}/test.db"
            conn = init_database(db_path)

            config = Config.__new__(Config)
            config.accounts = {
                "acct-main": AccountConfig(platform="x"),
                "acct-qt": AccountConfig(platform="x"),
            }
            config.targets = {
                "qt-target": TargetConfig(
                    account="acct-qt",
                    strategy="building-public",
                    source="main-target",
                ),
                "main-target": TargetConfig(
                    account="acct-main",
                    strategy="building-public",
                    primary=True,
                ),
            }
            config.scheduling = Config.__new__(Config)
            config.scheduling.timezone = "UTC"
            config.scheduling.optimal_days = []
            config.scheduling.optimal_hours = []
            config.scheduling.max_per_week = 100

            decisions = {
                "building-public": StrategyDecisionInput(
                    action="draft",
                    reason="Test",
                ),
            }

            result = route_to_targets(decisions, config, conn)
            conn.close()

            # main-target first (independent), qt-target second (dependent)
            assert len(result) == 2
            assert result[0].target_name == "main-target"
            assert result[1].target_name == "qt-target"
