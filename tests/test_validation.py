"""Tests for validation functions."""

import json
from unittest.mock import MagicMock, patch

import pytest

from social_hook.setup.validation import validate_claude_cli


VALID_CLI_RESPONSE = [
    {"type": "result", "result": "{\"status\": \"ok\"}"},
]


class TestValidateClaudeCli:
    @patch("social_hook.setup.validation.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(VALID_CLI_RESPONSE),
            stderr="",
        )
        ok, msg = validate_claude_cli()
        assert ok is True
        assert msg == "Claude CLI working"

        # Verify command structure
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "claude"
        assert "-p" in cmd
        assert "--model" in cmd
        assert "haiku" in cmd
        assert "--output-format" in cmd

    @patch("social_hook.setup.validation.subprocess.run")
    def test_nonzero_exit(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="Error: something went wrong",
        )
        ok, msg = validate_claude_cli()
        assert ok is False
        assert "Claude CLI error" in msg

    @patch("social_hook.setup.validation.subprocess.run", side_effect=FileNotFoundError)
    def test_not_installed(self, mock_run):
        ok, msg = validate_claude_cli()
        assert ok is False
        assert "not found" in msg.lower()

    @patch("social_hook.setup.validation.subprocess.run")
    def test_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired("claude", 30)
        ok, msg = validate_claude_cli()
        assert ok is False
        assert "timed out" in msg.lower()

    @patch("social_hook.setup.validation.subprocess.run")
    def test_missing_structured_output(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps([{"type": "text", "text": "hello"}]),
            stderr="",
        )
        ok, msg = validate_claude_cli()
        assert ok is False
        assert "unexpected response" in msg.lower()

    @patch("social_hook.setup.validation.subprocess.run")
    def test_claudecode_env_removed(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(VALID_CLI_RESPONSE),
            stderr="",
        )
        with patch.dict("os.environ", {"CLAUDECODE": "1", "PATH": "/usr/bin"}):
            validate_claude_cli()

        env = mock_run.call_args[1]["env"]
        assert "CLAUDECODE" not in env
