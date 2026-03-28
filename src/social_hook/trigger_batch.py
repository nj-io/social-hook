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
from social_hook.models import CommitInfo, PipelineStage
from social_hook.trigger_context import (
    AnalyzerOutcome,
    build_platform_summaries,
    fetch_evaluator_extras,
)
from social_hook.trigger_git import parse_commit_info

if TYPE_CHECKING:
    from social_hook.models import Decision
    from social_hook.trigger_context import TriggerContext

logger = logging.getLogger(__name__)


def _run_commit_analyzer(
    ctx: TriggerContext,
    context,
    evaluator_client,
) -> AnalyzerOutcome:
    """Pure gating function — no LLM calls.

    Checks the commit_analysis_interval counter and returns a gating signal.
    Stage 1 LLM runs at the call site: inline in run_trigger (single-commit)
    or inside evaluate_batch (batch).

    Returns AnalyzerOutcome with:
    - result: Cached CommitAnalysisResult if available, else None.
    - should_evaluate: True when interval threshold met, False to defer.
    """
    from social_hook.llm.schemas import CommitAnalysisResult
    from social_hook.parsing import safe_json_loads

    # 1. Increment commit count
    new_count = ops.increment_analysis_commit_count(ctx.conn, ctx.project.id)

    # 2. Check interval threshold
    interval = 1
    if ctx.project_config and hasattr(ctx.project_config, "context") and ctx.project_config.context:
        interval = getattr(ctx.project_config.context, "commit_analysis_interval", 1)
    if interval < 1:
        interval = 1

    logger.info(
        "Commit analyzer: count=%d, interval=%d, project=%s",
        new_count,
        interval,
        ctx.project.id,
    )

    if new_count < interval:
        # Interval not met — check for cached analysis from most recent cycle
        cached_cycle = ops.get_latest_cycle_with_analysis(ctx.conn, ctx.project.id)
        if cached_cycle and cached_cycle.commit_analysis_json:
            cached_data = safe_json_loads(
                cached_cycle.commit_analysis_json,
                "cached_commit_analysis_json",
                default=None,
            )
            if cached_data is not None:
                try:
                    result = CommitAnalysisResult.model_validate(cached_data)
                    if ctx.verbose:
                        print(f"Using cached analysis (count {new_count}/{interval})")
                    return AnalyzerOutcome(result=result, should_evaluate=False)
                except Exception as e:
                    logger.warning("Failed to validate cached analysis, running fresh: %s", e)
            else:
                logger.warning("Failed to parse cached analysis JSON, running fresh")
        else:
            # No cache yet (first commits on this project) — still defer
            if ctx.verbose:
                print(f"No cached analysis, deferring (count {new_count}/{interval})")
            return AnalyzerOutcome(result=None, should_evaluate=False)

    # 3. Threshold met — signal caller to proceed. No LLM here.
    ops.reset_analysis_commit_count(ctx.conn, ctx.project.id)
    if ctx.verbose:
        print(f"Commit analysis interval met (count {new_count}/{interval})")
    return AnalyzerOutcome(result=None, should_evaluate=True)


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
            classification = (
                analyzer_result.commit_analysis.classification.value
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
    if result == 0:
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
            "Batch targets path returned non-zero (%d), not marking deferred decisions", result
        )

    return result
