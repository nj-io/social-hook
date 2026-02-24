"""Tests for YAML config parsing with dynamic platform registry."""

import pytest

from social_hook.config.yaml import (
    Config,
    MediaGenerationConfig,
    SchedulingConfig,
    WebConfig,
    load_config,
    validate_config,
)
from social_hook.config.platforms import OutputPlatformConfig
from social_hook.errors import ConfigError


class TestDynamicPlatformParsing:
    """Test dynamic platform registry parsing from YAML."""

    def test_dynamic_platform_parsing(self, temp_dir):
        """Parse config with x + linkedin + blog."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            """\
platforms:
  x:
    enabled: true
    priority: primary
    account_tier: free
  linkedin:
    enabled: true
    priority: secondary
  blog:
    enabled: true
    priority: secondary
    type: custom
    format: article
    description: My tech blog
"""
        )
        config = load_config(config_path)

        assert len(config.platforms) == 3
        assert "x" in config.platforms
        assert "linkedin" in config.platforms
        assert "blog" in config.platforms

        assert config.platforms["x"].enabled is True
        assert config.platforms["x"].priority == "primary"
        assert config.platforms["x"].account_tier == "free"
        assert config.platforms["x"].type == "builtin"

        assert config.platforms["linkedin"].enabled is True
        assert config.platforms["linkedin"].priority == "secondary"
        assert config.platforms["linkedin"].type == "builtin"

        assert config.platforms["blog"].enabled is True
        assert config.platforms["blog"].type == "custom"
        assert config.platforms["blog"].format == "article"
        assert config.platforms["blog"].description == "My tech blog"

    def test_custom_platform_parsing(self, temp_dir):
        """Parse custom platform with description, format, max_length."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            """\
platforms:
  newsletter:
    enabled: true
    priority: secondary
    type: custom
    description: Weekly developer newsletter
    format: email
    max_length: 10000
    filter: significant
    frequency: minimal
"""
        )
        config = load_config(config_path)

        nl = config.platforms["newsletter"]
        assert nl.type == "custom"
        assert nl.description == "Weekly developer newsletter"
        assert nl.format == "email"
        assert nl.max_length == 10000
        assert nl.filter == "significant"
        assert nl.frequency == "minimal"

    def test_default_platform_when_empty(self, temp_dir):
        """Empty platforms section creates X as primary."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text("models:\n  evaluator: anthropic/claude-opus-4-5\n")
        config = load_config(config_path)

        assert "x" in config.platforms
        assert config.platforms["x"].enabled is True
        assert config.platforms["x"].priority == "primary"
        assert config.platforms["x"].account_tier == "free"

    def test_default_config_returns_x_primary(self):
        """Default Config() has X as primary platform."""
        config = Config()
        assert "x" in config.platforms
        assert config.platforms["x"].enabled is True
        assert config.platforms["x"].priority == "primary"

    def test_platforms_is_dict(self, temp_dir):
        """config.platforms is a dict, not a dataclass."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            "platforms:\n  x:\n    enabled: true\n    account_tier: free\n"
        )
        config = load_config(config_path)
        assert isinstance(config.platforms, dict)

    def test_unknown_platform_name_auto_custom(self, temp_dir):
        """Unknown platform names default to type=custom."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            "platforms:\n  mastodon:\n    enabled: true\n"
        )
        config = load_config(config_path)
        assert config.platforms["mastodon"].type == "custom"

    def test_builtin_platform_default_type(self, temp_dir):
        """x and linkedin default to type=builtin."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            "platforms:\n  x:\n    enabled: true\n  linkedin:\n    enabled: true\n"
        )
        config = load_config(config_path)
        assert config.platforms["x"].type == "builtin"
        assert config.platforms["linkedin"].type == "builtin"

    def test_invalid_priority_raises(self, temp_dir):
        """Invalid priority value raises ConfigError."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            "platforms:\n  x:\n    enabled: true\n    priority: tertiary\n"
        )
        with pytest.raises(ConfigError, match="Invalid priority"):
            load_config(config_path)

    def test_invalid_filter_raises(self, temp_dir):
        """Invalid filter value raises ConfigError."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            "platforms:\n  x:\n    enabled: true\n    filter: extreme\n"
        )
        with pytest.raises(ConfigError, match="Invalid filter"):
            load_config(config_path)

    def test_invalid_frequency_raises(self, temp_dir):
        """Invalid frequency value raises ConfigError."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            "platforms:\n  x:\n    enabled: true\n    frequency: ultra\n"
        )
        with pytest.raises(ConfigError, match="Invalid frequency"):
            load_config(config_path)

    def test_platform_not_dict_raises(self, temp_dir):
        """Non-dict platform value raises ConfigError."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            "platforms:\n  x: true\n"
        )
        with pytest.raises(ConfigError, match="must be a dict"):
            load_config(config_path)

    def test_invalid_x_tier_raises(self, temp_dir):
        """Invalid X account_tier raises ConfigError."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            "platforms:\n  x:\n    enabled: true\n    account_tier: ultra_premium\n"
        )
        with pytest.raises(ConfigError, match="Invalid account_tier"):
            load_config(config_path)


