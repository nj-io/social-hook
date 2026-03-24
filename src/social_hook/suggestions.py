"""Operator content suggestion processing.

Suggestions are a trigger source for the strategy evaluator,
alongside commits, time-based checks, and plugins.
"""

import logging
import sqlite3

from social_hook.db import operations as ops
from social_hook.filesystem import generate_id
from social_hook.models import ContentSuggestion, EvaluationCycle

logger = logging.getLogger(__name__)


def create_suggestion(
    conn: sqlite3.Connection,
    project_id: str,
    idea: str,
    strategy: str | None = None,
    media_refs: list[str] | None = None,
    source: str = "operator",
) -> ContentSuggestion:
    """Create a content suggestion.

    If strategy is None, the evaluator decides which strategies
    are relevant for this suggestion.
    """
    suggestion = ContentSuggestion(
        id=generate_id("suggestion"),
        project_id=project_id,
        idea=idea,
        strategy=strategy,
        media_refs=media_refs,
        status="pending",
        source=source,
    )
    ops.insert_content_suggestion(conn, suggestion)
    logger.info("Suggestion %s created (strategy=%s, source=%s)", suggestion.id, strategy, source)
    return suggestion


def evaluate_suggestion(
    conn: sqlite3.Connection,
    config: object,
    project_id: str,
    suggestion_id: str,
    dry_run: bool = False,
) -> str | None:
    """Evaluate a suggestion via the strategy evaluator.

    Creates an evaluation cycle with trigger_type='operator_suggestion'
    using Phase 2's evaluation_cycles CRUD in operations.py.
    The evaluator receives the suggestion idea as the trigger content
    alongside the project brief and strategy definitions.

    Returns evaluation_cycle_id or None.
    """
    try:
        # Find the suggestion
        suggestions = ops.get_suggestions_by_project(conn, project_id)
        suggestion = None
        for s in suggestions:
            if s.id == suggestion_id:
                suggestion = s
                break

        if suggestion is None:
            logger.error("Suggestion '%s' not found in project '%s'", suggestion_id, project_id)
            return None

        if suggestion.status != "pending":
            logger.warning(
                "Suggestion %s has status '%s', expected 'pending'",
                suggestion_id,
                suggestion.status,
            )
            return None

        # Create evaluation cycle
        cycle = EvaluationCycle(
            id=generate_id("cycle"),
            project_id=project_id,
            trigger_type="operator_suggestion",
            trigger_ref=suggestion_id,
        )

        if not dry_run:
            ops.insert_evaluation_cycle(conn, cycle)
            # Update suggestion status
            old_status = suggestion.status
            ops.update_suggestion_status(conn, suggestion_id, "evaluated")
            logger.info("Suggestion %s: %s -> evaluated", suggestion_id, old_status)
        else:
            logger.info(
                "[DRY RUN] Would create evaluation cycle %s for suggestion %s",
                cycle.id,
                suggestion_id,
            )

        # TODO: Call Phase 2's strategy evaluator with suggestion idea as trigger content.
        # The evaluator receives the suggestion alongside the project brief and
        # strategy definitions. Integration deferred until strategy evaluator API is finalized.

        return cycle.id

    except Exception:
        logger.error("Failed to evaluate suggestion %s", suggestion_id, exc_info=True)
        return None


def dismiss_suggestion(conn: sqlite3.Connection, suggestion_id: str) -> bool:
    """Dismiss a suggestion (status -> 'dismissed').

    Returns True if the suggestion was found and updated.
    """
    updated = ops.update_suggestion_status(conn, suggestion_id, "dismissed")
    if updated:
        logger.info("Suggestion %s -> dismissed", suggestion_id)
    else:
        logger.warning("Suggestion %s not found for dismissal", suggestion_id)
    return updated
