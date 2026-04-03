"""Batch evaluation and commit analyzer for the trigger pipeline.

evaluate_batch() combines multiple deferred commits into a single
evaluation. _run_commit_analyzer() gates whether evaluation proceeds
based on an interval counter.
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

from social_hook.db import operations as ops
from social_hook.models.core import CommitInfo
from social_hook.models.enums import PipelineStage
from social_hook.trigger_context import (
    AnalyzerOutcome,
    build_platform_summaries,
    fetch_evaluator_extras,
)
from social_hook.trigger_git import parse_commit_info

if TYPE_CHECKING:
    from social_hook.models.core import Decision
    from social_hook.trigger_context import TriggerContext

logger = logging.getLogger(__name__)


def _run_commit_analyzer_gate(
    conn,
    project,
    project_config,
    verbose: bool = False,
) -> AnalyzerOutcome:
    """Lightweight interval gating — runs EARLY in run_trigger before expensive work.

    Only increments the counter and checks the threshold. No context assembly,
    no LLM client, no cached analysis lookup. Used by the fast-path deferral
    in run_trigger to skip context assembly, discovery, and LLM setup for
    commits that will be deferred.
    """
    interval = 1
    if project_config and hasattr(project_config, "context") and project_config.context:
        interval = getattr(project_config.context, "commit_analysis_interval", 1)
    if interval < 1:
        interval = 1

    if interval <= 1:
        # No batching — always evaluate
        return AnalyzerOutcome(result=None, should_evaluate=True)

    new_count = ops.increment_analysis_commit_count(conn, project.id)

    logger.info(
        "Interval gate: count=%d, interval=%d, project=%s",
        new_count,
        interval,
        project.id,
    )

    if new_count < interval:
        if verbose:
            print(f"Commit deferred by interval gate (count {new_count}/{interval})")
        return AnalyzerOutcome(result=None, should_evaluate=False)

    if verbose:
        print(f"Interval threshold met (count {new_count}/{interval})")
    return AnalyzerOutcome(result=None, should_evaluate=True)


def _reset_interval_counter(
    ctx: TriggerContext,
    context,
    evaluator_client,
) -> None:
    """Reset interval counter after threshold commit enters the evaluation path."""
    ops.reset_analysis_commit_count(ctx.conn, ctx.project.id)
    if ctx.verbose:
        print("Analysis commit counter reset")


def evaluate_batch(
    ctx: TriggerContext,
    deferred_commits: list[Decision],
    trigger_commit_hash: str,
    context,
    evaluator_client,
) -> int:
    """Evaluate a batch of deferred commits together with the trigger commit.

    Combines diffs from all deferred commits plus the trigger commit, runs
    stage 1 (CommitAnalyzer) and stage 2 (Evaluator) on the combined input,
    then passes through the full targets pipeline via _run_targets_path.

    Connection ownership: does NOT own ctx.conn. Caller manages lifecycle.

    Args:
        ctx: Trigger context (config, conn, db, project, etc.)
        deferred_commits: Deferred decisions to include in batch
        trigger_commit_hash: The commit that crossed the threshold
        context: Assembled evaluator context
        evaluator_client: LLM client for evaluation

    Returns:
        0 on success, non-zero on failure
    """
    # Lazy import to avoid circular: trigger_batch -> trigger -> trigger_batch
    from social_hook.llm.analyzer import CommitAnalyzer
    from social_hook.llm.evaluator import Evaluator
    from social_hook.trigger import _run_targets_path

    # 0. Mark deferred decisions as "processing" so UI shows all rows as active
    deferred_ids = [d.id for d in deferred_commits]
    ops.mark_decisions_processing(ctx.conn, deferred_ids)
    for d in deferred_commits:
        ctx.db.emit_data_event("decision", "updated", d.id, ctx.project.id)

    # 1. Build combined CommitInfo from all deferred hashes + trigger hash
    all_hashes = [d.commit_hash for d in deferred_commits] + [trigger_commit_hash]
    diffs = []
    all_files: list[str] = []
    total_insertions = 0
    total_deletions = 0

    for h in all_hashes:
        ci = parse_commit_info(h, ctx.project.repo_path)
        if ci.diff:
            first_line = ci.message.splitlines()[0] if ci.message else ""
            diffs.append(f"--- Commit {h[:8]}: {first_line} ---\n{ci.diff}")
            all_files.extend(ci.files_changed)
            total_insertions += ci.insertions
            total_deletions += ci.deletions

    if not diffs:
        logger.warning("Batch evaluation: all commits had empty diffs, skipping")
        return 0

    # Use trigger commit's info as base
    trigger_ci = parse_commit_info(trigger_commit_hash, ctx.project.repo_path)
    combined = CommitInfo(
        hash=trigger_commit_hash,
        message=f"Batch of {len(all_hashes)} commits: {trigger_ci.message}",
        diff="\n\n".join(diffs),
        files_changed=list(dict.fromkeys(all_files)),  # dedupe, preserve order
        insertions=total_insertions,
        deletions=total_deletions,
        timestamp=trigger_ci.timestamp,
        parent_timestamp=trigger_ci.parent_timestamp,
    )

    # 2. Run stage 1: CommitAnalyzer on combined diffs
    ctx.db.emit_data_event(
        "pipeline", PipelineStage.ANALYZING, trigger_commit_hash[:8], ctx.project.id
    )
    if ctx.task_id:
        ctx.db.emit_task_stage(ctx.task_id, "analyzing", "Analyzing commit", ctx.project.id)
    analyzer_result = None
    try:
        analyzer = CommitAnalyzer(evaluator_client)
        analyzer_result = analyzer.analyze(
            commit=combined,
            context=context,
            db=ctx.db,
            show_prompt=ctx.show_prompt,
        )
        if ctx.verbose:
            from social_hook.parsing import enum_value

            classification = (
                enum_value(analyzer_result.commit_analysis.classification)
                if analyzer_result.commit_analysis.classification
                else "unknown"
            )
            print(f"Batch stage 1 complete (classification: {classification})")
    except Exception as e:
        logger.warning("Batch commit analyzer failed (non-fatal): %s", e)
        if ctx.verbose:
            print(f"Batch commit analyzer skipped: {e}", file=sys.stderr)

    # 3. Run stage 2: Evaluator on combined diffs
    platform_summaries = build_platform_summaries(ctx.config)
    extras = fetch_evaluator_extras(ctx.conn, ctx.project.id, ctx.config)
    scheduling_state = extras.scheduling_state
    all_topics = extras.all_topics
    held_topics = extras.held_topics
    active_arcs_all = extras.active_arcs

    ctx.db.emit_data_event(
        "pipeline", PipelineStage.EVALUATING, trigger_commit_hash[:8], ctx.project.id
    )
    if ctx.task_id:
        ctx.db.emit_task_stage(ctx.task_id, "evaluating", "Evaluating strategies", ctx.project.id)
    try:
        evaluator = Evaluator(evaluator_client)
        evaluation = evaluator.evaluate(
            combined,
            context,
            ctx.db,
            show_prompt=ctx.show_prompt,
            platform_summaries=platform_summaries or None,
            media_config=ctx.config.media_generation,
            media_guidance=ctx.project_config.media_guidance if ctx.project_config else None,
            strategy_config=ctx.project_config.strategy if ctx.project_config else None,
            summary_config=ctx.project_config.summary if ctx.project_config else None,
            scheduling_state=scheduling_state,
            strategies=ctx.config.content_strategies or None,
            held_topics=held_topics or None,
            active_arcs_all=active_arcs_all or None,
            targets=ctx.config.targets or None,
            all_topics=all_topics or None,
            analysis=analyzer_result,
        )
    except Exception as e:
        logger.error("LLM API error during batch evaluation: %s", e)
        if ctx.verbose:
            print(f"Batch evaluation failed: {e}", file=sys.stderr)
        return 3

    # 4. Run full targets pipeline
    analysis = evaluation.commit_analysis
    try:
        result = _run_targets_path(
            ctx=ctx,
            evaluation=evaluation,
            analysis=analysis,
            commit_hash=trigger_commit_hash,
            context=context,
            evaluator_client=evaluator_client,
            analyzer_result=analyzer_result,
            trigger_type="batch",
            batch_commit_hashes=all_hashes,
        )
    except Exception as e:
        logger.error("Batch targets path failed: %s", e)
        return 3

    # 5. After success: mark deferred decisions with batch_id
    exit_code: int = result.exit_code if hasattr(result, "exit_code") else result  # type: ignore[assignment]
    if exit_code == 0:
        # Get cycle ID from the cycle just inserted by _run_targets_path
        recent_cycles = ops.get_recent_cycles(ctx.conn, ctx.project.id, limit=1)
        cycle_id = recent_cycles[0].id if recent_cycles else "unknown"

        deferred_ids = [d.id for d in deferred_commits]
        ops.mark_deferred_decisions_batched(ctx.conn, deferred_ids, cycle_id)
        for d in deferred_commits:
            ctx.db.emit_data_event("decision", "updated", d.id, ctx.project.id)

        if ctx.verbose:
            print(f"Batch evaluation complete: {len(all_hashes)} commits, cycle {cycle_id}")
    else:
        logger.warning(
            "Batch targets path returned non-zero (%d), not marking deferred decisions",
            exit_code,
        )

    return exit_code
