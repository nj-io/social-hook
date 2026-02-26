"""Consolidation tick: processes batched consolidate/deferred decisions."""

import json
import logging
from pathlib import Path
from typing import Optional

from social_hook.config.yaml import load_full_config
from social_hook.db import operations as ops
from social_hook.db.connection import init_database
from social_hook.errors import ConfigError
from social_hook.filesystem import generate_id, get_base_path, get_db_path
from social_hook.models import Decision, Draft, DraftTweet
from social_hook.scheduler import acquire_lock, release_lock

logger = logging.getLogger(__name__)


def get_consolidation_lock_path() -> Path:
    """Get the path to the consolidation lock file."""
    return get_base_path() / "consolidation.lock"


def consolidation_tick(
    dry_run: bool = False,
    config_path: Optional[str] = None,
    lock_path: Optional[Path] = None,
) -> int:
    """Run one consolidation tick: process batched decisions.

    Args:
        dry_run: If True, skip DB writes and real API calls
        config_path: Optional config file override
        lock_path: Optional lock file path override (for testing)

    Returns:
        Number of decisions processed
    """
    effective_lock = lock_path or get_consolidation_lock_path()

    if not acquire_lock(effective_lock):
        logger.info("Consolidation tick skipped: lock held by another process")
        return 0

    try:
        # Load config
        config = load_full_config(yaml_path=config_path)

        if not config.consolidation.enabled:
            logger.debug("Consolidation is disabled")
            return 0

        # Init DB
        db_path = get_db_path()
        conn = init_database(db_path)

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(conn, dry_run=dry_run)

        # Get all projects
        projects = ops.get_all_projects(conn)
        total_processed = 0

        for project in projects:
            if project.paused:
                continue

            decisions = ops.get_unprocessed_consolidation_decisions(
                conn, project.id, limit=config.consolidation.batch_size,
            )
            if not decisions:
                continue

            batch_id = generate_id("batch")
            decision_ids = [d.id for d in decisions]

            if config.consolidation.mode == "notify_only":
                _process_notify_only(config, project, decisions, batch_id, dry_run)
            elif config.consolidation.mode == "re_evaluate":
                _process_re_evaluate(
                    config, conn, db, project, decisions, batch_id, dry_run,
                )

            # Mark as processed (direct DB write, not via DryRunContext)
            if not dry_run:
                ops.mark_decisions_processed(conn, decision_ids, batch_id)
                ops.emit_data_event(conn, "decision", "updated", project_id=project.id)

            total_processed += len(decisions)

        conn.close()
        return total_processed

    finally:
        release_lock(effective_lock)


def _process_notify_only(config, project, decisions, batch_id, dry_run):
    """Send a notification summarizing the batched decisions."""
    summaries = []
    for d in decisions:
        summary = d.commit_summary or d.commit_message or d.commit_hash[:8]
        summaries.append(f"- [{d.decision}] {summary}")

    message = (
        f"*Consolidation batch* `{batch_id[:12]}`\n"
        f"Project: {project.name}\n"
        f"Decisions: {len(decisions)}\n\n"
        + "\n".join(summaries)
    )

    from social_hook.notifications import send_notification

    send_notification(config, message, dry_run=dry_run)


