"""Tests for config/targets.py — dataclasses and validation (Chunk 1)."""

import pytest

from social_hook.config.targets import (
    AccountConfig,
    PlatformCredentialConfig,
    PlatformSettingsConfig,
    TargetConfig,
    validate_targets_config,
)
from social_hook.config.yaml import Config, ContentStrategyConfig, IdentityConfig
from social_hook.errors import ConfigError


def _make_config(**overrides) -> Config:
    """Build a Config with sensible defaults for targets validation tests."""
    defaults = dict(
        identities={"dev": IdentityConfig(type="myself", label="Dev")},
        default_identity="dev",
        content_strategies={
            "building-public": ContentStrategyConfig(audience="developers"),
        },
        platform_credentials={
            "x-app": PlatformCredentialConfig(platform="x"),
        },
        accounts={
            "my-x": AccountConfig(platform="x", identity="dev"),
        },
        targets={
            "main-feed": TargetConfig(
                account="my-x",
                strategy="building-public",
                primary=True,
            ),
        },
        max_targets=3,
    )
    defaults.update(overrides)
    return Config(**defaults)


class TestDataclassDefaults:
    """Test that dataclass defaults are correct."""

    def test_platform_credential_defaults(self):
        pc = PlatformCredentialConfig(platform="x")
        assert pc.platform == "x"
        assert pc.client_id == ""
        assert pc.client_secret == ""

    def test_account_defaults(self):
        acct = AccountConfig(platform="x")
        assert acct.platform == "x"
        assert acct.app is None
        assert acct.tier is None
        assert acct.identity is None
        assert acct.entity is None

    def test_target_defaults(self):
        tgt = TargetConfig(account="my-x")
        assert tgt.account == "my-x"
        assert tgt.destination == "timeline"
        assert tgt.strategy == ""
        assert tgt.primary is False
        assert tgt.source is None
        assert tgt.community_id is None
        assert tgt.share_with_followers is False
        assert tgt.frequency is None
        assert tgt.scheduling is None

    def test_platform_settings_defaults(self):
        ps = PlatformSettingsConfig()
        assert ps.cross_account_gap_minutes == 0


class TestValidTargetsConfig:
    """Test that valid configs pass validation."""

    def test_valid_config_passes(self):
        config = _make_config()
        # Should not raise
        validate_targets_config(config)

    def test_empty_config_skips_validation(self):
        config = Config()
        # Should not raise — no accounts/targets means skip
        validate_targets_config(config)

    def test_multiple_targets_valid(self):
        config = _make_config(
            accounts={
                "my-x": AccountConfig(platform="x", identity="dev"),
                "my-linkedin": AccountConfig(platform="linkedin", identity="dev"),
            },
            targets={
                "x-feed": TargetConfig(
                    account="my-x",
                    strategy="building-public",
                    primary=True,
                ),
                "linkedin-feed": TargetConfig(
                    account="my-linkedin",
                    strategy="building-public",
                    primary=True,
                ),
            },
        )
        validate_targets_config(config)


class TestAccountRefValidation:
    """Test target -> account reference validation."""

    def test_unknown_account_raises(self):
        config = _make_config(
            targets={
                "bad-target": TargetConfig(
                    account="nonexistent",
                    strategy="building-public",
                ),
            },
        )
        with pytest.raises(ConfigError, match="unknown account 'nonexistent'"):
            validate_targets_config(config)


class TestIdentityRefValidation:
    """Test account -> identity reference validation."""

    def test_unknown_identity_raises(self):
        config = _make_config(
            accounts={
                "my-x": AccountConfig(platform="x", identity="ghost"),
            },
        )
        with pytest.raises(ConfigError, match="unknown identity 'ghost'"):
            validate_targets_config(config)

    def test_none_identity_ok(self):
        config = _make_config(
            accounts={
                "my-x": AccountConfig(platform="x", identity=None),
            },
        )
        validate_targets_config(config)


class TestStrategyRefValidation:
    """Test target -> strategy reference validation."""

    def test_empty_strategy_raises(self):
        config = _make_config(
            targets={
                "bad": TargetConfig(account="my-x", strategy=""),
            },
        )
        with pytest.raises(ConfigError, match="empty strategy"):
            validate_targets_config(config)

    def test_unknown_strategy_raises(self):
        config = _make_config(
            targets={
                "bad": TargetConfig(account="my-x", strategy="nonexistent"),
            },
        )
        with pytest.raises(ConfigError, match="unknown strategy 'nonexistent'"):
            validate_targets_config(config)


