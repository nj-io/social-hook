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
from social_hook.models.content import ContentTopic, EvaluationCycle
from social_hook.models.core import CommitInfo
from social_hook.setup.templates import CODE_DRIVEN_TEMPLATES, POSITIONING_TEMPLATES

logger = logging.getLogger(__name__)

# =============================================================================
# Strategy type resolution
# =============================================================================


def resolve_strategy_type(
    strategy_name: str,
    strategy_config: Any | None = None,
    llm_client: Any | None = None,
) -> str:
    """Resolve whether a strategy is code-driven or positioning-driven.

    Resolution order:
    1. Explicit strategy_type field on the strategy config (set by previous classification)
    2. Known template names (POSITIONING_TEMPLATES / CODE_DRIVEN_TEMPLATES)
    3. LLM classification via StrategyClassifier agent (result cached on config)
    4. Default: "code-driven"

    When an LLM classification is made, the result is returned but NOT persisted here —
    the caller should write it back to config via save_config() to cache for future calls.
    """
    # 1. Check explicit strategy_type on config
    if strategy_config is not None:
        explicit_type = getattr(strategy_config, "strategy_type", None)
        if explicit_type in ("code-driven", "positioning"):
            return str(explicit_type)

    # 2. Check known template names
    if strategy_name in POSITIONING_TEMPLATES:
        return "positioning"
    if strategy_name in CODE_DRIVEN_TEMPLATES:
        return "code-driven"

    # 3. LLM classification for custom strategies
    if llm_client is not None and strategy_config is not None:
        try:
            from social_hook.llm.strategy_classifier import StrategyClassifier

            classifier = StrategyClassifier(llm_client)
            return classifier.classify(strategy_name, strategy_config)
        except Exception:
            logger.warning(
                "LLM classification failed for strategy '%s', defaulting to code-driven",
                strategy_name,
                exc_info=True,
            )

    # 4. Default
    return "code-driven"


def is_positioning_strategy(strategy_name: str, strategy_config: Any | None = None) -> bool:
    """Check if a strategy is positioning-driven.

    Convenience wrapper around resolve_strategy_type(). For synchronous use
    without LLM — checks config field and known templates only.
    """
    return resolve_strategy_type(strategy_name, strategy_config) == "positioning"


def _persist_strategy_types(
    strategy_types: dict[str, str],
    strategy_configs: dict[str, Any] | None,
) -> None:
    """Write newly-resolved strategy_type values back to config.

    Only writes if the config object has a strategy_type field that is currently
    unset. Known templates don't need persisting — they're resolved from frozensets.
    """
    if not strategy_configs:
        return

    updates: dict[str, dict[str, str]] = {}
    for name, resolved_type in strategy_types.items():
        # Skip known templates — no need to persist
        if name in POSITIONING_TEMPLATES or name in CODE_DRIVEN_TEMPLATES:
            continue
        scfg = strategy_configs.get(name)
        if scfg is None:
            continue
        existing = getattr(scfg, "strategy_type", None)
        if existing in ("code-driven", "positioning"):
            continue  # Already persisted
        updates[name] = {"strategy_type": resolved_type}

    if not updates:
        return

    try:
        from social_hook.config.yaml import save_config
        from social_hook.filesystem import get_config_path

        save_config(
            {"content_strategies": updates},
            config_path=get_config_path(),
            deep_merge=True,
        )
        logger.info(
            "Persisted strategy_type for %d custom strategies: %s",
            len(updates),
            list(updates.keys()),
        )
    except Exception:
        logger.warning("Failed to persist strategy_type classifications", exc_info=True)


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
    strategy_configs: dict[str, Any] | None = None,
    llm_client: Any | None = None,
) -> list[ContentTopic]:
    """Process topic suggestions from the commit analyzer (stage 1).

    Each suggestion has title, description, and strategy_type (code-driven or
    positioning). Topics are created scoped to the appropriate strategies based
    on strategy_type. Custom strategies are classified via LLM on first use.

    Args:
        conn: Database connection
        project_id: Project ID
        suggestions: List of TopicSuggestion objects from analyzer
        strategies: All strategy names for the project
        strategy_configs: Dict of strategy name -> ContentStrategyConfig (for LLM classification)
        llm_client: Optional LLM client for classifying custom strategies

    Returns list of newly created ContentTopic objects.
    """
    if not suggestions or not strategies:
        return []

    # Resolve each strategy's type (uses config cache, template names, or LLM)
    strategy_types: dict[str, str] = {}
    for s in strategies:
        scfg = strategy_configs.get(s) if strategy_configs else None
        strategy_types[s] = resolve_strategy_type(s, scfg, llm_client)

    # Persist any newly-classified strategy types back to config
    _persist_strategy_types(strategy_types, strategy_configs)

    positioning = [s for s in strategies if strategy_types[s] == "positioning"]
    code_driven = [s for s in strategies if strategy_types[s] == "code-driven"]

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
                from social_hook.models.core import Decision

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
            from social_hook.models.core import Decision
            from social_hook.parsing import enum_value

            first_strategy = next(iter(evaluation.strategies.values()), None)
            if first_strategy and enum_value(first_strategy.action) == "draft":
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