def _process_re_evaluate(config, conn, db, project, decisions, batch_id, dry_run):
    """Re-evaluate batched decisions as a combined unit."""
    from social_hook.config.platforms import passes_content_filter, resolve_platform
    from social_hook.config.project import load_project_config
    from social_hook.llm.dry_run import DryRunContext
    from social_hook.llm.factory import create_client
    from social_hook.llm.prompts import assemble_evaluator_context
    from social_hook.models import CommitInfo
    from social_hook.scheduling import calculate_optimal_time

    # Load project config
    project_config = load_project_config(project.repo_path)

    # Combine commit summaries for the evaluator
    combined_summary = "\n".join(
        f"- {d.commit_summary or d.commit_message or d.commit_hash[:8]}"
        for d in decisions
    )

    # Assemble context (use the latest decision's commit for timestamps)
    context = assemble_evaluator_context(
        db, project.id, project_config,
    )

    # Build a synthetic CommitInfo representing the batch
    commit = CommitInfo(
        hash=f"batch-{batch_id[:8]}",
        message=f"Consolidation batch of {len(decisions)} commits:\n{combined_summary}",
        diff="",
        files_changed=[],
    )

    # Create evaluator client and re-evaluate
    try:
        evaluator_client = create_client(config.models.evaluator, config)
    except ConfigError as e:
        logger.error(f"Config error creating evaluator client: {e}")
        return

    from social_hook.llm.evaluator import Evaluator

    try:
        evaluator = Evaluator(evaluator_client)

        platform_summaries = []
        for pname, pcfg in config.platforms.items():
            if pcfg.enabled:
                summary = f"{pname} ({pcfg.priority})"
                if pcfg.type == "custom" and pcfg.description:
                    summary += f" -- {pcfg.description}"
                platform_summaries.append(summary)

        evaluation = evaluator.evaluate(
            commit, context, db,
            platform_summaries=platform_summaries or None,
            media_config=config.media_generation,
            media_guidance=project_config.media_guidance if project_config else None,
            strategy_config=project_config.strategy if project_config else None,
            summary_config=project_config.summary if project_config else None,
        )
    except Exception as e:
        logger.error(f"LLM API error during consolidation re-evaluation: {e}")
        return

    if evaluation.decision != "post_worthy":
        logger.info(
            f"Consolidation re-evaluation for {project.name}: {evaluation.decision}"
        )
        return

    # Post-worthy: update the most recent decision in the batch
    most_recent = decisions[-1]
    if not dry_run:
        ops.update_decision(
            conn,
            most_recent.id,
            decision="post_worthy",
            reasoning=evaluation.reasoning,
            angle=getattr(evaluation, "angle", None),
            episode_type=getattr(evaluation, "episode_type", None),
            post_category=getattr(evaluation, "post_category", None),
            media_tool=getattr(evaluation, "media_tool", None),
        )
        ops.emit_data_event(conn, "decision", "updated", most_recent.id, project.id)

    # Create drafts per platform (following trigger.py pattern)
    resolved_platforms = {}
    for pname, pcfg in config.platforms.items():
        if pcfg.enabled:
            resolved_platforms[pname] = resolve_platform(
                pname, pcfg, config.scheduling,
            )

    if not resolved_platforms:
        return

    ep_type = getattr(evaluation, "episode_type", None)
    if ep_type is not None and hasattr(ep_type, "value"):
        ep_type = ep_type.value
    target_platforms = {}
    for pname, rpcfg in resolved_platforms.items():
        if passes_content_filter(rpcfg.filter, ep_type):
            target_platforms[pname] = rpcfg

    if not target_platforms:
        return

    try:
        drafter_client = create_client(config.models.drafter, config)
    except ConfigError as e:
        logger.error(f"Config error creating drafter client: {e}")
        return

    from social_hook.llm.drafter import Drafter
    from social_hook.trigger import _generate_media, _needs_thread, _parse_thread_tweets
    from social_hook.config.yaml import TIER_CHAR_LIMITS

    drafter = Drafter(drafter_client)

    # Generate media once
    media_paths, media_type_str, media_spec_dict = _generate_media(
        config, evaluation, dry_run=dry_run,
        project_config=project_config,
    )

    # Draft for each platform
    created_drafts = []
    for pname, rpcfg in target_platforms.items():
        try:
            draft_result = drafter.create_draft(
                evaluation, context, commit, db,
                platform=pname,
                platform_config=rpcfg,
                config=project_config.context,
                media_config=config.media_generation,
                media_guidance=project_config.media_guidance if project_config else None,
            )
            draft_result.platform = pname

            use_thread = _needs_thread(
                draft_result, pname, rpcfg.account_tier or "free",
                thread_min=config.scheduling.thread_min_tweets,
            )
            thread_tweets = []
            if use_thread:
                thread_result = drafter.create_thread(
                    evaluation, context, commit, db, platform=pname,
                    media_config=config.media_generation,
                    media_guidance=project_config.media_guidance if project_config else None,
                )
                thread_tweets = _parse_thread_tweets(
                    thread_result.content,
                    thread_min=config.scheduling.thread_min_tweets,
                )
                draft_content = thread_result.content
                draft_reasoning = thread_result.reasoning
            else:
                draft_content = draft_result.content
                draft_reasoning = draft_result.reasoning

            schedule = calculate_optimal_time(
                conn, project.id,
                platform=pname,
                tz=config.scheduling.timezone,
                max_posts_per_day=rpcfg.max_posts_per_day,
                min_gap_minutes=rpcfg.min_gap_minutes,
                optimal_days=rpcfg.optimal_days,
                optimal_hours=rpcfg.optimal_hours,
                max_per_week=config.scheduling.max_per_week,
            )

            if schedule.deferred:
                continue

            draft = Draft(
                id=generate_id("draft"),
                project_id=project.id,
                decision_id=most_recent.id,
                platform=pname,
                content=draft_content,
                media_paths=media_paths,
                media_type=media_type_str,
                media_spec=media_spec_dict,
                suggested_time=schedule.datetime,
                reasoning=draft_reasoning,
            )
            db.insert_draft(draft)
            db.emit_data_event("draft", "created", draft.id, project.id)

            if thread_tweets:
                for pos, tc in enumerate(thread_tweets):
                    db.insert_draft_tweet(DraftTweet(
                        id=generate_id("tweet"), draft_id=draft.id,
                        position=pos, content=tc,
                    ))

            created_drafts.append(draft)

        except Exception as e:
            logger.error(f"Error creating draft for {pname}: {e}")

    if created_drafts:
        from social_hook.notifications import send_notification

        platform_list = ", ".join(d.platform for d in created_drafts)
        message = (
            f"*Consolidation re-evaluation* `{batch_id[:12]}`\n"
            f"Project: {project.name}\n"
            f"Result: post_worthy\n"
            f"Drafts created for: {platform_list}\n"
            f"Batched {len(decisions)} decisions"
        )
        send_notification(config, message, dry_run=dry_run)
