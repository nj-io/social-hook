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
