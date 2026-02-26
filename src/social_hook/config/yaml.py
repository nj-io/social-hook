"""YAML configuration loading and parsing."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from social_hook.config.platforms import OutputPlatformConfig
from social_hook.constants import CONFIG_DIR_NAME
from social_hook.errors import ConfigError

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

# Default configuration values
DEFAULT_CONFIG = {
    "models": {
        "evaluator": "anthropic/claude-opus-4-5",
        "drafter": "anthropic/claude-opus-4-5",
        "gatekeeper": "anthropic/claude-haiku-4-5",
    },
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
    "web": {
        "enabled": False,
        "port": 3000,
    },
    "consolidation": {
        "enabled": False,
        "mode": "notify_only",
        "batch_size": 20,
    },
    "channels": {},
}


@dataclass
class ModelsConfig:
    """Model configuration."""

    evaluator: str = "anthropic/claude-opus-4-5"
    drafter: str = "anthropic/claude-opus-4-5"
    gatekeeper: str = "anthropic/claude-haiku-4-5"


@dataclass
class MediaGenerationConfig:
    """Media generation configuration — infrastructure toggles only.

    Content guidance (use_when, constraints, prompt_example) lives in
    content-config.yaml via MediaToolGuidance in project.py.
    """

    enabled: bool = True
    tools: dict[str, bool] = field(default_factory=lambda: {
        "mermaid": True,
        "nano_banana_pro": True,
        "playwright": True,
        "ray_so": True,
    })


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
    model: Optional[str] = None  # None = use evaluator model


@dataclass
class WebConfig:
    """Web dashboard configuration."""

    enabled: bool = False
    port: int = 3000


@dataclass
class ConsolidationConfig:
    """Consolidation processing configuration."""

    enabled: bool = False
    mode: str = "notify_only"  # "notify_only" or "re_evaluate"
    batch_size: int = 20


@dataclass
class ChannelConfig:
    """Configuration for a single messaging channel."""
    enabled: bool = False
    allowed_chat_ids: list[str] = field(default_factory=list)


@dataclass
class Config:
    """Main configuration object."""

    models: ModelsConfig = field(default_factory=ModelsConfig)
    platforms: dict[str, OutputPlatformConfig] = field(default_factory=lambda: {
        "x": OutputPlatformConfig(enabled=True, priority="primary", type="builtin", account_tier="free"),
    })
    media_generation: MediaGenerationConfig = field(default_factory=MediaGenerationConfig)
    scheduling: SchedulingConfig = field(default_factory=SchedulingConfig)
    journey_capture: JourneyCaptureConfig = field(default_factory=JourneyCaptureConfig)
    web: WebConfig = field(default_factory=WebConfig)
    consolidation: ConsolidationConfig = field(default_factory=ConsolidationConfig)
    channels: dict[str, ChannelConfig] = field(default_factory=dict)

    # Environment variables (populated by load_full_config)
    env: dict[str, str] = field(default_factory=dict)


def load_config(config_path: Optional[str | Path] = None) -> Config:
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
    # Models
    models_data = data.get("models", {})
    models = ModelsConfig(
        evaluator=models_data.get("evaluator", "anthropic/claude-opus-4-5"),
        drafter=models_data.get("drafter", "anthropic/claude-opus-4-5"),
        gatekeeper=models_data.get("gatekeeper", "anthropic/claude-haiku-4-5"),
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
            )

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
        )

    # Default: X enabled as primary if no platforms specified
    if not platforms:
        platforms["x"] = OutputPlatformConfig(
            enabled=True, priority="primary", type="builtin", account_tier="free",
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
            )
    journey_capture = JourneyCaptureConfig(
        enabled=jc_data.get("enabled", False),
        model=jc_model,
    )

    # Web dashboard
    web_data = data.get("web", {})
    web_port = web_data.get("port", 3000)
    if not isinstance(web_port, int) or web_port < 1 or web_port > 65535:
        raise ConfigError(f"Invalid web port '{web_port}': must be integer 1-65535")
    web = WebConfig(enabled=web_data.get("enabled", False), port=web_port)

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

    return Config(
        models=models,
        platforms=platforms,
        media_generation=media_generation,
        scheduling=scheduling,
        journey_capture=journey_capture,
        web=web,
        consolidation=consolidation,
        channels=channels,
    )


def validate_config(data: dict[str, Any]) -> Config:
    """Validate a raw config dict. Raises ConfigError if invalid."""
    return _parse_config(data)


def load_full_config(
    env_path: Optional[str | Path] = None,
    yaml_path: Optional[str | Path] = None,
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
