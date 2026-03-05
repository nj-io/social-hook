"""Tests for dynamic platform registry (config/platforms.py)."""

import pytest

from social_hook.config.platforms import (
    FILTER_EPISODE_TYPES,
    FREQUENCY_PARAMS,
    FREQUENCY_PRESETS,
    OutputPlatformConfig,
    passes_content_filter,
    resolve_platform,
)
from social_hook.config.yaml import SchedulingConfig
from social_hook.errors import ConfigError


@pytest.fixture
def global_scheduling():
    """Default global scheduling config for resolve_platform tests."""
    return SchedulingConfig()


class TestOutputPlatformConfigDefaults:
    """Verify OutputPlatformConfig default values."""

    def test_output_platform_config_defaults(self):
        cfg = OutputPlatformConfig()
        assert cfg.enabled is False
        assert cfg.priority == "secondary"
        assert cfg.type == "builtin"
        assert cfg.account_tier is None
        assert cfg.description is None
        assert cfg.format is None
        assert cfg.max_length is None
        assert cfg.filter is None
        assert cfg.frequency is None
        assert cfg.scheduling is None


class TestResolvePlatform:
    """Test resolve_platform() smart default resolution."""

    def test_resolve_x_primary(self, global_scheduling):
        raw = OutputPlatformConfig(enabled=True, priority="primary", type="builtin")
        resolved = resolve_platform("x", raw, global_scheduling)
        assert resolved.filter == "all"
        assert resolved.frequency == "high"
        assert resolved.max_posts_per_day == 3
        assert resolved.min_gap_minutes == 30

    def test_resolve_x_secondary(self, global_scheduling):
        raw = OutputPlatformConfig(enabled=True, priority="secondary", type="builtin")
        resolved = resolve_platform("x", raw, global_scheduling)
        assert resolved.filter == "notable"
        assert resolved.frequency == "moderate"
        assert resolved.max_posts_per_day == 1
        assert resolved.min_gap_minutes == 120

    def test_resolve_linkedin_primary(self, global_scheduling):
        raw = OutputPlatformConfig(enabled=True, priority="primary", type="builtin")
        resolved = resolve_platform("linkedin", raw, global_scheduling)
        assert resolved.filter == "notable"
        assert resolved.frequency == "moderate"

    def test_resolve_linkedin_secondary(self, global_scheduling):
        raw = OutputPlatformConfig(enabled=True, priority="secondary", type="builtin")
        resolved = resolve_platform("linkedin", raw, global_scheduling)
        assert resolved.filter == "significant"
        assert resolved.frequency == "low"

    def test_resolve_custom_primary(self, global_scheduling):
        raw = OutputPlatformConfig(enabled=True, priority="primary", type="custom")
        resolved = resolve_platform("blog", raw, global_scheduling)
        assert resolved.filter == "notable"
        assert resolved.frequency == "moderate"

    def test_resolve_custom_secondary(self, global_scheduling):
        raw = OutputPlatformConfig(enabled=True, priority="secondary", type="custom")
        resolved = resolve_platform("newsletter", raw, global_scheduling)
        assert resolved.filter == "significant"
        assert resolved.frequency == "low"

    def test_resolve_explicit_filter_overrides_default(self, global_scheduling):
        """User sets filter=all on secondary -- it sticks, not overridden by smart default."""
        raw = OutputPlatformConfig(
            enabled=True,
            priority="secondary",
            type="builtin",
            filter="all",
        )
        resolved = resolve_platform("x", raw, global_scheduling)
        assert resolved.filter == "all"  # User override, not "notable"

    def test_resolve_explicit_frequency_overrides_default(self, global_scheduling):
        """User sets frequency=high on secondary -- it sticks."""
        raw = OutputPlatformConfig(
            enabled=True,
            priority="secondary",
            type="builtin",
            frequency="high",
        )
        resolved = resolve_platform("x", raw, global_scheduling)
        assert resolved.frequency == "high"
        assert resolved.max_posts_per_day == 3  # From high preset

    def test_resolve_scheduling_override(self, global_scheduling):
        """Per-platform scheduling overrides frequency preset defaults."""
        raw = OutputPlatformConfig(
            enabled=True,
            priority="primary",
            type="builtin",
            scheduling={"max_posts_per_day": 5, "min_gap_minutes": 15},
        )
        resolved = resolve_platform("x", raw, global_scheduling)
        assert resolved.max_posts_per_day == 5
        assert resolved.min_gap_minutes == 15
        # optimal_days/hours fall back to global
        assert resolved.optimal_days == global_scheduling.optimal_days
        assert resolved.optimal_hours == global_scheduling.optimal_hours

    def test_resolve_preserves_identity_fields(self, global_scheduling):
        """Resolved config preserves name, enabled, type, account_tier, etc."""
        raw = OutputPlatformConfig(
            enabled=True,
            priority="primary",
            type="custom",
            account_tier=None,
            description="My blog",
            format="article",
            max_length=5000,
        )
        resolved = resolve_platform("blog", raw, global_scheduling)
        assert resolved.name == "blog"
        assert resolved.enabled is True
        assert resolved.type == "custom"
        assert resolved.description == "My blog"
        assert resolved.format == "article"
        assert resolved.max_length == 5000


