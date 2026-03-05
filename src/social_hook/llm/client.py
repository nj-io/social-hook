"""Claude API client wrapper with pricing calculation."""

from typing import Any

import anthropic

from social_hook.errors import AuthError
from social_hook.llm.base import LLMClient, NormalizedResponse, NormalizedToolCall, NormalizedUsage

# Pricing per million tokens (in cents) for cost estimation
# Source: https://docs.anthropic.com/en/docs/about-claude/pricing
MODEL_PRICING = {
    "claude-opus-4-5": {
        "input": 1500,  # $15 / 1M tokens
        "output": 7500,  # $75 / 1M tokens
        "cache_read": 150,  # $1.50 / 1M tokens
        "cache_write": 1875,  # $18.75 / 1M tokens
    },
    "claude-sonnet-4-5": {
        "input": 300,  # $3 / 1M tokens
        "output": 1500,  # $15 / 1M tokens
        "cache_read": 30,  # $0.30 / 1M tokens
        "cache_write": 375,  # $3.75 / 1M tokens
    },
    "claude-haiku-4-5": {
        "input": 80,  # $0.80 / 1M tokens
        "output": 400,  # $4 / 1M tokens
        "cache_read": 8,  # $0.08 / 1M tokens
        "cache_write": 100,  # $1 / 1M tokens
    },
}


def _calculate_cost_cents(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> float:
    """Calculate cost in cents from token counts.

    Args:
        model: Model name (e.g., "claude-opus-4-5")
        input_tokens: Non-cached input tokens
        output_tokens: Output tokens
        cache_read_tokens: Tokens read from cache
        cache_creation_tokens: Tokens written to cache

    Returns:
        Estimated cost in cents
    """
    pricing = MODEL_PRICING.get(model)
    if not pricing:
        return 0.0

    cost = (
        (input_tokens / 1_000_000) * pricing["input"]
        + (output_tokens / 1_000_000) * pricing["output"]
        + (cache_read_tokens / 1_000_000) * pricing["cache_read"]
        + (cache_creation_tokens / 1_000_000) * pricing["cache_write"]
    )
    return round(cost, 4)


class ClaudeClient(LLMClient):
    """Wrapper around Anthropic SDK with usage tracking.

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

        cost_cents = _calculate_cost_cents(
            self.model,
            input_tokens,
            output_tokens,
            cache_read_tokens,
            cache_creation_tokens,
        )

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
        )

        return NormalizedResponse(
            content=normalized_content,
            usage=normalized_usage,
            raw=response,
        )
