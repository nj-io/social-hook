"""Tests for cli/logs.py commands and _init_logging wiring."""

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from social_hook.cli import app

runner = CliRunner()


# =============================================================================
# _init_logging tests
# =============================================================================


class TestInitLogging:
    """Verify _init_logging calls setup_logging with correct args."""

    @patch("social_hook.logging.setup_logging")
    @patch("social_hook.filesystem.get_db_path", return_value="/tmp/test.db")
    @patch("social_hook.config.load_full_config")
    @patch("social_hook.error_feed.error_feed")
    def test_init_logging_basic(self, mock_feed, mock_config, mock_db, mock_setup):
        from social_hook.cli import _init_logging

        _init_logging("cli")

        mock_feed.set_db_path.assert_called_once_with("/tmp/test.db")
        mock_setup.assert_called_once_with(
            "cli",
            error_feed=mock_feed,
            notification_sender=None,
            console=True,
        )

    @patch("social_hook.logging.setup_logging")
    @patch("social_hook.filesystem.get_db_path", return_value="/tmp/test.db")
    @patch("social_hook.config.load_full_config")
    @patch("social_hook.error_feed.error_feed")
    @patch("social_hook.notifications.send_notification")
    def test_init_logging_with_notify(self, mock_send, mock_feed, mock_config, mock_db, mock_setup):
        from social_hook.cli import _init_logging

        _init_logging("trigger", notify=True)

        # notification_sender should be set (a lambda)
        call_args = mock_setup.call_args
        assert call_args[1]["notification_sender"] is not None
        assert call_args[0] == ("trigger",)

    @patch("social_hook.logging.setup_logging")
    @patch("social_hook.config.load_full_config", side_effect=Exception("no config"))
    def test_init_logging_config_failure(self, mock_config, mock_setup):
        from social_hook.cli import _init_logging

        # Should not raise, just disable DB/notification sinks
        _init_logging("cli")

        mock_setup.assert_called_once_with(
            "cli",
            error_feed=None,
            notification_sender=None,
            console=True,
        )

    @patch("social_hook.logging.setup_logging")
    @patch("social_hook.filesystem.get_db_path", return_value="/tmp/test.db")
    @patch("social_hook.config.load_full_config")
    @patch("social_hook.error_feed.error_feed")
    def test_init_logging_console_false(self, mock_feed, mock_config, mock_db, mock_setup):
        from social_hook.cli import _init_logging

        _init_logging("trigger", console=False, notify=True)

        call_args = mock_setup.call_args
        assert call_args[1]["console"] is False


# =============================================================================
# logs (default command — query)
# =============================================================================


