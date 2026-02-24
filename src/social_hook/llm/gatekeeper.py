"""Gatekeeper agent: routes Telegram messages (T15)."""

import logging
from typing import Any, Optional

from social_hook.errors import MalformedResponseError
from social_hook.llm.base import LLMClient
from social_hook.llm.prompts import assemble_gatekeeper_prompt, load_prompt
from social_hook.llm.schemas import (
    GatekeeperOperation,
    RouteAction,
    RouteActionInput,
    extract_tool_call,
)

logger = logging.getLogger(__name__)


def _extract_text_content(response: Any) -> str:
    """Extract text content from LLM response as fallback."""
    parts = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", ""))
        elif isinstance(block, str):
            parts.append(block)
    return "\n".join(parts).strip()


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

        try:
            tool_input = extract_tool_call(response, "route_action")
            return RouteActionInput.validate(tool_input)
        except MalformedResponseError:
            # LLM responded with text instead of using the tool — construct
            # a known-good RouteActionInput directly (not from LLM output).
            logger.warning("Gatekeeper LLM skipped route_action tool, using text fallback")
            text = _extract_text_content(response)
            return RouteActionInput(
                action=RouteAction.handle_directly,
                operation=GatekeeperOperation.query,
                params={"answer": text or "I'm your social-hook assistant. Try sending a draft or ask me a question!"},
            )
