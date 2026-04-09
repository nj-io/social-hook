"""Dynamic platform registry with smart defaults and content filtering."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from social_hook.adapters.models import ARTICLE, SINGLE, THREAD
from social_hook.errors import ConfigError

if TYPE_CHECKING:
    from social_hook.config.yaml import SchedulingConfig

# Valid values for validation
CONTENT_FILTERS = {"all", "notable", "significant"}
FREQUENCY_PRESETS = {"high", "moderate", "low", "minimal"}
VALID_PRIORITIES = ("primary", "secondary")
VALID_PLATFORM_TYPES = ("builtin", "custom")

# Frequency preset -> scheduling params
FREQUENCY_PARAMS: dict[str, dict[str, int]] = {
    "high": {"max_posts_per_day": 3, "min_gap_minutes": 30},
    "moderate": {"max_posts_per_day": 1, "min_gap_minutes": 120},
    "low": {"max_posts_per_day": 1, "min_gap_minutes": 2880},
    "minimal": {"max_posts_per_day": 1, "min_gap_minutes": 10080},
}

# Smart defaults: platform_name + priority -> filter + frequency
SMART_DEFAULTS: dict[str, dict[str, dict[str, str]]] = {
    "x": {
        "primary": {"filter": "all", "frequency": "high"},
        "secondary": {"filter": "notable", "frequency": "moderate"},
    },
    "linkedin": {
        "primary": {"filter": "notable", "frequency": "moderate"},
        "secondary": {"filter": "significant", "frequency": "low"},
    },
    "_custom": {
        "primary": {"filter": "notable", "frequency": "moderate"},
        "secondary": {"filter": "significant", "frequency": "low"},
    },
}


# Platform vehicle support — used at config validation time when adapter
# instances are unavailable. Must stay in sync with PlatformAdapter.capabilities().
PLATFORM_VEHICLE_SUPPORT: dict[str, list] = {
    "x": [SINGLE, THREAD, ARTICLE],
    "linkedin": [SINGLE, ARTICLE],
}


@dataclass
class OutputPlatformConfig:
    """Configuration for a single output platform."""

    enabled: bool = False
    priority: str = "secondary"  # "primary" or "secondary"

    # Platform identity
    type: str = "builtin"  # "builtin" or "custom"
    account_tier: str | None = None  # X-specific (free/basic/premium/premium_plus)

    # Custom platform fields (type=custom only)
    description: str | None = None  # Extra context for the drafter
    format: str | None = None  # "tweet", "post", "article", "email", etc.
    max_length: int | None = None  # Character limit (None = no limit)

    # Advanced settings (None = resolved from priority + platform via smart defaults)
    filter: str | None = None  # "all", "notable", "significant"
    frequency: str | None = None  # "high", "moderate", "low", "minimal"

    # Per-platform scheduling overrides (None = use global + frequency preset)
    scheduling: dict | None = None

    # Reference to named identity definition
    identity: str | None = None


@dataclass
class ResolvedPlatformConfig:
    """Fully resolved platform config -- all defaults applied. Used by pipeline."""

    name: str
    enabled: bool
    priority: str
    type: str
    account_tier: str | None
    description: str | None
    format: str | None
    max_length: int | None
    filter: str  # Always resolved (never None)
    frequency: str  # Always resolved (never None)
    max_posts_per_day: int  # Resolved from frequency preset or scheduling override
    min_gap_minutes: int  # Resolved from frequency preset or scheduling override
    optimal_days: list[str] = field(default_factory=list)
    optimal_hours: list[int] = field(default_factory=list)


def resolve_platform(
    name: str,
    raw: OutputPlatformConfig,
    global_scheduling: "SchedulingConfig",
) -> ResolvedPlatformConfig:
    """Resolve all None fields to concrete defaults.

    Args:
        name: Platform name (e.g., "x", "linkedin", "blog")
        raw: User-provided platform config (may have None fields)
        global_scheduling: Global scheduling config for fallback values

    Returns:
        ResolvedPlatformConfig with all fields populated

    Raises:
        ConfigError: If priority, filter, or frequency values are invalid
    """
    priority = raw.priority
    if priority not in VALID_PRIORITIES:
        raise ConfigError(f"Invalid priority '{priority}' for platform '{name}'")

    # Look up smart defaults for this platform + priority
    defaults_key = name if name in SMART_DEFAULTS else "_custom"
    defaults = SMART_DEFAULTS[defaults_key][priority]

    # Resolve filter
    resolved_filter = raw.filter if raw.filter is not None else defaults["filter"]
    if resolved_filter not in CONTENT_FILTERS:
        raise ConfigError(f"Invalid filter '{resolved_filter}' for platform '{name}'")

    # Resolve frequency
    resolved_frequency = raw.frequency if raw.frequency is not None else defaults["frequency"]
    if resolved_frequency not in FREQUENCY_PRESETS:
        raise ConfigError(f"Invalid frequency '{resolved_frequency}' for platform '{name}'")

    # Resolve scheduling params from frequency preset
    freq_params = FREQUENCY_PARAMS[resolved_frequency]

    # Per-platform scheduling overrides take precedence
    sched = raw.scheduling or {}
    max_posts_per_day = sched.get("max_posts_per_day", freq_params["max_posts_per_day"])
    min_gap_minutes = sched.get("min_gap_minutes", freq_params["min_gap_minutes"])
    optimal_days = sched.get("optimal_days", global_scheduling.optimal_days)
    optimal_hours = sched.get("optimal_hours", global_scheduling.optimal_hours)

    return ResolvedPlatformConfig(
        name=name,
        enabled=raw.enabled,
        priority=priority,
        type=raw.type,
        account_tier=raw.account_tier,
        description=raw.description,
        format=raw.format,
        max_length=raw.max_length,
        filter=resolved_filter,
        frequency=resolved_frequency,
        max_posts_per_day=max_posts_per_day,
        min_gap_minutes=min_gap_minutes,
        optimal_days=optimal_days,
        optimal_hours=optimal_hours,
    )
