"""One-shot trigger: commit evaluation and draft creation pipeline."""

from __future__ import annotations

import logging
import sys

from social_hook.config.yaml import load_full_config
from social_hook.db import operations as ops
from social_hook.db.connection import init_database
from social_hook.error_feed import ErrorSeverity, error_feed
from social_hook.errors import ConfigError, DatabaseError
from social_hook.filesystem import generate_id, get_db_path
from social_hook.llm.dry_run import DryRunContext
from social_hook.llm.prompts import assemble_evaluator_context
from social_hook.models.core import Decision
from social_hook.models.enums import PipelineStage, is_draftable
from social_hook.parsing import enum_value
from social_hook.rate_limits import check_rate_limit

logger = logging.getLogger(__name__)


from social_hook.trigger_context import (  # noqa: E402, F401
    AnalyzerOutcome,
    TargetsPathResult,
    TriggerContext,
    build_platform_summaries,
    ensure_project_brief,
    fetch_evaluator_extras,
)
from social_hook.trigger_git import (  # noqa: E402, F401
    _get_current_branch,
    git_remote_origin,
    parse_commit_info,
)


def run_trigger(
    commit_hash: str,
    repo_path: str,
    dry_run: bool = False,
    config_path: str | None = None,
    verbose: bool = False,
    show_prompt: bool = False,
    trigger_source: str = "commit",
    existing_decision_id: str | None = None,
    current_branch: str | None = None,
    task_id: str | None = None,
) -> int:
    """Run the commit-to-draft trigger pipeline.

    Exit codes:
        0 = success or unregistered (silent)
        1 = config error
        2 = DB error
        3 = LLM API error
        4 = Telegram error (non-fatal, draft still saved)

    Args:
        commit_hash: Git commit hash to evaluate
        repo_path: Path to the repository
        dry_run: If True, skip DB writes and real API calls
        config_path: Optional override for config location
        verbose: If True, print detailed output
        existing_decision_id: If provided, reuse this ID instead of generating
            a new one. Used by retrigger to update in-place (upsert).
        current_branch: Branch the commit belongs to. When provided, skips
            HEAD detection (important for retrigger/drain where HEAD is
            irrelevant). Falls back to reading HEAD if not supplied.

    Returns:
        Exit code (0-4)
    """
    # 1. Load config
    try:
        config = load_full_config(
            yaml_path=config_path if config_path else None,
        )
    except ConfigError as e:
        logger.error(f"Config error: {e}")
        error_feed.emit(
            ErrorSeverity.ERROR,
            f"Config error in trigger: {e}",
            context={"commit_hash": commit_hash, "repo_path": repo_path},
            source="config",
        )
        if verbose:
            print(f"Config error: {e}", file=sys.stderr)
        return 1

    # 2. Initialize DB
    try:
        db_path = get_db_path()
        conn = init_database(db_path)
    except DatabaseError as e:
        logger.error(f"Database error: {e}")
        error_feed.emit(
            ErrorSeverity.ERROR,
            f"Database error in trigger: {e}",
            context={"commit_hash": commit_hash},
            source="database",
        )
        if verbose:
            print(f"Database error: {e}", file=sys.stderr)
        return 2

    db = DryRunContext(conn, dry_run=dry_run)
    db.trigger_source = trigger_source

    # 3. Check registration
    project = ops.get_project_by_path(conn, repo_path)
    if project is None:
        # Try worktree detection via origin
        origin = git_remote_origin(repo_path)
        if origin:
            projects = ops.get_project_by_origin(conn, origin)
            if projects:
                project = projects[0]  # Use first match

    if project is None:
        # Not registered - exit silently
        if verbose:
            print(f"Repository {repo_path} is not registered. Exiting.")
        conn.close()
        return 0

    if project.paused:
        if verbose:
            print(f"Project {project.name} is paused. Skipping.")
        conn.close()
        return 0

    # Resolve branch: callers that know the branch (retrigger, drain) pass it
    # directly via current_branch. Git hooks read HEAD (correct — developer
    # just committed). Fall back to HEAD when no branch is supplied.
    if not current_branch:
        current_branch = _get_current_branch(repo_path)

    # Branch filter: skip commits from non-target branches.
    # Manual retriggers and drain bypass this — the user explicitly chose the commit.
    if (
        project.trigger_branch
        and current_branch != project.trigger_branch
        and trigger_source not in ("manual", "drain")
    ):
        branch_desc = current_branch or "(detached HEAD)"
        if verbose:
            print(
                f"Branch '{branch_desc}' doesn't match trigger branch "
                f"'{project.trigger_branch}'. Skipping."
            )
        conn.close()
        return 0

    # 4. Rate limit gate (skip for manual triggers and drain)
    if trigger_source not in ("manual", "drain"):
        gate_result = check_rate_limit(conn, config.rate_limits)
        if gate_result.blocked:
            decision = Decision(
                id=existing_decision_id or generate_id("decision"),
                project_id=project.id,
                commit_hash=commit_hash,
                decision="deferred_eval",
                reasoning=gate_result.reason,
                commit_message=None,
                trigger_source=trigger_source,
                branch=current_branch,
            )
            if existing_decision_id:
                ops.upsert_decision(conn, decision)
            else:
                db.insert_decision(decision)
            db.emit_data_event("decision", "created", decision.id, project.id)
            if verbose:
                print(f"Evaluation deferred: {gate_result.reason}")
            conn.close()
            return 0

    # 5. Load project config
    from social_hook.config.project import load_project_config

    project_config = load_project_config(repo_path)

    # 5b. Interval gating — BEFORE expensive context assembly, discovery, LLM setup.
    # Deferred commits only need config + project + commit message, not full context.
    has_targets = (
        getattr(config, "targets", None) and isinstance(config.targets, dict) and config.targets
    )

    # Bypass switch: manual retrigger respects interval by default (set True to skip queue)
    MANUAL_BYPASSES_INTERVAL = False  # noqa: N806
    skip_interval = (
        (trigger_source == "manual" and MANUAL_BYPASSES_INTERVAL)
        or trigger_source == "drain"  # rate-limit-drained commits skip interval (already counted)
    )

    if has_targets and not skip_interval:
        # Cheap gating check — only needs counter + interval setting
        outcome = _run_commit_analyzer_gate(conn, project, project_config, verbose)
        if not outcome.should_evaluate:
            # Fast path: parse commit for message, create deferred decision, return
            commit = parse_commit_info(commit_hash, repo_path)
            decision = Decision(
                id=existing_decision_id or generate_id("decision"),
                project_id=project.id,
                commit_hash=commit_hash,
                decision="deferred_eval",
                reasoning="Deferred: commit awaiting batch threshold",
                commit_message=commit.message,
                processed=True,  # NOT drained by scheduler
                trigger_source=trigger_source,
                branch=current_branch,
            )
            if existing_decision_id:
                ops.upsert_decision(conn, decision)
            else:
                db.insert_decision(decision)
            db.emit_data_event("decision", "created", decision.id, project.id)
            db.emit_data_event("pipeline", PipelineStage.QUEUED, commit_hash[:8], project.id)
            if verbose:
                print("Evaluation deferred: interval not met")
            conn.close()
            return 0

    # 6. Parse commit (needed for timestamp-filtered context)
    commit = parse_commit_info(commit_hash, repo_path)

    # 6b. Assemble context (with commit timestamps for narrative filtering)
    context = assemble_evaluator_context(
        db,
        project.id,
        project_config,
        commit_timestamp=commit.timestamp,
        parent_timestamp=commit.parent_timestamp,
    )

    # 6b. Auto-discovery: seed project summary if missing, refresh if stale
    ensure_project_brief(
        config=config,
        project_config=project_config,
        conn=conn,
        db=db,
        project=project,
        context=context,
        entity_id=commit_hash[:8],
        verbose=verbose,
    )

    if verbose and context.project_summary:
        print(f"Using project summary ({len(context.project_summary)} chars)")

    if verbose:
        print(f"Processing commit {commit.hash[:8]}: {commit.message}")

    # 7. Evaluate
    from social_hook.llm.evaluator import Evaluator
    from social_hook.llm.factory import create_client

    try:
        evaluator_client = create_client(config.models.evaluator, config, verbose=verbose)
    except ConfigError as e:
        logger.error(f"Config error: {e}")
        error_feed.emit(
            ErrorSeverity.ERROR,
            f"Evaluator client config error: {e}",
            context={"commit_hash": commit_hash, "project_id": project.id},
            source="config",
        )
        if verbose:
            print(f"Config error: {e}", file=sys.stderr)
        conn.close()
        return 1

    # Stage 1: Commit Analyzer (targets path only, with interval gating)
    analyzer_result = None
    if has_targets:
        ctx = TriggerContext(
            config=config,
            conn=conn,
            db=db,
            project=project,
            commit=commit,
            project_config=project_config,
            current_branch=current_branch,
            dry_run=dry_run,
            verbose=verbose,
            show_prompt=show_prompt,
            existing_decision_id=existing_decision_id,
            task_id=task_id,
        )

        # Reset counter (was incremented by early gate)
        _reset_interval_counter(ctx=ctx, context=context, evaluator_client=evaluator_client)

        # Check for deferred commits to batch
        deferred = ops.get_interval_deferred_decisions(conn, project.id)
        if deferred:
            result = evaluate_batch(
                ctx=ctx,
                deferred_commits=deferred,
                trigger_commit_hash=commit_hash,
                context=context,
                evaluator_client=evaluator_client,
            )
            conn.close()
            return 0
        else:
            # Threshold met — check for deferred commits to batch
            deferred = ops.get_interval_deferred_decisions(conn, project.id)
            if deferred:
                result = evaluate_batch(
                    ctx=ctx,
                    deferred_commits=deferred,
                    trigger_commit_hash=commit_hash,
                    context=context,
                    evaluator_client=evaluator_client,
                )
                conn.close()
                return result

    # Build evaluator context helpers (only for single-commit path;
    # evaluate_batch builds its own via fetch_evaluator_extras)
    platform_summaries = build_platform_summaries(config)
    extras = fetch_evaluator_extras(conn, project.id, config)
    scheduling_state = extras.scheduling_state
    all_topics = extras.all_topics
    held_topics = extras.held_topics
    active_arcs_all = extras.active_arcs

    if has_targets:
        # Single-commit path: run stage 1 inline
        db.emit_data_event("pipeline", PipelineStage.ANALYZING, commit_hash[:8], project.id)
        try:
            from social_hook.llm.analyzer import CommitAnalyzer

            stage1 = CommitAnalyzer(evaluator_client)
            analyzer_result = stage1.analyze(
                commit=commit, context=context, db=db, show_prompt=show_prompt
            )
            if verbose:
                cls = (
                    enum_value(analyzer_result.commit_analysis.classification)
                    if analyzer_result.commit_analysis.classification
                    else "unknown"
                )
                print(f"Stage 1 complete (classification: {cls})")
        except Exception as e:
            logger.warning("Commit analyzer failed (non-fatal): %s", e, exc_info=True)
            analyzer_result = None

        # Trivial check on fresh analysis
        if analyzer_result is not None and _is_trivial_classification(analyzer_result):
            logger.info("Trivial commit %s, skipping strategy evaluation", commit_hash[:8])
            result = _run_trivial_skip(
                ctx=ctx, analyzer_result=analyzer_result, commit_hash=commit_hash
            )
            conn.close()
            return result

        # Single-commit path: run stage 1 inline
        db.emit_data_event("pipeline", PipelineStage.ANALYZING, commit_hash[:8], project.id)
        if ctx.task_id:
            ctx.db.emit_task_stage(ctx.task_id, "analyzing", "Analyzing commit", project.id)
        try:
            from social_hook.llm.analyzer import CommitAnalyzer

            stage1 = CommitAnalyzer(evaluator_client)
            analyzer_result = stage1.analyze(
                commit=commit, context=context, db=db, show_prompt=show_prompt
            )
            if verbose:
                cls = (
                    analyzer_result.commit_analysis.classification.value
                    if analyzer_result.commit_analysis.classification
                    else "unknown"
                )
                print(f"Stage 1 complete (classification: {cls})")
        except Exception as e:
            logger.warning("Commit analyzer failed (non-fatal): %s", e, exc_info=True)
            analyzer_result = None

        # Trivial check on fresh analysis
        if analyzer_result is not None and _is_trivial_classification(analyzer_result):
            logger.info("Trivial commit %s, skipping strategy evaluation", commit_hash[:8])
            result = _run_trivial_skip(
                ctx=ctx, analyzer_result=analyzer_result, commit_hash=commit_hash
            )
            conn.close()
            return result

        db.emit_data_event("pipeline", PipelineStage.EVALUATING, commit_hash[:8], project.id)
        if ctx.task_id:
            ctx.db.emit_task_stage(ctx.task_id, "evaluating", "Evaluating strategies", project.id)

    # Guard: targets configured but no content strategies defined
    if has_targets and not config.content_strategies:
        logger.warning("Targets configured but no content strategies defined — skipping evaluation")
        decision = Decision(
            id=existing_decision_id or generate_id("decision"),
            project_id=project.id,
            commit_hash=commit_hash,
            decision="skip",
            reasoning="Targets configured but no content strategies defined",
            commit_message=commit.message,
            trigger_source=trigger_source,
            branch=current_branch,
        )
        if existing_decision_id:
            ops.upsert_decision(conn, decision)
        else:
            db.insert_decision(decision)
        db.emit_data_event("decision", "created", decision.id, project.id)
        if verbose:
            print("Skipped: no content strategies defined for targets")
        conn.close()
        return 0

    try:
        evaluator = Evaluator(evaluator_client)
        evaluation = evaluator.evaluate(
            commit,
            context,
            db,
            show_prompt=show_prompt,
            platform_summaries=platform_summaries or None,
            media_config=config.media_generation,
            media_guidance=project_config.media_guidance if project_config else None,
            strategy_config=project_config.strategy if project_config else None,
            summary_config=project_config.summary if project_config else None,
            scheduling_state=scheduling_state,
            strategies=config.content_strategies or None,
            held_topics=held_topics or None,
            active_arcs_all=active_arcs_all or None,
            targets=config.targets or None,
            all_topics=all_topics or None,
            analysis=analyzer_result,
        )
    except Exception as e:
        logger.error(f"LLM API error during evaluation: {e}")
        if verbose:
            print(f"LLM API error: {e}", file=sys.stderr)
        conn.close()
        return 3

    # 8. Map evaluation output to Decision
    analysis = evaluation.commit_analysis

    # --- New targets path: when config.targets has real target entries ---
    if has_targets:
        path_result = _run_targets_path(
            ctx=ctx,
            evaluation=evaluation,
            analysis=analysis,
            commit_hash=commit_hash,
            context=context,
            evaluator_client=evaluator_client,
            analyzer_result=analyzer_result,
        )
        conn.close()
        return path_result.exit_code

    # --- Legacy path: single "default" target ---
    logger.warning("No targets configured. Using legacy platform-based drafting.")
    target = evaluation.strategies.get("default")
    if target is None:
        logger.error("Evaluation missing 'default' target")
        if verbose:
            print("Error: evaluation missing 'default' target", file=sys.stderr)
        conn.close()
        return 3

    decision_type = enum_value(target.action)  # "draft", "hold", or "skip"

    decision = Decision(
        id=existing_decision_id or generate_id("decision"),
        project_id=project.id,
        commit_hash=commit_hash,
        decision=decision_type,
        reasoning=target.reason,
        commit_message=commit.message,
        angle=target.angle,
        episode_type=None,
        episode_tags=analysis.episode_tags,
        post_category=enum_value(target.post_category),
        arc_id=target.arc_id,
        media_tool=enum_value(target.media_tool),
        targets={"default": target.model_dump()},
        commit_summary=analysis.summary,
        consolidate_with=target.consolidate_with,
        reference_posts=target.reference_posts,
        branch=current_branch,
    )

    # Hold count enforcement
    if decision_type == "hold":
        max_hold = project_config.context.max_hold_count if project_config else 5
        current_held = ops.get_held_decisions(conn, project.id)
        if len(current_held) >= max_hold:
            logger.warning(f"Hold limit reached ({max_hold}), forcing skip for {commit_hash[:8]}")
            decision.decision = "skip"
            decision_type = "skip"

    if existing_decision_id:
        ops.upsert_decision(conn, decision)
    else:
        db.insert_decision(decision)
    db.emit_data_event("decision", "created", decision.id, project.id)

    # 8b. Arc activation: create new arc or link to existing
    if is_draftable(decision.decision):
        _arc_id = target.arc_id
        _new_arc_theme = target.new_arc_theme

        if _new_arc_theme and not _arc_id:
            try:
                from social_hook.narrative.arcs import create_arc as _create_arc

                new_arc_id = _create_arc(db.conn, project.id, _new_arc_theme)
                db.update_decision(decision.id, arc_id=new_arc_id)
                decision.arc_id = new_arc_id
                if verbose:
                    print(f"Created new arc: {new_arc_id} ({_new_arc_theme})")
            except Exception as e:
                logger.warning(f"Arc creation failed (non-fatal): {e}")
                if verbose:
                    print(f"Arc creation skipped: {e}", file=sys.stderr)

    # 8c. Held decision absorption
    if is_draftable(decision.decision) and target.consolidate_with:
        valid_ids = [d.id for d in context.held_decisions]
        absorbed = [cid for cid in target.consolidate_with if cid in valid_ids]
        if absorbed and not dry_run:
            batch_id = generate_id("batch")
            ops.mark_decisions_processed(conn, absorbed, batch_id)

    # 8d. Queue actions (supersede/drop + merge groups) — runs on ANY decision type
    if evaluation.queue_actions:
        for _target_name, actions in evaluation.queue_actions.items():
            for qa in actions:
                action_type = qa.action
                if action_type == "merge":
                    continue  # handled by _execute_merge_groups below
                if not dry_run:
                    draft_ref = ops.get_draft(conn, qa.draft_id)
                    # Intentionally excludes deferred — queue actions target active drafts only
                    if not draft_ref or draft_ref.status not in ("draft", "approved", "scheduled"):
                        if verbose:
                            print(f"Queue action skipped: draft {qa.draft_id} not actionable")
                        continue
                    ops.execute_queue_action(conn, action_type, qa.draft_id, qa.reason)
                if verbose:
                    print(f"Queue action: {action_type} draft {qa.draft_id}")

        # Execute merge groups (creates replacement drafts via drafter)
        if not dry_run:
            _execute_merge_groups(
                evaluation.queue_actions,
                config,
                conn,
                db,
                project,
                context,
                project_config,
                dry_run,
                verbose,
            )

    # 8e. Send decision notification for non-draftable decisions
    if (
        not dry_run
        and config.notification_level == "all_decisions"
        and not is_draftable(decision.decision)
    ):
        _send_decision_notification(config, project, commit, decision)

    if verbose:
        print(f"Decision: {decision_type}")
        print(f"Reasoning: {target.reason}")

    # 9. If draftable, create drafts per platform
    if is_draftable(decision.decision):
        from social_hook.drafting import draft
        from social_hook.drafting_intents import intent_from_platforms

        db.emit_data_event("pipeline", PipelineStage.DRAFTING, commit_hash[:8], project.id)
        intent = intent_from_platforms(evaluation, decision.id, config)

        draft_results = draft(
            intent,
            config,
            conn,
            db,
            project,
            context,
            commit,
            project_config=project_config,
            dry_run=dry_run,
            verbose=verbose,
        )

        # Increment arc post count if drafts were created for an arc
        if draft_results and decision.arc_id:
            try:
                from social_hook.narrative.arcs import increment_arc_post_count

                increment_arc_post_count(db.conn, decision.arc_id)
                if verbose:
                    print(f"Incremented post count for arc: {decision.arc_id}")
            except Exception as e:
                logger.warning(f"Arc post count increment failed (non-fatal): {e}")

        # Notifications
        if not dry_run:
            if draft_results:
                from social_hook.notifications import notify_draft_review

                notify_draft_review(
                    config,
                    project_name=project.name,
                    project_id=project.id,
                    commit_hash=commit.hash,
                    commit_message=commit.message,
                    draft_results=draft_results,
                )
            elif config.notification_level != "drafts_only":
                _send_decision_notification(config, project, commit, decision)

    conn.close()
    return 0


