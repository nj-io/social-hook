"""Claude API client wrapper with catalog-based cost estimation."""

from typing import Any

import anthropic

from social_hook.errors import AuthError
from social_hook.llm.base import LLMClient, NormalizedResponse, NormalizedToolCall, NormalizedUsage
from social_hook.llm.catalog import estimate_cost_cents


class ClaudeClient(LLMClient):
    """Wrapper around Anthropic SDK with usage tracking.

    The Anthropic SDK does not return a per-call dollar cost, so cost is
    estimated from the model catalog (``catalog.estimate_cost_cents``) — the
    single source of pricing truth shared with the setup wizard and settings
    UI. Unknown/unpriced models record ``cost_cents=0`` with
    ``cost_source="unknown"`` rather than a wrong number.

    Args:
        api_key: Anthropic API key
        model: Claude model to use (required, no default)
    """

    provider = "anthropic"

    def __init__(self, api_key: str, model: str) -> None:
        self.model = model
        self.full_id = f"{self.provider}/{self.model}"
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system: str | None = None,
        max_tokens: int = 4096,
    ) -> NormalizedResponse:
        """Make a Claude API call with tool use.

        Args:
            messages: Conversation messages
            tools: Tool definitions for function calling
            system: System prompt
            max_tokens: Maximum output tokens

        Returns:
            NormalizedResponse with tool calls and usage data

        Raises:
            AuthError: If API authentication fails
            MalformedResponseError: If response has no tool call
            anthropic.RateLimitError: If rate limited after SDK retries
            anthropic.APIStatusError: For other API errors
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "max_tokens": max_tokens,
        }
        if system:
            kwargs["system"] = system

        try:
            response = self._client.messages.create(**kwargs)
        except anthropic.AuthenticationError as e:
            raise AuthError(f"Claude API authentication failed: {e}") from e

        # Extract usage
        usage = response.usage
        input_tokens = usage.input_tokens
        output_tokens = usage.output_tokens
        cache_read_tokens = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_creation_tokens = getattr(usage, "cache_creation_input_tokens", 0) or 0

        cost_cents = estimate_cost_cents(
            self.full_id,
            input_tokens,
            output_tokens,
            cache_read_tokens,
            cache_creation_tokens,
        )
        cost_source = "registry" if cost_cents > 0 else "unknown"

        # Wrap in NormalizedResponse
        normalized_content = []
        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                normalized_content.append(
                    NormalizedToolCall(type="tool_use", name=block.name, input=block.input)
                )
            else:
                normalized_content.append(block)

        normalized_usage = NormalizedUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=cache_read_tokens,
            cache_creation_input_tokens=cache_creation_tokens,
            cost_cents=cost_cents,
            cost_source=cost_source,
        )

        return NormalizedResponse(
            content=normalized_content,
            usage=normalized_usage,
            raw=response,
        )
