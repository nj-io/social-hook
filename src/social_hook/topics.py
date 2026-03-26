"""Content topic queue management.

Topics accumulate material from commits (code-driven) or are seeded by
discovery/operator (positioning-driven). The evaluator works through
topics by priority rather than reacting to individual commits.
"""

import logging
import re
import sqlite3
from pathlib import Path
from typing import Any

from social_hook.db import operations as ops
from social_hook.errors import ConfigError
from social_hook.filesystem import generate_id
from social_hook.models import CommitInfo, ContentTopic, EvaluationCycle
from social_hook.setup.templates import POSITIONING_TEMPLATES

logger = logging.getLogger(__name__)

_TOPIC_EXTRACTION_PROMPT_PATH = (
    Path(__file__).resolve().parent / "llm" / "prompts" / "topic_extraction.md"
)
_topic_extraction_prompt_cache: str | None = None


def _get_topic_extraction_prompt() -> str:
    """Read and cache the topic extraction prompt template."""
    global _topic_extraction_prompt_cache
    if _topic_extraction_prompt_cache is None:
        _topic_extraction_prompt_cache = _TOPIC_EXTRACTION_PROMPT_PATH.read_text(encoding="utf-8")
    return _topic_extraction_prompt_cache


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


def seed_topics_from_brief(
    conn: sqlite3.Connection,
    project_id: str,
    brief: str,
    strategies: list[str],
    granularity: str = "low",
    strategy_configs: dict[str, Any] | None = None,
    llm_client: Any | None = None,
) -> list[ContentTopic]:
    """Seed product-level topics from the project brief.

    Uses LLM-assisted extraction when an llm_client is provided, falling
    back to bullet parsing from the Key Capabilities section.

    Called after discovery generates or updates the brief.
    Creates topics scoped to positioning-driven strategies.
    Topics are created_by='discovery' with status='uncovered'.
    Does not overwrite existing topics -- only adds new ones.

    Args:
        conn: Database connection
        project_id: Project ID
        brief: Project brief text
        strategies: List of strategy names
        granularity: Topic granularity level (low/medium/high)
        strategy_configs: Dict of strategy name -> config dict with
            audience, voice_tone, post_when, angle fields
        llm_client: Optional LLM client for topic extraction

    Returns list of newly created ContentTopic objects.
    """
    if not strategies:
        logger.info("No strategies provided, skipping topic seeding")
        return []

    # Only seed product topics for positioning-driven strategies
    positioning_strategies = [s for s in strategies if is_positioning_strategy(s)]
    if not positioning_strategies:
        logger.info("No positioning strategies found, skipping brief-based topic seeding")
        return []

    if not brief:
        logger.warning("Empty brief for project %s, skipping topic seeding", project_id)
        return []

    created: list[ContentTopic] = []
    for strategy in positioning_strategies:
        # Extract topics via LLM or fallback to bullet parsing
        extracted = _extract_topics_for_strategy(
            brief, strategy, granularity, strategy_configs, llm_client
        )
        if not extracted:
            logger.warning(
                "No topics extracted for strategy %s in project %s",
                strategy,
                project_id,
            )
            continue

        existing = ops.get_topics_by_strategy(conn, project_id, strategy)
        existing_names = {t.topic.lower(): t for t in existing}

        for item in extracted:
            topic = _insert_topic_if_new(
                conn,
                project_id,
                strategy,
                title=item["title"],
                created_by="discovery",
                existing_by_name=existing_names,
                description=item.get("description"),
            )
            if topic is not None:
                created.append(topic)

    return created


def _extract_topics_for_strategy(
    brief: str,
    strategy: str,
    granularity: str,
    strategy_configs: dict[str, Any] | None,
    llm_client: Any | None,
) -> list[dict[str, str]]:
    """Extract topics for a strategy, using LLM if available, else bullet parsing.

    Returns list of dicts with 'title' and optional 'description' keys.
    """
    # Try LLM extraction first
    if llm_client is not None:
        try:
            return _llm_extract_topics(brief, strategy, granularity, strategy_configs, llm_client)
        except Exception:
            logger.warning(
                "LLM topic extraction failed for strategy %s, falling back to bullet parsing",
                strategy,
                exc_info=True,
            )

    # Fallback: parse Key Capabilities bullets (no descriptions)
    capabilities = _parse_key_capabilities(brief)
    return [{"title": cap} for cap in capabilities]


