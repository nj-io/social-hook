"""Tests for targets integration (Chunk 6) — scheduler wiring, error feed, backward compat."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from social_hook.config.targets import (
    AccountConfig,
    PlatformCredentialConfig,
    TargetConfig,
)
from social_hook.config.yaml import load_config
from social_hook.error_feed import ErrorFeed, ErrorSeverity


def _write_config(tmp_path: Path, data: dict) -> Path:
    """Write a config dict to a YAML file and return the path."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(data, default_flow_style=False))
    return config_path


OLD_FORMAT_CONFIG = {
    "models": {
        "evaluator": "anthropic/claude-opus-4-5",
        "drafter": "anthropic/claude-sonnet-4-5",
        "gatekeeper": "anthropic/claude-haiku-4-5",
    },
    "platforms": {
        "x": {
            "enabled": True,
            "priority": "primary",
            "account_tier": "free",
        },
    },
    "content_strategies": {
        "building-public": {"audience": "devs", "voice": "casual"},
    },
    "content_strategy": "building-public",
}

NEW_FORMAT_CONFIG = {
    "models": {
        "evaluator": "anthropic/claude-opus-4-5",
        "drafter": "anthropic/claude-sonnet-4-5",
        "gatekeeper": "anthropic/claude-haiku-4-5",
    },
    "identities": {
        "dev": {"type": "myself", "label": "Developer"},
    },
    "default_identity": "dev",
    "content_strategies": {
        "building-public": {
            "audience": "devs",
            "voice": "casual",
            "angle": "behind-the-scenes",
            "format_preference": "single",
        },
    },
    "platform_credentials": {
        "x-app": {
            "platform": "x",
            "client_id": "test-id",
            "client_secret": "test-secret",
        },
    },
    "accounts": {
        "my-x": {
            "platform": "x",
            "app": "x-app",
            "tier": "basic",
            "identity": "dev",
        },
    },
    "targets": {
        "main-feed": {
            "account": "my-x",
            "destination": "timeline",
            "strategy": "building-public",
            "primary": True,
        },
    },
    "max_targets": 5,
}


class TestAutoMigrationIntegration:
    """Old-format config auto-migrates and all sections are accessible."""

    def test_old_format_loads_and_auto_migrates(self, tmp_path):
        config_path = _write_config(tmp_path, OLD_FORMAT_CONFIG)
        config = load_config(config_path)

        # Legacy platforms still work
        assert "x" in config.platforms
        assert config.platforms["x"].enabled is True

        # Auto-migrated sections created
        assert "x" in config.accounts
        assert config.accounts["x"].platform == "x"
        assert config.accounts["x"].tier == "free"
        assert "x" in config.targets
        assert config.targets["x"].primary is True
        assert config.targets["x"].strategy == "building-public"
        assert "x" in config.platform_credentials


class TestNewFormatIntegration:
    """New-format config loads all sections correctly."""

    def test_new_format_all_sections_accessible(self, tmp_path):
        config_path = _write_config(tmp_path, NEW_FORMAT_CONFIG)
        config = load_config(config_path)

        # Platform credentials
        assert "x-app" in config.platform_credentials
        assert config.platform_credentials["x-app"].client_id == "test-id"

        # Accounts
        assert "my-x" in config.accounts
        assert config.accounts["my-x"].tier == "basic"

        # Targets
        assert "main-feed" in config.targets
        assert config.targets["main-feed"].primary is True

        # Strategies expanded
        cs = config.content_strategies["building-public"]
        assert cs.angle == "behind-the-scenes"
        assert cs.format_preference == "single"

        # Max targets
        assert config.max_targets == 5


