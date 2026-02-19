"""Tests for trigger pipeline (T29)."""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from social_hook.db import init_database, insert_project
from social_hook.filesystem import generate_id
from social_hook.models import Project
from social_hook.trigger import (
    git_remote_origin,
    parse_commit_info,
    run_trigger,
    send_telegram_notification,
)


class TestParseCommitInfo:
    """Tests for parse_commit_info."""

    def test_parse_valid_commit(self, temp_dir):
        """Parse a real git commit in a temp repo."""
        repo = temp_dir / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", str(repo)], capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "test@test.com"],
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "Test"],
            capture_output=True,
        )

        # Create a file and commit
        (repo / "test.py").write_text("print('hello')")
        subprocess.run(["git", "-C", str(repo), "add", "."], capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "Initial commit"],
            capture_output=True,
        )

        # Get commit hash
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True,
        )
        commit_hash = result.stdout.strip()

        commit = parse_commit_info(commit_hash, str(repo))
        assert commit.hash == commit_hash
        assert commit.message == "Initial commit"

    def test_parse_nonexistent_commit(self, temp_dir):
        """Gracefully handles nonexistent commit."""
        commit = parse_commit_info("nonexistent", str(temp_dir))
        assert commit.hash == "nonexistent"
        assert "(unable to parse)" in commit.message


class TestGitRemoteOrigin:
    """Tests for git_remote_origin."""

    def test_no_remote(self, temp_dir):
        """Returns None for repo without remote."""
        repo = temp_dir / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", str(repo)], capture_output=True)
        assert git_remote_origin(str(repo)) is None

    def test_with_remote(self, temp_dir):
        """Returns origin URL."""
        repo = temp_dir / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", str(repo)], capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo), "remote", "add", "origin",
             "git@github.com:user/repo.git"],
            capture_output=True,
        )
        assert git_remote_origin(str(repo)) == "git@github.com:user/repo.git"

    def test_non_git_directory(self, temp_dir):
        """Returns None for non-git directory."""
        assert git_remote_origin(str(temp_dir)) is None


