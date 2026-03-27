"""Content topic queue management.

Topics accumulate material from commits (code-driven) or are seeded by
discovery/operator (positioning-driven). The evaluator works through
topics by priority rather than reacting to individual commits.
"""

import logging
import sqlite3
from typing import Any

from social_hook.db import operations as ops
from social_hook.errors import ConfigError
from social_hook.filesystem import generate_id
from social_hook.models import CommitInfo, ContentTopic, EvaluationCycle
from social_hook.setup.templates import POSITIONING_TEMPLATES

logger = logging.getLogger(__name__)


def is_positioning_strategy(strategy_name: str) -> bool:
    """Check if a strategy is positioning-driven based on template name.

    Positioning strategies get product topics (seeded from brief).
    Code-driven strategies (and custom/unrecognized) get implementation topics
    (created from commit tags).
    """
    return strategy_name in POSITIONING_TEMPLATES


def _insert_topic_if_new(
    conn: sqlite3.Connection,
    project_id: str,
    strategy: str,
    title: str,
    created_by: str,
    existing_by_name: dict[str, ContentTopic],
    description: str | None = None,
) -> ContentTopic | None:
    """Insert a topic if no existing topic matches the title (case-insensitive).

    Skips creation when a topic with the same name already exists (including
    dismissed topics, which should not be recreated by auto-seeding).

    Returns the new ContentTopic, or None if skipped.
    """
    existing_topic = existing_by_name.get(title.lower())
    if existing_topic is not None:
        label = "dismissed" if existing_topic.status == "dismissed" else "existing"
        logger.info("Skipping %s topic for strategy %s: %s", label, strategy, title)
        return None

    topic = ContentTopic(
        id=generate_id("topic"),
        project_id=project_id,
        strategy=strategy,
        topic=title,
        description=description,
        status="uncovered",
        created_by=created_by,
    )
    ops.insert_content_topic(conn, topic)
    ops.emit_data_event(conn, "topic", "created", topic.id, project_id)
    logger.info(
        "Created topic for strategy %s: %s (id=%s, created_by=%s)",
        strategy,
        title,
        topic.id,
        created_by,
    )
    return topic


def process_topic_suggestions(
    conn: sqlite3.Connection,
    project_id: str,
    suggestions: list[Any],
    strategies: list[str],
) -> list[ContentTopic]:
    """Process topic suggestions from the commit analyzer (stage 1).

    Each suggestion has title, description, and strategy_type (code-driven or
    positioning). Topics are created scoped to the appropriate strategies based
    on strategy_type.

    Args:
        conn: Database connection
        project_id: Project ID
        suggestions: List of TopicSuggestion objects from analyzer
        strategies: All strategy names for the project

    Returns list of newly created ContentTopic objects.
    """
    if not suggestions or not strategies:
        return []

    # Split strategies by type
    positioning = [s for s in strategies if is_positioning_strategy(s)]
    code_driven = [s for s in strategies if not is_positioning_strategy(s)]

    # Pre-fetch existing topics per strategy
    existing_by_strategy: dict[str, dict[str, ContentTopic]] = {}
    for strategy in strategies:
        topics_for_strat = ops.get_topics_by_strategy(conn, project_id, strategy)
        existing_by_strategy[strategy] = {t.topic.lower(): t for t in topics_for_strat}

    created: list[ContentTopic] = []
    for suggestion in suggestions:
        title = getattr(suggestion, "title", "").strip()
        if not title:
            continue
        description = getattr(suggestion, "description", None)
        if description:
            description = description.strip() or None
        strategy_type = getattr(suggestion, "strategy_type", "code-driven")

        # Route to appropriate strategies
        if strategy_type == "positioning":
            target_strategies = positioning
            created_by = "discovery"
        else:
            target_strategies = code_driven
            created_by = "track1"

        if not target_strategies:
            logger.info(
                "No %s strategies for topic suggestion: %s",
                strategy_type,
                title,
            )
            continue

        for strategy in target_strategies:
            existing_by_name = existing_by_strategy.get(strategy, {})
            topic = _insert_topic_if_new(
                conn,
                project_id,
                strategy,
                title=title,
                created_by=created_by,
                existing_by_name=existing_by_name,
                description=description,
            )
            if topic is not None:
                created.append(topic)
                # Update cache so next suggestion sees this topic
                existing_by_name[title.lower()] = topic

    return created


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
    """Get topics ready for evaluation: holding with commits accumulated.

    Returns topics with status='holding' and commit_count > 0 for the
    given strategy. Also includes _global strategy topics.
    """
    strategy_topics = ops.get_topics_by_strategy(conn, project_id, strategy)
    evaluable = [t for t in strategy_topics if t.status == "holding" and t.commit_count > 0]

    if strategy != "_global":
        global_topics = ops.get_topics_by_strategy(conn, project_id, "_global")
        evaluable.extend(t for t in global_topics if t.status == "holding" and t.commit_count > 0)

    return evaluable


def force_draft_topic(
    conn: sqlite3.Connection,
    config: Any,
    project_id: str,
    topic_id: str,
    strategy: str,
    dry_run: bool = False,
) -> str | None:
    """Force-draft a held or uncovered topic via a scoped evaluator call.

    Called when operator clicks "Draft Now" on a held or uncovered topic.

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

        if topic.status not in ("holding", "uncovered"):
            logger.warning(
                "Cannot force-draft topic %s: status is %s, expected 'holding' or 'uncovered'",
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
                "Topic %s: %s -> force-draft requested (cycle=%s, strategy=%s)",
                topic_id,
                topic.status,
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
            strategies=config.content_strategies or None,
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
            "Topic %s: %s -> force-draft completed (cycle=%s, strategy=%s)",
            topic_id,
            topic.status,
            cycle_id,
            strategy,
        )

        return cycle_id

    except ConfigError:
        raise
    except Exception:
        logger.error("Failed to force-draft topic %s", topic_id, exc_info=True)
        return None