def _llm_extract_topics(
    brief: str,
    strategy: str,
    granularity: str,
    strategy_configs: dict[str, Any] | None,
    llm_client: Any,
) -> list[dict[str, str]]:
    """Use SingleToolAgent to extract topics from the brief via LLM."""
    from social_hook.llm.agent import SingleToolAgent
    from social_hook.llm.schemas import TOPIC_EXTRACTION_TOOL

    # Load prompt template (cached after first read)
    prompt_template = _get_topic_extraction_prompt()

    # Get strategy-specific context
    audience = ""
    angle = ""
    post_when = ""
    if strategy_configs and strategy in strategy_configs:
        scfg = strategy_configs[strategy]
        if isinstance(scfg, dict):
            audience = scfg.get("audience", "")
            angle = scfg.get("voice_tone", "") or scfg.get("angle", "")
            post_when = scfg.get("post_when", "")
        else:
            audience = getattr(scfg, "audience", "") or ""
            angle = getattr(scfg, "voice_tone", "") or getattr(scfg, "angle", "") or ""
            post_when = getattr(scfg, "post_when", "") or ""

    system_prompt = (
        prompt_template.replace("{{strategy_name}}", strategy)
        .replace("{{audience}}", audience or "General audience")
        .replace("{{angle}}", angle or "General")
        .replace("{{post_when}}", post_when or "When relevant")
        .replace("{{granularity}}", granularity)
        .replace("{{brief}}", brief)
    )

    agent = SingleToolAgent(llm_client)
    result, _response = agent.call_tool(
        messages=[{"role": "user", "content": "Extract content topics from this project brief."}],
        tool_schema=TOPIC_EXTRACTION_TOOL,
        system=system_prompt,
        max_tokens=2048,
    )

    topics = result.get("topics", [])
    if not isinstance(topics, list):
        logger.warning("LLM returned non-list topics for strategy %s", strategy)
        return []

    # Validate and normalize
    extracted: list[dict[str, str]] = []
    for item in topics:
        if not isinstance(item, dict):
            continue
        title = item.get("title", "").strip()
        if not title:
            continue
        extracted.append(
            {
                "title": title,
                "description": item.get("description", "").strip() or None,
            }
        )

    if not extracted:
        logger.warning("LLM returned no valid topics for strategy %s", strategy)

    return extracted


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


# Granularity gating: which commit classifications create new topics
_GRANULARITY_MIN_CLASSIFICATION = {
    "low": {"notable", "significant"},
    "medium": {"routine", "notable", "significant"},
    "high": {"routine", "notable", "significant"},  # all non-trivial
}


def _classification_meets_granularity(classification: str, granularity: str) -> bool:
    """Check if a commit classification is significant enough for the granularity level."""
    allowed = _GRANULARITY_MIN_CLASSIFICATION.get(granularity)
    if allowed is None:
        logger.warning("Unknown granularity level: %s, defaulting to 'low'", granularity)
        allowed = _GRANULARITY_MIN_CLASSIFICATION["low"]
    return classification in allowed


def create_topics_from_tags(
    conn: sqlite3.Connection,
    project_id: str,
    tags: list[str],
    classification: str,
    strategies: list[str],
    granularity: str = "low",
) -> list[ContentTopic]:
    """Create implementation topics from commit tags for code-driven strategies.

    Called by the pipeline after stage 1 commit analysis. For each tag that
    doesn't match an existing topic, creates a new topic scoped to code-driven
    strategies. Respects granularity gating and skips dismissed topics.

    Args:
        conn: Database connection
        project_id: Project ID
        tags: Episode tags from commit analysis
        classification: Commit classification (trivial/routine/notable/significant)
        strategies: All strategy names for the project
        granularity: Topic granularity level (low/medium/high)

    Returns list of newly created ContentTopic objects.
    """
    if not tags or not strategies:
        return []

    # Gate on classification vs granularity
    if not _classification_meets_granularity(classification, granularity):
        logger.info(
            "Classification %s below threshold for granularity %s, skipping topic creation",
            classification,
            granularity,
        )
        return []

    # Filter to code-driven strategies only (non-positioning)
    code_strategies = [s for s in strategies if not is_positioning_strategy(s)]
    if not code_strategies:
        logger.info("No code-driven strategies, skipping tag-based topic creation")
        return []

    # Pre-fetch existing topics per strategy (avoids N+1 queries in the loop)
    existing_by_strategy: dict[str, dict[str, ContentTopic]] = {}
    for strategy in code_strategies:
        topics_for_strat = ops.get_topics_by_strategy(conn, project_id, strategy)
        existing_by_strategy[strategy] = {t.topic.lower(): t for t in topics_for_strat}

    created: list[ContentTopic] = []
    for tag in tags:
        # Check if any existing topic already matches this tag
        matching = ops.get_topics_matching_tag(conn, project_id, tag)
        if matching:
            continue

        # Clean up the tag for use as a topic title
        title = tag.replace("-", " ").replace("_", " ").title().strip()
        if not title:
            continue

        for strategy in code_strategies:
            existing_by_name = existing_by_strategy[strategy]
            topic = _insert_topic_if_new(
                conn,
                project_id,
                strategy,
                title=title,
                created_by="track1",
                existing_by_name=existing_by_name,
            )
            if topic is not None:
                created.append(topic)
                # Update the in-memory index so subsequent tags see this topic
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