class TestSendTelegramNotification:
    """Tests for send_telegram_notification."""

    @patch("social_hook.trigger.requests.post")
    def test_successful_send(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        result = send_telegram_notification("token", "123", "Hello")
        assert result is True
        mock_post.assert_called_once()

    @patch("social_hook.trigger.requests.post")
    def test_failed_send(self, mock_post):
        mock_post.return_value = MagicMock(status_code=400)
        result = send_telegram_notification("token", "123", "Hello")
        assert result is False

    @patch("social_hook.trigger.requests.post")
    def test_network_error(self, mock_post):
        import requests
        mock_post.side_effect = requests.RequestException("Connection failed")
        result = send_telegram_notification("token", "123", "Hello")
        assert result is False


class TestRunTrigger:
    """Tests for run_trigger."""

    @patch("social_hook.trigger.load_full_config")
    def test_config_error_returns_1(self, mock_config):
        """Config error returns exit code 1."""
        from social_hook.errors import ConfigError
        mock_config.side_effect = ConfigError("bad config")
        exit_code = run_trigger("abc123", "/tmp/nonexistent")
        assert exit_code == 1

    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_db_error_returns_2(self, mock_config, mock_db):
        """DB error returns exit code 2."""
        from social_hook.errors import DatabaseError
        mock_config.return_value = MagicMock()
        mock_db.side_effect = DatabaseError("db error")
        exit_code = run_trigger("abc123", "/tmp/nonexistent")
        assert exit_code == 2

    @patch("social_hook.trigger.ops.get_project_by_origin")
    @patch("social_hook.trigger.git_remote_origin")
    @patch("social_hook.trigger.ops.get_project_by_path")
    @patch("social_hook.trigger.get_db_path")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_unregistered_repo_returns_0(
        self, mock_config, mock_db, mock_db_path, mock_by_path, mock_origin, mock_by_origin
    ):
        """Unregistered repo exits silently with 0."""
        mock_config.return_value = MagicMock()
        mock_db.return_value = MagicMock()
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = None
        mock_origin.return_value = None
        mock_by_origin.return_value = []

        exit_code = run_trigger("abc123", "/tmp/nonexistent")
        assert exit_code == 0

    @patch("social_hook.trigger.ops.get_project_by_path")
    @patch("social_hook.trigger.get_db_path")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_paused_project_returns_0(
        self, mock_config, mock_db, mock_db_path, mock_by_path
    ):
        """Paused project exits with 0."""
        mock_config.return_value = MagicMock()
        mock_db.return_value = MagicMock()
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(
            id="p1", name="test", repo_path="/tmp", paused=True,
        )

        exit_code = run_trigger("abc123", "/tmp")
        assert exit_code == 0


class TestTriggerUsesAdapter:
    """Tests that trigger notification uses TelegramAdapter."""

    @patch("social_hook.messaging.telegram.TelegramAdapter.send_message")
    @patch("social_hook.bot.commands.set_chat_draft_context")
    @patch("social_hook.trigger.calculate_optimal_time")
    @patch("social_hook.llm.drafter.Drafter")
    @patch("social_hook.llm.evaluator.Evaluator")
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.config.project.load_project_config")
    @patch("social_hook.trigger.assemble_evaluator_context")
    @patch("social_hook.trigger.parse_commit_info")
    @patch("social_hook.trigger.ops.get_project_by_path")
    @patch("social_hook.trigger.get_db_path")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_trigger_sends_via_adapter(
        self, mock_config, mock_init_db, mock_db_path, mock_by_path,
        mock_parse, mock_context, mock_proj_config, mock_create_client,
        mock_evaluator_cls, mock_drafter_cls, mock_schedule,
        mock_set_context, mock_adapter_send,
    ):
        """run_trigger uses TelegramAdapter.send_message instead of direct HTTP."""
        from datetime import datetime
        from social_hook.messaging.base import SendResult

        # Config with Telegram env vars
        cfg = MagicMock()
        cfg.platforms.x.enabled = True
        cfg.platforms.x.account_tier = "free"
        cfg.platforms.linkedin.enabled = False
        cfg.scheduling.timezone = "UTC"
        cfg.scheduling.max_posts_per_day = 3
        cfg.scheduling.min_gap_minutes = 30
        cfg.scheduling.optimal_days = None
        cfg.scheduling.optimal_hours = None
        cfg.env.get = lambda key, default="": {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "TELEGRAM_ALLOWED_CHAT_IDS": "111,222",
        }.get(key, default)
        mock_config.return_value = cfg

        mock_init_db.return_value = MagicMock()
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(
            id="p1", name="test-proj", repo_path="/tmp",
        )

        # Commit
        commit = MagicMock()
        commit.hash = "abc12345"
        commit.message = "Add feature"
        mock_parse.return_value = commit

        mock_context.return_value = {}
        mock_proj_config.return_value = MagicMock()

        # Evaluator says post-worthy
        evaluator_instance = MagicMock()
        evaluation = MagicMock()
        evaluation.decision = "post_worthy"
        evaluation.reasoning = "Good commit"
        evaluation.angle = "new feature"
        evaluation.episode_type = "launch"
        evaluation.post_category = "arc"
        evaluation.arc_id = None
        evaluation.media_tool = None
        evaluation.platforms = {}
        evaluator_instance.evaluate.return_value = evaluation
        mock_evaluator_cls.return_value = evaluator_instance

        # Drafter
        drafter_instance = MagicMock()
        draft_result = MagicMock()
        draft_result.content = "Check out this feature!"
        draft_result.reasoning = "Short and punchy"
        draft_result.format_hint = "single"
        draft_result.beat_count = 1
        drafter_instance.create_draft.return_value = draft_result
        mock_drafter_cls.return_value = drafter_instance

        # Schedule
        schedule = MagicMock()
        schedule.datetime = datetime(2026, 2, 20, 12, 0, 0)
        schedule.time_reason = "optimal"
        mock_schedule.return_value = schedule

        # Adapter send returns success
        mock_adapter_send.return_value = SendResult(success=True, message_id="m1")

        exit_code = run_trigger("abc12345", "/tmp", dry_run=False)
        assert exit_code == 0

        # TelegramAdapter.send_message should have been called for each chat ID
        assert mock_adapter_send.call_count == 2
        # Verify it was called with chat IDs "111" and "222"
        call_chat_ids = [c.args[0] for c in mock_adapter_send.call_args_list]
        assert "111" in call_chat_ids
        assert "222" in call_chat_ids
