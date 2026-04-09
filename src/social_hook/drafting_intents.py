"""DraftingIntent builder functions for each entry point into the drafting pipeline."""

from __future__ import annotations

import logging
import sqlite3
from typing import TYPE_CHECKING, Any

from social_hook.config.platforms import resolve_platform
from social_hook.parsing import enum_value

if TYPE_CHECKING:
    from social_hook.config.yaml import Config
    from social_hook.drafting import DraftingIntent
    from social_hook.llm.schemas import LogEvaluationInput
    from social_hook.models.core import Decision, Draft
    from social_hook.routing import RoutedTarget

logger = logging.getLogger(__name__)


def intent_from_routed_targets(
    routed: list[RoutedTarget],
    decision_id: str,
    evaluation: LogEvaluationInput,
    config: Config,
    conn: sqlite3.Connection,
    project_id: str,
    content_source_registry: Any = None,
    cycle_id: str | None = None,
) -> list[DraftingIntent]:
    """Groups by draft_group -> one intent per group with multiple PlatformSpecs.

    Resolves content sources per strategy.
    Used by: commit trigger (targets), suggestion eval, topic maturity, consolidation.
    """
    from social_hook.content_sources import content_sources as default_registry
    from social_hook.drafting import DraftingIntent, PlatformSpec
    from social_hook.llm.schemas import ContextSourceSpec

    registry = content_source_registry or default_registry

    # Only process targets with "draft" action
    draft_actions = [ta for ta in routed if ta.action == "draft"]
    if not draft_actions:
        return []

    # Detect preview targets: no account configured or account lacks OAuth creds
    accounts_with_creds: set[str] = set()
    cred_rows = conn.execute("SELECT account_name FROM oauth_tokens").fetchall()
    for r in cred_rows:
        accounts_with_creds.add(r[0])

    # Resolve content sources per strategy
    resolved_context: dict[str, dict[str, str]] = {}
    for ta in draft_actions:
        strategy_name = ta.target_config.strategy
        if strategy_name in resolved_context:
            continue
        spec = getattr(ta.strategy_decision, "context_source", None)
        topic_id = getattr(ta.strategy_decision, "topic_id", None)
        if topic_id:
            if spec is None:
                spec = ContextSourceSpec(types=["topic"], topic_id=topic_id)
            else:
                if "topic" not in spec.types:
                    spec.types.append("topic")
                spec.topic_id = topic_id
        if spec and hasattr(spec, "types") and spec.types:
            kwargs: dict[str, Any] = {"conn": conn, "project_id": project_id}
            if hasattr(spec, "topic_id") and spec.topic_id:
                kwargs["topic_id"] = spec.topic_id
            if hasattr(spec, "suggestion_id") and spec.suggestion_id:
                kwargs["suggestion_id"] = spec.suggestion_id
            resolved_context[strategy_name] = registry.resolve(source_types=spec.types, **kwargs)
        else:
            resolved_context[strategy_name] = {}

    # Group by draft_group
    groups: dict[str, list[RoutedTarget]] = {}
    ungrouped: list[RoutedTarget] = []
    for ta in draft_actions:
        if ta.draft_group:
            groups.setdefault(ta.draft_group, []).append(ta)
        else:
            ungrouped.append(ta)

    intents: list[DraftingIntent] = []

    def _resolve_target_platform(ta: RoutedTarget):
        account = ta.account_config
        platform_name = account.platform
        pcfg = config.platforms.get(platform_name)
        if pcfg:
            return resolve_platform(platform_name, pcfg, config.scheduling)
        from social_hook.config.platforms import OutputPlatformConfig

        raw = OutputPlatformConfig(
            enabled=True,
            priority="primary" if ta.target_config.primary else "secondary",
            type="builtin" if platform_name in ("x", "linkedin") else "custom",
            account_tier=account.tier,
        )
        return resolve_platform(platform_name, raw, config.scheduling)

    def _build_intent(targets: list[RoutedTarget]) -> DraftingIntent:
        first = targets[0]
        sd = first.strategy_decision
        content_ctx = resolved_context.get(first.target_config.strategy, {})

        platform_specs = []
        for ta in targets:
            rpcfg = _resolve_target_platform(ta)
            preview = (
                not ta.target_config.account or ta.target_config.account not in accounts_with_creds
            )
            platform_specs.append(
                PlatformSpec(
                    platform=rpcfg.name,
                    resolved=rpcfg,
                    target_id=ta.target_name,
                    preview_mode=preview,
                )
            )

        return DraftingIntent(
            decision="draft",
            vehicle=getattr(sd, "vehicle", None),
            angle=sd.angle or "",
            reasoning=sd.reason,
            post_category=enum_value(sd.post_category),
            commit_summary=evaluation.commit_analysis.summary
            if hasattr(evaluation, "commit_analysis")
            else None,
            platforms=platform_specs,
            arc_id=sd.arc_id,
            reference_posts=sd.reference_posts,
            media_tool=enum_value(sd.media_tool),
            include_project_docs=sd.include_project_docs or False,
            content_source_context=content_ctx or None,
            topic_id=getattr(sd, "topic_id", None),
            decision_id=decision_id,
            cycle_id=cycle_id,
        )

    # Grouped targets -> one intent per group
    for _group_name, group_targets in groups.items():
        intents.append(_build_intent(group_targets))

    # Ungrouped targets -> one intent each
    for ta in ungrouped:
        intents.append(_build_intent([ta]))

    return intents


