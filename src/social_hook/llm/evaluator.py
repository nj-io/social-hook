"""Evaluator agent: assesses commits for post-worthiness (T13)."""

from typing import Any, Optional

from social_hook.config.project import ContextConfig
from social_hook.db import operations as ops
from social_hook.llm.client import ClaudeClient
from social_hook.llm.prompts import assemble_evaluator_prompt, load_prompt
from social_hook.llm.schemas import LogDecisionInput, extract_tool_call
from social_hook.models import CommitInfo, ProjectContext


class Evaluator:
    """Evaluates commits and decides post-worthiness.

    Args:
        client: ClaudeClient configured with the evaluator model
    """

    def __init__(self, client: ClaudeClient) -> None:
        self.client = client

    def evaluate(
        self,
        commit: CommitInfo,
        context: ProjectContext,
        db: Any,
        config: Optional[ContextConfig] = None,
        show_prompt: bool = False,
    ) -> LogDecisionInput:
        """Evaluate a commit for post-worthiness.

        Args:
            commit: Git commit information
            context: Assembled project state
            db: Database context (DryRunContext) for usage logging
            config: Context config for prompt assembly limits
            show_prompt: If True, print the full system prompt and user message

        Returns:
            Validated LogDecisionInput from the LLM
        """
        prompt = load_prompt("evaluator")
        system = assemble_evaluator_prompt(prompt, context, commit, config)

        # Check summary freshness and include hint
        freshness = None
        if hasattr(db, "get_summary_freshness"):
            freshness = db.get_summary_freshness(context.project.id)

        user_message = (
            f"Evaluate this commit for post-worthiness.\n"
            f"Commit: {commit.hash[:8]} - {commit.message}"
        )

        if freshness:
            user_message += (
                f"\n\nSummary freshness: {freshness.get('commits_since_summary', 0)} "
                f"commits since last update, "
                f"{freshness.get('days_since_summary', 'N/A')} days since update."
            )

        if show_prompt:
            import sys
            print("=" * 72, file=sys.stderr)
            print("EVALUATOR SYSTEM PROMPT", file=sys.stderr)
            print("=" * 72, file=sys.stderr)
            print(system, file=sys.stderr)
            print("=" * 72, file=sys.stderr)
            print("USER MESSAGE", file=sys.stderr)
            print("=" * 72, file=sys.stderr)
            print(user_message, file=sys.stderr)
            print("=" * 72, file=sys.stderr)

        response = self.client.complete(
            messages=[{"role": "user", "content": user_message}],
            tools=[LogDecisionInput.to_tool_schema()],
            system=system,
            operation_type="evaluate",
            db=db,
            project_id=context.project.id,
            commit_hash=commit.hash,
        )

        tool_input = extract_tool_call(response, "log_decision")
        return LogDecisionInput.validate(tool_input)
