"""Tests for ClaudeCliClient."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from social_hook.errors import ConfigError, MalformedResponseError
from social_hook.llm.base import NormalizedResponse, NormalizedToolCall
from social_hook.llm.claude_cli import ClaudeCliClient, _extract_json

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

# stream-json NDJSON format: one JSON object per line
SYSTEM_EVENT = {"type": "system", "subtype": "init"}

TEXT_DELTA_EVENT = {
    "type": "stream_event",
    "event": {
        "type": "content_block_delta",
        "index": 0,
        "delta": {
            "type": "text_delta",
            "text": '{"decision": "post_worthy"}',
        },
    },
}

INPUT_JSON_DELTA_EVENT = {
    "type": "stream_event",
    "event": {
        "type": "content_block_delta",
        "index": 0,
        "delta": {"type": "input_json_delta", "partial_json": '{"decision": "post_worthy"}'},
    },
}

RESULT_EVENT = {
    "type": "result",
    "subtype": "success",
    "result": '{"decision": "post_worthy"}',
    "usage": {
        "input_tokens": 100,
        "output_tokens": 50,
        "cache_read_input_tokens": 10,
        "cache_creation_input_tokens": 5,
    },
}


def _make_ndjson(*events):
    """Create NDJSON string from event objects."""
    return "\n".join(json.dumps(e) for e in events)


# Default valid NDJSON output with text delta + result
VALID_NDJSON = _make_ndjson(SYSTEM_EVENT, TEXT_DELTA_EVENT, RESULT_EVENT)


def _make_mock_popen(returncode=0, stdout=None, stderr=""):
    """Create a mock Popen that returns the given output on communicate()."""
    if stdout is None:
        stdout = VALID_NDJSON
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = (stdout, stderr)
    mock_proc.returncode = returncode
    mock_proc.kill = MagicMock()
    mock_proc.wait = MagicMock()
    return mock_proc


def _capture_system_prompt(mock_popen, mock_proc):
    """Set up a Popen side_effect that captures the system prompt file content.

    The temp file is deleted in complete()'s finally block, so we must read it
    during the Popen call (while the file still exists).

    Returns a dict with a 'content' key that will be populated after complete() runs.
    """
    captured = {"content": None, "path": None}

    def side_effect(cmd, **kwargs):
        idx = cmd.index("--system-prompt-file")
        path = cmd[idx + 1]
        captured["path"] = path
        captured["content"] = Path(path).read_text(encoding="utf-8")
        return mock_proc

    mock_popen.side_effect = side_effect
    return captured


class TestExtractJson:
    def test_raw_json(self):
        result = _extract_json('{"decision": "post_worthy"}')
        assert result == {"decision": "post_worthy"}

    def test_json_in_code_fence(self):
        text = '```json\n{"decision": "post_worthy"}\n```'
        result = _extract_json(text)
        assert result == {"decision": "post_worthy"}

    def test_json_in_plain_code_fence(self):
        text = '```\n{"decision": "post_worthy"}\n```'
        result = _extract_json(text)
        assert result == {"decision": "post_worthy"}

    def test_json_embedded_in_text(self):
        text = 'Here is the evaluation:\n{"decision": "post_worthy"}\nDone.'
        result = _extract_json(text)
        assert result == {"decision": "post_worthy"}

    def test_json_with_whitespace(self):
        result = _extract_json('  \n{"decision": "post_worthy"}\n  ')
        assert result == {"decision": "post_worthy"}

    def test_no_json_raises(self):
        with pytest.raises(MalformedResponseError, match="Could not extract JSON"):
            _extract_json("no json here at all")

    def test_nested_json(self):
        text = '{"decision": "post_worthy", "meta": {"count": 1}}'
        result = _extract_json(text)
        assert result == {"decision": "post_worthy", "meta": {"count": 1}}


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
    @patch("social_hook.llm.claude_cli.subprocess.Popen")
    def test_basic_command(self, mock_popen):
        mock_proc = _make_mock_popen()
        _capture_system_prompt(mock_popen, mock_proc)
        client = ClaudeCliClient(model="sonnet")
        client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        cmd = mock_popen.call_args[0][0]
        assert cmd[0] == "claude"
        assert cmd[1] == "-p"
        # Prompt is piped via stdin, not as a CLI argument
        assert "Evaluate this commit" not in cmd
        assert "--model" in cmd
        assert "sonnet" in cmd
        assert "--output-format" in cmd
        assert "stream-json" in cmd
        assert "--tools" in cmd
        assert "--no-session-persistence" in cmd
        # Must NOT use --json-schema (causes multi-turn validation loops)
        assert "--json-schema" not in cmd
        # Must use --system-prompt-file, not --system-prompt (avoids ARG_MAX)
        assert "--system-prompt-file" in cmd
        assert "--system-prompt" not in cmd
        # Verify prompt sent via stdin
        mock_proc.communicate.assert_called_once()
        call_kwargs = mock_proc.communicate.call_args
        assert call_kwargs[1]["input"] == "Evaluate this commit"

    @patch("social_hook.llm.claude_cli.subprocess.Popen")
    def test_system_prompt_includes_json_instructions(self, mock_popen):
        mock_proc = _make_mock_popen()
        captured = _capture_system_prompt(mock_popen, mock_proc)
        client = ClaudeCliClient()
        client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL], system="Be concise")

        system_prompt = captured["content"]
        # Original system prompt is preserved
        assert "Be concise" in system_prompt
        # JSON instructions are appended
        assert "Required Output Format" in system_prompt
        assert '"decision"' in system_prompt  # Schema embedded

    @patch("social_hook.llm.claude_cli.subprocess.Popen")
    def test_system_prompt_has_json_instructions_when_no_system(self, mock_popen):
        mock_proc = _make_mock_popen()
        captured = _capture_system_prompt(mock_popen, mock_proc)
        client = ClaudeCliClient()
        client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        system_prompt = captured["content"]
        assert "Required Output Format" in system_prompt

    @patch("social_hook.llm.claude_cli.subprocess.Popen")
    def test_schema_embedded_in_system_prompt(self, mock_popen):
        mock_proc = _make_mock_popen()
        captured = _capture_system_prompt(mock_popen, mock_proc)
        client = ClaudeCliClient()
        client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        system_prompt = captured["content"]
        # The full schema should be embedded in the system prompt file
        assert '"type": "object"' in system_prompt
        assert '"decision"' in system_prompt
        assert '"required"' in system_prompt

    @patch("social_hook.llm.claude_cli.subprocess.Popen")
    def test_claudecode_env_var_removed(self, mock_popen):
        mock_popen.return_value = _make_mock_popen()
        client = ClaudeCliClient()
        with patch.dict("os.environ", {"CLAUDECODE": "1", "PATH": "/usr/bin"}):
            client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        env = mock_popen.call_args[1]["env"]
        assert "CLAUDECODE" not in env
        assert "PATH" in env

    @patch("social_hook.llm.claude_cli.subprocess.Popen")
    def test_timeout_set(self, mock_popen):
        mock_popen.return_value = _make_mock_popen()
        client = ClaudeCliClient()
        client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        mock_popen.return_value.communicate.assert_called_once_with(
            input="Evaluate this commit",
            timeout=300,
        )

    @patch("social_hook.llm.claude_cli.subprocess.Popen")
    def test_runs_in_new_session(self, mock_popen):
        mock_popen.return_value = _make_mock_popen()
        client = ClaudeCliClient()
        client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        assert mock_popen.call_args[1]["start_new_session"] is True


class TestSystemPromptFileCleanup:
    """Verify the temp file is cleaned up on all exit paths."""

    @patch("social_hook.llm.claude_cli.subprocess.Popen")
    def test_file_cleaned_up_on_success(self, mock_popen):
        mock_proc = _make_mock_popen()
        captured = _capture_system_prompt(mock_popen, mock_proc)
        client = ClaudeCliClient()
        client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        assert captured["path"] is not None
        assert not Path(captured["path"]).exists(), "Temp file should be deleted after success"

    @patch("social_hook.llm.claude_cli.subprocess.Popen")
    def test_file_cleaned_up_on_nonzero_exit(self, mock_popen):
        mock_proc = _make_mock_popen(returncode=1, stderr="Some error")
        captured = _capture_system_prompt(mock_popen, mock_proc)
        client = ClaudeCliClient()

        with pytest.raises(MalformedResponseError):
            client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        assert captured["path"] is not None
        assert not Path(captured["path"]).exists(), "Temp file should be deleted after error"

    @patch("social_hook.llm.claude_cli.subprocess.Popen")
    def test_file_cleaned_up_on_timeout(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.communicate.side_effect = subprocess.TimeoutExpired("claude", 300)
        mock_proc.kill = MagicMock()
        mock_proc.wait = MagicMock()
        captured = _capture_system_prompt(mock_popen, mock_proc)
        client = ClaudeCliClient()

        with pytest.raises(MalformedResponseError, match="timed out"):
            client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        assert captured["path"] is not None
        assert not Path(captured["path"]).exists(), "Temp file should be deleted after timeout"

    @patch("social_hook.llm.claude_cli.subprocess.Popen", side_effect=FileNotFoundError)
    def test_file_cleaned_up_when_cli_not_found(self, mock_popen):
        """Temp file is created before Popen — must be cleaned up even if CLI is missing."""
        client = ClaudeCliClient()

        # Track the temp file via os.write mock
        written_paths = []
        original_mkstemp = __import__("tempfile").mkstemp

        def tracking_mkstemp(**kwargs):
            fd, path = original_mkstemp(**kwargs)
            written_paths.append(path)
            return fd, path

        with (
            patch("social_hook.llm.claude_cli.tempfile.mkstemp", side_effect=tracking_mkstemp),
            pytest.raises(ConfigError, match="Claude CLI not found"),
        ):
            client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        assert len(written_paths) == 1
        assert not Path(written_paths[0]).exists(), "Temp file should be deleted when CLI not found"


class TestResponseParsing:
    @patch("social_hook.llm.claude_cli.subprocess.Popen")
    def test_text_delta_to_tool_call(self, mock_popen):
        """Text from stream_event content_block_delta is parsed into a tool call."""
        mock_popen.return_value = _make_mock_popen()
        client = ClaudeCliClient()
        resp = client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        assert isinstance(resp, NormalizedResponse)
        assert len(resp.content) == 1
        tc = resp.content[0]
        assert isinstance(tc, NormalizedToolCall)
        assert tc.name == "log_decision"
        assert tc.input == {"decision": "post_worthy"}
        assert tc.type == "tool_use"

    @patch("social_hook.llm.claude_cli.subprocess.Popen")
    def test_multiple_text_deltas_accumulated(self, mock_popen):
        """Multiple text deltas are joined to form the complete response."""
        delta1 = {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": '{"decision":'},
            },
        }
        delta2 = {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": ' "post_worthy"}'},
            },
        }
        ndjson = _make_ndjson(SYSTEM_EVENT, delta1, delta2, RESULT_EVENT)
        mock_popen.return_value = _make_mock_popen(stdout=ndjson)
        client = ClaudeCliClient()
        resp = client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        assert resp.content[0].input == {"decision": "post_worthy"}

    @patch("social_hook.llm.claude_cli.subprocess.Popen")
    def test_thinking_deltas_ignored(self, mock_popen):
        """Thinking deltas are not included in the text output."""
        thinking_delta = {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "Let me think..."},
            },
        }
        ndjson = _make_ndjson(SYSTEM_EVENT, thinking_delta, TEXT_DELTA_EVENT, RESULT_EVENT)
        mock_popen.return_value = _make_mock_popen(stdout=ndjson)
        client = ClaudeCliClient()
        resp = client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        assert resp.content[0].input == {"decision": "post_worthy"}

    @patch("social_hook.llm.claude_cli.subprocess.Popen")
    def test_usage_parsed(self, mock_popen):
        mock_popen.return_value = _make_mock_popen()
        client = ClaudeCliClient()
        resp = client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        assert resp.usage.input_tokens == 100
        assert resp.usage.output_tokens == 50
        assert resp.usage.cache_read_input_tokens == 10
        assert resp.usage.cache_creation_input_tokens == 5

    @patch("social_hook.llm.claude_cli.subprocess.Popen")
    def test_missing_usage_defaults_to_zero(self, mock_popen):
        """Result event without usage field defaults to zero tokens."""
        result_no_usage = {"type": "result", "subtype": "success", "result": "ignored"}
        ndjson = _make_ndjson(SYSTEM_EVENT, TEXT_DELTA_EVENT, result_no_usage)
        mock_popen.return_value = _make_mock_popen(stdout=ndjson)
        client = ClaudeCliClient()
        resp = client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        assert resp.usage.input_tokens == 0
        assert resp.usage.output_tokens == 0

    @patch("social_hook.llm.claude_cli.subprocess.Popen")
    def test_raw_envelope_preserved(self, mock_popen):
        mock_popen.return_value = _make_mock_popen()
        client = ClaudeCliClient()
        resp = client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        assert resp.raw == RESULT_EVENT

    @patch("social_hook.llm.claude_cli.subprocess.Popen")
    def test_fallback_to_result_field(self, mock_popen):
        """When no text deltas, falls back to the result field."""
        result_only = {
            "type": "result",
            "subtype": "success",
            "result": '{"decision": "post_worthy"}',
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        ndjson = _make_ndjson(SYSTEM_EVENT, result_only)
        mock_popen.return_value = _make_mock_popen(stdout=ndjson)
        client = ClaudeCliClient()
        resp = client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        assert resp.content[0].input == {"decision": "post_worthy"}

    @patch("social_hook.llm.claude_cli.subprocess.Popen")
    def test_json_in_code_fence_parsed(self, mock_popen):
        """Model outputs JSON in markdown code fence — still works."""
        delta = {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "index": 0,
                "delta": {
                    "type": "text_delta",
                    "text": '```json\n{"decision": "post_worthy"}\n```',
                },
            },
        }
        ndjson = _make_ndjson(SYSTEM_EVENT, delta, RESULT_EVENT)
        mock_popen.return_value = _make_mock_popen(stdout=ndjson)
        client = ClaudeCliClient()
        resp = client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        assert resp.content[0].input == {"decision": "post_worthy"}


class TestErrorHandling:
    def test_multiple_tools_raises_config_error(self):
        client = ClaudeCliClient()
        with pytest.raises(ConfigError, match="exactly 1 tool schema"):
            client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL, SAMPLE_TOOL])

    @patch("social_hook.llm.claude_cli.subprocess.Popen", side_effect=FileNotFoundError)
    def test_cli_not_found_raises_config_error(self, mock_popen):
        client = ClaudeCliClient()
        with pytest.raises(ConfigError, match="Claude CLI not found"):
            client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

    @patch("social_hook.llm.claude_cli.subprocess.Popen")
    def test_timeout_raises_malformed(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.communicate.side_effect = subprocess.TimeoutExpired("claude", 300)
        mock_proc.kill = MagicMock()
        mock_proc.wait = MagicMock()
        mock_popen.return_value = mock_proc

        client = ClaudeCliClient()
        with pytest.raises(MalformedResponseError, match="timed out"):
            client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        mock_proc.kill.assert_called_once()

    @patch("social_hook.llm.claude_cli.subprocess.Popen")
    def test_keyboard_interrupt_kills_process(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.communicate.side_effect = KeyboardInterrupt
        mock_proc.kill = MagicMock()
        mock_proc.wait = MagicMock()
        mock_popen.return_value = mock_proc

        client = ClaudeCliClient()
        with pytest.raises(KeyboardInterrupt):
            client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        mock_proc.kill.assert_called_once()

    @patch("social_hook.llm.claude_cli.subprocess.Popen")
    def test_nonzero_exit_raises_malformed(self, mock_popen):
        mock_popen.return_value = _make_mock_popen(returncode=1, stderr="Some error")
        client = ClaudeCliClient()
        with pytest.raises(MalformedResponseError, match="Claude CLI error"):
            client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

    @patch("social_hook.llm.claude_cli.subprocess.Popen")
    def test_no_text_content_raises_malformed(self, mock_popen):
        """No text deltas and no result field raises error."""
        ndjson = _make_ndjson(SYSTEM_EVENT, {"type": "result", "subtype": "success"})
        mock_popen.return_value = _make_mock_popen(stdout=ndjson)
        client = ClaudeCliClient()
        with pytest.raises(MalformedResponseError, match="No text content"):
            client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

    @patch("social_hook.llm.claude_cli.subprocess.Popen")
    def test_unparseable_result_raises_malformed(self, mock_popen):
        """Result field with non-JSON text raises error when no deltas present."""
        result = {
            "type": "result",
            "subtype": "success",
            "result": "not json at all",
        }
        ndjson = _make_ndjson(SYSTEM_EVENT, result)
        mock_popen.return_value = _make_mock_popen(stdout=ndjson)
        client = ClaudeCliClient()
        with pytest.raises(MalformedResponseError, match="Could not extract JSON"):
            client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

    @patch("social_hook.llm.claude_cli.subprocess.Popen")
    def test_garbage_stdout_raises_malformed(self, mock_popen):
        """Complete garbage stdout (no valid NDJSON lines) raises error."""
        mock_popen.return_value = _make_mock_popen(stdout="not json at all{")
        client = ClaudeCliClient()
        with pytest.raises(MalformedResponseError, match="No text content"):
            client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])


class TestInputJsonDelta:
    """Tests for input_json_delta parsing in the NDJSON stream."""

    @patch("social_hook.llm.claude_cli.subprocess.Popen")
    def test_input_json_delta_parsed(self, mock_popen):
        """input_json_delta events are parsed into a tool call."""
        ndjson = _make_ndjson(SYSTEM_EVENT, INPUT_JSON_DELTA_EVENT, RESULT_EVENT)
        mock_popen.return_value = _make_mock_popen(stdout=ndjson)
        client = ClaudeCliClient()
        resp = client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        assert isinstance(resp, NormalizedResponse)
        assert len(resp.content) == 1
        tc = resp.content[0]
        assert isinstance(tc, NormalizedToolCall)
        assert tc.name == "log_decision"
        assert tc.input == {"decision": "post_worthy"}

    @patch("social_hook.llm.claude_cli.subprocess.Popen")
    def test_multiple_input_json_deltas_accumulated(self, mock_popen):
        """Multiple input_json_delta events with chunked partial_json are reassembled."""
        delta1 = {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "input_json_delta", "partial_json": '{"decision":'},
            },
        }
        delta2 = {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "input_json_delta", "partial_json": ' "post_worthy"}'},
            },
        }
        ndjson = _make_ndjson(SYSTEM_EVENT, delta1, delta2, RESULT_EVENT)
        mock_popen.return_value = _make_mock_popen(stdout=ndjson)
        client = ClaudeCliClient()
        resp = client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        assert resp.content[0].input == {"decision": "post_worthy"}

    @patch("social_hook.llm.claude_cli.subprocess.Popen")
    def test_mixed_text_and_input_json_blocks(self, mock_popen):
        """text_delta and input_json_delta at the same index are both accumulated."""
        text_block = {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": '{"decision":'},
            },
        }
        tool_block = {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "input_json_delta", "partial_json": ' "post_worthy"}'},
            },
        }
        ndjson = _make_ndjson(SYSTEM_EVENT, text_block, tool_block, RESULT_EVENT)
        mock_popen.return_value = _make_mock_popen(stdout=ndjson)
        client = ClaudeCliClient()
        resp = client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        # Both delta types at the same index are concatenated into one result
        assert resp.content[0].input == {"decision": "post_worthy"}

    @patch("social_hook.llm.claude_cli.subprocess.Popen")
    def test_unknown_delta_type_ignored_gracefully(self, mock_popen):
        """signature_delta type doesn't crash the parser."""
        sig_delta = {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "signature_delta", "signature": "abc123"},
            },
        }
        ndjson = _make_ndjson(SYSTEM_EVENT, sig_delta, TEXT_DELTA_EVENT, RESULT_EVENT)
        mock_popen.return_value = _make_mock_popen(stdout=ndjson)
        client = ClaudeCliClient()
        resp = client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        # Should still parse the text_delta successfully
        assert resp.content[0].input == {"decision": "post_worthy"}
