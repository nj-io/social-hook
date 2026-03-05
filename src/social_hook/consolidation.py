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
from social_hook.models import Decision
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

            decisions = ops.get_held_decisions(
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

        # Phase 2: Auto-consolidate drafts in time window
        for project in projects:
            if project.paused:
                continue
            if config.consolidation.auto_consolidate_drafts:
                _auto_consolidate_drafts(config, conn, project, dry_run)

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
    from social_hook.config.project import load_project_config
    from social_hook.llm.factory import create_client
    from social_hook.llm.prompts import assemble_evaluator_context
    from social_hook.models import CommitInfo

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

    target = evaluation.targets.get("default")
    if not target:
        logger.info(f"Consolidation re-evaluation for {project.name}: no default target")
        return

    def _val(x):
        return x.value if hasattr(x, "value") else x

    if _val(target.action) != "draft":
        logger.info(
            f"Consolidation re-evaluation for {project.name}: {_val(target.action)}"
        )
        return

    # Draftable: update the most recent decision in the batch
    most_recent = decisions[-1]
    if not dry_run:
        ops.update_decision(
            conn,
            most_recent.id,
            decision="draft",
            reasoning=target.reason,
            angle=target.angle,
            episode_type=_val(target.episode_type),
            post_category=_val(target.post_category),
            media_tool=_val(target.media_tool),
        )
        ops.emit_data_event(conn, "decision", "updated", most_recent.id, project.id)

    # Create drafts per platform via shared pipeline
    from social_hook.compat import make_eval_compat
    from social_hook.drafting import draft_for_platforms

    eval_compat = make_eval_compat(evaluation, "draft")
    draft_results = draft_for_platforms(
        config, conn, db, project, decision_id=most_recent.id,
        evaluation=eval_compat, context=context, commit=commit,
        project_config=project_config, dry_run=dry_run,
    )

    if draft_results:
        from social_hook.notifications import send_notification

        created_drafts = [r.draft for r in draft_results]
        platform_list = ", ".join(d.platform for d in created_drafts)
        message = (
            f"*Consolidation re-evaluation* `{batch_id[:12]}`\n"
            f"Project: {project.name}\n"
            f"Result: draft\n"
            f"Drafts created for: {platform_list}\n"
            f"Batched {len(decisions)} decisions"
        )
        send_notification(config, message, dry_run=dry_run)


def _auto_consolidate_drafts(config, conn, project, dry_run):
    """Phase 2: Auto-consolidate drafts within a time window.

    Safety net -- fires rarely when evaluator is managing consolidation well.
    Groups pending drafts by platform and notifies if count exceeds threshold.
    """
    from collections import defaultdict

    time_window = config.consolidation.time_window_hours
    max_drafts = config.consolidation.time_window_max_drafts

    drafts = ops.get_drafts_in_time_window(conn, project.id, time_window)

    # Only consider non-approved unless consolidate_approved is True
    if not config.consolidation.consolidate_approved:
        drafts = [d for d in drafts if d.status == "draft"]

    # Group by platform
    by_platform = defaultdict(list)
    for d in drafts:
        by_platform[d.platform].append(d)

    for platform, platform_drafts in by_platform.items():
        if len(platform_drafts) <= max_drafts:
            continue

        logger.info(
            f"Auto-consolidation: {len(platform_drafts)} {platform} drafts in "
            f"{time_window}h window (threshold: {max_drafts})"
        )

        if dry_run:
            continue

        from social_hook.notifications import send_notification

        message = (
            f"*Auto-consolidation alert*\n"
            f"Project: {project.name}\n"
            f"Platform: {platform}\n"
            f"{len(platform_drafts)} drafts in {time_window}h window "
            f"(threshold: {max_drafts})\n"
            f"Consider reviewing and consolidating manually."
        )
        send_notification(config, message, dry_run=dry_run)
