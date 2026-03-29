"""Secondary trigger entry points — summary and suggestion triggers.

Alternative ways to enter the pipeline that don't go through the
standard commit evaluation flow.
"""

from __future__ import annotations

import logging
import sys

from social_hook.config.yaml import load_full_config
from social_hook.db import operations as ops
from social_hook.db.connection import init_database
from social_hook.errors import ConfigError, DatabaseError
from social_hook.filesystem import generate_id, get_db_path
from social_hook.llm.prompts import assemble_evaluator_context
from social_hook.models.core import CommitInfo, Decision
from social_hook.models.enums import PipelineStage

logger = logging.getLogger(__name__)


def run_summary_trigger(
    config,
    conn,
    db,
    project,
    summary: str,
    repo_path: str,
    verbose: bool = False,
) -> dict | None:
    """Generate an introductory first draft from project summary.

    Creates a Decision with trigger_source="manual" and decision="draft",
    then calls the drafter directly. No evaluator call needed.

    Returns draft info dict or None on failure.
    """
    from social_hook.compat import make_eval_compat
    from social_hook.config.project import load_project_config
    from social_hook.drafting import draft_for_platforms

    project_config = load_project_config(repo_path)

    # Create a manual decision (no commit)
    decision = Decision(
        id=generate_id("decision"),
        project_id=project.id,
        commit_hash="summary",
        decision="draft",
        reasoning="Summary-based introductory draft",
        commit_message="Project introduction",
        angle="Introduce the project and what it does",
        trigger_source="manual",
    )
    db.insert_decision(decision)
    db.emit_data_event("decision", "created", decision.id, project.id)

    # Assemble context (no commit timestamps)
    context = assemble_evaluator_context(db, project.id, project_config)

    # Build a minimal evaluation-compatible object for the drafter
    from social_hook.llm.schemas import (
        CommitAnalysis,
        LogEvaluationInput,
        PostCategorySchema,
        StrategyDecisionInput,
        TargetAction,
    )

    evaluation = LogEvaluationInput(
        commit_analysis=CommitAnalysis(
            summary=summary[:500],
            episode_tags=["introduction"],
        ),
        strategies={
            "default": StrategyDecisionInput(
                action=TargetAction.draft,
                reason="Summary-based introduction",
                angle="Introduce the project and what it does",
                post_category=PostCategorySchema.opportunistic,
            ),
        },
    )
    eval_compat = make_eval_compat(evaluation, "draft")

    # Draft
    db.emit_data_event("pipeline", PipelineStage.DRAFTING, "summary", project.id)

    commit = CommitInfo(
        hash="summary",
        message="Project introduction",
        diff=summary[:1000],
        files_changed=[],
    )

    try:
        draft_results = draft_for_platforms(
            config=config,
            conn=conn,
            db=db,
            project=project,
            decision_id=decision.id,
            evaluation=eval_compat,
            context=context,
            commit=commit,
            project_config=project_config,
            verbose=verbose,
        )
    except Exception as e:
        logger.error("Summary draft failed: %s", e)
        if verbose:
            print(f"Summary draft failed: {e}", file=sys.stderr)
        return None

    if not draft_results:
        return None

    # Return first draft info
    first = draft_results[0]
    return {
        "decision_id": decision.id,
        "draft_id": first.draft.id,
        "platform": first.draft.platform,
        "content": first.draft.content,
    }


def run_suggestion_trigger(
    suggestion_id: str,
    project_id: str,
    config_path: str | None = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    """Trigger evaluation from an operator content suggestion.

    Similar to run_trigger() but:
    - No commit analysis stage (no commit)
    - Trigger content is the suggestion idea
    - trigger_type = 'operator_suggestion'

    Returns:
        Exit code: 0 = success, 1 = error
    """
    # 1. Load config
    try:
        config = load_full_config(
            yaml_path=config_path if config_path else None,
        )
    except ConfigError as e:
        logger.error("Config error: %s", e)
        if verbose:
            print(f"Config error: {e}", file=sys.stderr)
        return 1

    # 2. Initialize DB
    try:
        db_path = get_db_path()
        conn = init_database(db_path)
    except DatabaseError as e:
        logger.error("Database error: %s", e)
        if verbose:
            print(f"Database error: {e}", file=sys.stderr)
        return 1

    # 3. Validate project exists
    project = ops.get_project(conn, project_id)
    if project is None:
        logger.error("Project '%s' not found", project_id)
        if verbose:
            print(f"Project '{project_id}' not found", file=sys.stderr)
        conn.close()
        return 1

    # 4. Validate suggestion exists and is pending
    suggestions = ops.get_suggestions_by_project(conn, project_id)
    suggestion = None
    for s in suggestions:
        if s.id == suggestion_id:
            suggestion = s
            break

    if suggestion is None:
        conn.close()
        raise ConfigError(f"Suggestion '{suggestion_id}' not found in project '{project_id}'")

    if suggestion.status != "pending":
        conn.close()
        raise ConfigError(
            f"Suggestion '{suggestion_id}' has status '{suggestion.status}', expected 'pending'"
        )

    # 5. Evaluate suggestion
    from social_hook.suggestions import evaluate_suggestion

    try:
        cycle_id = evaluate_suggestion(
            conn,
            config,
            project_id,
            suggestion_id,
            dry_run=dry_run,
        )
    except Exception as e:
        logger.error("Suggestion evaluation failed: %s", e)
        if verbose:
            print(f"Suggestion evaluation failed: {e}", file=sys.stderr)
        conn.close()
        return 1

    if cycle_id is None:
        logger.error("Suggestion evaluation returned no cycle for %s", suggestion_id)
        conn.close()
        return 1

    if verbose:
        print(f"Suggestion {suggestion_id} evaluated, cycle: {cycle_id}")

    conn.close()
    return 0
