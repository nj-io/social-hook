"""Brand-primary candidate operations — combine held topics, trigger hero launch.

Both functions route through the existing drafting pipeline.
They are LLM operations — callers must handle progress/errors.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from social_hook.db import operations as ops
from social_hook.filesystem import generate_id
from social_hook.models import Decision, Draft, EvaluationCycle

logger = logging.getLogger(__name__)

BRAND_PRIMARY_STRATEGY = "brand-primary"


def combine_candidates(
    conn: sqlite3.Connection, config: Any, topic_ids: list[str], project_id: str
) -> str:
    """Combine 2+ held brand-primary topics into a single draft.

    Creates a synthetic evaluation with context_source combining all selected topics.
    Routes through normal drafting pipeline.
    Returns the new draft_id.

    Raises ValueError if fewer than 2 topic_ids provided.
    Raises ValueError if any topic is not in 'holding' status.
    Raises ValueError if any topic doesn't belong to brand-primary strategy.
    Updates selected topics' status to 'covered'.
    """
    if len(topic_ids) < 2:
        raise ValueError("combine_candidates requires at least 2 topic IDs")

    topics = []
    for tid in topic_ids:
        topic = ops.get_topic(conn, tid)
        if topic is None:
            raise ValueError(f"Topic not found: {tid}")
        if topic.status != "holding":
            raise ValueError(f"Topic {tid} is not in 'holding' status (current: {topic.status})")
        if topic.strategy != BRAND_PRIMARY_STRATEGY:
            raise ValueError(
                f"Topic {tid} strategy is '{topic.strategy}', expected '{BRAND_PRIMARY_STRATEGY}'"
            )
        topics.append(topic)

    # Create evaluation cycle
    cycle_id = generate_id("cycle")
    cycle = EvaluationCycle(
        id=cycle_id,
        project_id=project_id,
        trigger_type="combine",
        trigger_ref=",".join(topic_ids),
    )
    ops.insert_evaluation_cycle(conn, cycle)

    # Build combined context from all topics
    context_parts = []
    for t in topics:
        desc = f" — {t.description}" if t.description else ""
        context_parts.append(f"- {t.topic}{desc}")
    combined_context = "Combined brand-primary topics:\n" + "\n".join(context_parts)

    # Create a synthetic decision for the drafting pipeline
    decision_id = generate_id("decision")
    decision = Decision(
        id=decision_id,
        project_id=project_id,
        commit_hash=f"combine:{cycle_id}",
        decision="draft",
        reasoning=combined_context,
        commit_message=combined_context,
        trigger_source="combine",
    )
    ops.insert_decision(conn, decision)

    # Create draft
    draft_id = generate_id("draft")
    draft = Draft(
        id=draft_id,
        project_id=project_id,
        decision_id=decision_id,
        platform="preview",
        content=combined_context,
        status="draft",
        evaluation_cycle_id=cycle_id,
    )
    ops.insert_draft(conn, draft)

    # Update topic statuses
    for t in topics:
        ops.update_topic_status(conn, t.id, "covered")

    logger.info(
        "Combined %d topics into draft %s (cycle %s)",
        len(topics),
        draft_id,
        cycle_id,
    )
    return draft_id


def trigger_hero_launch(
    conn: sqlite3.Connection, config: Any, project_id: str, project_path: str
) -> str:
    """Trigger a hero launch draft using all available brand-primary context.

    Assembles: full project brief + all held brand-primary candidates + all covered topics.
    Drafter receives maximum context with brand-primary strategy.
    Routes through normal drafting pipeline.
    Returns the new draft_id.
    """
    # Get project summary (brief)
    summary = ops.get_project_summary(conn, project_id)
    brief = summary or ""

    # Get all brand-primary topics
    all_topics = ops.get_topics_by_strategy(conn, project_id, BRAND_PRIMARY_STRATEGY)

    held = [t for t in all_topics if t.status == "holding"]
    covered = [t for t in all_topics if t.status == "covered"]

    # Build hero launch context
    context_parts = [f"Hero launch for project at {project_path}"]
    if brief:
        context_parts.append(f"\nProject brief:\n{brief}")

    if held:
        context_parts.append("\nHeld candidates:")
        for t in held:
            desc = f" — {t.description}" if t.description else ""
            context_parts.append(f"- {t.topic}{desc}")

    if covered:
        context_parts.append("\nCovered topics:")
        for t in covered:
            desc = f" — {t.description}" if t.description else ""
            context_parts.append(f"- {t.topic}{desc}")

    hero_context = "\n".join(context_parts)

    # Create evaluation cycle
    cycle_id = generate_id("cycle")
    cycle = EvaluationCycle(
        id=cycle_id,
        project_id=project_id,
        trigger_type="hero_launch",
    )
    ops.insert_evaluation_cycle(conn, cycle)

    # Create decision
    decision_id = generate_id("decision")
    decision = Decision(
        id=decision_id,
        project_id=project_id,
        commit_hash=f"hero_launch:{cycle_id}",
        decision="draft",
        reasoning="Hero launch triggered",
        commit_message=hero_context,
        trigger_source="hero_launch",
    )
    ops.insert_decision(conn, decision)

    # Create draft
    draft_id = generate_id("draft")
    draft = Draft(
        id=draft_id,
        project_id=project_id,
        decision_id=decision_id,
        platform="preview",
        content=hero_context,
        status="draft",
        evaluation_cycle_id=cycle_id,
    )
    ops.insert_draft(conn, draft)

    logger.info(
        "Hero launch draft %s created (cycle %s, %d held, %d covered topics)",
        draft_id,
        cycle_id,
        len(held),
        len(covered),
    )
    return draft_id
