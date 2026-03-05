"""OpenAI-compatible provider client for OpenAI, OpenRouter, Ollama."""

import json
from typing import Any

from social_hook.errors import ConfigError, MalformedResponseError
from social_hook.llm.base import LLMClient, NormalizedResponse, NormalizedToolCall, NormalizedUsage

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore[assignment,misc]


def _convert_tool_schema(anthropic_tool: dict) -> dict:
    """Convert Anthropic tool schema to OpenAI function calling format.

    Anthropic: {"name": "log_decision", "description": "...", "input_schema": {...}}
    OpenAI:    {"type": "function", "function": {"name": "log_decision", "description": "...", "parameters": {...}}}
    """
    return {
        "type": "function",
        "function": {
            "name": anthropic_tool["name"],
            "description": anthropic_tool.get("description", ""),
            "parameters": anthropic_tool.get("input_schema", {}),
        },
    }


class OpenAICompatClient(LLMClient):
    """LLM client for OpenAI-compatible APIs (OpenAI, OpenRouter, Ollama)."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        provider_name: str = "openai",
    ):
        if OpenAI is None:
            raise ConfigError("openai package required for OpenAI/OpenRouter/Ollama providers.")
        self.model = model
        self.provider = provider_name
        self.full_id = f"{self.provider}/{self.model}"
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system: str | None = None,
        max_tokens: int = 4096,
    ) -> NormalizedResponse:
        # 1. Convert tool schemas: Anthropic -> OpenAI format
        openai_tools = [_convert_tool_schema(t) for t in tools]

        # 2. Build messages (system prompt is a message in OpenAI format)
        openai_messages = []
        if system:
            openai_messages.append({"role": "system", "content": system})
        openai_messages.extend(messages)

        # 3. Call API
        try:
            response = self._client.chat.completions.create(  # type: ignore[call-overload]
                model=self.model,
                messages=openai_messages,
                tools=openai_tools,
                tool_choice="required",
                max_tokens=max_tokens,
            )
        except Exception as e:
            raise MalformedResponseError(f"OpenAI API error: {e}") from e

        # 4. Normalize response
        choice = response.choices[0]
        tool_calls = []
        for tc in choice.message.tool_calls or []:
            tool_calls.append(
                NormalizedToolCall(
                    name=tc.function.name,
                    input=json.loads(tc.function.arguments),
                )
            )

        usage = NormalizedUsage(
            input_tokens=getattr(response.usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(response.usage, "completion_tokens", 0) or 0,
        )

        return NormalizedResponse(content=tool_calls, usage=usage, raw=response)
