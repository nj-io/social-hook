"""Target routing -- maps per-strategy decisions to per-target actions.

Fully deterministic. No LLM calls. Unit-testable.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass

from social_hook.config.platforms import FREQUENCY_PARAMS
from social_hook.config.targets import AccountConfig, TargetConfig, resolve_target_platform
from social_hook.config.yaml import Config

# Import with fallback for Chunk 1 compatibility
from social_hook.llm.schemas import StrategyDecisionInput, TargetAction
from social_hook.scheduling import calculate_optimal_time

logger = logging.getLogger(__name__)


@dataclass
class RoutedTarget:
    """Resolved action for a specific target.

    Named RoutedTarget (not TargetAction) to avoid conflict with
    the TargetAction enum in schemas.py (skip/draft/hold).
    """

    target_name: str
    target_config: TargetConfig
    account_config: AccountConfig
    strategy_decision: StrategyDecisionInput
    action: str  # "draft", "skip", "defer"
    skip_reason: str | None = None
    draft_group: str | None = None


def route_to_targets(
    strategy_decisions: dict[str, StrategyDecisionInput],
    config: Config,
    conn: sqlite3.Connection,
) -> list[RoutedTarget]:
    """Map per-strategy decisions to per-target actions.

    For each target:
    1. Look up its strategy's decision
    2. Check scheduling slots (max_posts_per_day, min_gap_minutes)
    3. Check per-account posting gap
    4. Check source dependency (if source target didn't fire -> skip)
    5. Determine draft sharing groups (same strategy + same "draft" action)

    Note: Cross-account platform gap checks belong in the scheduler at
    post time (Phase 4), not here. Routing-time gap data would be stale
    by the time the post is actually published.

    Returns targets in posting order:
    - Primary targets first
    - Independent secondaries next
    - Dependent targets (with source) last
    """
    if not config.targets:
        return []

    routed: list[RoutedTarget] = []
    # Track which targets got "draft" action for source dependency checks
    draft_targets: set[str] = set()

    # First pass: resolve all targets without source dependencies
    # Second pass: resolve targets with source dependencies
    independent: list[str] = []
    dependent: list[str] = []
    for tname, tcfg in config.targets.items():
        if tcfg.source:
            dependent.append(tname)
        else:
            independent.append(tname)

    # Sort independent targets: primary first, then alphabetical
    independent.sort(key=lambda t: (not config.targets[t].primary, t))
    # Dependent targets sorted alphabetically
    dependent.sort()

    # Process independent targets first
    for tname in independent:
        rt = _route_single_target(tname, strategy_decisions, config, conn)
        routed.append(rt)
        if rt.action == "draft":
            draft_targets.add(tname)

    # Process dependent targets
    for tname in dependent:
        tcfg = config.targets[tname]
        # Check source dependency: if source didn't fire, skip
        if tcfg.source and tcfg.source not in draft_targets:
            if tcfg.account:
                account = config.accounts.get(tcfg.account)
                if not account:
                    logger.warning(
                        "Target '%s' references unknown account '%s'", tname, tcfg.account
                    )
                    continue
            elif tcfg.platform:
                account = AccountConfig(platform=tcfg.platform)
            else:
                logger.warning("Target '%s' has neither account nor platform", tname)
                continue
            strategy_name = tcfg.strategy
            decision = strategy_decisions.get(strategy_name)
            if not decision:
                logger.warning("Target '%s' references unknown strategy '%s'", tname, strategy_name)
                continue
            routed.append(
                RoutedTarget(
                    target_name=tname,
                    target_config=tcfg,
                    account_config=account,
                    strategy_decision=decision,
                    action="skip",
                    skip_reason=f"Source target '{tcfg.source}' did not draft",
                )
            )
        else:
            rt = _route_single_target(tname, strategy_decisions, config, conn)
            routed.append(rt)
            if rt.action == "draft":
                draft_targets.add(tname)

    # Assign draft groups: targets with same strategy + "draft" action share a group
    strategy_groups: dict[str, str] = {}
    for rt in routed:
        if rt.action == "draft":
            strategy_name = rt.target_config.strategy
            if strategy_name not in strategy_groups:
                strategy_groups[strategy_name] = f"group-{strategy_name}"
            rt.draft_group = strategy_groups[strategy_name]

    return routed


def _route_single_target(
    target_name: str,
    strategy_decisions: dict[str, StrategyDecisionInput],
    config: Config,
    conn: sqlite3.Connection,
) -> RoutedTarget:
    """Route a single target based on its strategy decision and scheduling."""
    tcfg = config.targets[target_name]

    if tcfg.account:
        account = config.accounts.get(tcfg.account)
        if not account:
            logger.warning("Target '%s' references unknown account '%s'", target_name, tcfg.account)
            # Return a skip with a clear reason
            return RoutedTarget(
                target_name=target_name,
                target_config=tcfg,
                account_config=AccountConfig(platform="unknown"),
                strategy_decision=StrategyDecisionInput(
                    action=TargetAction.skip, reason="Unknown account"
                ),
                action="skip",
                skip_reason=f"Unknown account '{tcfg.account}'",
            )
    elif tcfg.platform:
        # Accountless target: construct synthetic AccountConfig from target.platform
        logger.info(
            "Target '%s' is accountless (platform=%s), using synthetic account",
            target_name,
            tcfg.platform,
        )
        account = AccountConfig(platform=tcfg.platform)
    else:
        logger.warning("Target '%s' has neither account nor platform", target_name)
        return RoutedTarget(
            target_name=target_name,
            target_config=tcfg,
            account_config=AccountConfig(platform="unknown"),
            strategy_decision=StrategyDecisionInput(
                action=TargetAction.skip, reason="No account or platform"
            ),
            action="skip",
            skip_reason="Target has neither account nor platform configured",
        )

    strategy_name = tcfg.strategy
    decision = strategy_decisions.get(strategy_name)

    if not decision:
        logger.warning(
            "Target '%s' references strategy '%s' with no decision", target_name, strategy_name
        )
        return RoutedTarget(
            target_name=target_name,
            target_config=tcfg,
            account_config=account,
            strategy_decision=StrategyDecisionInput(
                action=TargetAction.skip, reason="No strategy decision"
            ),
            action="skip",
            skip_reason=f"No decision for strategy '{strategy_name}'",
        )

    action_str: str = (
        decision.action.value if hasattr(decision.action, "value") else str(decision.action)
    )

    if action_str == "skip":
        return RoutedTarget(
            target_name=target_name,
            target_config=tcfg,
            account_config=account,
            strategy_decision=decision,
            action="skip",
            skip_reason=decision.reason,
        )
    elif action_str == "hold":
        return RoutedTarget(
            target_name=target_name,
            target_config=tcfg,
            account_config=account,
            strategy_decision=decision,
            action="skip",
            skip_reason=f"Hold: {decision.reason}",
        )
    elif action_str == "draft":
        # Check scheduling constraints
        defer_reason = _check_scheduling_constraints(target_name, tcfg, config, conn)
        if defer_reason:
            return RoutedTarget(
                target_name=target_name,
                target_config=tcfg,
                account_config=account,
                strategy_decision=decision,
                action="defer",
                skip_reason=defer_reason,
            )
        return RoutedTarget(
            target_name=target_name,
            target_config=tcfg,
            account_config=account,
            strategy_decision=decision,
            action="draft",
        )
    else:
        logger.warning("Unknown action '%s' for target '%s'", action_str, target_name)
        return RoutedTarget(
            target_name=target_name,
            target_config=tcfg,
            account_config=account,
            strategy_decision=decision,
            action="skip",
            skip_reason=f"Unknown action '{action_str}'",
        )


def _check_scheduling_constraints(
    target_name: str,
    tcfg: TargetConfig,
    config: Config,
    conn: sqlite3.Connection,
) -> str | None:
    """Check if a target's scheduling constraints allow drafting.

    Returns a reason string if the target should be deferred, None if OK.
    """
    # Resolve scheduling params from target frequency or defaults
    frequency = tcfg.frequency or "moderate"
    if frequency not in FREQUENCY_PARAMS:
        logger.warning("Target '%s' has invalid frequency '%s'", target_name, frequency)
        return None  # Allow through, don't block on bad config

    freq_params = FREQUENCY_PARAMS[frequency]
    max_posts_per_day = freq_params["max_posts_per_day"]
    min_gap_minutes = freq_params["min_gap_minutes"]

    # Apply per-target scheduling overrides
    sched = tcfg.scheduling or {}
    max_posts_per_day = sched.get("max_posts_per_day", max_posts_per_day)
    min_gap_minutes = sched.get("min_gap_minutes", min_gap_minutes)

    # Use calculate_optimal_time to check slot availability
    # We don't use the result for actual scheduling -- just check if it defers
    platform = resolve_target_platform(tcfg, config) or "unknown"

    # Get a project_id from existing drafts context -- routing is called
    # per-evaluation so the project context is available to the caller.
    # Here we just check platform-level constraints.
    schedule = calculate_optimal_time(
        conn,
        project_id="__routing_check__",  # Placeholder -- we only check day/gap
        platform=platform,
        tz=config.scheduling.timezone,
        max_posts_per_day=max_posts_per_day,
        min_gap_minutes=min_gap_minutes,
        optimal_days=config.scheduling.optimal_days,
        optimal_hours=config.scheduling.optimal_hours,
        max_per_week=config.scheduling.max_per_week,
    )

    if schedule.deferred:
        return schedule.day_reason

    return None
