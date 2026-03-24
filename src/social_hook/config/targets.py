"""Target configuration dataclasses and validation.

Defines PlatformCredentialConfig, AccountConfig, TargetConfig,
PlatformSettingsConfig, and the validate_targets_config() function.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from social_hook.config.platforms import FREQUENCY_PRESETS
from social_hook.errors import ConfigError

if TYPE_CHECKING:
    from social_hook.config.yaml import Config

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

    account: str  # ref to accounts entry
    destination: str = "timeline"  # "timeline", "community", "quote-retweet"
    strategy: str = ""  # ref to content_strategies entry
    primary: bool = False
    source: str | None = None  # ref to another target (hard dependency)
    community_id: str | None = None  # required when destination=community
    share_with_followers: bool = False
    frequency: str | None = None  # "high", "moderate", "low", "minimal"
    scheduling: dict | None = None  # per-target overrides


@dataclass
class PlatformSettingsConfig:
    """Per-platform settings (not per-account).

    Parsed in Phase 1 but not enforced until a later phase
    (cross-account scheduling requires the multi-account posting loop).
    """

    cross_account_gap_minutes: int = 0  # 0 = disabled


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

    # --- Account reference validation ---
    for target_name, target in config.targets.items():
        if target.account not in config.accounts:
            raise ConfigError(
                f"Target '{target_name}' references unknown account '{target.account}'"
            )

    # --- Identity reference validation ---
    for account_name, account in config.accounts.items():
        if account.identity and account.identity not in config.identities:
            raise ConfigError(
                f"Account '{account_name}' references unknown identity '{account.identity}'"
            )

    # --- Strategy reference validation ---
    for target_name, target in config.targets.items():
        if not target.strategy:
            raise ConfigError(f"Target '{target_name}' has empty strategy (required field)")
        if target.strategy not in config.content_strategies:
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
            current = target_name
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
            account = config.accounts.get(target.account)
            if account:
                platform = account.platform
                if platform in primary_by_platform:
                    raise ConfigError(
                        f"Multiple primary targets for platform '{platform}': "
                        f"'{primary_by_platform[platform]}' and '{target_name}'"
                    )
                primary_by_platform[platform] = target_name

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