class TestErrorFeedWiring:
    """Test error feed integration patterns."""

    def test_error_feed_emit_with_db(self, tmp_path):
        """Error feed writes to DB when db_path is set."""
        from social_hook.db.connection import init_database

        db_path = str(tmp_path / "test.db")
        conn = init_database(db_path)
        conn.close()

        feed = ErrorFeed(db_path=db_path)
        feed.emit(ErrorSeverity.ERROR, "test error", source="scheduler")

        recent = feed.get_recent(limit=10)
        assert len(recent) == 1
        assert recent[0].message == "test error"
        assert recent[0].source == "scheduler"

    def test_error_feed_sender_fires_on_critical(self):
        """CRITICAL errors trigger the sender callback."""
        sent = []
        feed = ErrorFeed()
        feed.set_sender(lambda sev, msg: sent.append((sev, msg)))

        feed.emit(ErrorSeverity.CRITICAL, "critical failure", source="auth")

        assert len(sent) == 1
        assert sent[0][0] == "critical"
        assert "critical failure" in sent[0][1]

    def test_error_feed_sender_not_fired_on_info(self):
        """INFO errors do not trigger the sender callback."""
        sent = []
        feed = ErrorFeed()
        feed.set_sender(lambda sev, msg: sent.append((sev, msg)))

        feed.emit(ErrorSeverity.INFO, "just info")

        assert len(sent) == 0


class TestSchedulerPostDraftTargetBranching:
    """Test that _post_draft uses target_id when available."""

    def test_post_draft_legacy_path_no_target(self):
        """When draft has no target_id, legacy path is used."""
        from social_hook.adapters.models import PostResult
        from social_hook.scheduler import _post_draft

        mock_draft = MagicMock()
        mock_draft.platform = "x"
        mock_draft.preview_mode = False
        mock_draft.target_id = None
        mock_draft.content = "test content"
        mock_draft.decision_id = None
        mock_draft.media_paths = None
        mock_draft.post_format = None
        mock_draft.reference_post_id = None

        mock_config = MagicMock()
        mock_config.targets = {}

        mock_adapter = MagicMock()
        mock_adapter.post.return_value = PostResult(success=True, external_id="123")

        with patch("social_hook.scheduler._registry") as mock_registry:
            mock_registry.get.return_value = mock_adapter
            result = _post_draft(MagicMock(), mock_draft, mock_config, db_path="/tmp/test.db")

        assert result.success
        mock_registry.get.assert_called_once()

    def test_post_draft_target_path_with_target_id(self):
        """When draft has target_id matching config, targets path is used."""
        from social_hook.adapters.models import PostResult
        from social_hook.scheduler import _post_draft

        mock_draft = MagicMock()
        mock_draft.platform = "x"
        mock_draft.preview_mode = False
        mock_draft.target_id = "main-feed"
        mock_draft.content = "test content"
        mock_draft.decision_id = None
        mock_draft.media_paths = None
        mock_draft.post_format = None
        mock_draft.reference_post_id = None

        mock_config = MagicMock()
        mock_config.targets = {
            "main-feed": TargetConfig(account="my-x", strategy="bp"),
        }
        mock_config.accounts = {
            "my-x": AccountConfig(platform="x"),
        }
        mock_config.platform_credentials = {
            "x-app": PlatformCredentialConfig(platform="x", client_id="id", client_secret="sec"),
        }
        mock_config.env = {}

        mock_adapter = MagicMock()
        mock_adapter.post.return_value = PostResult(success=True, external_id="456")

        with patch("social_hook.scheduler._registry") as mock_registry:
            mock_registry.get_for_account.return_value = mock_adapter
            result = _post_draft(MagicMock(), mock_draft, mock_config, db_path="/tmp/test.db")

        assert result.success
        mock_registry.get_for_account.assert_called_once()


