"""Abstract LLM client interface and normalized response types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class NormalizedUsage:
    """Normalized token usage across providers."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class NormalizedToolCall:
    """Normalized tool call matching extract_tool_call() interface.

    Attributes match the content.type/content.name/content.input
    interface used by extract_tool_call() in schemas.py.
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
        operation_type: Optional[str] = None,
        db: Optional[Any] = None,
        project_id: Optional[str] = None,
        commit_hash: Optional[str] = None,
    ) -> NormalizedResponse:
        """Make an LLM API call with tool use.

        Args:
            messages: Conversation messages
            tools: Tool definitions for function calling
            system: System prompt
            max_tokens: Maximum output tokens
            operation_type: Label for usage tracking
            db: Database context for usage logging
            project_id: Project ID for usage tracking
            commit_hash: Git commit hash for usage tracking

        Returns:
            NormalizedResponse with tool calls and usage data
        """
        ...
