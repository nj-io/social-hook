"""Tests for X tier system configuration (Phase A)."""

import pytest

from social_hook.config.yaml import (
    TIER_CHAR_LIMITS,
    VALID_TIERS,
    load_config,
)
from social_hook.errors import ConfigError


class TestTierConstants:
    """Tier constants and char limit mapping."""

    def test_valid_tiers_includes_all_four(self):
        """All four X tiers are valid."""
        assert "free" in VALID_TIERS
        assert "basic" in VALID_TIERS
        assert "premium" in VALID_TIERS
        assert "premium_plus" in VALID_TIERS

    def test_valid_tiers_count(self):
        assert len(VALID_TIERS) == 4

    def test_free_tier_limit(self):
        assert TIER_CHAR_LIMITS["free"] == 280

    def test_basic_tier_limit(self):
        assert TIER_CHAR_LIMITS["basic"] == 25_000

    def test_premium_tier_limit(self):
        assert TIER_CHAR_LIMITS["premium"] == 25_000

    def test_premium_plus_tier_limit(self):
        assert TIER_CHAR_LIMITS["premium_plus"] == 25_000

    def test_all_tiers_have_limits(self):
        """Every valid tier has a char limit entry."""
        for tier in VALID_TIERS:
            assert tier in TIER_CHAR_LIMITS


class TestTierValidation:
    """Config parsing validates tier values."""

    def test_invalid_tier_raises_config_error(self, temp_dir):
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            "platforms:\n  x:\n    account_tier: ultra_premium\n"
        )
        with pytest.raises(ConfigError, match="Invalid account_tier"):
            load_config(config_path)

    def test_basic_tier_accepted(self, temp_dir):
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            "platforms:\n  x:\n    account_tier: basic\n"
        )
        config = load_config(config_path)
        assert config.platforms.x.account_tier == "basic"

    def test_premium_tier_accepted(self, temp_dir):
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            "platforms:\n  x:\n    account_tier: premium\n"
        )
        config = load_config(config_path)
        assert config.platforms.x.account_tier == "premium"

    def test_premium_plus_tier_accepted(self, temp_dir):
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            "platforms:\n  x:\n    account_tier: premium_plus\n"
        )
        config = load_config(config_path)
        assert config.platforms.x.account_tier == "premium_plus"

    def test_free_tier_accepted(self, temp_dir):
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            "platforms:\n  x:\n    account_tier: free\n"
        )
        config = load_config(config_path)
        assert config.platforms.x.account_tier == "free"

    def test_default_tier_is_free(self):
        config = load_config(None)
        assert config.platforms.x.account_tier == "free"
