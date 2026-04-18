"""Expert agent: handles escalated requests from Gatekeeper (T16)."""

import json
import os
from pathlib import Path
from typing import Any

from social_hook.llm._usage_logger import log_usage
from social_hook.llm.base import LLMClient, extract_tool_call
from social_hook.llm.prompts import assemble_expert_prompt, load_prompt
from social_hook.llm.schemas import ExpertResponseInput


class Expert:
    """Handles escalated requests requiring creative judgment.

    Shares the Drafter's model and prompt template but receives
    escalation-specific context.

    Args:
        client: ClaudeClient configured with the drafter model
    """

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def handle(
        self,
        draft: Any,
        user_message: str,
        escalation_reason: str,
        escalation_context: str | None = None,
        project_summary: str | None = None,
        db: Any | None = None,
        project_id: str | None = None,
        social_context: str | None = None,
        identity: Any | None = None,
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
            social_context: Project social context for voice consistency
            identity: Resolved IdentityConfig for maintaining perspective

        Returns:
            Validated ExpertResponseInput with response
        """
        prompt = load_prompt("drafter")  # Expert shares Drafter's prompt

        system = assemble_expert_prompt(
            prompt,
            draft,
            user_message,
            escalation_reason,
            escalation_context,
            project_summary,
            social_context=social_context,
            identity=identity,
        )

        response = self.client.complete(
            messages=[{"role": "user", "content": user_message}],
            tools=[ExpertResponseInput.to_tool_schema()],
            system=system,
        )
        log_usage(
            db, "expert", getattr(self.client, "full_id", "unknown"), response.usage, project_id
        )

        tool_input = extract_tool_call(response, "expert_response")
        # TEMP: env-gated raw-tool-call trace for E2E V8/V14 diagnosis.
        # Reverted after root-cause fixes land.
        _trace_dir = os.environ.get("SOCIAL_HOOK_LLM_TRACE_DIR")
        if _trace_dir:
            try:
                import time as _t

                Path(_trace_dir).mkdir(parents=True, exist_ok=True)
                _ts = f"{_t.time():.6f}"
                Path(_trace_dir, f"{_ts}-expert-raw.json").write_text(
                    json.dumps({"tool_input": tool_input}, indent=2, default=str)
                )
            except Exception:
                pass  # trace must never break the real call
        return ExpertResponseInput.validate(tool_input)
