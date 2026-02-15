"""Gatekeeper agent: routes Telegram messages (T15)."""

from typing import Any, Optional

from social_hook.llm.base import LLMClient
from social_hook.llm.prompts import assemble_gatekeeper_prompt, load_prompt
from social_hook.llm.schemas import RouteActionInput, extract_tool_call


class Gatekeeper:
    """Routes Telegram messages to appropriate handlers.

    Args:
        client: ClaudeClient configured with the gatekeeper model (Haiku)
    """

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def route(
        self,
        user_message: str,
        draft_context: Optional[Any] = None,
        project_summary: Optional[str] = None,
        db: Optional[Any] = None,
        project_id: Optional[str] = None,
    ) -> RouteActionInput:
        """Route a user message to the appropriate handler.

        Args:
            user_message: Telegram message text
            draft_context: Current draft object (if applicable)
            project_summary: Pre-injected project summary (~500 tokens)
            db: Database context for usage logging
            project_id: Project ID for usage tracking

        Returns:
            Validated RouteActionInput with routing decision
        """
        prompt = load_prompt("gatekeeper")

        # Use a minimal draft placeholder if none provided
        if draft_context is None:
            draft_context = {"content": "[No active draft]", "platform": "N/A"}

        system = assemble_gatekeeper_prompt(
            prompt, draft_context, user_message, project_summary,
        )

        response = self.client.complete(
            messages=[{"role": "user", "content": user_message}],
            tools=[RouteActionInput.to_tool_schema()],
            system=system,
            operation_type="gatekeeper",
            db=db,
            project_id=project_id,
        )

        tool_input = extract_tool_call(response, "route_action")
        return RouteActionInput.validate(tool_input)
