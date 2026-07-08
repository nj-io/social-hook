"""Tests for LiteLLMClient (OpenAI/OpenRouter/Ollama via LiteLLM, mocked)."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("litellm")

from social_hook.llm.base import ToolExtractionError, extract_tool_call  # noqa: E402
from social_hook.llm.litellm_client import (  # noqa: E402
    LiteLLMClient,
    _convert_tool_schema,
    _litellm_model_string,
)

TOOL = {
    "name": "route_action",
    "description": "Route the message",
    "input_schema": {"type": "object", "properties": {"action": {"type": "string"}}},
}


def _tool_call(name: str, args_json: str) -> MagicMock:
    tc = MagicMock()
    tc.function.name = name
    tc.function.arguments = args_json
    return tc


def _mock_response(
    *,
    tool_calls=None,
    content=None,
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
    cached_tokens: int = 0,
    response_cost=None,
) -> MagicMock:
    """Build a LiteLLM-shaped (OpenAI) completion response."""
    msg = MagicMock()
    msg.tool_calls = tool_calls  # None or a list
    msg.content = content  # None or str
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    ptd = MagicMock()
    ptd.cached_tokens = cached_tokens
    usage.prompt_tokens_details = ptd
    resp.usage = usage
    resp._hidden_params = {"response_cost": response_cost}
    return resp


class TestModelStringMapping:
    def test_openrouter_prefix(self):
        assert _litellm_model_string("openrouter", "z-ai/glm-5.2") == "openrouter/z-ai/glm-5.2"

    def test_ollama_uses_openai_compat(self):
        assert _litellm_model_string("ollama", "llama3.3") == "openai/llama3.3"

    def test_openai_bare(self):
        assert _litellm_model_string("openai", "gpt-4o") == "gpt-4o"

    def test_full_id_is_social_hook_identity(self):
        # full_id keeps provider/model, distinct from the litellm model string
        c = LiteLLMClient("llama3.3", "ollama", api_base="http://x/v1")
        assert c.full_id == "ollama/llama3.3"
        assert c._litellm_model == "openai/llama3.3"


class TestConvertToolSchema:
    def test_converts_to_openai_function(self):
        out = _convert_tool_schema(TOOL)
        assert out["type"] == "function"
        assert out["function"]["name"] == "route_action"
        assert out["function"]["parameters"] == TOOL["input_schema"]


class TestComplete:
    def _client(self) -> LiteLLMClient:
        return LiteLLMClient("z-ai/glm-5.2", "openrouter", api_key="sk-or-test")

    @patch("litellm.completion")
    def test_native_tool_call_parsed(self, mock_completion):
        mock_completion.return_value = _mock_response(
            tool_calls=[_tool_call("route_action", '{"action": "handle_directly"}')],
            response_cost=0.0012,
        )
        resp = self._client().complete(messages=[{"role": "user", "content": "hi"}], tools=[TOOL])
        tool_input = extract_tool_call(resp, "route_action")
        assert tool_input == {"action": "handle_directly"}
        # cost from provider (dollars -> cents)
        assert abs(resp.usage.cost_cents - 0.12) < 0.001
        assert resp.usage.cost_source == "provider"

    @patch("litellm.completion")
    def test_forces_single_tool_choice(self, mock_completion):
        mock_completion.return_value = _mock_response(tool_calls=[_tool_call("route_action", "{}")])
        self._client().complete(messages=[{"role": "user", "content": "hi"}], tools=[TOOL])
        kwargs = mock_completion.call_args.kwargs
        assert kwargs["tool_choice"] == {"type": "function", "function": {"name": "route_action"}}
        assert kwargs["drop_params"] is True
        assert kwargs["model"] == "openrouter/z-ai/glm-5.2"

    @patch("litellm.completion")
    def test_json_from_text_fallback(self, mock_completion):
        # Provider ignored the tool and answered with JSON in the message body
        mock_completion.return_value = _mock_response(
            tool_calls=None,
            content='Here you go:\n```json\n{"action": "handle_directly"}\n```',
        )
        resp = self._client().complete(messages=[{"role": "user", "content": "hi"}], tools=[TOOL])
        tool_input = extract_tool_call(resp, "route_action")
        assert tool_input == {"action": "handle_directly"}

    @patch("litellm.completion")
    def test_prose_returns_text_block_not_raise(self, mock_completion):
        # Plain prose (no JSON) → text block, no exception (preserves Gatekeeper fallback)
        mock_completion.return_value = _mock_response(
            tool_calls=None,
            content="I'm not sure how to route that.",
        )
        resp = self._client().complete(messages=[{"role": "user", "content": "hi"}], tools=[TOOL])
        assert len(resp.content) == 1
        assert resp.content[0].type == "text"
        assert "route" in resp.content[0].text
        # extract_tool_call raises (caught by prose-fallback callers), not complete()
        with pytest.raises(ToolExtractionError):
            extract_tool_call(resp, "route_action")

    @patch("litellm.completion_cost")
    @patch("litellm.completion")
    def test_cost_falls_back_to_catalog(self, mock_completion, mock_cost):
        # response_cost None and completion_cost raises (unmapped model) -> catalog
        mock_completion.return_value = _mock_response(
            tool_calls=[_tool_call("route_action", "{}")],
            prompt_tokens=1_000_000,
            completion_tokens=0,
            response_cost=None,
        )
        mock_cost.side_effect = Exception("model not in litellm cost map")
        resp = self._client().complete(messages=[{"role": "user", "content": "hi"}], tools=[TOOL])
        # GLM-5.2 catalog input price $0.93/M -> 1M input = $0.93 = 93 cents
        assert abs(resp.usage.cost_cents - 93.0) < 0.01
        assert resp.usage.cost_source == "registry"

    @patch("litellm.completion")
    def test_provider_error_wrapped(self, mock_completion):
        from social_hook.errors import MalformedResponseError

        mock_completion.side_effect = RuntimeError("connection refused")
        with pytest.raises(MalformedResponseError):
            self._client().complete(messages=[{"role": "user", "content": "hi"}], tools=[TOOL])
