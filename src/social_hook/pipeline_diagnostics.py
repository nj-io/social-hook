"""Pipeline-specific diagnostic checks for evaluation cycle health.

Registers 10 checks on the shared diagnostics_registry.
Import this module for side-effect registration.
"""

import logging

from social_hook.diagnostics import (
    Diagnostic,
    DiagnosticContext,
    DiagnosticSeverity,
    diagnostics_registry,
    flex_get,
    flex_get_action,
)

logger = logging.getLogger(__name__)

INFO = DiagnosticSeverity.INFO
WARNING = DiagnosticSeverity.WARNING
ERROR = DiagnosticSeverity.ERROR


@diagnostics_registry.register("draft_without_target")
def _check_draft_without_target(ctx: DiagnosticContext) -> list[Diagnostic]:
    """Strategy decided 'draft' but no target uses that strategy."""
    results: list[Diagnostic] = []
    strategies = ctx.get("strategies") or {}
    config_targets = ctx.get("config_targets") or {}

    # Build set of strategies referenced by targets
    target_strategies: set[str] = set()
    for _tname, tcfg in config_targets.items():
        strategy = flex_get(tcfg, "strategy")
        if strategy:
            target_strategies.add(strategy)

    for sname, sdata in strategies.items():
        action_str = flex_get_action(sdata)
        if action_str == "draft" and sname not in target_strategies:
            results.append(
                Diagnostic(
                    code="draft_without_target",
                    severity=WARNING,
                    message=f"Strategy '{sname}' decided draft but no target uses it",
                    suggestion=f"Add a target with strategy '{sname}'",
                    context={"strategy": sname},
                )
            )

    return results


@diagnostics_registry.register("no_platforms_enabled")
def _check_no_platforms_enabled(ctx: DiagnosticContext) -> list[Diagnostic]:
    """All platforms disabled or none configured."""
    config_platforms = ctx.get("config_platforms") or {}

    if not config_platforms:
        return [
            Diagnostic(
                code="no_platforms_enabled",
                severity=ERROR,
                message="No platforms configured",
                suggestion="Add at least one platform in content-config.yaml",
            )
        ]

    # Check if all platforms are disabled
    any_enabled = False
    for _pname, pcfg in config_platforms.items():
        if flex_get(pcfg, "enabled", True):
            any_enabled = True
            break

    if not any_enabled:
        return [
            Diagnostic(
                code="no_platforms_enabled",
                severity=ERROR,
                message="All platforms are disabled",
                suggestion="Enable at least one platform in content-config.yaml",
            )
        ]

    return []


@diagnostics_registry.register("no_strategies_defined")
def _check_no_strategies_defined(ctx: DiagnosticContext) -> list[Diagnostic]:
    """Targets exist but no content strategies defined."""
    has_targets = ctx.get("has_targets", False)
    has_strategies = ctx.get("has_strategies", False)

    if has_targets and not has_strategies:
        return [
            Diagnostic(
                code="no_strategies_defined",
                severity=WARNING,
                message="Targets configured but no content strategies defined",
                suggestion="Add content_strategies to content-config.yaml",
            )
        ]

    return []


@diagnostics_registry.register("preview_mode_targets")
def _check_preview_mode_targets(ctx: DiagnosticContext) -> list[Diagnostic]:
    """Targets drafting in preview mode (no account connected)."""
    results: list[Diagnostic] = []
    config_targets = ctx.get("config_targets") or {}

    for tname, tcfg in config_targets.items():
        if not flex_get(tcfg, "account"):
            results.append(
                Diagnostic(
                    code="preview_mode_targets",
                    severity=INFO,
                    message=f"Target '{tname}' is in preview mode (no account connected)",
                    suggestion=f"Connect an account to target '{tname}' to enable posting",
                    context={"target": tname},
                )
            )

    return results