class TestPostTargetIdPropagation:
    """Test that target_id propagates from Draft to Post."""

    def test_record_post_success_propagates_target_id(self):
        """record_post_success creates Post with draft's target_id."""
        from social_hook.adapters.models import PostResult
        from social_hook.scheduler import record_post_success

        mock_draft = MagicMock()
        mock_draft.id = "draft-1"
        mock_draft.project_id = "proj-1"
        mock_draft.platform = "x"
        mock_draft.content = "test"
        mock_draft.target_id = "main-feed"

        mock_result = PostResult(success=True, external_id="ext-1", external_url="https://x.com/1")
        mock_config = MagicMock()
        mock_conn = MagicMock()

        with (
            patch("social_hook.scheduler.ops"),
            patch("social_hook.scheduler.send_notification"),
            patch("social_hook.scheduler.generate_id", return_value="post-1"),
        ):
            post = record_post_success(
                mock_conn, mock_draft, mock_result, mock_config, "TestProject"
            )

        assert post.target_id == "main-feed"

    def test_record_post_success_none_target_id(self):
        """record_post_success handles None target_id (legacy drafts)."""
        from social_hook.adapters.models import PostResult
        from social_hook.scheduler import record_post_success

        mock_draft = MagicMock()
        mock_draft.id = "draft-2"
        mock_draft.project_id = "proj-2"
        mock_draft.platform = "x"
        mock_draft.content = "legacy"
        mock_draft.target_id = None

        mock_result = PostResult(success=True, external_id="ext-2", external_url="https://x.com/2")
        mock_config = MagicMock()
        mock_conn = MagicMock()

        with (
            patch("social_hook.scheduler.ops"),
            patch("social_hook.scheduler.send_notification"),
            patch("social_hook.scheduler.generate_id", return_value="post-2"),
        ):
            post = record_post_success(
                mock_conn, mock_draft, mock_result, mock_config, "TestProject"
            )

        assert post.target_id is None

    def test_record_post_success_db_round_trip(self, tmp_path):
        """target_id persists to DB when record_post_success writes the Post."""
        from social_hook.adapters.models import PostResult
        from social_hook.db.connection import init_database
        from social_hook.scheduler import record_post_success

        db_path = tmp_path / "test.db"
        conn = init_database(db_path)

        from social_hook.db import operations as ops
        from social_hook.filesystem import generate_id
        from social_hook.models import Decision, Draft, Project

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        ops.insert_project(conn, project)
        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc123",
            decision="draft",
            reasoning="test",
        )
        ops.insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Test post",
            status="scheduled",
            target_id="my-target",
        )
        ops.insert_draft(conn, draft)

        mock_result = PostResult(
            success=True, external_id="ext-99", external_url="https://x.com/99"
        )
        mock_config = MagicMock(channels={})

        with patch("social_hook.scheduler.send_notification"):
            post = record_post_success(
                conn, draft, mock_result, mock_config, project.name, dry_run=True
            )

        assert post.target_id == "my-target"

        # Verify in DB
        db_post = ops.get_post(conn, post.id)
        assert db_post is not None
        assert db_post.target_id == "my-target"
        conn.close()


class TestPreviewDraftBlocked:
    """Preview-mode drafts cannot be posted."""

    def test_preview_returns_failure(self):
        """_post_draft returns error for preview-mode draft."""
        from social_hook.scheduler import _post_draft

        mock_draft = MagicMock()
        mock_draft.platform = "x"
        mock_draft.preview_mode = True
        mock_draft.target_id = None

        result = _post_draft(MagicMock(), mock_draft, MagicMock(), db_path=None)
        assert result.success is False
        assert "account" in result.error.lower()


class TestMissingAccountInTargetPath:
    """When target references nonexistent account, return error."""

    def test_missing_account_returns_error(self):
        """_post_draft returns error when target's account is missing."""
        from social_hook.scheduler import _post_draft

        mock_draft = MagicMock()
        mock_draft.platform = "x"
        mock_draft.preview_mode = False
        mock_draft.target_id = "my-target"

        mock_config = MagicMock()
        mock_config.targets = {
            "my-target": TargetConfig(account="ghost", strategy="s"),
        }
        mock_config.accounts = {}  # account "ghost" not present

        result = _post_draft(MagicMock(), mock_draft, mock_config, db_path="/tmp/t.db")
        assert result.success is False
        assert "ghost" in result.error
