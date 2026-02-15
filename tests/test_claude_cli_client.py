"""Tests for ClaudeCliClient."""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from social_hook.errors import ConfigError, MalformedResponseError
from social_hook.llm.claude_cli import ClaudeCliClient
from social_hook.llm.base import NormalizedResponse, NormalizedToolCall, NormalizedUsage


SAMPLE_TOOL = {
    "name": "log_decision",
    "description": "Log a decision",
    "input_schema": {
        "type": "object",
        "properties": {"decision": {"type": "string"}},
        "required": ["decision"],
    },
}

SAMPLE_MESSAGES = [{"role": "user", "content": "Evaluate this commit"}]

VALID_ENVELOPE = {
    "structured_output": {"decision": "post_worthy"},
    "usage": {
        "input_tokens": 100,
        "output_tokens": 50,
        "cache_read_input_tokens": 10,
        "cache_creation_input_tokens": 5,
    },
}


def _mock_run_success(*args, **kwargs):
    """Create a mock subprocess result with valid JSON output."""
    mock = MagicMock()
    mock.returncode = 0
    mock.stdout = json.dumps(VALID_ENVELOPE)
    mock.stderr = ""
    return mock


class TestClaudeCliClientInit:
    def test_default_model(self):
        client = ClaudeCliClient()
        assert client.model == "sonnet"
        assert client.full_id == "claude-cli/sonnet"
        assert client.provider == "claude-cli"

    def test_custom_model(self):
        client = ClaudeCliClient(model="opus")
        assert client.model == "opus"
        assert client.full_id == "claude-cli/opus"


class TestCommandConstruction:
    @patch("social_hook.llm.claude_cli.subprocess.run", side_effect=_mock_run_success)
    def test_basic_command(self, mock_run):
        client = ClaudeCliClient(model="sonnet")
        client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "claude"
        assert cmd[1] == "-p"
        assert cmd[2] == "Evaluate this commit"
        assert "--model" in cmd
        assert "sonnet" in cmd
        assert "--output-format" in cmd
        assert "json" in cmd
        assert "--json-schema" in cmd
        assert "--tools" in cmd
        assert "--no-session-persistence" in cmd

    @patch("social_hook.llm.claude_cli.subprocess.run", side_effect=_mock_run_success)
    def test_system_prompt_included(self, mock_run):
        client = ClaudeCliClient()
        client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL], system="Be concise")

        cmd = mock_run.call_args[0][0]
        assert "--system-prompt" in cmd
        idx = cmd.index("--system-prompt")
        assert cmd[idx + 1] == "Be concise"

    @patch("social_hook.llm.claude_cli.subprocess.run", side_effect=_mock_run_success)
    def test_system_prompt_omitted_when_none(self, mock_run):
        client = ClaudeCliClient()
        client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        cmd = mock_run.call_args[0][0]
        assert "--system-prompt" not in cmd

    @patch("social_hook.llm.claude_cli.subprocess.run", side_effect=_mock_run_success)
    def test_schema_is_json_serialized(self, mock_run):
        client = ClaudeCliClient()
        client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        cmd = mock_run.call_args[0][0]
        idx = cmd.index("--json-schema")
        schema_str = cmd[idx + 1]
        parsed = json.loads(schema_str)
        assert parsed == SAMPLE_TOOL["input_schema"]

    @patch("social_hook.llm.claude_cli.subprocess.run", side_effect=_mock_run_success)
    def test_claudecode_env_var_removed(self, mock_run):
        client = ClaudeCliClient()
        with patch.dict("os.environ", {"CLAUDECODE": "1", "PATH": "/usr/bin"}):
            client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        env = mock_run.call_args[1]["env"]
        assert "CLAUDECODE" not in env
        assert "PATH" in env

    @patch("social_hook.llm.claude_cli.subprocess.run", side_effect=_mock_run_success)
    def test_timeout_set(self, mock_run):
        client = ClaudeCliClient()
        client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        assert mock_run.call_args[1]["timeout"] == 120