class TestLogsQuery:
    """Tests for 'social-hook logs' default query command."""

    @patch("social_hook.cli.logs._get_conn")
    def test_no_errors(self, mock_conn):
        conn = MagicMock()
        mock_conn.return_value = conn
        with patch("social_hook.db.operations.get_recent_system_errors", return_value=[]):
            result = runner.invoke(app, ["logs"])
            assert result.exit_code == 0
            assert "No system errors" in result.output

    @patch("social_hook.cli.logs._get_conn")
    def test_shows_errors(self, mock_conn):
        conn = MagicMock()
        mock_conn.return_value = conn

        mock_record = MagicMock()
        mock_record.severity = "error"
        mock_record.component = "trigger"
        mock_record.source = "auth"
        mock_record.message = "Token expired"
        mock_record.created_at = "2026-03-26 10:00:00"
        mock_record.to_dict.return_value = {
            "severity": "error",
            "component": "trigger",
            "source": "auth",
            "message": "Token expired",
            "created_at": "2026-03-26 10:00:00",
        }

        with patch(
            "social_hook.db.operations.get_recent_system_errors", return_value=[mock_record]
        ):
            result = runner.invoke(app, ["logs"])
            assert result.exit_code == 0
            assert "error" in result.output
            assert "Token expired" in result.output

    @patch("social_hook.cli.logs._get_conn")
    def test_json_output(self, mock_conn):
        conn = MagicMock()
        mock_conn.return_value = conn

        mock_record = MagicMock()
        mock_record.to_dict.return_value = {
            "severity": "error",
            "message": "fail",
        }

        with patch(
            "social_hook.db.operations.get_recent_system_errors", return_value=[mock_record]
        ):
            result = runner.invoke(app, ["logs", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "errors" in data
            assert data["errors"][0]["severity"] == "error"

    @patch("social_hook.cli.logs._get_conn")
    def test_filters_passed(self, mock_conn):
        conn = MagicMock()
        mock_conn.return_value = conn

        with patch(
            "social_hook.db.operations.get_recent_system_errors", return_value=[]
        ) as mock_get:
            result = runner.invoke(
                app, ["logs", "--severity", "error", "--component", "trigger", "--limit", "10"]
            )
            assert result.exit_code == 0
            mock_get.assert_called_once_with(
                conn, limit=10, severity="error", component="trigger", source=None
            )


# =============================================================================
# logs tail
# =============================================================================


class TestLogsTail:
    """Tests for 'social-hook logs tail' command."""

    @patch("social_hook.cli.logs.subprocess")
    def test_tail_with_component(self, mock_subprocess, temp_dir):
        logs_dir = temp_dir / "logs"
        logs_dir.mkdir()
        (logs_dir / "trigger.log").write_text("test log line\n")

        with patch("social_hook.filesystem.get_base_path", return_value=temp_dir):
            result = runner.invoke(app, ["logs", "tail", "trigger"])
            assert result.exit_code == 0
            mock_subprocess.run.assert_called_once()
            cmd = mock_subprocess.run.call_args[0][0]
            assert "tail" in cmd
            assert str(logs_dir / "trigger.log") in cmd

    def test_tail_invalid_component(self, temp_dir):
        logs_dir = temp_dir / "logs"
        logs_dir.mkdir()

        with patch("social_hook.filesystem.get_base_path", return_value=temp_dir):
            result = runner.invoke(app, ["logs", "tail", "invalid"])
            assert result.exit_code == 1
            assert "Unknown component" in result.output

    def test_tail_no_logs_dir(self, temp_dir):
        with patch("social_hook.filesystem.get_base_path", return_value=temp_dir):
            result = runner.invoke(app, ["logs", "tail"])
            assert result.exit_code == 1
            assert "not found" in result.output


# =============================================================================
# logs health
# =============================================================================


class TestLogsHealth:
    """Tests for 'social-hook logs health' command."""

    @patch("social_hook.cli.logs._get_conn")
    def test_healthy(self, mock_conn):
        conn = MagicMock()
        mock_conn.return_value = conn

        with patch(
            "social_hook.db.operations.get_error_health_status",
            return_value={"info": 0, "warning": 0, "error": 0, "critical": 0},
        ):
            result = runner.invoke(app, ["logs", "health"])
            assert result.exit_code == 0
            assert "healthy" in result.output

    @patch("social_hook.cli.logs._get_conn")
    def test_degraded(self, mock_conn):
        conn = MagicMock()
        mock_conn.return_value = conn

        with patch(
            "social_hook.db.operations.get_error_health_status",
            return_value={"info": 0, "warning": 2, "error": 3, "critical": 0},
        ):
            result = runner.invoke(app, ["logs", "health"])
            assert result.exit_code == 0
            assert "degraded" in result.output

    @patch("social_hook.cli.logs._get_conn")
    def test_health_json(self, mock_conn):
        conn = MagicMock()
        mock_conn.return_value = conn

        with patch(
            "social_hook.db.operations.get_error_health_status",
            return_value={"info": 1, "warning": 0, "error": 0, "critical": 0},
        ):
            result = runner.invoke(app, ["logs", "health", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["status"] == "healthy"
            assert data["total_24h"] == 1
            assert data["by_severity"]["info"] == 1

    @patch("social_hook.cli.logs._get_conn")
    def test_health_global_json_flag(self, mock_conn):
        """Test that global --json flag works for health subcommand."""
        conn = MagicMock()
        mock_conn.return_value = conn

        with patch(
            "social_hook.db.operations.get_error_health_status",
            return_value={"info": 0, "warning": 0, "error": 0, "critical": 0},
        ):
            result = runner.invoke(app, ["--json", "logs", "health"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "status" in data
