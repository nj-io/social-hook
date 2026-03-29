"""Trigger pipeline side effects — brief updates, notifications, merges.

Functions that produce side effects (DB writes, LLM calls, notifications)
as part of the trigger pipeline. Separated from the orchestrator for
focused responsibility.
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

from social_hook.db import operations as ops

if TYPE_CHECKING:
    from social_hook.models.core import CommitInfo, Decision, Draft

logger = logging.getLogger(__name__)


def _trigger_brief_update(
    evaluation,
    analysis,
    conn,
    db,
    project,
    evaluator_client,
    dry_run: bool,
    verbose: bool,
) -> bool:
    """Update the project brief after commit analysis if the commit is non-trivial.

    Returns True ONLY when the brief content actually changed and the write
    succeeded. Returns False for all other paths (no tags, ImportError,
    Exception, brief unchanged, dry_run).
    """
    # Only update for non-trivial commits (has episode tags beyond trivial markers)
    if not analysis.episode_tags:
        return False

    try:
        from social_hook.llm.brief import update_brief_from_commit

        current_brief = ops.get_project_summary(conn, project.id)
        if not current_brief:
            return False

        # Get section metadata from the project
        proj = ops.get_project(conn, project.id)
        section_metadata = proj.brief_section_metadata if proj else None

        updated_brief, updated_metadata, changed_keys = update_brief_from_commit(
            current_brief=current_brief,
            commit_analysis_summary=analysis.summary,
            commit_analysis_tags=analysis.episode_tags,
            client=evaluator_client,
            section_metadata=section_metadata,
            db=db,
            project_id=project.id,
        )
        if updated_brief != current_brief and not dry_run:
            db.update_project_summary(project.id, updated_brief)
            if verbose:
                print(f"Brief updated: sections changed: {changed_keys}")
            return True
        else:
            return False
    except ImportError:
        logger.debug("brief.py not available, skipping brief update")
        return False
    except Exception as e:
        logger.warning("Brief update failed (non-fatal): %s", e)
        if verbose:
            print(f"Brief update skipped: {e}", file=sys.stderr)
        return False


def _send_decision_notification(config, project, commit, decision):
    """Send a decision notification to all configured channels."""
    from social_hook.messaging.base import OutboundMessage
    from social_hook.notifications import broadcast_notification

    reasoning_preview = (
        (decision.reasoning[:200] + "...") if len(decision.reasoning) > 200 else decision.reasoning
    )
    msg_text = (
        f"Commit evaluated\n\n"
        f"Project: {project.name}\n"
        f"Commit: {commit.hash[:8]} - {commit.message}\n"
        f"Decision: {decision.decision}\n"
        f"Reasoning: {reasoning_preview}"
    )
    broadcast_notification(config, OutboundMessage(text=msg_text))


def _build_merge_evaluation(
    drafts: list[Draft],
    decisions: list[Decision],
    merge_instruction: str | None,
):
    """Build a synthetic evaluation for a merge group.

    Returns a SimpleNamespace matching the shape produced by make_eval_compat()
    in compat.py — the same interface the drafter pipeline expects.
    """
    from types import SimpleNamespace

    latest = decisions[-1]

    if merge_instruction:
        angle = merge_instruction
    else:
        combined = " + ".join(d.angle for d in decisions if d.angle)
        angle = combined or "Consolidate these drafts"

    combined_summary = "\n".join(
        f"- {d.commit_summary or d.commit_message or d.commit_hash[:8]}" for d in decisions
    )

    return SimpleNamespace(
        decision="draft",
        reasoning=f"Merged from {len(drafts)} drafts",
        angle=angle,
        episode_type=None,
        post_category=latest.post_category,
        arc_id=latest.arc_id,
        new_arc_theme=None,
        media_tool=latest.media_tool,
        reference_posts=None,
        commit_summary=combined_summary,
        include_project_docs=None,
    )


def _build_merge_commit(
    decisions: list[Decision],
    drafts: list[Draft],
) -> CommitInfo:
    """Build a synthetic CommitInfo for a merge group.

    Injects original draft contents into the diff field so the drafter
    sees them in the "### Diff" section of the system prompt.
    """
    from social_hook.models.core import CommitInfo

    summaries = "\n".join(
        f"- {d.commit_summary or d.commit_message or d.commit_hash[:8]}" for d in decisions
    )
    diff_section = "Original drafts to consolidate:\n" + "\n---\n".join(
        f"Draft {i + 1}:\n{d.content}" for i, d in enumerate(drafts)
    )
    return CommitInfo(
        hash=f"merge-{decisions[-1].commit_hash[:8]}",
        message=f"Merge of {len(drafts)} drafts:\n{summaries}",
        diff=diff_section,
        files_changed=[],
    )


def _execute_merge_groups(
    queue_actions: dict[str, list],
    config,
    conn,
    db,
    project,
    context,
    project_config,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Execute merge queue actions grouped by merge_group.

    For each merge group: load drafts, sub-group by platform, call drafter
    to create a replacement draft, supersede originals.
    """
    from collections import defaultdict

    from social_hook.drafting import draft_for_platforms

    for _target_name, actions in queue_actions.items():
        merge_actions = [a for a in actions if a.action == "merge"]
        if not merge_actions:
            continue

        # Group by merge_group label
        groups: dict[str, list] = defaultdict(list)
        for ma in merge_actions:
            group_key = ma.merge_group or "default"
            groups[group_key].append(ma)

        for group_key, group_actions in groups.items():
            # Extract merge_instruction (first non-null in the group)
            merge_instruction = next(
                (a.merge_instruction for a in group_actions if a.merge_instruction),
                None,
            )

            # Load and validate drafts + their parent decisions
            valid_drafts: list[Draft] = []
            valid_decisions: list[Decision] = []
            for ga in group_actions:
                draft = ops.get_draft(conn, ga.draft_id)
                # Intentionally excludes deferred — queue actions target active drafts only
                if (
                    not draft
                    or draft.status not in ("draft", "approved", "scheduled")
                    or draft.project_id != project.id
                ):
                    if verbose:
                        print(f"Merge skipped: draft {ga.draft_id} not actionable")
                    continue
                valid_drafts.append(draft)
                if draft.decision_id:
                    dec = ops.get_decision(conn, draft.decision_id)
                    if dec:
                        valid_decisions.append(dec)

            if len(valid_drafts) < 2 or not valid_decisions:
                if verbose:
                    print(
                        f"Merge group {group_key}: {len(valid_drafts)} valid draft(s), "
                        f"{len(valid_decisions)} decision(s) — skipping"
                    )
                continue

            # Sub-group by platform
            by_platform: dict[str, list[Draft]] = defaultdict(list)
            for d in valid_drafts:
                by_platform[d.platform].append(d)

            for platform, platform_drafts in by_platform.items():
                if len(platform_drafts) < 2:
                    if verbose:
                        logger.info(
                            "Merge group %s: only 1 draft on %s, skipping",
                            group_key,
                            platform,
                        )
                    continue

                pcfg = config.platforms.get(platform)
                if not pcfg or not pcfg.enabled:
                    continue

                try:
                    # Collect decisions for this platform's drafts
                    platform_decision_ids = {d.decision_id for d in platform_drafts}
                    platform_decisions = [
                        dec for dec in valid_decisions if dec.id in platform_decision_ids
                    ] or valid_decisions[-1:]  # fallback to latest

                    merged_eval = _build_merge_evaluation(
                        platform_drafts, platform_decisions, merge_instruction
                    )
                    merged_commit = _build_merge_commit(platform_decisions, platform_drafts)

                    draft_results = draft_for_platforms(
                        config,
                        conn,
                        db,
                        project,
                        decision_id=platform_decisions[-1].id,
                        evaluation=merged_eval,
                        context=context,
                        commit=merged_commit,
                        project_config=project_config,
                        target_platform_names=[platform],
                        dry_run=dry_run,
                        verbose=verbose,
                    )

                    if draft_results and not dry_run:
                        replacement_id = draft_results[0].draft.id
                        for d in platform_drafts:
                            ops.supersede_draft(conn, d.id, replacement_id)
                            db.emit_data_event("draft", "updated", d.id, project.id)

                    if verbose and draft_results:
                        print(
                            f"Merged {len(platform_drafts)} {platform} drafts "
                            f"→ {len(draft_results)} replacement(s)"
                        )

                except Exception as e:
                    logger.error("Merge group %s/%s failed: %s", group_key, platform, e)
                    if verbose:
                        print(f"Merge group {group_key}/{platform} failed: {e}")