class TestWebConfig:
    """Test WebConfig parsing."""

    def test_web_config_defaults(self):
        """Default web config: disabled, port 3000."""
        config = Config()
        assert config.web.enabled is False
        assert config.web.port == 3000

    def test_web_config_parsing(self, temp_dir):
        """Parse web config from YAML."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            "web:\n  enabled: true\n  port: 8080\n"
        )
        config = load_config(config_path)
        assert config.web.enabled is True
        assert config.web.port == 8080

    def test_web_port_validation_string(self, temp_dir):
        """Non-integer port raises ConfigError."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            "web:\n  port: not_a_number\n"
        )
        with pytest.raises(ConfigError, match="Invalid web port"):
            load_config(config_path)

    def test_web_port_validation_zero(self, temp_dir):
        """Port 0 raises ConfigError."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            "web:\n  port: 0\n"
        )
        with pytest.raises(ConfigError, match="Invalid web port"):
            load_config(config_path)

    def test_web_port_validation_too_high(self, temp_dir):
        """Port > 65535 raises ConfigError."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            "web:\n  port: 70000\n"
        )
        with pytest.raises(ConfigError, match="Invalid web port"):
            load_config(config_path)


class TestMediaGenerationConfig:
    """Test MediaGenerationConfig parsing."""

    def test_defaults_have_four_tools_all_true(self):
        """Default MediaGenerationConfig has 4 tools, all True."""
        config = MediaGenerationConfig()
        assert config.enabled is True
        assert len(config.tools) == 4
        assert config.tools["mermaid"] is True
        assert config.tools["nano_banana_pro"] is True
        assert config.tools["playwright"] is True
        assert config.tools["ray_so"] is True

    def test_config_default_uses_media_generation(self):
        """Default Config() uses media_generation, not image_generation."""
        config = Config()
        assert hasattr(config, "media_generation")
        assert not hasattr(config, "image_generation")
        assert config.media_generation.enabled is True
        assert len(config.media_generation.tools) == 4

    def test_per_tool_override_parsing(self, temp_dir):
        """tools: {mermaid: false} disables mermaid, others default True."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            """\
media_generation:
  enabled: true
  tools:
    mermaid: false
"""
        )
        config = load_config(config_path)
        assert config.media_generation.enabled is True
        assert config.media_generation.tools["mermaid"] is False
        assert config.media_generation.tools["nano_banana_pro"] is True
        assert config.media_generation.tools["playwright"] is True
        assert config.media_generation.tools["ray_so"] is True

    def test_disabled_media_generation(self, temp_dir):
        """media_generation.enabled: false disables all media generation."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            "media_generation:\n  enabled: false\n"
        )
        config = load_config(config_path)
        assert config.media_generation.enabled is False

    def test_empty_media_generation_uses_defaults(self, temp_dir):
        """Empty media_generation section uses all defaults."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            "media_generation: {}\n"
        )
        config = load_config(config_path)
        assert config.media_generation.enabled is True
        assert len(config.media_generation.tools) == 4


class TestSchedulingConfigExtended:
    """Test SchedulingConfig new fields."""

    def test_defaults(self):
        """Default SchedulingConfig has max_per_week=10, thread_min_tweets=4."""
        config = SchedulingConfig()
        assert config.max_per_week == 10
        assert config.thread_min_tweets == 4

    def test_parsing_from_yaml(self, temp_dir):
        """Parse max_per_week and thread_min_tweets from YAML."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            """\
scheduling:
  timezone: America/New_York
  max_per_week: 15
  thread_min_tweets: 6
"""
        )
        config = load_config(config_path)
        assert config.scheduling.max_per_week == 15
        assert config.scheduling.thread_min_tweets == 6
        assert config.scheduling.timezone == "America/New_York"

    def test_partial_override_keeps_defaults(self, temp_dir):
        """Override only max_per_week, thread_min_tweets keeps default."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            "scheduling:\n  max_per_week: 20\n"
        )
        config = load_config(config_path)
        assert config.scheduling.max_per_week == 20
        assert config.scheduling.thread_min_tweets == 4  # default


class TestValidateConfig:
    """Test validate_config() public function."""

    def test_validate_config_returns_config(self):
        """validate_config returns a Config object."""
        result = validate_config({})
        assert isinstance(result, Config)

    def test_validate_config_raises_on_invalid(self):
        """validate_config raises ConfigError on invalid data."""
        with pytest.raises(ConfigError):
            validate_config({"platforms": {"x": {"priority": "bad"}}})