from social_hook.trigger_decisions import (  # noqa: E402, F401
    _combine_strategy_reasoning,
    _determine_overall_decision,
    _is_trivial_classification,
)


def _run_trivial_skip(
    ctx: TriggerContext,
    analyzer_result,
    commit_hash: str,
) -> int:
    """Handle trivial commits: create cycle, do tag matching, skip stage 2."""
    import json

    from social_hook.models.content import EvaluationCycle

    analysis = analyzer_result.commit_analysis

    # Create evaluation cycle record
    cycle = EvaluationCycle(
        id=generate_id("cycle"),
        project_id=ctx.project.id,
        trigger_type="commit",
        trigger_ref=commit_hash,
    )
    ctx.db.insert_evaluation_cycle(cycle)

    # Store analysis JSON on the cycle for caching
    try:
        analysis_json = json.dumps(analyzer_result.model_dump(), default=str)
        ops.update_cycle_analysis_json(ctx.conn, cycle.id, analysis_json)
    except Exception as e:
        logger.warning(f"Failed to cache analysis JSON (non-fatal): {e}")

    # Tag-to-topic matching (even trivial commits may match topics)
    # Deduplicate: a topic matching multiple tags should only be incremented once
    incremented_topic_ids: set[str] = set()
    for tag in analysis.episode_tags:
        matching_topics = ops.get_topics_matching_tag(ctx.conn, ctx.project.id, tag)
        for topic in matching_topics:
            if topic.id not in incremented_topic_ids:
                ops.increment_topic_commit_count(ctx.conn, topic.id)
                incremented_topic_ids.add(topic.id)
            ops.insert_topic_commit(ctx.conn, topic.id, commit_hash, matched_tag=tag)

    # Create skip decision
    decision = Decision(
        id=ctx.existing_decision_id or generate_id("decision"),
        project_id=ctx.project.id,
        commit_hash=commit_hash,
        decision="skip",
        reasoning="Trivial commit — skipped strategy evaluation",
        commit_message=ctx.commit.message,
        episode_tags=analysis.episode_tags,
        commit_summary=analysis.summary,
        branch=ctx.current_branch,
    )

    if ctx.existing_decision_id:
        ops.upsert_decision(ctx.conn, decision)
    else:
        ctx.db.insert_decision(decision)
    ctx.db.emit_data_event("decision", "created", decision.id, ctx.project.id)

    if ctx.verbose:
        print("Decision: skip (trivial commit)")
        print(f"Summary: {analysis.summary}")

    return 0