class TestSourceRefValidation:
    """Test source chain and circular dependency detection."""

    def test_unknown_source_raises(self):
        config = _make_config(
            targets={
                "a": TargetConfig(
                    account="my-x",
                    strategy="building-public",
                    source="nonexistent",
                ),
            },
        )
        with pytest.raises(ConfigError, match="unknown source target"):
            validate_targets_config(config)

    def test_circular_dependency_raises(self):
        config = _make_config(
            targets={
                "a": TargetConfig(
                    account="my-x",
                    strategy="building-public",
                    source="b",
                ),
                "b": TargetConfig(
                    account="my-x",
                    strategy="building-public",
                    source="a",
                ),
            },
        )
        with pytest.raises(ConfigError, match="Circular dependency"):
            validate_targets_config(config)

    def test_valid_source_chain(self):
        config = _make_config(
            targets={
                "a": TargetConfig(
                    account="my-x",
                    strategy="building-public",
                    primary=True,
                ),
                "b": TargetConfig(
                    account="my-x",
                    strategy="building-public",
                    source="a",
                ),
            },
        )
        validate_targets_config(config)


class TestPrimaryValidation:
    """Test at-most-one primary per platform."""

    def test_two_primaries_same_platform_raises(self):
        config = _make_config(
            targets={
                "a": TargetConfig(
                    account="my-x",
                    strategy="building-public",
                    primary=True,
                ),
                "b": TargetConfig(
                    account="my-x",
                    strategy="building-public",
                    primary=True,
                ),
            },
        )
        with pytest.raises(ConfigError, match="Multiple primary targets"):
            validate_targets_config(config)

    def test_primaries_different_platforms_ok(self):
        config = _make_config(
            accounts={
                "my-x": AccountConfig(platform="x", identity="dev"),
                "my-li": AccountConfig(platform="linkedin", identity="dev"),
            },
            targets={
                "a": TargetConfig(
                    account="my-x",
                    strategy="building-public",
                    primary=True,
                ),
                "b": TargetConfig(
                    account="my-li",
                    strategy="building-public",
                    primary=True,
                ),
            },
        )
        validate_targets_config(config)


class TestCommunityValidation:
    """Test community_id required for community destination."""

    def test_community_without_id_raises(self):
        config = _make_config(
            targets={
                "comm": TargetConfig(
                    account="my-x",
                    strategy="building-public",
                    destination="community",
                ),
            },
        )
        with pytest.raises(ConfigError, match="no community_id"):
            validate_targets_config(config)

    def test_community_with_id_ok(self):
        config = _make_config(
            targets={
                "comm": TargetConfig(
                    account="my-x",
                    strategy="building-public",
                    destination="community",
                    community_id="12345",
                ),
            },
        )
        validate_targets_config(config)


class TestMaxTargetsValidation:
    """Test max_targets limit enforcement."""

    def test_exceeding_max_targets_raises(self):
        targets = {}
        for i in range(4):
            targets[f"t{i}"] = TargetConfig(
                account="my-x",
                strategy="building-public",
            )
        config = _make_config(targets=targets, max_targets=3)
        with pytest.raises(ConfigError, match="Too many targets"):
            validate_targets_config(config)


class TestFrequencyValidation:
    """Test frequency field validation."""

    def test_invalid_frequency_raises(self):
        config = _make_config(
            targets={
                "bad": TargetConfig(
                    account="my-x",
                    strategy="building-public",
                    frequency="invalid",
                ),
            },
        )
        with pytest.raises(ConfigError, match="invalid frequency"):
            validate_targets_config(config)

    def test_valid_frequency_ok(self):
        config = _make_config(
            targets={
                "ok": TargetConfig(
                    account="my-x",
                    strategy="building-public",
                    frequency="moderate",
                ),
            },
        )
        validate_targets_config(config)


class TestDestinationValidation:
    """Test destination field validation."""

    def test_invalid_destination_raises(self):
        config = _make_config(
            targets={
                "bad": TargetConfig(
                    account="my-x",
                    strategy="building-public",
                    destination="invalid",
                ),
            },
        )
        with pytest.raises(ConfigError, match="invalid destination"):
            validate_targets_config(config)


class TestContentStrategyConfigBackwardCompat:
    """Test that ContentStrategyConfig new fields default to None."""

    def test_old_style_strategy_still_works(self):
        cs = ContentStrategyConfig(
            audience="devs",
            voice="casual",
            post_when="interesting commits",
            avoid="marketing speak",
        )
        assert cs.angle is None
        assert cs.format_preference is None
        assert cs.media_preference is None
        assert cs.min_length is None
        assert cs.requires is None

    def test_full_strategy(self):
        cs = ContentStrategyConfig(
            audience="devs",
            voice="casual",
            angle="behind-the-scenes",
            post_when="interesting commits",
            avoid="marketing speak",
            format_preference="thread",
            media_preference="screenshot",
            min_length=100,
            requires=["playwright"],
        )
        assert cs.angle == "behind-the-scenes"
        assert cs.format_preference == "thread"
        assert cs.media_preference == "screenshot"
        assert cs.min_length == 100
        assert cs.requires == ["playwright"]
