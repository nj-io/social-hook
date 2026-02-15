"""Tests for OpenAICompatClient."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from social_hook.errors import ConfigError, MalformedResponseError
from social_hook.llm.base import NormalizedResponse, NormalizedToolCall, NormalizedUsage
from social_hook.llm.openai_compat import OpenAICompatClient, _convert_tool_schema


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


def _make_mock_openai_response(
    tool_name="log_decision",
    tool_args='{"decision":"post_worthy"}',
    prompt_tokens=100,
    completion_tokens=50,
):
    """Build a mock OpenAI chat completion response."""
    func = SimpleNamespace(name=tool_name, arguments=tool_args)
    tool_call = SimpleNamespace(function=func)
    message = SimpleNamespace(tool_calls=[tool_call])
    choice = SimpleNamespace(message=message)
    usage = SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    return SimpleNamespace(choices=[choice], usage=usage)


class TestConvertToolSchema:
    def test_anthropic_to_openai_format(self):
        result = _convert_tool_schema(SAMPLE_TOOL)
        assert result["type"] == "function"
        assert result["function"]["name"] == "log_decision"
        assert result["function"]["description"] == "Log a decision"
        assert result["function"]["parameters"] == SAMPLE_TOOL["input_schema"]

    def test_missing_description_defaults_to_empty(self):
        tool = {"name": "test", "input_schema": {"type": "object"}}
        result = _convert_tool_schema(tool)
        assert result["function"]["description"] == ""

    def test_missing_input_schema_defaults_to_empty(self):
        tool = {"name": "test", "description": "desc"}
        result = _convert_tool_schema(tool)
        assert result["function"]["parameters"] == {}


class TestOpenAICompatClientInit:
    @patch("social_hook.llm.openai_compat.OpenAI")
    def test_basic_init(self, mock_openai_cls):
        client = OpenAICompatClient(api_key="sk-test", model="gpt-4o")
        assert client.model == "gpt-4o"
        assert client.provider == "openai"
        assert client.full_id == "openai/gpt-4o"
        mock_openai_cls.assert_called_once_with(
            api_key="sk-test", base_url="https://api.openai.com/v1"
        )

    @patch("social_hook.llm.openai_compat.OpenAI")
    def test_custom_provider_and_base_url(self, mock_openai_cls):
        client = OpenAICompatClient(
            api_key="sk-or-test",
            model="anthropic/claude-3.5-sonnet",
            base_url="https://openrouter.ai/api/v1",
            provider_name="openrouter",
        )
        assert client.provider == "openrouter"
        assert client.full_id == "openrouter/anthropic/claude-3.5-sonnet"
        mock_openai_cls.assert_called_once_with(
            api_key="sk-or-test", base_url="https://openrouter.ai/api/v1"
        )

    def test_missing_openai_package_raises_config_error(self):
        """When openai is not installed (OpenAI is None), ConfigError is raised."""
        with patch("social_hook.llm.openai_compat.OpenAI", None):
            with pytest.raises(ConfigError, match="openai package required"):
                OpenAICompatClient(api_key="sk-test", model="gpt-4o")


class TestComplete:
    @patch("social_hook.llm.openai_compat.OpenAI")
    def test_system_prompt_prepended(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_openai_response()
        mock_openai_cls.return_value = mock_client

        client = OpenAICompatClient(api_key="sk-test", model="gpt-4o")
        client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL], system="Be concise")

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        msgs = call_kwargs["messages"]
        assert msgs[0] == {"role": "system", "content": "Be concise"}
        assert msgs[1] == SAMPLE_MESSAGES[0]

    @patch("social_hook.llm.openai_compat.OpenAI")
    def test_no_system_prompt(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_openai_response()
        mock_openai_cls.return_value = mock_client

        client = OpenAICompatClient(api_key="sk-test", model="gpt-4o")
        client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        msgs = call_kwargs["messages"]
        assert len(msgs) == 1
        assert msgs[0] == SAMPLE_MESSAGES[0]

    @patch("social_hook.llm.openai_compat.OpenAI")
    def test_tool_schema_converted(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_openai_response()
        mock_openai_cls.return_value = mock_client

        client = OpenAICompatClient(api_key="sk-test", model="gpt-4o")
        client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        tools = call_kwargs["tools"]
        assert len(tools) == 1
        assert tools[0]["type"] == "function"
        assert tools[0]["function"]["name"] == "log_decision"

    @patch("social_hook.llm.openai_compat.OpenAI")
    def test_tool_choice_required(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_openai_response()
        mock_openai_cls.return_value = mock_client

        client = OpenAICompatClient(api_key="sk-test", model="gpt-4o")
        client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["tool_choice"] == "required"

    @patch("social_hook.llm.openai_compat.OpenAI")
    def test_response_normalization(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_openai_response()
        mock_openai_cls.return_value = mock_client

        client = OpenAICompatClient(api_key="sk-test", model="gpt-4o")
        resp = client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        assert isinstance(resp, NormalizedResponse)
        assert len(resp.content) == 1
        tc = resp.content[0]
        assert isinstance(tc, NormalizedToolCall)
        assert tc.name == "log_decision"
        assert tc.input == {"decision": "post_worthy"}
        assert tc.type == "tool_use"

    @patch("social_hook.llm.openai_compat.OpenAI")
    def test_usage_mapping(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_openai_response(
            prompt_tokens=200, completion_tokens=75
        )
        mock_openai_cls.return_value = mock_client

        client = OpenAICompatClient(api_key="sk-test", model="gpt-4o")
        resp = client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        assert resp.usage.input_tokens == 200
        assert resp.usage.output_tokens == 75
        assert resp.usage.cache_read_input_tokens == 0
        assert resp.usage.cache_creation_input_tokens == 0

    @patch("social_hook.llm.openai_compat.OpenAI")
    def test_multiple_tool_calls(self, mock_openai_cls):
        func1 = SimpleNamespace(name="tool_a", arguments='{"x": 1}')
        func2 = SimpleNamespace(name="tool_b", arguments='{"y": 2}')
        tc1 = SimpleNamespace(function=func1)
        tc2 = SimpleNamespace(function=func2)
        message = SimpleNamespace(tool_calls=[tc1, tc2])
        choice = SimpleNamespace(message=message)
        usage = SimpleNamespace(prompt_tokens=50, completion_tokens=30)
        mock_response = SimpleNamespace(choices=[choice], usage=usage)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_cls.return_value = mock_client

        client = OpenAICompatClient(api_key="sk-test", model="gpt-4o")
        resp = client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        assert len(resp.content) == 2
        assert resp.content[0].name == "tool_a"
        assert resp.content[0].input == {"x": 1}
        assert resp.content[1].name == "tool_b"
        assert resp.content[1].input == {"y": 2}

    @patch("social_hook.llm.openai_compat.OpenAI")
    def test_api_error_raises_malformed(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Connection timeout")
        mock_openai_cls.return_value = mock_client

        client = OpenAICompatClient(api_key="sk-test", model="gpt-4o")
        with pytest.raises(MalformedResponseError, match="OpenAI API error"):
            client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

    @patch("social_hook.llm.openai_compat.OpenAI")
    def test_raw_response_preserved(self, mock_openai_cls):
        mock_response = _make_mock_openai_response()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_cls.return_value = mock_client

        client = OpenAICompatClient(api_key="sk-test", model="gpt-4o")
        resp = client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL])

        assert resp.raw is mock_response


class TestUsageLogging:
    @patch("social_hook.llm.openai_compat.OpenAI")
    def test_usage_logged_with_db(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_openai_response()
        mock_openai_cls.return_value = mock_client

        client = OpenAICompatClient(api_key="sk-test", model="gpt-4o")
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
        assert usage_log.model == "openai/gpt-4o"
        assert usage_log.input_tokens == 100
        assert usage_log.output_tokens == 50
        assert usage_log.cost_cents == 0.0
        assert usage_log.project_id == "proj-123"

    @patch("social_hook.llm.openai_compat.OpenAI")
    def test_no_logging_without_db(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_openai_response()
        mock_openai_cls.return_value = mock_client

        client = OpenAICompatClient(api_key="sk-test", model="gpt-4o")
        resp = client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL], operation_type="evaluate")
        assert resp is not None

    @patch("social_hook.llm.openai_compat.OpenAI")
    def test_no_logging_without_operation_type(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_openai_response()
        mock_openai_cls.return_value = mock_client

        client = OpenAICompatClient(api_key="sk-test", model="gpt-4o")
        mock_db = MagicMock()
        mock_db.insert_usage = MagicMock()

        client.complete(SAMPLE_MESSAGES, [SAMPLE_TOOL], db=mock_db)
        mock_db.insert_usage.assert_not_called()
