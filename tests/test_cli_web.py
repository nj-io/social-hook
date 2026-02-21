"""Tests for the `web` CLI command."""

from unittest.mock import patch

from typer.testing import CliRunner

from social_hook.cli import app

runner = CliRunner()


class TestWebCommand:
    def test_web_command_exists(self):
        """Verify the web command is registered in the CLI app."""
        result = runner.invoke(app, ["web", "--help"])
        assert result.exit_code == 0
        assert "web dashboard" in result.output.lower()

    def test_web_help_text(self):
        """Verify help text mentions relevant options."""
        result = runner.invoke(app, ["web", "--help"])
        assert result.exit_code == 0
        assert "--port" in result.output
        assert "--api-port" in result.output
        assert "--host" in result.output
        assert "--install" in result.output

    @patch("shutil.which", return_value=None)
    def test_web_requires_node(self, mock_which):
        """Verify error when Node.js is not found."""
        result = runner.invoke(app, ["web"])
        assert result.exit_code == 1
        assert "Node.js" in result.output
