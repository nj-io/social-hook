"""Target configuration dataclasses and validation.

Defines PlatformCredentialConfig, AccountConfig, TargetConfig,
PlatformSettingsConfig, and the validate_targets_config() function.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from social_hook.config.platforms import FREQUENCY_PRESETS, PLATFORM_THREAD_SUPPORT, SMART_DEFAULTS
from social_hook.errors import ConfigError

if TYPE_CHECKING:
    from social_hook.config.yaml import Config

logger = logging.getLogger(__name__)

# Known builtin platforms (platforms with SMART_DEFAULTS entries, excluding _custom)
KNOWN_BUILTIN_PLATFORMS = {k for k in SMART_DEFAULTS if k != "_custom"}

# Valid destinations for targets
VALID_DESTINATIONS = {"timeline", "community", "quote-retweet"}


@dataclass
class PlatformCredentialConfig:
    """Static app credentials for a platform."""

    platform: str  # "x", "linkedin"
    client_id: str = ""
    client_secret: str = ""


@dataclass
class AccountConfig:
    """An authenticated presence on a platform."""

    platform: str  # "x", "linkedin"
    app: str | None = None  # ref to platform_credentials entry (defaults to first match)
    tier: str | None = None  # X-specific: "free", "basic", "premium", "premium_plus"
    identity: str | None = None  # ref to identities entry
    entity: str | None = None  # LinkedIn-specific: "personal" or org URN


@dataclass
class TargetConfig:
    """A specific content flow -- the pipeline unit."""

    account: str = ""  # ref to accounts entry (empty for accountless/preview-mode targets)
    platform: str = ""  # direct platform name (used when account is empty)
    destination: str = "timeline"  # "timeline", "community", "quote-retweet"
    strategy: str = ""  # ref to content_strategies entry
    primary: bool = False
    source: str | None = None  # ref to another target (hard dependency)
    community_id: str | None = None  # required when destination=community
    share_with_followers: bool = False
    status: str | None = None  # "disabled" or None (enabled)
    frequency: str | None = None  # "high", "moderate", "low", "minimal"
    scheduling: dict | None = None  # per-target overrides


@dataclass
class PlatformSettingsConfig:
    """Per-platform settings (not per-account).

    Parsed in Phase 1 but not enforced until a later phase
    (cross-account scheduling requires the multi-account posting loop).
    """

    cross_account_gap_minutes: int = 0  # 0 = disabled


def resolve_target_platform(target: TargetConfig, config: Config) -> str:
    """Return the platform name for a target.

    If the target has an account, look up the account's platform.
    If the target has no account, use target.platform directly.
    """
    if target.account:
        account = config.accounts.get(target.account)
        if account:
            return account.platform
        else:
            logger.warning(
                "Target references unknown account '%s', falling back to target.platform",
                target.account,
            )
            return target.platform
    else:
        return target.platform


def resolve_default_platform(config: Config) -> str:
    """Find the default platform from configured targets.

    Priority: primary target's platform > first target's platform > "x".
    """
    targets = getattr(config, "targets", None) or {}
    for _name, target in targets.items():
        if target.primary:
            return resolve_target_platform(target, config)
    # Fall back to first target
    for _name, target in targets.items():
        platform = resolve_target_platform(target, config)
        if platform:
            return platform
    return "x"


def is_default_target_preview(config: Config) -> bool:
    """Check whether the default target is in preview mode (no account connected).

    Returns True if the primary target (or first target) has no account,
    or if no targets are configured.
    """
    targets = getattr(config, "targets", None) or {}
    for _name, target in targets.items():
        if target.primary:
            return not bool(target.account)
    # Fall back to first target
    for _name, target in targets.items():
        return not bool(target.account)
    return True


def validate_targets_config(config: Config) -> None:
    """Validate targets-related config sections.

    Fail-fast: raises ConfigError on first validation failure,
    matching existing _parse_config() pattern.

    Checks (from TARGETS_DESIGN.md Config Validation):
    - Account refs resolve (target -> account exists)
    - Identity refs resolve (account -> identity or default_identity)
    - Strategy refs resolve (target -> content_strategies exists)
    - Source refs resolve -- circular dependency detection via visited-set DFS
    - At most one primary: true per platform
    - community_id required when destination: community
    - max_targets limit not exceeded
    - Duplicate accounts -> name uniqueness checked
    - Empty strategy string -> error (required field)

    Args:
        config: Fully parsed Config object

    Raises:
        ConfigError: On first validation failure
    """
    # Skip validation if no targets config sections exist
    if not config.accounts and not config.targets:
        return

    # --- Account / platform reference validation ---
    for target_name, target in config.targets.items():
        if target.account:
            # Account-linked target: account must resolve
            if target.account not in config.accounts:
                raise ConfigError(
                    f"Target '{target_name}' references unknown account '{target.account}'"
                )
        elif target.platform:
            # Accountless target: platform must be a known builtin platform
            if target.platform not in KNOWN_BUILTIN_PLATFORMS:
                raise ConfigError(
                    f"Target '{target_name}' has unknown platform '{target.platform}': "
                    f"must be one of {sorted(KNOWN_BUILTIN_PLATFORMS)}"
                )
        else:
            # Neither account nor platform specified
            raise ConfigError(
                f"Target '{target_name}' must have either 'account' or 'platform' specified"
            )

    # --- Identity reference validation ---
    for account_name, account in config.accounts.items():
        if account.identity and account.identity not in config.identities:
            raise ConfigError(
                f"Account '{account_name}' references unknown identity '{account.identity}'"
            )

    # --- Strategy reference validation ---
    # Valid strategies = config overrides + built-in templates
    from social_hook.setup.templates import STRATEGY_TEMPLATES

    valid_strategies = set(config.content_strategies.keys()) | {
        t.id for t in STRATEGY_TEMPLATES if t.id != "custom"
    }
    for target_name, target in config.targets.items():
        if not target.strategy:
            raise ConfigError(f"Target '{target_name}' has empty strategy (required field)")
        if target.strategy not in valid_strategies:
            raise ConfigError(
                f"Target '{target_name}' references unknown strategy '{target.strategy}'"
            )

    # --- Source reference validation with circular dependency detection ---
    for target_name, target in config.targets.items():
        if target.source is not None:
            if target.source not in config.targets:
                raise ConfigError(
                    f"Target '{target_name}' references unknown source target '{target.source}'"
                )
            # DFS cycle detection: walk source chain
            visited: set[str] = set()
            current: str | None = target_name
            while current is not None:
                if current in visited:
                    raise ConfigError(
                        f"Circular dependency detected in target source chain: "
                        f"'{target_name}' -> ... -> '{current}'"
                    )
                visited.add(current)
                current_target = config.targets.get(current)
                current = current_target.source if current_target else None

    # --- At most one primary per platform ---
    primary_by_platform: dict[str, str] = {}  # platform -> first primary target name
    for target_name, target in config.targets.items():
        if target.primary:
            platform = resolve_target_platform(target, config)
            if platform:
                if platform in primary_by_platform:
                    raise ConfigError(
                        f"Multiple primary targets for platform '{platform}': "
                        f"'{primary_by_platform[platform]}' and '{target_name}'"
                    )
                primary_by_platform[platform] = target_name
            else:
                logger.warning("Target '%s' is primary but has no resolvable platform", target_name)

    # --- community_id required when destination=community ---
    for target_name, target in config.targets.items():
        if target.destination == "community" and not target.community_id:
            raise ConfigError(
                f"Target '{target_name}' has destination 'community' but no community_id specified"
            )

    # --- max_targets limit ---
    if len(config.targets) > config.max_targets:
        raise ConfigError(
            f"Too many targets ({len(config.targets)}): max_targets is {config.max_targets}"
        )

    # --- Frequency validation ---
    for target_name, target in config.targets.items():
        if target.frequency is not None and target.frequency not in FREQUENCY_PRESETS:
            raise ConfigError(
                f"Target '{target_name}' has invalid frequency '{target.frequency}': "
                f"must be one of {sorted(FREQUENCY_PRESETS)}"
            )

    # --- Destination validation ---
    for target_name, target in config.targets.items():
        if target.destination not in VALID_DESTINATIONS:
            raise ConfigError(
                f"Target '{target_name}' has invalid destination '{target.destination}': "
                f"must be one of {sorted(VALID_DESTINATIONS)}"
            )

    # --- Strategy constraint validation ---
    validate_strategy_constraints(config)


def validate_strategy_constraints(config: Config) -> None:
    """Validate cross-cutting constraints between strategies and platforms.

    Checks:
    - strategy.min_length <= platform max_length (ConfigError if exceeds)
    - strategy.format_preference "thread" requires platform thread support (warning)
    - strategy.requires tools are enabled in media config (ConfigError if missing)

    Called from validate_targets_config().

    Args:
        config: Fully parsed Config object

    Raises:
        ConfigError: On min_length or requires constraint violation
    """
    if not config.content_strategies:
        return

    # Build strategy -> platforms map from targets
    strategy_platforms: dict[str, set[str]] = {}
    for _target_name, target in config.targets.items():
        platform = resolve_target_platform(target, config)
        if target.strategy:
            strategy_platforms.setdefault(target.strategy, set()).add(platform)

    # Get enabled media tools
    media_config = getattr(config, "media_generation", None)
    enabled_tools: set[str] = set()
    if media_config and getattr(media_config, "enabled", False):
        for tool_name, enabled in getattr(media_config, "tools", {}).items():
            if enabled:
                enabled_tools.add(tool_name)

    for strat_name, strat in config.content_strategies.items():
        platforms = strategy_platforms.get(strat_name, set())

        # --- min_length vs platform max_length ---
        if strat.min_length is not None:
            for platform_name in platforms:
                pcfg = config.platforms.get(platform_name)
                if pcfg and pcfg.max_length is not None and strat.min_length > pcfg.max_length:
                    raise ConfigError(
                        f"Strategy '{strat_name}' min_length ({strat.min_length}) "
                        f"exceeds platform '{platform_name}' max_length ({pcfg.max_length})"
                    )

        # --- format_preference "thread" requires thread support ---
        if strat.format_preference == "thread":
            for platform_name in platforms:
                supports = PLATFORM_THREAD_SUPPORT.get(platform_name)
                if supports is False:
                    logger.warning(
                        "Strategy '%s' prefers threads but platform '%s' does not support threads",
                        strat_name,
                        platform_name,
                    )
                elif supports is None:
                    logger.warning(
                        "Strategy '%s' prefers threads but platform '%s' "
                        "has unknown thread support",
                        strat_name,
                        platform_name,
                    )

        # --- requires tools enabled in media config ---
        if strat.requires:
            for tool_name in strat.requires:
                if tool_name not in enabled_tools:
                    raise ConfigError(
                        f"Strategy '{strat_name}' requires tool '{tool_name}' "
                        f"but it is not enabled in media_generation.tools"
                    )
