"""Content topic queue management.

Topics accumulate material from commits (code-driven) or are seeded by
discovery/operator (positioning-driven). The evaluator works through
topics by priority rather than reacting to individual commits.
"""

import logging
import re
import sqlite3

from social_hook.db import operations as ops
from social_hook.errors import ConfigError
from social_hook.filesystem import generate_id
from social_hook.models import ContentTopic, EvaluationCycle

logger = logging.getLogger(__name__)


def seed_topics_from_brief(
    conn: sqlite3.Connection,
    project_id: str,
    brief: str,
    strategies: list[str],
) -> list[ContentTopic]:
    """Seed product-level topics from the project brief's Key Capabilities section.

    Called after discovery generates or updates the brief.
    Creates topics scoped to positioning-driven strategies.
    Topics are created_by='discovery' with status='uncovered'.
    Does not overwrite existing topics -- only adds new ones.

    Returns list of newly created ContentTopic objects.
    """
    if not strategies:
        logger.info("No strategies provided, skipping topic seeding")
        return []

    # Parse Key Capabilities section from brief markdown
    capabilities = _parse_key_capabilities(brief)
    if not capabilities:
        logger.warning(
            "No 'Key Capabilities' section found in brief for project %s, skipping topic seeding",
            project_id,
        )
        return []

    created: list[ContentTopic] = []
    for strategy in strategies:
        existing = ops.get_topics_by_strategy(conn, project_id, strategy)
        existing_names = {t.topic.lower() for t in existing}

        for cap in capabilities:
            if cap.lower() in existing_names:
                logger.info("Topic already exists for strategy %s: %s", strategy, cap)
                continue

            topic = ContentTopic(
                id=generate_id("topic"),
                project_id=project_id,
                strategy=strategy,
                topic=cap,
                status="uncovered",
                created_by="discovery",
            )
            ops.insert_content_topic(conn, topic)
            logger.info(
                "Created topic for strategy %s: %s (id=%s)",
                strategy,
                cap,
                topic.id,
            )
            created.append(topic)

    return created


def _parse_key_capabilities(brief: str) -> list[str]:
    """Extract bullet points from the Key Capabilities section of a brief.

    Returns list of capability strings (stripped of bullet prefix).
    """
    if not brief:
        return []

    # Find "## Key Capabilities" heading
    pattern = r"^## Key Capabilities\s*$"
    match = re.search(pattern, brief, re.MULTILINE)
    if match is None:
        return []

    # Extract content until next ## heading or end
    start = match.end()
    next_heading = re.search(r"^## ", brief[start:], re.MULTILINE)
    section = brief[start : start + next_heading.start()] if next_heading else brief[start:]

    # Extract bullet points
    capabilities = []
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") or stripped.startswith("* "):
            cap = stripped[2:].strip()
            if cap:
                capabilities.append(cap)

    return capabilities


def match_tags_to_topics(
    conn: sqlite3.Connection,
    project_id: str,
    tags: list[str],
) -> list[str]:
    """Find topics whose names/descriptions match the given tags.

    Uses case-insensitive substring matching -- tag "auth" matches topic "auth system".
    Returns list of matching topic IDs (deduplicated).
    """
    if not tags:
        return []

    matched_ids: list[str] = []
    seen: set[str] = set()

    for tag in tags:
        matching_topics = ops.get_topics_matching_tag(conn, project_id, tag)
        for topic in matching_topics:
            if topic.id not in seen:
                matched_ids.append(topic.id)
                seen.add(topic.id)

    return matched_ids


def get_evaluable_topics(
    conn: sqlite3.Connection,
    project_id: str,
    strategy: str,
) -> list[ContentTopic]:
    """Return topics the evaluator should consider for drafting.

    Returns topics where status == 'holding' and commit_count > 0.
    Also includes topics with strategy='_global'.
    The evaluator decides whether there is enough material to draft;
    this function does NOT apply a numeric threshold.
    """
    strategy_topics = ops.get_topics_by_strategy(conn, project_id, strategy)
    global_topics = (
        ops.get_topics_by_strategy(conn, project_id, "_global") if strategy != "_global" else []
    )

    result: list[ContentTopic] = []
    seen: set[str] = set()

    for topic in strategy_topics + global_topics:
        if topic.id in seen:
            continue
        seen.add(topic.id)

        if topic.status == "holding" and topic.commit_count > 0:
            result.append(topic)

    return result


def force_draft_topic(
    conn: sqlite3.Connection,
    config: object,
    project_id: str,
    topic_id: str,
    strategy: str,
    dry_run: bool = False,
) -> str | None:
    """Force-draft a held topic via a scoped evaluator call.

    Called when operator clicks "Draft Now" on a held topic.

    Creates evaluation cycle with trigger_type='topic_maturity',
    trigger_ref=topic_id. The evaluator receives the topic's accumulated
    commit material via the ContentSource 'topic' resolver.

    Returns evaluation_cycle_id or None on failure.
    """
    try:
        topic = ops.get_topic(conn, topic_id)
        if topic is None:
            raise ConfigError(f"Topic not found: {topic_id}")

        if topic.status != "holding":
            logger.warning(
                "Cannot force-draft topic %s: status is %s, expected 'holding'",
                topic_id,
                topic.status,
            )
            return None

        cycle_id = generate_id("cycle")
        cycle = EvaluationCycle(
            id=cycle_id,
            project_id=project_id,
            trigger_type="topic_maturity",
            trigger_ref=topic_id,
        )

        if not dry_run:
            ops.insert_evaluation_cycle(conn, cycle)
            logger.info(
                "Created evaluation cycle %s for force-draft of topic %s",
                cycle_id,
                topic_id,
            )
        else:
            logger.info(
                "[DRY RUN] Would create evaluation cycle %s for topic %s",
                cycle_id,
                topic_id,
            )

        # TODO: Call Phase 2's strategy evaluator with topic description as
        # trigger content. The evaluator produces context_source, arc_id,
        # angle per its normal output, then routes through the drafting
        # pipeline. Stub until evaluator API is finalized.
        logger.info(
            "Topic %s: holding -> force-draft requested (cycle=%s, strategy=%s)",
            topic_id,
            cycle_id,
            strategy,
        )

        return cycle_id

    except ConfigError:
        raise
    except Exception:
        logger.error("Failed to force-draft topic %s", topic_id, exc_info=True)
        return None
