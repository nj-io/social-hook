"""Evaluator agent: assesses commits for post-worthiness (T13)."""

from typing import TYPE_CHECKING, Any, Optional

from social_hook.config.project import ContextConfig
from social_hook.llm._usage_logger import log_usage
from social_hook.llm.base import LLMClient, extract_tool_call
from social_hook.llm.prompts import assemble_evaluator_prompt, load_prompt
from social_hook.llm.schemas import CommitAnalysisResult, LogEvaluationInput
from social_hook.models import CommitInfo, ProjectContext
from social_hook.scheduling import ProjectSchedulingState

if TYPE_CHECKING:
    from social_hook.config.project import MediaToolGuidance, StrategyConfig, SummaryConfig
    from social_hook.config.yaml import ContentStrategyConfig, MediaGenerationConfig


class Evaluator:
    """Evaluates commits and decides post-worthiness.

    Args:
        client: ClaudeClient configured with the evaluator model
    """

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def evaluate(
        self,
        commit: CommitInfo,
        context: ProjectContext,
        db: Any,
        config: ContextConfig | None = None,
        show_prompt: bool = False,
        platform_summaries: list[str] | None = None,
        media_config: Optional["MediaGenerationConfig"] = None,
        media_guidance: dict[str, "MediaToolGuidance"] | None = None,
        strategy_config: Optional["StrategyConfig"] = None,
        summary_config: Optional["SummaryConfig"] = None,
        scheduling_state: ProjectSchedulingState | None = None,
        strategies: dict[str, "ContentStrategyConfig"] | None = None,
        held_topics: list | None = None,
        active_arcs_all: list | None = None,
        targets: dict | None = None,
        all_topics: list | None = None,
        analysis: CommitAnalysisResult | None = None,
    ) -> LogEvaluationInput:
        """Evaluate a commit for post-worthiness.

        Args:
            commit: Git commit information
            context: Assembled project state
            db: Database context (DryRunContext) for usage logging
            config: Context config for prompt assembly limits
            show_prompt: If True, print the full system prompt and user message
            platform_summaries: Optional list of platform summary strings for context
            media_config: Media generation config (enabled tools)
            media_guidance: Per-tool content guidance
            strategy_config: Strategy thresholds (portfolio window, episode prefs)
            summary_config: Summary refresh thresholds
            strategies: Content strategy definitions (audience, voice, angle, etc.)
            held_topics: Held topics for per-strategy posting state
            active_arcs_all: Active arcs across all strategies
            targets: Target definitions for post-to-strategy mapping
            all_topics: All topics for topic queue section
            analysis: Pre-computed stage 1 commit analysis (classification, tags, summary)

        Returns:
            Validated LogEvaluationInput from the LLM
        """
        prompt = load_prompt("evaluator")
        system = assemble_evaluator_prompt(
            prompt,
            context,
            commit,
            config,
            platform_summaries=platform_summaries,
            media_config=media_config,
            media_guidance=media_guidance,
            strategy_config=strategy_config,
            summary_config=summary_config,
            scheduling_state=scheduling_state,
            strategies=strategies,
            held_topics=held_topics,
            active_arcs_all=active_arcs_all,
            targets=targets,
            all_topics=all_topics,
            analysis=analysis,
        )

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
            tools=[LogEvaluationInput.to_tool_schema()],
            system=system,
        )
        log_usage(
            db,
            "evaluate",
            getattr(self.client, "full_id", "unknown"),
            response.usage,
            context.project.id,
            commit.hash,
        )

        tool_input = extract_tool_call(response, "log_evaluation")
        return LogEvaluationInput.validate(tool_input)
