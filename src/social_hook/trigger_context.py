"""Trigger pipeline context dataclasses and shared helpers.

TriggerContext carries infrastructure (config, DB, project) through
pipeline stages. Helper functions eliminate duplication between
run_trigger() and evaluate_batch().
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from social_hook.db import operations as ops

if TYPE_CHECKING:
    from social_hook.config.project import ProjectConfig
    from social_hook.config.yaml import Config
    from social_hook.llm.dry_run import DryRunContext
    from social_hook.models.core import CommitInfo, Project

logger = logging.getLogger(__name__)


@dataclass
class AnalyzerOutcome:
    """Result from stage 1 commit analyzer with evaluation gating signal.

    result: The commit analysis, or None on error.
    should_evaluate: True = proceed to stage 2, False = defer (interval not met).
    """

    result: object | None  # CommitAnalysisResult | None (avoids import at module level)
    should_evaluate: bool


@dataclass
class TriggerContext:
    """Shared context for trigger pipeline functions.

    Groups the parameters that flow through _run_commit_analyzer,
    _run_trivial_skip, and _run_targets_path.
    """

    config: Config
    conn: sqlite3.Connection
    db: DryRunContext
    project: Project
    commit: CommitInfo
    project_config: ProjectConfig | None
    current_branch: str | None
    dry_run: bool
    verbose: bool
    show_prompt: bool
    existing_decision_id: str | None = None
    task_id: str | None = None  # background task ID for stage tracking


@dataclass
class TargetsPathResult:
    """Result from the targets pipeline path.

    exit_code: 0 = success, non-zero = failure (matches run_trigger conventions).
    cycle_id: The evaluation cycle ID created by this pipeline run.
    decision_id: The trigger decision ID created/upserted by this pipeline run.
    """

    exit_code: int
    cycle_id: str | None = None
    decision_id: str | None = None


@dataclass
class EvaluatorExtras:
    """Pre-evaluation context gathered from DB.

    Groups the scheduling state, topics, and arcs fetched before
    calling the Evaluator. Used by both run_trigger and evaluate_batch.
    """

    scheduling_state: Any  # ProjectSchedulingState | None
    all_topics: list
    held_topics: list
    active_arcs: list


def build_platform_summaries(config: Config) -> list[str]:
    """Build human-readable platform summary strings for evaluator context.

    Includes tier, character limit, and available content vehicles per platform.

    Args:
        config: Global Config object with platforms dict.

    Returns:
        List of summary strings like
        "x (primary, basic tier, 25K chars) — vehicles: Self-contained post, Multi-part narrative".
    """
    from social_hook.config.platforms import PLATFORM_VEHICLE_SUPPORT
    from social_hook.config.yaml import TIER_CHAR_LIMITS

    summaries = []
    for pname, pcfg in config.platforms.items():
        if pcfg.enabled:
            tier = pcfg.account_tier or "free"
            char_limit = TIER_CHAR_LIMITS.get(tier, 25000)
            # Format char limit as human-readable (e.g. 280, 25K)
            if char_limit >= 1000:
                limit_str = f"{char_limit // 1000}K chars"
            else:
                limit_str = f"{char_limit} chars"

            summary = f"{pname} ({pcfg.priority}, {tier} tier, {limit_str})"
            if pcfg.type == "custom" and pcfg.description:
                summary += f" — {pcfg.description}"

            # Add available vehicles from PLATFORM_VEHICLE_SUPPORT
            vehicles = PLATFORM_VEHICLE_SUPPORT.get(pname, [])
            if vehicles:
                vehicle_descs = [cap.description for cap in vehicles]
                summary += f" — vehicles: {', '.join(vehicle_descs)}"

            summaries.append(summary)
    return summaries


def fetch_evaluator_extras(
    conn: sqlite3.Connection, project_id: str, config: Config
) -> EvaluatorExtras:
    """Fetch scheduling state, topics, and arcs for evaluator context.

    Args:
        conn: Database connection.
        project_id: Project ID.
        config: Global Config object.

    Returns:
        EvaluatorExtras with scheduling_state, all_topics, held_topics, active_arcs.
    """
    from social_hook.scheduling import get_scheduling_state

    try:
        scheduling_state = get_scheduling_state(conn, project_id, config)
    except Exception as e:
        logger.warning("Failed to get scheduling state (non-fatal): %s", e)
        scheduling_state = None

    all_topics = ops.get_topics_by_project(conn, project_id, include_dismissed=False)
    held_topics = [t for t in all_topics if t.status == "holding"]
    active_arcs = ops.get_arcs_by_project(conn, project_id, status="active")

    return EvaluatorExtras(
        scheduling_state=scheduling_state,
        all_topics=all_topics,
        held_topics=held_topics,
        active_arcs=active_arcs,
    )


def ensure_project_brief(
    config,
    project_config,
    conn,
    db,
    project,
    context,
    entity_id: str = "",
    verbose: bool = False,
) -> None:
    """Ensure the project has a brief (discovery summary). Run discovery if missing, refresh if stale.

    Shared by run_trigger and evaluate_batch so any evaluation path gets a brief.
    Modifies ``context.project_summary`` and ``context.file_summaries`` in-place.
    """
    if getattr(context, "project_summary", None) is None:
        fresh_summary = ops.get_project_summary(conn, project.id)
        if fresh_summary:
            context.project_summary = fresh_summary

    if getattr(context, "project_summary", None) is None:
        # No summary — run discovery
        try:
            from social_hook.llm.discovery import discover_project
            from social_hook.llm.factory import create_client as _create_client

            discovery_client = _create_client(config.models.evaluator, config, verbose=verbose)
            summary, selected_files, file_summaries, prompt_docs = discover_project(
                client=discovery_client,
                repo_path=project.repo_path,
                project_docs=project_config.context.project_docs if project_config else [],
                max_discovery_tokens=project_config.context.max_discovery_tokens
                if project_config
                else 60000,
                max_file_size=project_config.context.max_file_size if project_config else 256000,
                db=db,
                project_id=project.id,
                on_progress=lambda stage: db.emit_data_event(
                    "pipeline", stage, entity_id, project.id
                ),
            )
            if summary:
                db.update_project_summary(project.id, summary)
                db.update_discovery_files(project.id, selected_files)
                if file_summaries:
                    db.upsert_file_summaries(project.id, file_summaries)
                if prompt_docs:
                    db.update_prompt_docs(project.id, prompt_docs)
                db.emit_data_event("project", "updated", project.id, project.id)
                context.project_summary = summary
                context.file_summaries = file_summaries if file_summaries else []
                if verbose:
                    print(f"Project discovery complete: {len(selected_files)} files analyzed")
        except Exception as e:
            logger.warning("Project discovery failed (non-fatal): %s", e)
            if verbose:
                print(f"Project discovery skipped: {e}", file=sys.stderr)
    elif project_config and project_config.summary:
        # Summary exists — check if stale and needs refresh
        try:
            freshness = db.get_summary_freshness(project.id)
            cfg = project_config.summary
            needs_refresh = freshness["commits_since_summary"] >= cfg.refresh_after_commits or (
                freshness["days_since_summary"] is not None
                and freshness["days_since_summary"] >= cfg.refresh_after_days
            )
        except Exception:
            logger.warning("Summary freshness check failed, skipping refresh", exc_info=True)
            needs_refresh = False
        if needs_refresh:
            try:
                from social_hook.llm.discovery import discover_project
                from social_hook.llm.factory import create_client as _create_client

                discovery_client = _create_client(config.models.evaluator, config, verbose=verbose)
                summary, selected_files, file_summaries, prompt_docs = discover_project(
                    client=discovery_client,
                    repo_path=project.repo_path,
                    project_docs=project_config.context.project_docs if project_config else [],
                    max_discovery_tokens=project_config.context.max_discovery_tokens
                    if project_config
                    else 60000,
                    max_file_size=project_config.context.max_file_size
                    if project_config
                    else 256000,
                    db=db,
                    project_id=project.id,
                    on_progress=lambda stage: db.emit_data_event(
                        "pipeline", stage, entity_id, project.id
                    ),
                )
                if summary:
                    db.update_project_summary(project.id, summary)
                    db.update_discovery_files(project.id, selected_files)
                    if file_summaries:
                        db.upsert_file_summaries(project.id, file_summaries)
                    if prompt_docs:
                        db.update_prompt_docs(project.id, prompt_docs)
                    db.emit_data_event("project", "updated", project.id, project.id)
                    context.project_summary = summary
                    context.file_summaries = file_summaries if file_summaries else []
                    if verbose:
                        print(f"Project summary refreshed: {len(selected_files)} files analyzed")
            except Exception as e:
                logger.warning("Project summary refresh failed (non-fatal): %s", e)
                if verbose:
                    print(f"Summary refresh skipped: {e}", file=sys.stderr)
