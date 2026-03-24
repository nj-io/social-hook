"""Content topic queue management.

Topics accumulate material from commits (code-driven) or are seeded by
discovery/operator (positioning-driven). The evaluator works through
topics by priority rather than reacting to individual commits.
"""

import logging
import re
import sqlite3
from typing import Any

from social_hook.db import operations as ops
from social_hook.errors import ConfigError
from social_hook.filesystem import generate_id
from social_hook.models import CommitInfo, ContentTopic, EvaluationCycle

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
    config: Any,
    project_id: str,
    topic_id: str,
    strategy: str,
    dry_run: bool = False,
) -> str | None:
    """Force-draft a held topic via a scoped evaluator call.

    Called when operator clicks "Draft Now" on a held topic.

    Creates evaluation cycle with trigger_type='topic_maturity',
    trigger_ref=topic_id. The evaluator receives the topic's accumulated
    commit material and description as trigger content, then routes
    through the drafting pipeline.

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
            return cycle_id

        # Build trigger content from topic description and accumulated commits
        trigger_parts = [f"Topic: {topic.topic}"]
        if topic.description:
            trigger_parts.append(f"Description: {topic.description}")
        trigger_parts.append(f"Strategy: {strategy}")
        trigger_parts.append(f"Accumulated commits: {topic.commit_count}")
        trigger_content = "\n".join(trigger_parts)

        # Run evaluation + drafting if config is available
        if config is None or not getattr(config, "models", None):
            logger.info(
                "Topic %s: holding -> force-draft requested (cycle=%s, strategy=%s)",
                topic_id,
                cycle_id,
                strategy,
            )
            return cycle_id

        from social_hook.config.project import load_project_config
        from social_hook.llm.evaluator import Evaluator
        from social_hook.llm.factory import create_client
        from social_hook.llm.prompts import assemble_evaluator_context

        project = ops.get_project(conn, project_id)
        if project is None:
            logger.error("Project '%s' not found", project_id)
            return cycle_id

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(conn, dry_run=dry_run)
        project_config = load_project_config(project.repo_path)
        context = assemble_evaluator_context(db, project_id, project_config)

        # Build a synthetic CommitInfo with the topic content
        commit = CommitInfo(
            hash=f"topic:{topic_id[:8]}",
            message=trigger_content,
            diff="",
            files_changed=[],
        )

        # Create evaluator client and evaluate
        evaluator_client = create_client(config.models.evaluator, config)
        evaluator = Evaluator(evaluator_client)
        evaluation = evaluator.evaluate(
            commit,
            context,
            db,
            strategy_config=project_config.strategy if project_config else None,
            summary_config=project_config.summary if project_config else None,
        )

        # Route and draft if targets config exists
        if getattr(config, "targets", None) and isinstance(config.targets, dict) and config.targets:
            from social_hook.drafting import draft_for_targets
            from social_hook.routing import route_to_targets

            target_actions = route_to_targets(evaluation.strategies, config, conn)
            draftable_actions = [a for a in target_actions if a.action == "draft"]
            if draftable_actions:
                from social_hook.content_sources import content_sources
                from social_hook.models import Decision

                decision = Decision(
                    id=generate_id("decision"),
                    project_id=project_id,
                    commit_hash=commit.hash,
                    decision="draft",
                    reasoning=trigger_content,
                    commit_message=trigger_content,
                    trigger_source="topic_maturity",
                )
                ops.insert_decision(conn, decision)

                draft_for_targets(
                    draftable_actions,
                    config,
                    conn,
                    db,
                    project,
                    decision_id=decision.id,
                    evaluation=evaluation,
                    context=context,
                    commit=commit,
                    content_source_registry=content_sources,
                    project_config=project_config,
                    dry_run=dry_run,
                )
        else:
            # Legacy path: draft for platforms
            from social_hook.compat import make_eval_compat
            from social_hook.drafting import draft_for_platforms
            from social_hook.models import Decision

            def _val(x: Any) -> Any:
                return x.value if hasattr(x, "value") else x

            first_strategy = next(iter(evaluation.strategies.values()), None)
            if first_strategy and _val(first_strategy.action) == "draft":
                decision = Decision(
                    id=generate_id("decision"),
                    project_id=project_id,
                    commit_hash=commit.hash,
                    decision="draft",
                    reasoning=trigger_content,
                    commit_message=trigger_content,
                    trigger_source="topic_maturity",
                )
                ops.insert_decision(conn, decision)

                eval_compat = make_eval_compat(evaluation, "draft")
                draft_for_platforms(
                    config=config,
                    conn=conn,
                    db=db,
                    project=project,
                    decision_id=decision.id,
                    evaluation=eval_compat,
                    context=context,
                    commit=commit,
                    project_config=project_config,
                )

        logger.info(
            "Topic %s: holding -> force-draft completed (cycle=%s, strategy=%s)",
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
