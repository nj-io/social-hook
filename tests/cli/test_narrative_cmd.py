"""Tests for journey CLI sub-app and narrative-capture hidden command."""

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from social_hook.cli import app

runner = CliRunner()


# =============================================================================
# journey on / off / status
# =============================================================================


class TestJourneyOn:
    """Tests for 'journey on' command."""

    @patch("social_hook.setup.install.install_narrative_hook")
    @patch("social_hook.cli.journey.get_config_path")
    def test_enables_config_and_installs_hook(self, mock_config_path, mock_install, temp_dir):
        config_file = temp_dir / "config.yaml"
        config_file.write_text("models:\n  evaluator: anthropic/claude-opus-4-5\n")
        mock_config_path.return_value = config_file
        mock_install.return_value = (True, "Narrative hook installed")

        result = runner.invoke(app, ["journey", "on"])
        assert result.exit_code == 0
        assert "enabled" in result.output.lower()

        # Verify config was updated
        import yaml

        data = yaml.safe_load(config_file.read_text())
        assert data["journey_capture"]["enabled"] is True

        mock_install.assert_called_once()

    @patch("social_hook.setup.install.install_narrative_hook")
    @patch("social_hook.cli.journey.get_config_path")
    def test_creates_config_if_missing(self, mock_config_path, mock_install, temp_dir):
        config_file = temp_dir / "config.yaml"
        mock_config_path.return_value = config_file
        mock_install.return_value = (True, "Narrative hook installed")

        result = runner.invoke(app, ["journey", "on"])
        assert result.exit_code == 0
        assert config_file.exists()

        import yaml

        data = yaml.safe_load(config_file.read_text())
        assert data["journey_capture"]["enabled"] is True

    @patch("social_hook.setup.install.install_narrative_hook")
    @patch("social_hook.cli.journey.get_config_path")
    def test_warns_on_hook_install_failure(self, mock_config_path, mock_install, temp_dir):
        config_file = temp_dir / "config.yaml"
        mock_config_path.return_value = config_file
        mock_install.return_value = (False, "Could not read settings file")

        result = runner.invoke(app, ["journey", "on"])
        assert result.exit_code == 0
        assert "Warning" in result.output


class TestJourneyOff:
    """Tests for 'journey off' command."""

    @patch("social_hook.setup.install.uninstall_narrative_hook")
    @patch("social_hook.cli.journey.get_config_path")
    def test_disables_config_and_uninstalls_hook(self, mock_config_path, mock_uninstall, temp_dir):
        config_file = temp_dir / "config.yaml"
        config_file.write_text("journey_capture:\n  enabled: true\n")
        mock_config_path.return_value = config_file
        mock_uninstall.return_value = (True, "Narrative hook removed")

        result = runner.invoke(app, ["journey", "off"])
        assert result.exit_code == 0
        assert "disabled" in result.output.lower()

        import yaml

        data = yaml.safe_load(config_file.read_text())
        assert data["journey_capture"]["enabled"] is False

        mock_uninstall.assert_called_once()


class TestJourneyStatus:
    """Tests for 'journey status' command."""

    @patch("social_hook.cli.journey.shutil")
    @patch("social_hook.setup.install.check_narrative_hook_installed")
    @patch("social_hook.config.yaml.load_full_config")
    @patch("social_hook.cli.journey.get_narratives_path")
    def test_shows_status_enabled(
        self, mock_narr_path, mock_config, mock_hook, mock_shutil, temp_dir
    ):
        config = MagicMock()
        config.journey_capture.enabled = True
        mock_config.return_value = config
        mock_hook.return_value = True
        mock_shutil.which.return_value = "/usr/local/bin/claude"
        mock_narr_path.return_value = temp_dir
        # Create some narrative files
        (temp_dir / "proj1.jsonl").write_text("{}\n")
        (temp_dir / "proj2.jsonl").write_text("{}\n")

        result = runner.invoke(app, ["journey", "status"])
        assert result.exit_code == 0
        assert "yes" in result.output  # enabled: yes
        assert "detected" in result.output  # claude CLI detected

    @patch("social_hook.cli.journey.shutil")
    @patch("social_hook.setup.install.check_narrative_hook_installed")
    @patch("social_hook.config.yaml.load_full_config")
    @patch("social_hook.cli.journey.get_narratives_path")
    def test_shows_status_disabled(
        self, mock_narr_path, mock_config, mock_hook, mock_shutil, temp_dir
    ):
        config = MagicMock()
        config.journey_capture.enabled = False
        mock_config.return_value = config
        mock_hook.return_value = False
        mock_shutil.which.return_value = None
        mock_narr_path.return_value = temp_dir / "nonexistent"

        result = runner.invoke(app, ["journey", "status"])
        assert result.exit_code == 0
        assert "no" in result.output  # enabled: no
        assert "not found" in result.output  # claude CLI not found


# =============================================================================
# narrative-capture hidden command
# =============================================================================