class TestConstants:
    """Verify constant mappings are consistent."""

    def test_frequency_params_mapping(self):
        """All frequency presets map to valid params."""
        for preset in FREQUENCY_PRESETS:
            params = FREQUENCY_PARAMS[preset]
            assert "max_posts_per_day" in params
            assert "min_gap_minutes" in params
            assert isinstance(params["max_posts_per_day"], int)
            assert isinstance(params["min_gap_minutes"], int)

    def test_filter_episode_types_mapping(self):
        """All filters have correct episode sets."""
        assert FILTER_EPISODE_TYPES["all"] is None
        assert "milestone" in FILTER_EPISODE_TYPES["notable"]
        assert "launch" in FILTER_EPISODE_TYPES["notable"]
        assert "decision" not in FILTER_EPISODE_TYPES["notable"]
        assert FILTER_EPISODE_TYPES["significant"] == {"milestone", "launch", "synthesis"}


class TestValidation:
    """Test validation errors for invalid values."""

    def test_invalid_priority_raises(self, global_scheduling):
        raw = OutputPlatformConfig(enabled=True, priority="tertiary")
        with pytest.raises(ConfigError, match="Invalid priority 'tertiary'"):
            resolve_platform("x", raw, global_scheduling)

    def test_invalid_filter_raises(self, global_scheduling):
        raw = OutputPlatformConfig(enabled=True, priority="primary", filter="extreme")
        with pytest.raises(ConfigError, match="Invalid filter 'extreme'"):
            resolve_platform("x", raw, global_scheduling)

    def test_invalid_frequency_raises(self, global_scheduling):
        raw = OutputPlatformConfig(enabled=True, priority="primary", frequency="ultra")
        with pytest.raises(ConfigError, match="Invalid frequency 'ultra'"):
            resolve_platform("x", raw, global_scheduling)


class TestPassesContentFilter:
    """Test passes_content_filter() function."""

    def test_passes_content_filter(self):
        # "all" filter passes everything
        assert passes_content_filter("all", "decision") is True
        assert passes_content_filter("all", "milestone") is True
        assert passes_content_filter("all", None) is True

        # "notable" filter
        assert passes_content_filter("notable", "milestone") is True
        assert passes_content_filter("notable", "launch") is True
        assert passes_content_filter("notable", "synthesis") is True
        assert passes_content_filter("notable", "demo_proof") is True
        assert passes_content_filter("notable", "before_after") is True
        assert passes_content_filter("notable", "postmortem") is True
        assert passes_content_filter("notable", "decision") is False

        # "significant" filter
        assert passes_content_filter("significant", "milestone") is True
        assert passes_content_filter("significant", "launch") is True
        assert passes_content_filter("significant", "synthesis") is True
        assert passes_content_filter("significant", "demo_proof") is False
        assert passes_content_filter("significant", "decision") is False

        # None episode_type
        assert passes_content_filter("notable", None) is False
        assert passes_content_filter("significant", None) is False
