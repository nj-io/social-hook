"""YAML configuration loading and parsing."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from social_hook.config.platforms import OutputPlatformConfig
from social_hook.constants import CONFIG_DIR_NAME
from social_hook.errors import ConfigError
from social_hook.parsing import check_unknown_keys

# Valid X account tiers and their character limits
VALID_TIERS = ("free", "basic", "premium", "premium_plus")

# NOTE: Keep in sync with KNOWN_PLATFORMS in messaging/factory.py
KNOWN_CHANNELS = {"telegram", "slack", "web"}
TIER_CHAR_LIMITS = {
    "free": 280,
    "basic": 25_000,
    "premium": 25_000,
    "premium_plus": 25_000,
}


def _detect_default_models() -> dict[str, str]:
    """Detect best default models based on available providers.

    If the Claude CLI is installed, use it (free via subscription).
    Otherwise fall back to Anthropic API (requires API key).
    """
    import shutil

    if shutil.which("claude"):
        return {
            "evaluator": "claude-cli/sonnet",
            "drafter": "claude-cli/sonnet",
            "gatekeeper": "claude-cli/haiku",
        }
    return {
        "evaluator": "anthropic/claude-opus-4-5",
        "drafter": "anthropic/claude-opus-4-5",
        "gatekeeper": "anthropic/claude-haiku-4-5",
    }


# Default configuration values
DEFAULT_CONFIG = {
    "models": _detect_default_models(),
    "platforms": {
        "x": {"enabled": True, "priority": "primary", "account_tier": "free"},
    },
    "media_generation": {
        "enabled": True,
        "tools": {
            "mermaid": True,
            "nano_banana_pro": True,
            "playwright": True,
            "ray_so": True,
        },
    },
    "scheduling": {
        "timezone": "UTC",
        "max_posts_per_day": 3,
        "min_gap_minutes": 30,
        "optimal_days": ["Tue", "Wed", "Thu"],
        "optimal_hours": [9, 12, 17],
    },
    "journey_capture": {
        "enabled": False,
    },
    "consolidation": {
        "enabled": False,
        "mode": "notify_only",
        "batch_size": 20,
    },
    "rate_limits": {
        "max_evaluations_per_day": 15,
        "min_evaluation_gap_minutes": 10,
        "batch_throttled": False,
    },
    "channels": {
        "web": {"enabled": True},
    },
}


@dataclass
class ModelsConfig:
    """Model configuration.

    Defaults are resolved at import time by _detect_default_models():
    claude-cli/ if Claude CLI is installed, anthropic/ otherwise.
    """

    evaluator: str = field(default_factory=lambda: DEFAULT_CONFIG["models"]["evaluator"])  # type: ignore[index]
    drafter: str = field(default_factory=lambda: DEFAULT_CONFIG["models"]["drafter"])  # type: ignore[index]
    gatekeeper: str = field(default_factory=lambda: DEFAULT_CONFIG["models"]["gatekeeper"])  # type: ignore[index]


@dataclass
class MediaGenerationConfig:
    """Media generation configuration — infrastructure toggles only.

    Content guidance (use_when, constraints, prompt_example) lives in
    content-config.yaml via MediaToolGuidance in project.py.
    """

    enabled: bool = True
    tools: dict[str, bool] = field(
        default_factory=lambda: {
            "mermaid": True,
            "nano_banana_pro": True,
            "playwright": True,
            "ray_so": True,
        }
    )


@dataclass
class SchedulingConfig:
    """Scheduling configuration."""

    timezone: str = "UTC"
    max_posts_per_day: int = 3
    min_gap_minutes: int = 30
    optimal_days: list[str] = field(default_factory=lambda: ["Tue", "Wed", "Thu"])
    optimal_hours: list[int] = field(default_factory=lambda: [9, 12, 17])
    max_per_week: int = 10
    thread_min_tweets: int = 4


@dataclass
class JourneyCaptureConfig:
    """Development journey capture configuration."""

    enabled: bool = False
    model: str | None = None  # None = use evaluator model


@dataclass
class ConsolidationConfig:
    """Consolidation processing configuration."""

    enabled: bool = False
    mode: str = "notify_only"  # "notify_only" or "re_evaluate"
    batch_size: int = 20
    auto_consolidate_drafts: bool = True
    consolidate_approved: bool = False
    time_window_hours: float = 4.0
    time_window_max_drafts: int = 3


@dataclass
class ChannelConfig:
    """Configuration for a single messaging channel."""

    enabled: bool = False
    allowed_chat_ids: list[str] = field(default_factory=list)


@dataclass
class RateLimitsConfig:
    """Rate limiting configuration for evaluator calls."""

    max_evaluations_per_day: int = 15
    min_evaluation_gap_minutes: int = 10
    batch_throttled: bool = False


@dataclass
class IdentityConfig:
    """Named identity definition for content authorship."""

    type: str = "myself"  # "myself" | "team" | "company" | "project" | "custom"
    label: str = ""
    description: str | None = None
    intro_hook: str | None = None


@dataclass
class ContentStrategyConfig:
    """Content strategy definition. Matches TARGETS_DESIGN.md strategy shape."""

    audience: str | None = None
    voice: str | None = None
    post_when: str | None = None
    avoid: str | None = None


@dataclass
class Config:
    """Main configuration object."""

    models: ModelsConfig = field(default_factory=ModelsConfig)
    platforms: dict[str, OutputPlatformConfig] = field(
        default_factory=lambda: {
            "x": OutputPlatformConfig(
                enabled=True, priority="primary", type="builtin", account_tier="free"
            ),
        }
    )
    media_generation: MediaGenerationConfig = field(default_factory=MediaGenerationConfig)
    scheduling: SchedulingConfig = field(default_factory=SchedulingConfig)
    journey_capture: JourneyCaptureConfig = field(default_factory=JourneyCaptureConfig)
    consolidation: ConsolidationConfig = field(default_factory=ConsolidationConfig)
    rate_limits: RateLimitsConfig = field(default_factory=RateLimitsConfig)
    channels: dict[str, ChannelConfig] = field(default_factory=dict)
    notification_level: str = "all_decisions"  # "all_decisions" or "drafts_only"
    identities: dict[str, IdentityConfig] = field(default_factory=dict)
    default_identity: str | None = None
    content_strategies: dict[str, ContentStrategyConfig] = field(default_factory=dict)
    content_strategy: str | None = None  # Reference to active strategy name

    # Environment variables (populated by load_full_config)
    env: dict[str, str] = field(default_factory=dict)


def resolve_identity(config: Config, platform_name: str) -> IdentityConfig | None:
    """Resolve identity for a platform: platform.identity -> default_identity -> None."""
    pcfg = config.platforms.get(platform_name)
    identity_name = (pcfg.identity if pcfg else None) or config.default_identity
    if identity_name and identity_name in config.identities:
        return config.identities[identity_name]
    return None


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merge overlay into base, modifying base in-place."""
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def save_config(
    updates: dict[str, Any],
    config_path: str | Path,
    deep_merge: bool = False,
) -> tuple[dict[str, Any], str | None]:
    """Merge updates into existing config, validate, and write.

    config_path is required (no default) to prevent accidental writes to the
    real config file in tests. Both callers (server.py, CLI) know their path.

    Returns (merged_dict, hook_warning_or_None). Raises ConfigError on failure.
    """
    import logging

    logger = logging.getLogger(__name__)
    config_path = Path(config_path)

    # Read existing
    if config_path.exists():
        try:
            current = yaml.safe_load(config_path.read_text()) or {}
        except yaml.YAMLError:
            current = {}
    else:
        current = {}

    # Merge
    if deep_merge:
        _deep_merge(current, updates)
    else:
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(current.get(key), dict):
                current[key].update(value)
            else:
                current[key] = value

    # Validate before writing
    validate_config(current)

    # Write
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.dump(current, default_flow_style=False, sort_keys=False))

    # Journey capture hooks
    hook_warning = None
    if "journey_capture" in updates:
        jc_enabled = updates["journey_capture"].get("enabled")
        if jc_enabled is True:
            from social_hook.setup.install import install_narrative_hook

            success, msg = install_narrative_hook()
            if not success:
                logger.warning("Failed to install narrative hook: %s", msg)
                hook_warning = msg
        elif jc_enabled is False:
            from social_hook.setup.install import uninstall_narrative_hook

            success, msg = uninstall_narrative_hook()
            if not success:
                logger.warning("Failed to uninstall narrative hook: %s", msg)
                hook_warning = msg

    return (current, hook_warning)