class TestResponseParsing:
    @patch("social_hook.llm.claude_cli.subprocess.run", side_effect=_mock_run_success)
    def test_structured_output_to_tool_call(self, mock_run):
        client = ClaudeCliClient()
        resp = client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        assert isinstance(resp, NormalizedResponse)
        assert len(resp.content) == 1
        tc = resp.content[0]
        assert isinstance(tc, NormalizedToolCall)
        assert tc.name == "log_decision"
        assert tc.input == {"decision": "post_worthy"}
        assert tc.type == "tool_use"

    @patch("social_hook.llm.claude_cli.subprocess.run", side_effect=_mock_run_success)
    def test_usage_parsed(self, mock_run):
        client = ClaudeCliClient()
        resp = client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        assert resp.usage.input_tokens == 100
        assert resp.usage.output_tokens == 50
        assert resp.usage.cache_read_input_tokens == 10
        assert resp.usage.cache_creation_input_tokens == 5

    @patch("social_hook.llm.claude_cli.subprocess.run")
    def test_missing_usage_defaults_to_zero(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"structured_output": {"decision": "skip"}}),
            stderr="",
        )
        client = ClaudeCliClient()
        resp = client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        assert resp.usage.input_tokens == 0
        assert resp.usage.output_tokens == 0

    @patch("social_hook.llm.claude_cli.subprocess.run", side_effect=_mock_run_success)
    def test_raw_envelope_preserved(self, mock_run):
        client = ClaudeCliClient()
        resp = client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        assert resp.raw == VALID_ENVELOPE


class TestErrorHandling:
    def test_multiple_tools_raises_config_error(self):
        client = ClaudeCliClient()
        with pytest.raises(ConfigError, match="exactly 1 tool schema"):
            client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL, SAMPLE_TOOL])

    @patch("social_hook.llm.claude_cli.subprocess.run", side_effect=FileNotFoundError)
    def test_cli_not_found_raises_config_error(self, mock_run):
        client = ClaudeCliClient()
        with pytest.raises(ConfigError, match="Claude CLI not found"):
            client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

    @patch("social_hook.llm.claude_cli.subprocess.run", side_effect=subprocess.TimeoutExpired("claude", 120))
    def test_timeout_raises_malformed(self, mock_run):
        client = ClaudeCliClient()
        with pytest.raises(MalformedResponseError, match="timed out"):
            client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

    @patch("social_hook.llm.claude_cli.subprocess.run")
    def test_nonzero_exit_raises_malformed(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="Some error")
        client = ClaudeCliClient()
        with pytest.raises(MalformedResponseError, match="Claude CLI error"):
            client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

    @patch("social_hook.llm.claude_cli.subprocess.run")
    def test_invalid_json_raises_malformed(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="not json{", stderr="")
        client = ClaudeCliClient()
        with pytest.raises(MalformedResponseError, match="invalid JSON"):
            client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

    @patch("social_hook.llm.claude_cli.subprocess.run")
    def test_missing_structured_output_raises_malformed(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"result": "something else"}),
            stderr="",
        )
        client = ClaudeCliClient()
        with pytest.raises(MalformedResponseError, match="No structured output"):
            client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])


class TestUsageLogging:
    @patch("social_hook.llm.claude_cli.subprocess.run", side_effect=_mock_run_success)
    def test_usage_logged_with_db(self, mock_run):
        client = ClaudeCliClient()
        mock_db = MagicMock()
        mock_db.insert_usage = MagicMock()

        client.complete(
            SAMPLE_MESSAGES,
            [SAMPLE_TOOL],
            operation_type="evaluate",
            db=mock_db,
            project_id="proj-123",
            commit_hash="abc123",
        )

        mock_db.insert_usage.assert_called_once()
        usage_log = mock_db.insert_usage.call_args[0][0]
        assert usage_log.model == "claude-cli/sonnet"
        assert usage_log.input_tokens == 100
        assert usage_log.output_tokens == 50
        assert usage_log.cost_cents == 0.0
        assert usage_log.project_id == "proj-123"
        assert usage_log.commit_hash == "abc123"

    @patch("social_hook.llm.claude_cli.subprocess.run", side_effect=_mock_run_success)
    def test_no_logging_without_db(self, mock_run):
        client = ClaudeCliClient()
        # Should not raise even without db
        resp = client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL], operation_type="evaluate")
        assert resp is not None

    @patch("social_hook.llm.claude_cli.subprocess.run", side_effect=_mock_run_success)
    def test_no_logging_without_operation_type(self, mock_run):
        client = ClaudeCliClient()
        mock_db = MagicMock()
        mock_db.insert_usage = MagicMock()

        client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL], db=mock_db)
        mock_db.insert_usage.assert_not_called()
