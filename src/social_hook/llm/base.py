"""Abstract LLM client interface and normalized response types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Union


@dataclass
class NormalizedUsage:
    """Normalized token usage across providers."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cost_cents: float = 0.0  # Set by providers that know pricing


class ToolExtractionError(ValueError):
    """Raised when an expected tool call is not found in an LLM response."""
    pass


@dataclass
class NormalizedToolCall:
    """Normalized tool call matching extract_tool_call() interface.

    Attributes match the content.type/content.name/content.input
    interface used by extract_tool_call().
    """
    type: str = "tool_use"
    name: str = ""
    input: dict = field(default_factory=dict)


@dataclass
class NormalizedResponse:
    """Normalized LLM response across providers.

    content: list of NormalizedToolCall (or text blocks)
    usage: NormalizedUsage with token counts
    raw: Original provider response for debugging
    """
    content: list = field(default_factory=list)
    usage: NormalizedUsage = field(default_factory=NormalizedUsage)
    raw: Any = None


class LLMClient(ABC):
    """Abstract base class for LLM provider clients."""

    provider: str
    model: str

    @abstractmethod
    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system: Optional[str] = None,
        max_tokens: int = 4096,
    ) -> NormalizedResponse:
        """Make an LLM API call with tool use.

        Args:
            messages: Conversation messages
            tools: Tool definitions for function calling
            system: System prompt
            max_tokens: Maximum output tokens

        Returns:
            NormalizedResponse with tool calls and usage data
        """
        ...


def extract_tool_call(response: Any, expected_tool: Union[str, list[str]]) -> dict:
    """Extract a named tool call from a response.

    Args:
        response: Any object with a .content list of tool call objects.
        expected_tool: Tool name or list of tool names to match.

    Returns:
        Tool call input dict.

    Raises:
        ToolExtractionError: If no matching tool call found.
    """
    if isinstance(expected_tool, str):
        tool_names = [expected_tool]
    else:
        tool_names = expected_tool
    for content in response.content:
        if getattr(content, "type", None) == "tool_use" and getattr(content, "name", None) in tool_names:
            return content.input
    label = tool_names[0] if len(tool_names) == 1 else str(tool_names)
    raise ToolExtractionError(f"No {label} tool call in response")
