"""Pure decision logic for the trigger pipeline.

All functions are deterministic with no DB, LLM, or I/O dependencies.
They transform evaluation data into decision types and reasoning strings.
"""

from __future__ import annotations

import logging

from social_hook.parsing import enum_value

logger = logging.getLogger(__name__)


def _determine_overall_decision(
    strategies: dict,
) -> str:
    """Derive a single DecisionType from per-strategy decisions.

    Rules:
    - Empty strategies dict -> log warning, return "skip".
    - If any strategy has action "draft" -> "draft"
    - If all strategies have action "hold" -> "hold"
    - If all strategies have action "skip" -> "skip"
    - Mixed hold+skip (no draft) -> "skip"
    """
    if not strategies:
        logger.warning("Empty strategies dict in _determine_overall_decision")
        return "skip"

    actions = set()
    for decision in strategies.values():
        actions.add(enum_value(decision.action))

    if "draft" in actions:
        return "draft"
    if actions == {"hold"}:
        return "hold"
    return "skip"


def _combine_strategy_reasoning(
    strategies: dict,
) -> str:
    """Combine per-strategy reasoning into a single string for the Decision record.

    Format: "strategy-name: reason; strategy-name: reason"
    Truncate to 500 chars if needed.
    """
    parts = []
    for name, decision in strategies.items():
        parts.append(f"{name}: {decision.reason}")
    combined = "; ".join(parts)
    if len(combined) > 500:
        combined = combined[:497] + "..."
    return combined


def _is_trivial_classification(analyzer_result) -> bool:
    """Check if the analyzer classified the commit as trivial."""
    if analyzer_result is None:
        return False
    ca = analyzer_result.commit_analysis
    if ca and ca.classification:
        return bool(enum_value(ca.classification) == "trivial")
    else:
        logger.warning("Analyzer result has no classification, treating as non-trivial")
        return False