def intent_from_platforms(
    evaluation: LogEvaluationInput,
    decision_id: str,
    config: Config,
) -> DraftingIntent:
    """Builds from config.platforms when no targets configured.

    Used by: commit trigger (no targets), summary trigger.
    """
    from social_hook.drafting import DraftingIntent, PlatformSpec

    # Build platform specs from config.platforms
    platform_specs = []
    for pname, pcfg in config.platforms.items():
        if pcfg.enabled:
            rpcfg = resolve_platform(pname, pcfg, config.scheduling)
            platform_specs.append(
                PlatformSpec(platform=pname, resolved=rpcfg),
            )

    # Extract fields from the first strategy decision (legacy single-target compat)
    strategies = getattr(evaluation, "strategies", None)
    if strategies is None:
        strategies = getattr(evaluation, "targets", {})
    first_sd = next(iter(strategies.values())) if strategies else None

    return DraftingIntent(
        decision="draft",
        vehicle=getattr(first_sd, "vehicle", None) if first_sd else None,
        angle=first_sd.angle or "" if first_sd else "",
        reasoning=first_sd.reason if first_sd else "",
        post_category=enum_value(first_sd.post_category) if first_sd else None,
        commit_summary=evaluation.commit_analysis.summary
        if hasattr(evaluation, "commit_analysis")
        else None,
        platforms=platform_specs,
        arc_id=first_sd.arc_id if first_sd else None,
        reference_posts=first_sd.reference_posts if first_sd else None,
        media_tool=enum_value(first_sd.media_tool) if first_sd else None,
        include_project_docs=first_sd.include_project_docs or False if first_sd else False,
        decision_id=decision_id,
    )


def intent_from_decision(
    decision: Decision,
    config: Config,
    conn: sqlite3.Connection,
    target_platform: str | None = None,
) -> DraftingIntent:
    """Reads Decision fields directly into DraftingIntent.

    Sets include_project_docs=True so callers get project context in drafts.
    Used by: web Create Draft, Telegram redraft, CLI redraft, intro lifecycle.
    """
    from social_hook.drafting import DraftingIntent, PlatformSpec

    # Resolve platforms
    platform_specs = []
    if target_platform:
        pcfg = config.platforms.get(target_platform)
        if pcfg and pcfg.enabled:
            rpcfg = resolve_platform(target_platform, pcfg, config.scheduling)
            platform_specs.append(PlatformSpec(platform=target_platform, resolved=rpcfg))
    if not platform_specs:
        for pname, pcfg in config.platforms.items():
            if pcfg.enabled:
                rpcfg = resolve_platform(pname, pcfg, config.scheduling)
                platform_specs.append(PlatformSpec(platform=pname, resolved=rpcfg))

    # Extract vehicle from stored targets JSON if available
    vehicle = None
    if decision.targets and isinstance(decision.targets, dict):
        for _strategy_name, strategy_data in decision.targets.items():
            if isinstance(strategy_data, dict):
                vehicle = strategy_data.get("vehicle")
                if vehicle:
                    break

    return DraftingIntent(
        decision=decision.decision,
        vehicle=vehicle,
        angle=decision.angle or "",
        reasoning=decision.reasoning,
        post_category=decision.post_category,
        commit_summary=getattr(decision, "commit_summary", None),
        platforms=platform_specs,
        arc_id=getattr(decision, "arc_id", None),
        reference_posts=getattr(decision, "reference_posts", None),
        media_tool=getattr(decision, "media_tool", None),
        include_project_docs=True,
        decision_id=decision.id,
    )


def intent_from_merge(
    drafts: list[Draft],
    decisions: list[Decision],
    merge_instruction: str | None,
    config: Config,
    platform: str,
) -> DraftingIntent:
    """Builds from merge group data.

    Used by: merge execution in trigger_side_effects.py.
    """
    from social_hook.drafting import DraftingIntent, PlatformSpec

    # Resolve the platform config
    pcfg = config.platforms.get(platform)
    platform_specs = []
    if pcfg and pcfg.enabled:
        rpcfg = resolve_platform(platform, pcfg, config.scheduling)
        platform_specs.append(PlatformSpec(platform=platform, resolved=rpcfg))

    # Build angle from merge instruction + decision angles
    angles = [d.angle for d in decisions if d.angle]
    combined_angle = merge_instruction or "; ".join(angles) if angles else ""

    # Use first decision for metadata
    first_decision = decisions[0] if decisions else None

    return DraftingIntent(
        decision="draft",
        angle=combined_angle,
        reasoning=f"Merge of {len(drafts)} drafts"
        + (f": {merge_instruction}" if merge_instruction else ""),
        post_category=first_decision.post_category if first_decision else None,
        commit_summary=first_decision.commit_summary if first_decision else None,
        platforms=platform_specs,
        arc_id=first_decision.arc_id if first_decision else None,
        include_project_docs=True,
        decision_id=first_decision.id if first_decision else "",
    )
