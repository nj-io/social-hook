"""Tests for the `web` CLI command."""

import re
from unittest.mock import patch

from typer.testing import CliRunner

from social_hook.cli import app

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


runner = CliRunner()


class TestWebCommand:
    def test_web_command_exists(self):
        """Verify the web command is registered in the CLI app."""
        result = runner.invoke(app, ["web", "--help"])
        assert result.exit_code == 0
        assert "web dashboard" in strip_ansi(result.output).lower()

    def test_web_help_text(self):
        """Verify help text mentions relevant options."""
        result = runner.invoke(app, ["web", "--help"])
        assert result.exit_code == 0
        output = strip_ansi(result.output)
        assert "--port" in output
        assert "--api-port" in output
        assert "--host" in output
        assert "--install" in output

    @patch("shutil.which", return_value=None)
    def test_web_requires_node(self, mock_which):
        """Verify error when Node.js is not found."""
        result = runner.invoke(app, ["web"])
        assert result.exit_code == 1
        assert "Node.js" in result.output
