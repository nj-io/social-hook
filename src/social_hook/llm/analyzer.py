"""Commit Analyzer agent: stage 1 classification and understanding."""

import logging
from typing import Any

from social_hook.llm._usage_logger import log_usage
from social_hook.llm.base import LLMClient, extract_tool_call
from social_hook.llm.prompts import load_prompt
from social_hook.llm.schemas import CommitAnalysisResult
from social_hook.models import ProjectContext
from social_hook.models.core import CommitInfo

logger = logging.getLogger(__name__)


class CommitAnalyzer:
    """Stage 1: classifies commits and produces structured analysis.

    Args:
        client: LLMClient configured with the evaluator/analyzer model
    """

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def analyze(
        self,
        commit: CommitInfo,
        context: ProjectContext,
        db: Any,
        show_prompt: bool = False,
    ) -> CommitAnalysisResult:
        """Analyze a commit for classification, tags, and brief update instructions.

        Args:
            commit: Git commit information
            context: Assembled project state (for brief context)
            db: Database context (DryRunContext) for usage logging
            show_prompt: If True, print the full system prompt and user message

        Returns:
            Validated CommitAnalysisResult from the LLM
        """
        prompt = load_prompt("analyzer")

        # Assemble system prompt with project brief context
        system = self._assemble_system_prompt(prompt, context)

        user_message = f"Analyze this commit.\nCommit: {commit.hash[:8]} - {commit.message}\n"
        if commit.diff:
            # Cap diff at ~4000 chars to stay within token budget
            diff_preview = commit.diff[:4000]
            if len(commit.diff) > 4000:
                diff_preview += "\n... (diff truncated)"
            user_message += f"\nDiff:\n{diff_preview}"

        if show_prompt:
            import sys

            print("=" * 72, file=sys.stderr)
            print("ANALYZER SYSTEM PROMPT", file=sys.stderr)
            print("=" * 72, file=sys.stderr)
            print(system, file=sys.stderr)
            print("=" * 72, file=sys.stderr)
            print("USER MESSAGE", file=sys.stderr)
            print("=" * 72, file=sys.stderr)
            print(user_message, file=sys.stderr)
            print("=" * 72, file=sys.stderr)

        response = self.client.complete(
            messages=[{"role": "user", "content": user_message}],
            tools=[CommitAnalysisResult.to_tool_schema()],
            system=system,
        )
        log_usage(
            db,
            "analyze",
            getattr(self.client, "full_id", "unknown"),
            response.usage,
            context.project.id,
            commit.hash,
        )

        tool_input = extract_tool_call(response, "log_commit_analysis")
        return CommitAnalysisResult.validate(tool_input)

    def _assemble_system_prompt(self, prompt: str, context: ProjectContext) -> str:
        """Build system prompt with project brief for context."""
        sections = [prompt]

        if context.project.summary:
            sections.append(f"\n## Current Project Brief\n\n{context.project.summary}")

        return "\n".join(sections)
