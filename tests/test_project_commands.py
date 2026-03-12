"""Tests for project CLI commands (T34)."""

import subprocess
from unittest.mock import MagicMock, patch

from social_hook.db import (
    init_database,
    insert_project,
)
from social_hook.filesystem import generate_id
from social_hook.models import Project


class TestRegisterCommand:
    """Tests for project register."""

    @patch("social_hook.filesystem.get_db_path")
    @patch("social_hook.config.load_full_config")
    def test_register_git_repo(self, mock_config, mock_db_path, temp_dir):
        from typer.testing import CliRunner

        from social_hook.cli.project import app

        # Create a git repo
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

        db_path = temp_dir / "test.db"
        mock_config.return_value = MagicMock()
        mock_db_path.return_value = db_path

        # Init database at expected path
        init_database(db_path)

        runner = CliRunner()
        result = runner.invoke(app, ["register", str(repo)])

        # Should succeed
        assert result.exit_code == 0 or "Registered" in result.output

    @patch("social_hook.filesystem.get_db_path")
    @patch("social_hook.config.load_full_config")
    def test_register_non_git_dir(self, mock_config, mock_db_path, temp_dir):
        from typer.testing import CliRunner

        from social_hook.cli.project import app

        db_path = temp_dir / "test.db"
        mock_config.return_value = MagicMock()
        mock_db_path.return_value = db_path
        init_database(db_path)

        runner = CliRunner()
        result = runner.invoke(app, ["register", str(temp_dir)])
        assert result.exit_code == 1


class TestUnregisterCommand:
    """Tests for project unregister."""

    @patch("social_hook.filesystem.get_db_path")
    def test_unregister_with_force(self, mock_db_path, temp_dir):
        from typer.testing import CliRunner

        from social_hook.cli.project import app

        db_path = temp_dir / "test.db"
        mock_db_path.return_value = db_path
        conn = init_database(db_path)

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)
        conn.close()

        runner = CliRunner()
        result = runner.invoke(app, ["unregister", project.id, "--force"])
        assert "unregistered" in result.output.lower() or result.exit_code == 0

    @patch("social_hook.filesystem.get_db_path")
    def test_unregister_not_found(self, mock_db_path, temp_dir):
        from typer.testing import CliRunner

        from social_hook.cli.project import app

        db_path = temp_dir / "test.db"
        mock_db_path.return_value = db_path
        init_database(db_path)

        runner = CliRunner()
        result = runner.invoke(app, ["unregister", "nonexistent", "--force"])
        assert result.exit_code == 1


class TestListCommand:
    """Tests for project list."""

    @patch("social_hook.filesystem.get_db_path")
    def test_list_empty(self, mock_db_path, temp_dir):
        from typer.testing import CliRunner

        from social_hook.cli.project import app

        db_path = temp_dir / "test.db"
        mock_db_path.return_value = db_path
        init_database(db_path)

        runner = CliRunner()
        result = runner.invoke(app, ["list"])
        assert "no registered" in result.output.lower()

    @patch("social_hook.filesystem.get_db_path")
    def test_list_with_projects(self, mock_db_path, temp_dir):
        from typer.testing import CliRunner

        from social_hook.cli.project import app

        db_path = temp_dir / "test.db"
        mock_db_path.return_value = db_path
        conn = init_database(db_path)

        project = Project(id=generate_id("project"), name="my-project", repo_path="/tmp/test")
        insert_project(conn, project)
        conn.close()

        runner = CliRunner()
        result = runner.invoke(app, ["list"])
        assert "my-project" in result.output
