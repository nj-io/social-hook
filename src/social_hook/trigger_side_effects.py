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
    analyzer_result=None,
) -> bool:
    """Update the project brief after commit analysis if the commit is non-trivial.

    Returns True ONLY when the brief content actually changed and the write
    succeeded. Returns False for all other paths (no analyzer_result, no
    brief_update guidance, ImportError, Exception, brief unchanged, dry_run).

    Args:
        analyzer_result: Full CommitAnalysisResult from stage 1 (has brief_update field).
            When None (manual retriggers, batch paths), brief update is skipped.
    """
    # Gate: require analyzer_result with meaningful brief_update guidance
    if analyzer_result is None:
        return False

    brief_update = getattr(analyzer_result, "brief_update", None)
    if brief_update is None:
        return False

    # Only proceed if the analyzer identified sections to update or new facts
    if not brief_update.sections_to_update and not brief_update.new_facts:
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
            sections_to_update=brief_update.sections_to_update or None,
            new_facts=brief_update.new_facts or None,
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


def _run_diagnostics(
    ctx,
    cycle_id: str,
    evaluation,
    decision_type: str,
    *,
    hold_limit_forced: bool = False,
) -> list[dict]:
    """Run pipeline diagnostics and store results on cycle. Returns serialized list."""
    try:
        import json

        import social_hook.pipeline_diagnostics  # noqa: F401
        from social_hook.diagnostics import diagnostics_registry

        strategies = {
            name: {
                "action": getattr(sd.action, "value", sd.action),
                "reason": sd.reason,
                "arc_id": sd.arc_id,
                "topic_id": sd.topic_id,
            }
            for name, sd in evaluation.strategies.items()
        }

        # Build set of accounts with OAuth credentials (for preview mode diagnostics)
        cred_rows = ctx.conn.execute("SELECT account_name FROM oauth_tokens").fetchall()
        _accounts_with_creds = {r[0] for r in cred_rows}

        diag_context = {
            "strategies": strategies,
            "config_targets": ctx.config.targets or {},
            "config_strategies": ctx.config.content_strategies or {},
            "config_platforms": ctx.config.platforms or {},
            "config_accounts": ctx.config.accounts or {},
            "accounts_with_creds": _accounts_with_creds,
            "decision_type": decision_type,
            "hold_limit_forced": hold_limit_forced,
            "has_targets": bool(ctx.config.targets),
            "has_strategies": bool(ctx.config.content_strategies),
            "legacy_fallback": False,
        }

        results = diagnostics_registry.run(diag_context)

        serialized = [d.to_dict() for d in results]

        if not ctx.dry_run:
            ops.update_cycle_diagnostics(ctx.conn, cycle_id, json.dumps(serialized))

        return serialized
    except Exception:
        logger.warning("Pipeline diagnostics failed (non-fatal)", exc_info=True)
        return []


def _send_decision_notification(config, project, commit, decision, diagnostics=None):
    """Send a decision notification to all configured channels."""
    from social_hook.diagnostics import format_diagnostic_warnings
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

    if diagnostics:
        msg_text += format_diagnostic_warnings(diagnostics)

    broadcast_notification(config, OutboundMessage(text=msg_text))


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

    from social_hook.drafting import draft as run_draft
    from social_hook.drafting_intents import intent_from_merge

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
                draft_obj = ops.get_draft(conn, ga.draft_id)
                # Intentionally excludes deferred — queue actions target active drafts only
                if (
                    not draft_obj
                    or draft_obj.status not in ("draft", "approved", "scheduled")
                    or draft_obj.project_id != project.id
                ):
                    if verbose:
                        print(f"Merge skipped: draft {ga.draft_id} not actionable")
                    continue
                valid_drafts.append(draft_obj)
                if draft_obj.decision_id:
                    dec = ops.get_decision(conn, draft_obj.decision_id)
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

                    intent = intent_from_merge(
                        platform_drafts,
                        platform_decisions,
                        merge_instruction,
                        config,
                        platform,
                    )
                    merged_commit = _build_merge_commit(platform_decisions, platform_drafts)

                    draft_results = run_draft(
                        intent,
                        config,
                        conn,
                        db,
                        project,
                        context,
                        merged_commit,
                        project_config=project_config,
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
