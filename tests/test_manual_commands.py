"""Tests for manual CLI commands (T35)."""

from unittest.mock import MagicMock, patch

import pytest

from social_hook.db import init_database, insert_decision, insert_draft, insert_project
from social_hook.filesystem import generate_id
from social_hook.models import Decision, Draft, Project


class TestDraftCommand:
    """Tests for manual draft command."""

    @patch("social_hook.filesystem.get_db_path")
    def test_draft_not_found(self, mock_db_path, temp_dir):
        from typer.testing import CliRunner
        from social_hook.cli.manual import app

        db_path = temp_dir / "test.db"
        mock_db_path.return_value = db_path
        init_database(db_path)

        runner = CliRunner()
        result = runner.invoke(app, ["draft", "nonexistent_id"])
        assert result.exit_code == 1

    @patch("social_hook.filesystem.get_db_path")
    def test_draft_not_post_worthy(self, mock_db_path, temp_dir):
        from typer.testing import CliRunner
        from social_hook.cli.manual import app

        db_path = temp_dir / "test.db"
        mock_db_path.return_value = db_path
        conn = init_database(db_path)

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)
        decision = Decision(
            id=generate_id("decision"), project_id=project.id,
            commit_hash="abc", decision="not_post_worthy", reasoning="boring",
        )
        insert_decision(conn, decision)
        conn.close()

        runner = CliRunner()
        result = runner.invoke(app, ["draft", decision.id])
        assert result.exit_code == 1


class TestPostCommand:
    """Tests for manual post command."""

    @patch("social_hook.filesystem.get_db_path")
    @patch("social_hook.config.load_full_config")
    def test_post_not_found(self, mock_config, mock_db_path, temp_dir):
        from typer.testing import CliRunner
        from social_hook.cli.manual import app

        db_path = temp_dir / "test.db"
        mock_db_path.return_value = db_path
        mock_config.return_value = MagicMock()
        init_database(db_path)

        runner = CliRunner()
        result = runner.invoke(app, ["post", "nonexistent_id"])
        assert result.exit_code == 1

    @patch("social_hook.filesystem.get_db_path")
    @patch("social_hook.config.load_full_config")
    def test_post_wrong_status(self, mock_config, mock_db_path, temp_dir):
        from typer.testing import CliRunner
        from social_hook.cli.manual import app

        db_path = temp_dir / "test.db"
        mock_db_path.return_value = db_path
        mock_config.return_value = MagicMock()
        conn = init_database(db_path)

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)
        decision = Decision(
            id=generate_id("decision"), project_id=project.id,
            commit_hash="abc", decision="post_worthy", reasoning="good",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"), project_id=project.id,
            decision_id=decision.id, platform="x", content="Test", status="draft",
        )
        insert_draft(conn, draft)
        conn.close()

        runner = CliRunner()
        result = runner.invoke(app, ["post", draft.id])
        assert result.exit_code == 1
        assert "must be" in result.output.lower()
