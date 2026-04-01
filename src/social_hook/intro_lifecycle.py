"""Intro draft lifecycle: cascade re-draft on intro rejection."""

import logging
from collections import defaultdict

from social_hook.db import operations as ops

logger = logging.getLogger(__name__)


def on_intro_rejected(conn, draft, project_id, verbose=False, skip_intro=False) -> str:
    """Handle rejection of an intro draft.

    When skip_intro=True:
    - Mark platform as introduced (skip future intros)
    - No cascade, no re-draft

    When skip_intro=False (default):
    1. Reset platform_introduced for this draft's platform
    2. Find pending non-intro drafts for this platform
    3. Re-draft them with platform_introduced=False tone
    4. Mark originals as superseded

    Returns summary message.
    """
    if not getattr(draft, "is_intro", False):
        return ""

    platform = draft.platform

    # Skip intro: just mark as introduced and return
    if skip_intro:
        ops.set_platform_introduced(conn, project_id, platform, True)
        ops.emit_data_event(conn, "project", "updated", project_id, project_id)
        return f"Intro skipped for {platform}. Platform marked as introduced."

    # 1. Reset platform_introduced for this platform
    ops.reset_platform_introduced(conn, project_id, platform)
    ops.emit_data_event(conn, "project", "updated", project_id, project_id)

    # 2. Find pending non-intro drafts for this platform only
    pending = ops.get_pending_drafts(conn, project_id)
    non_intro = [d for d in pending if not getattr(d, "is_intro", False) and d.platform == platform]

    if not non_intro:
        if verbose:
            logger.info("Intro rejected for %s, no pending non-intro drafts to cascade", platform)
        return f"Intro rejected for {platform}. platform_introduced reset. No pending drafts to re-draft."

    # 3. Group by decision_id to avoid duplicate re-drafts
    by_decision = defaultdict(list)
    for d in non_intro:
        by_decision[d.decision_id].append(d)

    # 4. Re-draft each unique decision
    superseded_count = 0
    replacement_count = 0

    try:
        from social_hook.compat import evaluation_from_decision
        from social_hook.config.project import load_project_config
        from social_hook.config.yaml import load_full_config
        from social_hook.drafting import draft_for_platforms
        from social_hook.llm.dry_run import DryRunContext
        from social_hook.models.core import CommitInfo

        config = load_full_config()
        db = DryRunContext(conn, dry_run=False)

        for decision_id, drafts_for_decision in by_decision.items():
            decision = ops.get_decision(conn, decision_id)
            if not decision:
                continue

            # Build minimal eval compat from decision fields
            eval_compat = evaluation_from_decision(decision)

            commit = CommitInfo(
                hash=decision.commit_hash,
                message=decision.commit_message or "",
                diff="",
                files_changed=[],
            )

            project = ops.get_project(conn, project_id)
            if not project:
                continue

            project_config = load_project_config(project.repo_path)

            # Rebuild context with this platform not introduced
            from social_hook.llm.prompts import assemble_evaluator_context

            context = assemble_evaluator_context(db, project_id, project_config)
            context.platform_introduced[platform] = False

            try:
                new_results = draft_for_platforms(
                    config,
                    conn,
                    db,
                    project,
                    decision_id=decision_id,
                    evaluation=eval_compat,
                    context=context,
                    commit=commit,
                    project_config=project_config,
                    dry_run=False,
                    verbose=verbose,
                    target_platform_names=[platform],
                )
            except Exception as e:
                logger.warning(f"Re-draft failed for decision {decision_id}: {e}")
                continue

            if new_results:
                for old_draft in drafts_for_decision:
                    ops.update_draft(conn, old_draft.id, status="superseded")
                    superseded_count += 1
                replacement_count += len(new_results)
    except Exception as e:
        logger.error(f"Intro cascade failed: {e}")
        return f"Intro rejected for {platform}. platform_introduced reset. Cascade error: {e}"

    msg = (
        f"Intro rejected for {platform}. platform_introduced reset. "
        f"Superseded {superseded_count} drafts, created {replacement_count} replacements."
    )
    if verbose:
        logger.info(msg)
    return msg
