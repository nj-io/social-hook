"""Tests for manual CLI commands (T35)."""

from unittest.mock import MagicMock, patch

from social_hook.config.platforms import OutputPlatformConfig
from social_hook.config.yaml import Config
from social_hook.db import init_database, insert_decision, insert_draft, insert_project
from social_hook.filesystem import generate_id
from social_hook.models import Decision, Draft, Project


def _make_config(**overrides):
    """Create a Config with sensible defaults for testing."""
    config = Config()
    if "platforms" in overrides:
        config.platforms = overrides["platforms"]
    return config


def _make_config_no_platforms():
    """Config with no enabled platforms."""
    return Config(
        platforms={
            "x": OutputPlatformConfig(enabled=False, priority="primary", type="builtin"),
        }
    )


class TestDraftCommand:
    """Tests for manual draft command."""

    @patch("social_hook.filesystem.get_db_path")
    @patch("social_hook.config.load_full_config")
    def test_draft_not_found(self, mock_config, mock_db_path, temp_dir):
        from typer.testing import CliRunner

        from social_hook.cli.manual import app

        db_path = temp_dir / "test.db"
        mock_db_path.return_value = db_path
        mock_config.return_value = Config()
        init_database(db_path)

        runner = CliRunner()
        result = runner.invoke(app, ["draft", "nonexistent_id"])
        assert result.exit_code == 1

    @patch("social_hook.filesystem.get_db_path")
    @patch("social_hook.config.load_full_config")
    def test_draft_not_post_worthy_creates_drafts(self, mock_config, mock_db_path, temp_dir):
        """Manual draft overrides not_post_worthy decisions (no rejection)."""
        from typer.testing import CliRunner

        from social_hook.cli.manual import app

        db_path = temp_dir / "test.db"
        mock_db_path.return_value = db_path
        config = _make_config()
        mock_config.return_value = config
        conn = init_database(db_path)

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)
        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc",
            decision="skip",
            reasoning="boring",
        )
        insert_decision(conn, decision)
        conn.close()

        # Mock the drafting pipeline since we don't have real LLM/git
        with (
            patch("social_hook.trigger.parse_commit_info") as mock_parse,
            patch("social_hook.config.project.load_project_config") as mock_proj_config,
            patch("social_hook.llm.prompts.assemble_evaluator_context") as mock_ctx,
            patch("social_hook.drafting.draft_for_platforms") as mock_draft,
        ):
            mock_parse.return_value = MagicMock(timestamp=None, parent_timestamp=None)
            mock_proj_config.return_value = MagicMock()
            mock_ctx.return_value = MagicMock()
            mock_draft.return_value = []

            runner = CliRunner()
            result = runner.invoke(app, ["draft", decision.id])
            # Should NOT exit with 1 (no post_worthy rejection)
            assert result.exit_code == 0
            # draft_for_platforms should have been called
            mock_draft.assert_called_once()

    @patch("social_hook.filesystem.get_db_path")
    @patch("social_hook.config.load_full_config")
    def test_draft_no_enabled_platforms_uses_preview(self, mock_config, mock_db_path, temp_dir):
        """Draft with no enabled platforms falls back to preview platform."""
        from typer.testing import CliRunner

        from social_hook.cli.manual import app

        db_path = temp_dir / "test.db"
        mock_db_path.return_value = db_path
        mock_config.return_value = _make_config_no_platforms()
        init_database(db_path)

        runner = CliRunner()
        # Decision won't exist, so exits with "not found" — but doesn't
        # exit early with "no enabled platforms" anymore
        result = runner.invoke(app, ["draft", "some_id"])
        assert "not found" in result.output.lower()

    @patch("social_hook.filesystem.get_db_path")
    @patch("social_hook.config.load_full_config")
    def test_draft_platform_not_enabled(self, mock_config, mock_db_path, temp_dir):
        """Draft with --platform targeting a disabled platform errors."""
        from typer.testing import CliRunner

        from social_hook.cli.manual import app

        db_path = temp_dir / "test.db"
        mock_db_path.return_value = db_path
        mock_config.return_value = _make_config_no_platforms()
        init_database(db_path)

        runner = CliRunner()
        result = runner.invoke(app, ["draft", "some_id", "--platform", "x"])
        assert result.exit_code == 1
        assert "not enabled" in result.output.lower()


class TestConsolidateCommand:
    """Tests for manual consolidate command."""

    @patch("social_hook.config.load_full_config")
    def test_consolidate_fewer_than_2_ids(self, mock_config):
        """Consolidate with < 2 IDs exits with error."""
        from typer.testing import CliRunner

        from social_hook.cli.manual import app

        mock_config.return_value = _make_config()

        runner = CliRunner()
        result = runner.invoke(app, ["consolidate", "only_one_id"])
        assert result.exit_code == 1
        assert "at least 2" in result.output.lower()

    @patch("social_hook.filesystem.get_db_path")
    @patch("social_hook.config.load_full_config")
    def test_consolidate_different_projects(self, mock_config, mock_db_path, temp_dir):
        """Consolidate decisions from different projects errors."""
        from typer.testing import CliRunner

        from social_hook.cli.manual import app

        db_path = temp_dir / "test.db"
        mock_db_path.return_value = db_path
        mock_config.return_value = _make_config()
        conn = init_database(db_path)

        proj1 = Project(id=generate_id("project"), name="p1", repo_path="/tmp/p1")
        proj2 = Project(id=generate_id("project"), name="p2", repo_path="/tmp/p2")
        insert_project(conn, proj1)
        insert_project(conn, proj2)

        d1 = Decision(
            id=generate_id("decision"),
            project_id=proj1.id,
            commit_hash="aaa",
            decision="skip",
            reasoning="r1",
        )
        d2 = Decision(
            id=generate_id("decision"),
            project_id=proj2.id,
            commit_hash="bbb",
            decision="skip",
            reasoning="r2",
        )
        insert_decision(conn, d1)
        insert_decision(conn, d2)
        conn.close()

        runner = CliRunner()
        result = runner.invoke(app, ["consolidate", d1.id, d2.id])
        assert result.exit_code == 1
        assert "same project" in result.output.lower()

    @patch("social_hook.filesystem.get_db_path")
    @patch("social_hook.config.load_full_config")
    def test_consolidate_decision_not_found(self, mock_config, mock_db_path, temp_dir):
        """Consolidate with missing decision ID errors."""
        from typer.testing import CliRunner

        from social_hook.cli.manual import app

        db_path = temp_dir / "test.db"
        mock_db_path.return_value = db_path
        mock_config.return_value = _make_config()
        init_database(db_path)

        runner = CliRunner()
        result = runner.invoke(app, ["consolidate", "fake_id_1", "fake_id_2"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


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
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc",
            decision="draft",
            reasoning="good",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Test",
            status="posted",
        )
        insert_draft(conn, draft)
        conn.close()

        runner = CliRunner()
        result = runner.invoke(app, ["post", draft.id])
        assert result.exit_code == 1
        assert "must be" in result.output.lower()