from social_hook.trigger_batch import (  # noqa: E402, F401
    _reset_interval_counter,
    _run_commit_analyzer_gate,
    evaluate_batch,
)
from social_hook.trigger_side_effects import (  # noqa: E402, F401
    _run_diagnostics,
    _send_decision_notification,
    _trigger_brief_update,
)

# Backward-compat alias
_run_commit_analyzer = _run_commit_analyzer_gate  # noqa: F841


def _run_targets_path(
    ctx: TriggerContext,
    evaluation,
    analysis,
    commit_hash: str,
    context,
    evaluator_client,
    analyzer_result=None,
    trigger_type: str = "commit",
    batch_commit_hashes: list[str] | None = None,
    batch_deferred_ids: list[str] | None = None,
) -> TargetsPathResult:
    """New targets pipeline path: multi-strategy -> multi-target routing."""
    from social_hook.models.content import EvaluationCycle

    # Create evaluation cycle record
    cycle = EvaluationCycle(
        id=generate_id("cycle"),
        project_id=ctx.project.id,
        trigger_type=trigger_type,
        trigger_ref=",".join(batch_commit_hashes) if batch_commit_hashes else commit_hash,
    )
    ctx.db.insert_evaluation_cycle(cycle)

    # -- Phase A: Associate deferred batch decisions with this cycle immediately --
    if batch_deferred_ids:
        try:
            ops.mark_deferred_decisions_batched(ctx.conn, batch_deferred_ids, cycle.id)
            for did in batch_deferred_ids:
                ctx.db.emit_data_event("decision", "updated", did, ctx.project.id)
        except Exception:
            logger.warning("Batch membership marking failed (non-fatal)", exc_info=True)

    # If stage 1 analyzer produced a result, use it for enrichment
    if analyzer_result is not None:
        import json

        # Store analysis JSON on the cycle for caching
        try:
            analysis_json = json.dumps(analyzer_result.model_dump(), default=str)
            ops.update_cycle_analysis_json(ctx.conn, cycle.id, analysis_json)
        except Exception as e:
            logger.warning(f"Failed to cache analysis JSON (non-fatal): {e}")

        # Enrich the evaluator's analysis with stage 1 classification
        if analyzer_result.commit_analysis.classification:
            analysis.classification = analyzer_result.commit_analysis.classification

        # Use stage 1 tags if evaluator produced none
        if not analysis.episode_tags and analyzer_result.commit_analysis.episode_tags:
            analysis.episode_tags = analyzer_result.commit_analysis.episode_tags

        if ctx.verbose:
            classification = (
                enum_value(analyzer_result.commit_analysis.classification)
                if analyzer_result.commit_analysis.classification
                else "unknown"
            )
            print(f"Stage 1 classification: {classification}")

    # Brief update: if commit is non-trivial, update the brief
    _trigger_brief_update(
        evaluation=evaluation,
        analysis=analysis,
        conn=ctx.conn,
        db=ctx.db,
        project=ctx.project,
        evaluator_client=evaluator_client,
        dry_run=ctx.dry_run,
        verbose=ctx.verbose,
        analyzer_result=analyzer_result,
    )

    # Tag-to-topic matching: increment commit counts and record junction
    incremented_topic_ids: set[str] = set()
    for tag in analysis.episode_tags:
        matching_topics = ops.get_topics_matching_tag(ctx.conn, ctx.project.id, tag)
        for topic in matching_topics:
            if topic.id not in incremented_topic_ids:
                ops.increment_topic_commit_count(ctx.conn, topic.id)
                incremented_topic_ids.add(topic.id)
            ops.insert_topic_commit(ctx.conn, topic.id, commit_hash, matched_tag=tag)

    # Process topic suggestions from stage 1 analyzer
    if analyzer_result and getattr(analyzer_result, "topic_suggestions", None):
        try:
            from social_hook.topics import process_topic_suggestions

            strategy_names = (
                list(ctx.config.content_strategies.keys()) if ctx.config.content_strategies else []
            )
            process_topic_suggestions(
                conn=ctx.conn,
                project_id=ctx.project.id,
                suggestions=analyzer_result.topic_suggestions,
                strategies=strategy_names,
                strategy_configs=ctx.config.content_strategies,
                llm_client=evaluator_client,
            )
        except Exception:
            logger.warning("Topic creation from analyzer suggestions failed", exc_info=True)

    # -- Phase E: Decision creation --
    ctx.db.emit_data_event("pipeline", PipelineStage.DECIDING, commit_hash[:8], ctx.project.id)
    if ctx.task_id:
        ctx.db.emit_task_stage(ctx.task_id, "deciding", "Processing decision", ctx.project.id)

    # Validate topic_id references belong to correct strategy (LLM Output Validation)
    for strategy_name, strat_decision in evaluation.strategies.items():
        if strat_decision.topic_id:
            referenced_topic = ops.get_topic(ctx.conn, strat_decision.topic_id)
            if referenced_topic is None:
                logger.warning(
                    "Evaluator referenced nonexistent topic %s for strategy %s, stripping",
                    strat_decision.topic_id,
                    strategy_name,
                )
                strat_decision.topic_id = None
            elif referenced_topic.strategy != strategy_name:
                logger.warning(
                    "Evaluator referenced topic %s (strategy=%s) from strategy %s, stripping",
                    strat_decision.topic_id,
                    referenced_topic.strategy,
                    strategy_name,
                )
                strat_decision.topic_id = None

    # Update content topic statuses for held topics
    for _strategy_name, strat_decision in evaluation.strategies.items():
        action = enum_value(strat_decision.action)
        if action == "hold" and strat_decision.topic_id:
            ops.update_topic_hold(ctx.conn, strat_decision.topic_id, strat_decision.reason)
            ops.emit_data_event(
                ctx.conn, "topic", "updated", strat_decision.topic_id, ctx.project.id
            )

    # Derive overall decision from per-strategy decisions
    decision_type = _determine_overall_decision(evaluation.strategies)

    # Get the first "draft" strategy for arc/angle/category or fall back to first strategy
    first_draft_strategy = None
    for _sn, sd in evaluation.strategies.items():
        if enum_value(sd.action) == "draft":
            first_draft_strategy = sd
            break
    representative = first_draft_strategy or next(iter(evaluation.strategies.values()))

    decision = Decision(
        id=ctx.existing_decision_id or generate_id("decision"),
        project_id=ctx.project.id,
        commit_hash=commit_hash,
        decision=decision_type,
        reasoning=_combine_strategy_reasoning(evaluation.strategies),
        commit_message=ctx.commit.message,
        angle=representative.angle,
        episode_type=None,
        episode_tags=analysis.episode_tags,
        post_category=enum_value(representative.post_category),
        arc_id=representative.arc_id,
        media_tool=enum_value(representative.media_tool),
        targets={k: v.model_dump() for k, v in evaluation.strategies.items()},
        commit_summary=analysis.summary,
        consolidate_with=representative.consolidate_with,
        reference_posts=representative.reference_posts,
        branch=ctx.current_branch,
    )

    # Hold count enforcement
    hold_limit_forced = False
    if decision_type == "hold":
        max_hold = ctx.project_config.context.max_hold_count if ctx.project_config else 5
        current_held = ops.get_held_decisions(ctx.conn, ctx.project.id)
        if len(current_held) >= max_hold:
            logger.warning(f"Hold limit reached ({max_hold}), forcing skip for {commit_hash[:8]}")
            decision.decision = "skip"
            decision_type = "skip"
            hold_limit_forced = True

    if ctx.existing_decision_id:
        ops.upsert_decision(ctx.conn, decision)
    else:
        ctx.db.insert_decision(decision)
    ctx.db.emit_data_event("decision", "created", decision.id, ctx.project.id)

    # Set batch_id on trigger decision (after it's been created/upserted)
    if batch_deferred_ids:
        ctx.conn.execute(
            "UPDATE decisions SET batch_id = ? WHERE id = ?",
            (cycle.id, decision.id),
        )
        ctx.conn.commit()

    # Arc activation for draftable strategies
    if is_draftable(decision.decision):
        for _sn, sd in evaluation.strategies.items():
            if enum_value(sd.action) != "draft":
                continue
            if sd.new_arc_theme and not sd.arc_id:
                try:
                    from social_hook.narrative.arcs import create_arc as _create_arc

                    new_arc_id = _create_arc(ctx.db.conn, ctx.project.id, sd.new_arc_theme)
                    ctx.db.update_decision(decision.id, arc_id=new_arc_id)
                    decision.arc_id = new_arc_id
                    if ctx.verbose:
                        print(f"Created new arc: {new_arc_id} ({sd.new_arc_theme})")
                except Exception as e:
                    logger.warning(f"Arc creation failed (non-fatal): {e}")
                break  # Only one arc per decision

    # Held decision absorption
    if is_draftable(decision.decision) and representative.consolidate_with:
        valid_ids = [d.id for d in context.held_decisions]
        absorbed = [cid for cid in representative.consolidate_with if cid in valid_ids]
        if absorbed and not ctx.dry_run:
            batch_id = generate_id("batch")
            ops.mark_decisions_processed(ctx.conn, absorbed, batch_id)

    # Queue actions (same as legacy path)
    executed_queue_actions: list[dict[str, str]] = []
    if evaluation.queue_actions:
        for _target_name, actions in evaluation.queue_actions.items():
            for qa in actions:
                action_type = qa.action
                if action_type == "merge":
                    continue
                if not ctx.dry_run:
                    draft_ref = ops.get_draft(ctx.conn, qa.draft_id)
                    if not draft_ref or draft_ref.status not in ("draft", "approved", "scheduled"):
                        if ctx.verbose:
                            print(f"Queue action skipped: draft {qa.draft_id} not actionable")
                        continue
                    ops.execute_queue_action(ctx.conn, action_type, qa.draft_id, qa.reason)
                    executed_queue_actions.append(
                        {
                            "type": action_type,
                            "draft_id": qa.draft_id,
                            "reason": qa.reason or "",
                        }
                    )
                if ctx.verbose:
                    print(f"Queue action: {action_type} draft {qa.draft_id}")

        if not ctx.dry_run:
            _execute_merge_groups(
                evaluation.queue_actions,
                ctx.config,
                ctx.conn,
                ctx.db,
                ctx.project,
                context,
                ctx.project_config,
                ctx.dry_run,
                ctx.verbose,
            )

    # Run pipeline diagnostics before notification fork
    diagnostics_list = _run_diagnostics(
        ctx,
        cycle.id,
        evaluation,
        decision_type,
        hold_limit_forced=hold_limit_forced,
    )

    # Send decision notification for non-draftable decisions
    if (
        not ctx.dry_run
        and ctx.config.notification_level == "all_decisions"
        and not is_draftable(decision.decision)
    ):
        _send_decision_notification(
            ctx.config,
            ctx.project,
            ctx.commit,
            decision,
            diagnostics=diagnostics_list,
        )

    if ctx.verbose:
        print(f"Decision: {decision_type}")
        print(f"Reasoning: {decision.reasoning}")

    # Route per-strategy decisions to per-target actions and draft
    if is_draftable(decision.decision):
        from social_hook.content_sources import content_sources
        from social_hook.drafting import draft as run_draft
        from social_hook.drafting_intents import intent_from_routed_targets
        from social_hook.routing import route_to_targets

        ctx.db.emit_data_event("pipeline", PipelineStage.DRAFTING, commit_hash[:8], ctx.project.id)
        if ctx.task_id:
            ctx.db.emit_task_stage(ctx.task_id, "drafting", "Drafting content", ctx.project.id)

        target_actions = route_to_targets(evaluation.strategies, ctx.config, ctx.conn)
        draftable_actions = [a for a in target_actions if a.action == "draft"]

        if draftable_actions:
            intents = intent_from_routed_targets(
                draftable_actions,
                decision.id,
                evaluation,
                ctx.config,
                ctx.conn,
                project_id=ctx.project.id,
                content_source_registry=content_sources,
                cycle_id=cycle.id,
            )
            draft_results = []
            for _intent in intents:
                draft_results.extend(
                    run_draft(
                        _intent,
                        ctx.config,
                        ctx.conn,
                        ctx.db,
                        ctx.project,
                        context,
                        ctx.commit,
                        project_config=ctx.project_config,
                        dry_run=ctx.dry_run,
                        verbose=ctx.verbose,
                    )
                )

            # Increment arc post count if drafts were created for an arc
            if draft_results and decision.arc_id:
                try:
                    from social_hook.narrative.arcs import increment_arc_post_count

                    increment_arc_post_count(ctx.db.conn, decision.arc_id)
                    if ctx.verbose:
                        print(f"Incremented post count for arc: {decision.arc_id}")
                except Exception as e:
                    logger.warning(f"Arc post count increment failed (non-fatal): {e}")

            # Update topic status for strategies that drafted with a topic_id
            if draft_results and not ctx.dry_run:
                for _sn, sd in evaluation.strategies.items():
                    if enum_value(sd.action) == "draft" and sd.topic_id:
                        new_status = "partial" if sd.arc_id else "covered"
                        ops.update_topic_status(ctx.conn, sd.topic_id, new_status)
                        if ctx.verbose:
                            print(f"Topic {sd.topic_id} status -> {new_status}")

            draft_results_for_notification = draft_results
        else:
            draft_results_for_notification = None

        # Cycle notification (both draftable and non-draftable paths)
        cycle_drafts = (
            [r.draft for r in draft_results_for_notification]
            if draft_results_for_notification
            else []
        )
        should_notify = not ctx.dry_run and (
            cycle_drafts or ctx.config.notification_level != "drafts_only"
        )
        if should_notify:
            from social_hook.notifications import notify_evaluation_cycle

            strategy_outcomes = {
                sn: {
                    "action": enum_value(sd.action),
                    "reason": sd.reason,
                    "arc_id": sd.arc_id,
                    "topic_id": sd.topic_id,
                }
                for sn, sd in evaluation.strategies.items()
            }
            notify_evaluation_cycle(
                ctx.config,
                project_name=ctx.project.name,
                project_id=ctx.project.id,
                cycle_id=cycle.id,
                trigger_description=f"Commit {ctx.commit.hash[:8]} — {ctx.commit.message}",
                strategy_outcomes=strategy_outcomes,
                drafts=cycle_drafts,
                queue_actions=executed_queue_actions or None,
                diagnostics=diagnostics_list,
                dry_run=ctx.dry_run,
            )

    return TargetsPathResult(exit_code=0, cycle_id=cycle.id, decision_id=decision.id)


# Backward-compatible re-exports — tests import these from trigger.py
from social_hook.drafting import (  # noqa: E402, F401
    _generate_media,
)
from social_hook.trigger_secondary import (  # noqa: E402, F401
    run_suggestion_trigger,
    run_summary_trigger,
)
from social_hook.trigger_side_effects import (  # noqa: E402, F401
    _build_merge_commit,
    _execute_merge_groups,
)
