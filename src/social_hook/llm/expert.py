"""Expert agent: handles escalated requests from Gatekeeper (T16)."""

from typing import Any, Optional

from social_hook.llm.client import ClaudeClient
from social_hook.llm.prompts import assemble_expert_prompt, load_prompt
from social_hook.llm.schemas import ExpertResponseInput, extract_tool_call


class Expert:
    """Handles escalated requests requiring creative judgment.

    Shares the Drafter's model and prompt template but receives
    escalation-specific context.

    Args:
        client: ClaudeClient configured with the drafter model
    """

    def __init__(self, client: ClaudeClient) -> None:
        self.client = client

    def handle(
        self,
        draft: Any,
        user_message: str,
        escalation_reason: str,
        escalation_context: Optional[str] = None,
        project_summary: Optional[str] = None,
        db: Optional[Any] = None,
        project_id: Optional[str] = None,
    ) -> ExpertResponseInput:
        """Handle an escalated request.

        Args:
            draft: Current draft object
            user_message: Original Telegram message that triggered escalation
            escalation_reason: Why the Gatekeeper escalated
            escalation_context: Additional context from Gatekeeper
            project_summary: Pre-injected project summary
            db: Database context for usage logging
            project_id: Project ID for usage tracking

        Returns:
            Validated ExpertResponseInput with response
        """
        prompt = load_prompt("drafter")  # Expert shares Drafter's prompt

        system = assemble_expert_prompt(
            prompt, draft, user_message,
            escalation_reason, escalation_context,
            project_summary,
        )

        response = self.client.complete(
            messages=[{"role": "user", "content": user_message}],
            tools=[ExpertResponseInput.to_tool_schema()],
            system=system,
            operation_type="expert",
            db=db,
            project_id=project_id,
        )

        tool_input = extract_tool_call(response, "expert_response")
        return ExpertResponseInput.validate(tool_input)