class TestNarrativeCaptureDisabled:
    """narrative-capture exits silently when journey_capture is disabled."""

    @patch("social_hook.config.yaml.load_full_config")
    @patch("social_hook.filesystem.get_base_path")
    def test_disabled_config_exits_silently(self, mock_base_path, mock_config, temp_dir):
        mock_base_path.return_value = temp_dir
        config = MagicMock()
        config.journey_capture.enabled = False
        mock_config.return_value = config

        stdin_data = json.dumps(
            {"session_id": "s1", "transcript_path": "", "cwd": "/tmp", "trigger": "auto"}
        )
        result = runner.invoke(app, ["narrative-capture"], input=stdin_data)
        assert result.exit_code == 0


class TestNarrativeCaptureUnknownCwd:
    """narrative-capture exits silently when cwd is not a registered project."""

    @patch("social_hook.db.connection.init_database")
    @patch("social_hook.filesystem.get_db_path")
    @patch("social_hook.config.yaml.load_full_config")
    @patch("social_hook.filesystem.get_base_path")
    def test_unknown_cwd_exits_silently(
        self, mock_base_path, mock_config, mock_db_path, mock_init_db, temp_dir
    ):
        mock_base_path.return_value = temp_dir
        config = MagicMock()
        config.journey_capture.enabled = True
        config.journey_capture.model = None
        config.models.evaluator = "anthropic/claude-sonnet-4-5"
        mock_config.return_value = config
        mock_db_path.return_value = temp_dir / "test.db"

        from social_hook.db.connection import init_database as real_init_db

        conn = real_init_db(temp_dir / "test.db")
        mock_init_db.return_value = conn

        stdin_data = json.dumps(
            {
                "session_id": "s1",
                "transcript_path": "",
                "cwd": "/nonexistent/path/to/repo",
                "trigger": "auto",
            }
        )
        result = runner.invoke(app, ["narrative-capture"], input=stdin_data)
        assert result.exit_code == 0
        conn.close()


class TestNarrativeCapturePausedProject:
    """narrative-capture exits silently when project is paused."""

    @patch("social_hook.db.connection.init_database")
    @patch("social_hook.filesystem.get_db_path")
    @patch("social_hook.config.yaml.load_full_config")
    @patch("social_hook.filesystem.get_base_path")
    def test_paused_project_exits_silently(
        self, mock_base_path, mock_config, mock_db_path, mock_init_db, temp_dir
    ):
        mock_base_path.return_value = temp_dir
        config = MagicMock()
        config.journey_capture.enabled = True
        config.journey_capture.model = None
        config.models.evaluator = "anthropic/claude-sonnet-4-5"
        mock_config.return_value = config
        mock_db_path.return_value = temp_dir / "test.db"

        from social_hook.db.connection import init_database as real_init_db
        from social_hook.db.operations import insert_project
        from social_hook.filesystem import generate_id
        from social_hook.models.core import Project

        conn = real_init_db(temp_dir / "test.db")
        mock_init_db.return_value = conn

        cwd = "/tmp/paused-repo"
        project = Project(
            id=generate_id("project"),
            name="paused",
            repo_path=cwd,
            paused=True,
        )
        insert_project(conn, project)

        stdin_data = json.dumps(
            {
                "session_id": "s1",
                "transcript_path": "",
                "cwd": cwd,
                "trigger": "auto",
            }
        )
        result = runner.invoke(app, ["narrative-capture"], input=stdin_data)
        assert result.exit_code == 0
        conn.close()


class TestNarrativeCaptureHaikuReject:
    """narrative-capture exits silently with warning when model is Haiku."""

    @patch("social_hook.db.connection.init_database")
    @patch("social_hook.filesystem.get_db_path")
    @patch("social_hook.config.yaml.load_full_config")
    @patch("social_hook.filesystem.get_base_path")
    def test_haiku_model_exits_with_warning(
        self, mock_base_path, mock_config, mock_db_path, mock_init_db, temp_dir
    ):
        mock_base_path.return_value = temp_dir
        config = MagicMock()
        config.journey_capture.enabled = True
        config.journey_capture.model = "anthropic/claude-haiku-4-5"
        mock_config.return_value = config
        mock_db_path.return_value = temp_dir / "test.db"

        from social_hook.db.connection import init_database as real_init_db
        from social_hook.db.operations import insert_project
        from social_hook.filesystem import generate_id
        from social_hook.models.core import Project

        conn = real_init_db(temp_dir / "test.db")
        mock_init_db.return_value = conn

        cwd = "/tmp/haiku-repo"
        project = Project(
            id=generate_id("project"),
            name="haiku-test",
            repo_path=cwd,
        )
        insert_project(conn, project)

        stdin_data = json.dumps(
            {
                "session_id": "s1",
                "transcript_path": "",
                "cwd": cwd,
                "trigger": "auto",
            }
        )
        result = runner.invoke(app, ["narrative-capture"], input=stdin_data)
        assert result.exit_code == 0
        conn.close()


class TestNarrativeCaptureHelpHidden:
    """narrative-capture should not appear in --help output."""

    def test_hidden_from_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "narrative-capture" not in result.output


class TestJourneySubAppRegistered:
    """journey sub-app should appear in --help output."""

    def test_journey_in_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "journey" in result.output

    def test_journey_help(self):
        result = runner.invoke(app, ["journey", "--help"])
        assert result.exit_code == 0
        assert "on" in result.output
        assert "off" in result.output
        assert "status" in result.output
