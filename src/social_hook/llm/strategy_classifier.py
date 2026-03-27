"""Strategy Classifier agent: determines if a strategy is code-driven or positioning.

One-time LLM classification for custom strategies. Results are persisted to
config so the LLM is only called once per custom strategy lifetime.
"""

import logging
from typing import Any

from social_hook.llm._usage_logger import log_usage
from social_hook.llm.agent import SingleToolAgent
from social_hook.llm.base import LLMClient
from social_hook.llm.schemas import STRATEGY_CLASSIFICATION_TOOL

logger = logging.getLogger(__name__)


class StrategyClassifier:
    """Classifies a content strategy as code-driven or positioning-driven.

    Uses a simple binary classification tool — the LLM reads the strategy's
    audience, voice, post_when, and avoid fields and determines whether it's
    aimed at developers (code-driven) or users/buyers (positioning).

    Args:
        client: LLMClient configured with the evaluator model
    """

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def classify(
        self,
        strategy_name: str,
        strategy_config: Any,
        db: Any | None = None,
        project_id: str | None = None,
    ) -> str:
        """Classify a strategy as 'code-driven' or 'positioning'.

        Args:
            strategy_name: Name of the strategy
            strategy_config: Strategy config object with audience/voice/post_when/avoid
            db: Optional database context for usage logging
            project_id: Optional project ID for usage logging

        Returns:
            'code-driven' or 'positioning'
        """
        audience = getattr(strategy_config, "audience", "") or ""
        voice = getattr(strategy_config, "voice", "") or ""
        post_when = getattr(strategy_config, "post_when", "") or ""
        avoid = getattr(strategy_config, "avoid", "") or ""

        user_message = (
            f"Classify this content strategy:\n\n"
            f"Name: {strategy_name}\n"
            f"Audience: {audience}\n"
            f"Voice: {voice}\n"
            f"Post when: {post_when}\n"
            f"Avoid: {avoid}\n\n"
            f"Is this strategy aimed at developers/builders who want to see how "
            f"things are built (code-driven), or at users/buyers who care about "
            f"product value (positioning)?"
        )

        agent = SingleToolAgent(self.client)
        result, response = agent.call_tool(
            messages=[{"role": "user", "content": user_message}],
            tool_schema=STRATEGY_CLASSIFICATION_TOOL,
            max_tokens=256,
        )

        if db is not None:
            log_usage(
                db,
                "classify_strategy",
                getattr(self.client, "full_id", "unknown"),
                response.usage,
                project_id or "",
                strategy_name,
            )

        strategy_type = result.get("strategy_type", "code-driven")
        reasoning = result.get("reasoning", "")

        if strategy_type not in ("code-driven", "positioning"):
            logger.warning(
                "LLM returned invalid strategy_type '%s' for '%s', defaulting to code-driven",
                strategy_type,
                strategy_name,
            )
            return "code-driven"

        logger.info(
            "Classified strategy '%s' as %s: %s",
            strategy_name,
            strategy_type,
            reasoning,
        )
        return strategy_type
