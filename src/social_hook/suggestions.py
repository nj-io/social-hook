"""Operator content suggestion processing.

Suggestions are a trigger source for the strategy evaluator,
alongside commits, time-based checks, and plugins.
"""

import logging
import sqlite3
from typing import Any

from social_hook.db import operations as ops
from social_hook.filesystem import generate_id
from social_hook.models.content import ContentSuggestion, EvaluationCycle
from social_hook.models.core import CommitInfo

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
    config: Any,
    project_id: str,
    suggestion_id: str,
    dry_run: bool = False,
) -> str | None:
    """Evaluate a suggestion via the strategy evaluator.

    Creates an evaluation cycle with trigger_type='operator_suggestion',
    runs the evaluator with the suggestion idea as trigger content,
    then routes results through the drafting pipeline.

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
            old_status = suggestion.status
            ops.update_suggestion_status(conn, suggestion_id, "evaluated")
            logger.info("Suggestion %s: %s -> evaluated", suggestion_id, old_status)
        else:
            logger.info(
                "[DRY RUN] Would create evaluation cycle %s for suggestion %s",
                cycle.id,
                suggestion_id,
            )
            return cycle.id

        # Run evaluation + drafting if config is available
        if config is None or not getattr(config, "models", None):
            logger.info(
                "No config provided, skipping LLM evaluation for suggestion %s", suggestion_id
            )
            return cycle.id

        from social_hook.config.project import load_project_config
        from social_hook.llm.evaluator import Evaluator
        from social_hook.llm.factory import create_client
        from social_hook.llm.prompts import assemble_evaluator_context

        project = ops.get_project(conn, project_id)
        if project is None:
            logger.error("Project '%s' not found", project_id)
            return cycle.id

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(conn, dry_run=dry_run)
        project_config = load_project_config(project.repo_path)
        context = assemble_evaluator_context(db, project_id, project_config)

        # Build a synthetic CommitInfo with the suggestion idea
        commit = CommitInfo(
            hash=f"suggestion:{suggestion_id[:8]}",
            message=suggestion.idea,
            diff="",
            files_changed=[],
        )

        # Create evaluator client and evaluate
        evaluator_client = create_client(config.models.evaluator, config)
        evaluator = Evaluator(evaluator_client)
        evaluation = evaluator.evaluate(
            commit,
            context,
            db,
            strategy_config=project_config.strategy if project_config else None,
            summary_config=project_config.summary if project_config else None,
            strategies=config.content_strategies or None,
        )

        # Route and draft if targets config exists
        if getattr(config, "targets", None) and isinstance(config.targets, dict) and config.targets:
            from social_hook.content_sources import content_sources
            from social_hook.drafting import draft as run_draft
            from social_hook.drafting_intents import intent_from_routed_targets
            from social_hook.models.core import Decision
            from social_hook.routing import route_to_targets

            target_actions = route_to_targets(evaluation.strategies, config, conn)
            draftable_actions = [a for a in target_actions if a.action == "draft"]
            if draftable_actions:
                decision = Decision(
                    id=generate_id("decision"),
                    project_id=project_id,
                    commit_hash=commit.hash,
                    decision="draft",
                    reasoning=suggestion.idea,
                    commit_message=suggestion.idea,
                    trigger_source="operator_suggestion",
                )
                ops.insert_decision(conn, decision)

                intents = intent_from_routed_targets(
                    draftable_actions,
                    decision.id,
                    evaluation,
                    config,
                    conn,
                    project_id=project_id,
                    content_source_registry=content_sources,
                )
                for _intent in intents:
                    run_draft(
                        _intent,
                        config,
                        conn,
                        db,
                        project,
                        context,
                        commit,
                        project_config=project_config,
                        dry_run=dry_run,
                    )
        else:
            # Legacy path: draft for platforms
            from social_hook.drafting import draft as run_draft
            from social_hook.drafting_intents import intent_from_platforms
            from social_hook.models.core import Decision
            from social_hook.parsing import enum_value

            first_strategy = next(iter(evaluation.strategies.values()), None)
            if first_strategy and enum_value(first_strategy.action) == "draft":
                decision = Decision(
                    id=generate_id("decision"),
                    project_id=project_id,
                    commit_hash=commit.hash,
                    decision="draft",
                    reasoning=suggestion.idea,
                    commit_message=suggestion.idea,
                    trigger_source="operator_suggestion",
                )
                ops.insert_decision(conn, decision)

                intent = intent_from_platforms(evaluation, decision.id, config)
                run_draft(
                    intent,
                    config,
                    conn,
                    db,
                    project,
                    context,
                    commit,
                    project_config=project_config,
                )

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
