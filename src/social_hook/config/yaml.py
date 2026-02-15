"""YAML configuration loading and parsing."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from social_hook.errors import ConfigError

# Valid X account tiers and their character limits
VALID_TIERS = ("free", "basic", "premium", "premium_plus")
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
        "x": {"enabled": True, "account_tier": "free"},
        "linkedin": {"enabled": False},
    },
    "image_generation": {
        "enabled": True,
        "service": "nano_banana_pro",
    },
    "scheduling": {
        "timezone": "UTC",
        "max_posts_per_day": 3,
        "min_gap_minutes": 30,
        "optimal_days": ["Tue", "Wed", "Thu"],
        "optimal_hours": [9, 12, 17],
    },
}


@dataclass
class ModelsConfig:
    """Model configuration."""

    evaluator: str = "anthropic/claude-opus-4-5"
    drafter: str = "anthropic/claude-opus-4-5"
    gatekeeper: str = "anthropic/claude-haiku-4-5"


@dataclass
class PlatformConfig:
    """Single platform configuration."""

    enabled: bool = False
    account_tier: Optional[str] = None


@dataclass
class PlatformsConfig:
    """All platforms configuration."""

    x: PlatformConfig = field(default_factory=lambda: PlatformConfig(enabled=True, account_tier="free"))
    linkedin: PlatformConfig = field(default_factory=PlatformConfig)


@dataclass
class ImageGenerationConfig:
    """Image generation configuration."""

    enabled: bool = True
    service: str = "nano_banana_pro"


@dataclass
class SchedulingConfig:
    """Scheduling configuration."""

    timezone: str = "UTC"
    max_posts_per_day: int = 3
    min_gap_minutes: int = 30
    optimal_days: list[str] = field(default_factory=lambda: ["Tue", "Wed", "Thu"])
    optimal_hours: list[int] = field(default_factory=lambda: [9, 12, 17])


@dataclass
class Config:
    """Main configuration object."""

    models: ModelsConfig = field(default_factory=ModelsConfig)
    platforms: PlatformsConfig = field(default_factory=PlatformsConfig)
    image_generation: ImageGenerationConfig = field(default_factory=ImageGenerationConfig)
    scheduling: SchedulingConfig = field(default_factory=SchedulingConfig)

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

    # Platforms
    platforms_data = data.get("platforms", {})
    x_data = platforms_data.get("x", {})
    linkedin_data = platforms_data.get("linkedin", {})

    x_tier = x_data.get("account_tier", "free")
    if x_tier not in VALID_TIERS:
        raise ConfigError(
            f"Invalid account_tier '{x_tier}', must be one of {VALID_TIERS}"
        )

    platforms = PlatformsConfig(
        x=PlatformConfig(
            enabled=x_data.get("enabled", True),
            account_tier=x_tier,
        ),
        linkedin=PlatformConfig(
            enabled=linkedin_data.get("enabled", False),
        ),
    )

    # Image generation
    image_data = data.get("image_generation", {})
    image_generation = ImageGenerationConfig(
        enabled=image_data.get("enabled", True),
        service=image_data.get("service", "nano_banana_pro"),
    )

    # Scheduling
    sched_data = data.get("scheduling", {})
    scheduling = SchedulingConfig(
        timezone=sched_data.get("timezone", "UTC"),
        max_posts_per_day=sched_data.get("max_posts_per_day", 3),
        min_gap_minutes=sched_data.get("min_gap_minutes", 30),
        optimal_days=sched_data.get("optimal_days", ["Tue", "Wed", "Thu"]),
        optimal_hours=sched_data.get("optimal_hours", [9, 12, 17]),
    )

    return Config(
        models=models,
        platforms=platforms,
        image_generation=image_generation,
        scheduling=scheduling,
    )


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
        env_path = Path.home() / ".social-hook" / ".env"
    if yaml_path is None:
        yaml_path = Path.home() / ".social-hook" / "config.yaml"

    # Load environment variables
    env_vars = load_env(env_path)

    # Load YAML config
    config = load_config(yaml_path)

    # Attach env vars to config
    config.env = env_vars

    return config