def load_config(config_path: str | Path | None = None) -> Config:
    """Load configuration from YAML file.

    Args:
        config_path: Path to config.yaml. If None, returns default config.

    Returns:
        Config object with all settings

    Raises:
        ConfigError: If configuration is invalid
    """
    if config_path is None:
        return Config()

    config_path = Path(config_path)

    if not config_path.exists():
        return Config()

    try:
        content = config_path.read_text()
        data = yaml.safe_load(content) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in {config_path}: {e}") from e

    return _parse_config(data)


def _parse_config(data: dict[str, Any]) -> Config:
    """Parse raw config dict into Config object."""
    check_unknown_keys(
        data,
        {
            "models",
            "platforms",
            "media_generation",
            "scheduling",
            "journey_capture",
            "consolidation",
            "channels",
            "notification_level",
            "rate_limits",
            "identities",
            "default_identity",
            "content_strategies",
            "content_strategy",
            "web",
        },
        "content-config",
    )

    # Models
    models_data = data.get("models", {})
    default_models: dict[str, str] = DEFAULT_CONFIG["models"]  # type: ignore[assignment]
    models = ModelsConfig(
        evaluator=models_data.get("evaluator", default_models["evaluator"]),
        drafter=models_data.get("drafter", default_models["drafter"]),
        gatekeeper=models_data.get("gatekeeper", default_models["gatekeeper"]),
    )

    # Validate model names (must use provider/model-id format)
    from social_hook.llm.factory import parse_provider_model

    for role in ("evaluator", "drafter", "gatekeeper"):
        value = getattr(models, role)
        try:
            parse_provider_model(value)
        except ConfigError:
            raise ConfigError(
                f"Invalid model '{value}' for {role}: must use provider/model-id format "
                f"(e.g., 'anthropic/claude-opus-4-5', 'claude-cli/sonnet')"
            ) from None

    # Platforms (dynamic registry)
    from social_hook.config.platforms import (
        CONTENT_FILTERS,
        FREQUENCY_PRESETS,
        VALID_PLATFORM_TYPES,
        VALID_PRIORITIES,
    )

    platforms_data = data.get("platforms", {})
    platforms: dict[str, OutputPlatformConfig] = {}

    for name, pdata in platforms_data.items():
        if not isinstance(pdata, dict):
            raise ConfigError(f"Platform '{name}' config must be a dict")

        priority = pdata.get("priority", "secondary")
        if priority not in VALID_PRIORITIES:
            raise ConfigError(f"Invalid priority '{priority}' for platform '{name}'")

        ptype = pdata.get("type", "builtin" if name in ("x", "linkedin") else "custom")
        if ptype not in VALID_PLATFORM_TYPES:
            raise ConfigError(f"Invalid type '{ptype}' for platform '{name}'")

        # Validate X tier if present
        account_tier = pdata.get("account_tier")
        if name == "x" and account_tier and account_tier not in VALID_TIERS:
            raise ConfigError(
                f"Invalid account_tier '{account_tier}', must be one of {VALID_TIERS}"
            )

        # Validate filter/frequency if explicitly set
        pfilter = pdata.get("filter")
        if pfilter and pfilter not in CONTENT_FILTERS:
            raise ConfigError(f"Invalid filter '{pfilter}' for platform '{name}'")

        freq = pdata.get("frequency")
        if freq and freq not in FREQUENCY_PRESETS:
            raise ConfigError(f"Invalid frequency '{freq}' for platform '{name}'")

        platforms[name] = OutputPlatformConfig(
            enabled=pdata.get("enabled", False),
            priority=priority,
            type=ptype,
            account_tier=account_tier,
            description=pdata.get("description"),
            format=pdata.get("format"),
            max_length=pdata.get("max_length"),
            filter=pfilter,
            frequency=freq,
            scheduling=pdata.get("scheduling"),
            identity=pdata.get("identity"),
        )

    # Default: X enabled as primary if no platforms specified
    if not platforms:
        platforms["x"] = OutputPlatformConfig(
            enabled=True,
            priority="primary",
            type="builtin",
            account_tier="free",
        )

    # Media generation
    media_data = data.get("media_generation", {})
    default_tools = {
        "mermaid": True,
        "nano_banana_pro": True,
        "playwright": True,
        "ray_so": True,
    }
    tools_data = media_data.get("tools", {})
    merged_tools = {**default_tools, **tools_data}
    media_generation = MediaGenerationConfig(
        enabled=media_data.get("enabled", True),
        tools=merged_tools,
    )

    # Scheduling
    sched_data = data.get("scheduling", {})
    scheduling = SchedulingConfig(
        timezone=sched_data.get("timezone", "UTC"),
        max_posts_per_day=sched_data.get("max_posts_per_day", 3),
        min_gap_minutes=sched_data.get("min_gap_minutes", 30),
        optimal_days=sched_data.get("optimal_days", ["Tue", "Wed", "Thu"]),
        optimal_hours=sched_data.get("optimal_hours", [9, 12, 17]),
        max_per_week=sched_data.get("max_per_week", 10),
        thread_min_tweets=sched_data.get("thread_min_tweets", 4),
    )

    # Journey capture
    jc_data = data.get("journey_capture", {})
    jc_model = jc_data.get("model", None)
    if jc_model is not None:
        try:
            parse_provider_model(jc_model)
        except ConfigError:
            raise ConfigError(
                f"Invalid model '{jc_model}' for journey_capture: must use provider/model-id format "
                f"(e.g., 'anthropic/claude-opus-4-5', 'claude-cli/sonnet')"
            ) from None
    journey_capture = JourneyCaptureConfig(
        enabled=jc_data.get("enabled", False),
        model=jc_model,
    )

    # Consolidation
    cons_data = data.get("consolidation", {})
    cons_mode = cons_data.get("mode", "notify_only")
    if cons_mode not in ("notify_only", "re_evaluate"):
        raise ConfigError(
            f"Invalid consolidation mode '{cons_mode}': must be 'notify_only' or 're_evaluate'"
        )
    cons_batch = cons_data.get("batch_size", 20)
    if not isinstance(cons_batch, int) or cons_batch < 1:
        raise ConfigError(
            f"Invalid consolidation batch_size '{cons_batch}': must be positive integer"
        )
    consolidation = ConsolidationConfig(
        enabled=cons_data.get("enabled", False),
        mode=cons_mode,
        batch_size=cons_batch,
        auto_consolidate_drafts=cons_data.get("auto_consolidate_drafts", True),
        consolidate_approved=cons_data.get("consolidate_approved", False),
        time_window_hours=float(cons_data.get("time_window_hours", 4.0)),
        time_window_max_drafts=cons_data.get("time_window_max_drafts", 3),
    )

    # Rate limits
    rl_data = data.get("rate_limits", {})
    rl_max_eval = rl_data.get("max_evaluations_per_day", 15)
    if not isinstance(rl_max_eval, int) or rl_max_eval < 1:
        raise ConfigError(
            f"Invalid rate_limits.max_evaluations_per_day '{rl_max_eval}': must be positive integer"
        )
    rl_min_gap = rl_data.get("min_evaluation_gap_minutes", 10)
    if not isinstance(rl_min_gap, int) or rl_min_gap < 0:
        raise ConfigError(
            f"Invalid rate_limits.min_evaluation_gap_minutes '{rl_min_gap}': must be non-negative integer"
        )
    rate_limits = RateLimitsConfig(
        max_evaluations_per_day=rl_max_eval,
        min_evaluation_gap_minutes=rl_min_gap,
        batch_throttled=bool(rl_data.get("batch_throttled", False)),
    )

    # Channels
    channels_data = data.get("channels", {})
    channels: dict[str, ChannelConfig] = {}
    for name, ch_data in channels_data.items():
        if not isinstance(ch_data, dict):
            raise ConfigError(f"Channel '{name}' config must be a dict")
        if name not in KNOWN_CHANNELS:
            raise ConfigError(f"Unknown channel '{name}': must be one of {sorted(KNOWN_CHANNELS)}")
        chat_ids = ch_data.get("allowed_chat_ids", [])
        if not isinstance(chat_ids, list):
            raise ConfigError(f"Channel '{name}' allowed_chat_ids must be a list")
        channels[name] = ChannelConfig(
            enabled=ch_data.get("enabled", False),
            allowed_chat_ids=[str(cid) for cid in chat_ids],
        )

    # Notification level
    notification_level = data.get("notification_level", "all_decisions")
    if notification_level not in ("all_decisions", "drafts_only"):
        raise ConfigError(
            f"Invalid notification_level '{notification_level}': must be 'all_decisions' or 'drafts_only'"
        )

    # Identities
    identities: dict[str, IdentityConfig] = {}
    for id_name, id_data in data.get("identities", {}).items():
        if not isinstance(id_data, dict):
            raise ConfigError(f"Identity '{id_name}' config must be a dict")
        identities[id_name] = IdentityConfig(
            type=id_data.get("type", "myself"),
            label=id_data.get("label", id_name),
            description=id_data.get("description"),
            intro_hook=id_data.get("intro_hook"),
        )
    default_identity = data.get("default_identity")

    # Content strategies
    content_strategies: dict[str, ContentStrategyConfig] = {}
    for cs_name, cs_data in data.get("content_strategies", {}).items():
        if not isinstance(cs_data, dict):
            raise ConfigError(f"Content strategy '{cs_name}' config must be a dict")
        content_strategies[cs_name] = ContentStrategyConfig(
            audience=cs_data.get("audience"),
            voice=cs_data.get("voice"),
            post_when=cs_data.get("post_when"),
            avoid=cs_data.get("avoid"),
        )
    content_strategy = data.get("content_strategy")

    # Cross-reference validation
    if default_identity and default_identity not in identities:
        raise ConfigError(f"default_identity '{default_identity}' not found in identities")
    if content_strategy and content_strategy not in content_strategies:
        raise ConfigError(f"content_strategy '{content_strategy}' not found in content_strategies")
    for pname, pcfg in platforms.items():
        if pcfg.identity and pcfg.identity not in identities:
            raise ConfigError(f"Platform '{pname}' references unknown identity '{pcfg.identity}'")

    return Config(
        models=models,
        platforms=platforms,
        media_generation=media_generation,
        scheduling=scheduling,
        journey_capture=journey_capture,
        consolidation=consolidation,
        rate_limits=rate_limits,
        channels=channels,
        notification_level=notification_level,
        identities=identities,
        default_identity=default_identity,
        content_strategies=content_strategies,
        content_strategy=content_strategy,
    )


def validate_config(data: dict[str, Any]) -> Config:
    """Validate a raw config dict. Raises ConfigError if invalid."""
    return _parse_config(data)


def load_full_config(
    env_path: str | Path | None = None,
    yaml_path: str | Path | None = None,
) -> Config:
    """Load full configuration from both .env and config.yaml.

    Args:
        env_path: Path to .env file. If None, uses ~/.social-hook/.env
        yaml_path: Path to config.yaml. If None, uses ~/.social-hook/config.yaml

    Returns:
        Config object with all settings including environment variables

    Raises:
        ConfigError: If configuration is invalid
    """
    from social_hook.config.env import load_env

    # Set default paths
    if env_path is None:
        env_path = Path.home() / CONFIG_DIR_NAME / ".env"
    if yaml_path is None:
        yaml_path = Path.home() / CONFIG_DIR_NAME / "config.yaml"

    # Load environment variables
    env_vars = load_env(env_path)

    # Load YAML config
    config = load_config(yaml_path)

    # Attach env vars to config
    config.env = env_vars

    return config
