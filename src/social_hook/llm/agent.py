"""Generic single-tool LLM agent base class. Reusable — zero project imports."""

from abc import ABC
from typing import Any, Optional, Union

from social_hook.llm.base import LLMClient, NormalizedResponse, extract_tool_call


class SingleToolAgent(ABC):
    """Base for agents that call one LLM tool and return a validated result."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def call_tool(
        self,
        messages: list[dict[str, Any]],
        tool_schema: dict[str, Any],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        tool_name: Optional[Union[str, list[str]]] = None,
    ) -> tuple[dict[str, Any], NormalizedResponse]:
        """Call LLM with a single tool and extract the result.

        Args:
            messages: Chat messages to send.
            tool_schema: Tool definition dict with "name" key.
            system: Optional system prompt.
            max_tokens: Max output tokens.
            tool_name: Override tool name(s) to match in response.
                       Defaults to tool_schema["name"]. Pass a list
                       for backward-compat fallback.

        Returns:
            (tool_input_dict, full_response) so callers can
            access both the extracted tool call and usage data.
        """
        if tool_name is None:
            tool_name = tool_schema["name"]
        response = self.client.complete(
            messages=messages,
            tools=[tool_schema],
            system=system,
            max_tokens=max_tokens,
        )
        tool_input = extract_tool_call(response, tool_name)
        return tool_input, response