@diagnostics_registry.register("hold_limit_reached")
def _check_hold_limit_reached(ctx: DiagnosticContext) -> list[Diagnostic]:
    """Hold count exceeded, decision forced to skip."""
    hold_limit_forced = ctx.get("hold_limit_forced", False)

    if hold_limit_forced:
        return [
            Diagnostic(
                code="hold_limit_reached",
                severity=WARNING,
                message="Hold limit reached, decision forced to skip",
                suggestion="Review held decisions or increase max_hold_count",
            )
        ]

    return []


@diagnostics_registry.register("all_strategies_skipped")
def _check_all_strategies_skipped(ctx: DiagnosticContext) -> list[Diagnostic]:
    """Every strategy returned skip."""
    strategies = ctx.get("strategies") or {}

    if not strategies:
        return []

    all_skip = True
    for _sname, sdata in strategies.items():
        if flex_get_action(sdata) != "skip":
            all_skip = False
            break

    if all_skip:
        return [
            Diagnostic(
                code="all_strategies_skipped",
                severity=INFO,
                message="All strategies returned skip for this commit",
            )
        ]

    return []


@diagnostics_registry.register("target_unknown_account")
def _check_target_unknown_account(ctx: DiagnosticContext) -> list[Diagnostic]:
    """Target references account not in config.accounts."""
    results: list[Diagnostic] = []
    config_targets = ctx.get("config_targets") or {}
    config_accounts = ctx.get("config_accounts") or {}

    for tname, tcfg in config_targets.items():
        account = flex_get(tcfg, "account")
        if account and account not in config_accounts:
            results.append(
                Diagnostic(
                    code="target_unknown_account",
                    severity=WARNING,
                    message=f"Target '{tname}' references unknown account '{account}'",
                    suggestion=f"Add account '{account}' to accounts config or fix the target",
                    context={"target": tname, "account": account},
                )
            )

    return results


@diagnostics_registry.register("target_no_platform")
def _check_target_no_platform(ctx: DiagnosticContext) -> list[Diagnostic]:
    """Target has neither account nor platform."""
    results: list[Diagnostic] = []
    config_targets = ctx.get("config_targets") or {}

    for tname, tcfg in config_targets.items():
        if not flex_get(tcfg, "account") and not flex_get(tcfg, "platform"):
            results.append(
                Diagnostic(
                    code="target_no_platform",
                    severity=WARNING,
                    message=f"Target '{tname}' has neither account nor platform",
                    suggestion=f"Add an account or platform to target '{tname}'",
                    context={"target": tname},
                )
            )

    return results


@diagnostics_registry.register("target_unknown_strategy")
def _check_target_unknown_strategy(ctx: DiagnosticContext) -> list[Diagnostic]:
    """Target's strategy not in strategies dict (no evaluator decision)."""
    results: list[Diagnostic] = []
    config_targets = ctx.get("config_targets") or {}
    strategies = ctx.get("strategies") or {}

    for tname, tcfg in config_targets.items():
        strategy = flex_get(tcfg, "strategy")
        if strategy and strategy not in strategies:
            results.append(
                Diagnostic(
                    code="target_unknown_strategy",
                    severity=WARNING,
                    message=f"Target '{tname}' references strategy '{strategy}' with no evaluator decision",
                    suggestion=f"Ensure strategy '{strategy}' is defined in content_strategies",
                    context={"target": tname, "strategy": strategy},
                )
            )

    return results


@diagnostics_registry.register("legacy_drafting_fallback")
def _check_legacy_drafting_fallback(ctx: DiagnosticContext) -> list[Diagnostic]:
    """No targets configured, using deprecated platform-based drafting."""
    legacy_fallback = ctx.get("legacy_fallback", False)

    if legacy_fallback:
        return [
            Diagnostic(
                code="legacy_drafting_fallback",
                severity=WARNING,
                message="No targets configured, using deprecated platform-based drafting",
                suggestion="Configure targets in content-config.yaml for multi-account support",
            )
        ]

    return []
