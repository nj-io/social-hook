"""Gatekeeper agent: routes Telegram messages (T15)."""

import logging
from typing import Any, Optional

from social_hook.constants import PROJECT_SLUG
from social_hook.errors import MalformedResponseError
from social_hook.llm._usage_logger import log_usage
from social_hook.llm.base import LLMClient, ToolExtractionError, extract_tool_call
from social_hook.llm.prompts import assemble_gatekeeper_prompt, load_prompt
from social_hook.llm.schemas import (
    GatekeeperOperation,
    RouteAction,
    RouteActionInput,
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
        system_snapshot: Optional[str] = None,
        chat_history: Optional[str] = None,
        recent_decisions: Optional[list] = None,
        recent_posts: Optional[list] = None,
        lifecycle_phase: Optional[str] = None,
        active_arcs: Optional[list] = None,
        narrative_debt: Optional[int] = None,
        audience_introduced: Optional[bool] = None,
        linked_decision: Optional[Any] = None,
    ) -> RouteActionInput:
        """Route a user message to the appropriate handler.

        Args:
            user_message: Telegram message text
            draft_context: Current draft object (if applicable)
            project_summary: Pre-injected project summary (~500 tokens)
            db: Database context for usage logging
            project_id: Project ID for usage tracking
            system_snapshot: Compact system status block for context
            chat_history: Recent chat messages for conversational context
            recent_decisions: Recent evaluation decisions for context
            recent_posts: Recent published posts for context
            lifecycle_phase: Current project lifecycle phase
            active_arcs: Active narrative arcs
            narrative_debt: Current narrative debt counter
            audience_introduced: Whether audience has been introduced
            linked_decision: Decision linked to the current draft

        Returns:
            Validated RouteActionInput with routing decision
        """
        prompt = load_prompt("gatekeeper")

        # Use a minimal draft placeholder if none provided
        if draft_context is None:
            draft_context = {"content": "[No active draft]", "platform": "N/A"}

        system = assemble_gatekeeper_prompt(
            prompt, draft_context, user_message, project_summary,
            system_snapshot=system_snapshot,
            chat_history=chat_history,
            recent_decisions=recent_decisions,
            recent_posts=recent_posts,
            lifecycle_phase=lifecycle_phase,
            active_arcs=active_arcs,
            narrative_debt=narrative_debt,
            audience_introduced=audience_introduced,
            linked_decision=linked_decision,
        )

        response = self.client.complete(
            messages=[{"role": "user", "content": user_message}],
            tools=[RouteActionInput.to_tool_schema()],
            system=system,
        )
        log_usage(db, "gatekeeper", getattr(self.client, "full_id", "unknown"),
                  response.usage, project_id)

        try:
            tool_input = extract_tool_call(response, "route_action")
            return RouteActionInput.validate(tool_input)
        except (ToolExtractionError, MalformedResponseError):
            # LLM responded with text instead of using the tool — construct
            # a known-good RouteActionInput directly (not from LLM output).
            logger.warning("Gatekeeper LLM skipped route_action tool, using text fallback")
            text = _extract_text_content(response)
            return RouteActionInput(
                action=RouteAction.handle_directly,
                operation=GatekeeperOperation.query,
                params={"answer": text or f"I'm your {PROJECT_SLUG} assistant. Try sending a draft or ask me a question!"},
            )
