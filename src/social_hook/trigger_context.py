"""Trigger pipeline context dataclasses and shared helpers.

TriggerContext carries infrastructure (config, DB, project) through
pipeline stages. Helper functions eliminate duplication between
run_trigger() and evaluate_batch().
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from social_hook.db import operations as ops

if TYPE_CHECKING:
    from social_hook.config.project import ProjectConfig
    from social_hook.config.yaml import Config
    from social_hook.llm.dry_run import DryRunContext
    from social_hook.models import CommitInfo, Project

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

    Args:
        config: Global Config object with platforms dict.

    Returns:
        List of summary strings like "x (primary)" or "blog (secondary) — My blog".
    """
    summaries = []
    for pname, pcfg in config.platforms.items():
        if pcfg.enabled:
            summary = f"{pname} ({pcfg.priority})"
            if pcfg.type == "custom" and pcfg.description:
                summary += f" — {pcfg.description}"
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
