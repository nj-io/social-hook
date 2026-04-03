"""Tests for targets config parsing in yaml.py (Chunk 2)."""

from pathlib import Path

import pytest
import yaml

from social_hook.config.yaml import (
    Config,
    load_config,
    save_config,
)
from social_hook.errors import ConfigError


def _write_config(tmp_path: Path, data: dict) -> Path:
    """Write a config dict to a YAML file and return the path."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(data, default_flow_style=False))
    return config_path


FULL_TARGETS_CONFIG = {
    "models": {
        "evaluator": "anthropic/claude-opus-4-5",
        "drafter": "anthropic/claude-sonnet-4-5",
        "gatekeeper": "anthropic/claude-haiku-4-5",
    },
    "identities": {
        "dev": {"type": "myself", "label": "Developer"},
    },
    "default_identity": "dev",
    "content_strategies": {
        "building-public": {
            "audience": "developers",
            "voice": "casual",
            "angle": "behind-the-scenes",
            "post_when": "interesting commits",
            "avoid": "marketing",
            "format_preference": "single",
            "media_preference": "screenshot",
            "min_length": 100,
            "requires": ["playwright"],
        },
    },
    "platform_credentials": {
        "x-app": {
            "platform": "x",
            "client_id": "test-id",
            "client_secret": "test-secret",
        },
    },
    "accounts": {
        "my-x": {
            "platform": "x",
            "app": "x-app",
            "tier": "basic",
            "identity": "dev",
        },
    },
    "targets": {
        "main-feed": {
            "account": "my-x",
            "destination": "timeline",
            "strategy": "building-public",
            "primary": True,
            "frequency": "high",
        },
    },
    "platform_settings": {
        "x": {
            "cross_account_gap_minutes": 15,
        },
    },
    "max_targets": 5,
}


class TestRoundTrip:
    """Test writing and loading config preserves all fields."""

    def test_full_config_round_trip(self, tmp_path):
        config_path = _write_config(tmp_path, FULL_TARGETS_CONFIG)
        config = load_config(config_path)

        # Platform credentials
        assert "x-app" in config.platform_credentials
        pc = config.platform_credentials["x-app"]
        assert pc.platform == "x"
        assert pc.client_id == "test-id"
        assert pc.client_secret == "test-secret"

        # Accounts
        assert "my-x" in config.accounts
        acct = config.accounts["my-x"]
        assert acct.platform == "x"
        assert acct.app == "x-app"
        assert acct.tier == "basic"
        assert acct.identity == "dev"

        # Targets
        assert "main-feed" in config.targets
        tgt = config.targets["main-feed"]
        assert tgt.account == "my-x"
        assert tgt.destination == "timeline"
        assert tgt.strategy == "building-public"
        assert tgt.primary is True
        assert tgt.frequency == "high"

        # Platform settings
        assert "x" in config.platform_settings
        assert config.platform_settings["x"].cross_account_gap_minutes == 15

        # Max targets
        assert config.max_targets == 5

        # Strategy expanded fields
        cs = config.content_strategies["building-public"]
        assert cs.angle == "behind-the-scenes"
        assert cs.format_preference == "single"
        assert cs.media_preference == "screenshot"
        assert cs.min_length == 100
        assert cs.requires == ["playwright"]


class TestExplicitTargetsConfig:
    """Test that explicit accounts/targets config is used as-is."""

    def test_explicit_accounts_used(self, tmp_path):
        """When accounts: section exists, no auto-migration happens."""
        config_data = {
            "models": {
                "evaluator": "anthropic/claude-opus-4-5",
                "drafter": "anthropic/claude-sonnet-4-5",
                "gatekeeper": "anthropic/claude-haiku-4-5",
            },
            "platforms": {
                "x": {"enabled": True, "priority": "primary"},
            },
            "identities": {"dev": {"type": "myself", "label": "Dev"}},
            "content_strategies": {
                "bp": {"audience": "devs"},
            },
            "accounts": {
                "custom-x": {"platform": "x", "identity": "dev"},
            },
            "targets": {
                "my-feed": {
                    "account": "custom-x",
                    "strategy": "bp",
                    "primary": True,
                },
            },
        }
        config_path = _write_config(tmp_path, config_data)
        config = load_config(config_path)

        # Should have the explicit accounts, not auto-migrated
        assert "custom-x" in config.accounts
        assert "x" not in config.accounts


class TestMixedFormat:
    """Test configs with both old and new format sections."""

    def test_platforms_plus_explicit_targets(self, tmp_path):
        """Old platforms config coexists with new targets config."""
        config_data = {
            "models": {
                "evaluator": "anthropic/claude-opus-4-5",
                "drafter": "anthropic/claude-sonnet-4-5",
                "gatekeeper": "anthropic/claude-haiku-4-5",
            },
            "platforms": {
                "x": {"enabled": True, "priority": "primary", "account_tier": "free"},
            },
            "identities": {"dev": {"type": "myself", "label": "Dev"}},
            "content_strategies": {
                "bp": {"audience": "devs"},
            },
            "accounts": {
                "my-x": {"platform": "x", "identity": "dev"},
            },
            "targets": {
                "feed": {
                    "account": "my-x",
                    "strategy": "bp",
                    "primary": True,
                },
            },
        }
        config_path = _write_config(tmp_path, config_data)
        config = load_config(config_path)

        # platforms still parsed
        assert "x" in config.platforms
        assert config.platforms["x"].enabled is True

        # explicit accounts/targets used (not auto-migrated)
        assert "my-x" in config.accounts
        assert "feed" in config.targets


class TestSaveConfig:
    """Test save_config with new sections."""

    def test_save_new_sections(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        # Start with a base config
        base = {
            "models": {
                "evaluator": "anthropic/claude-opus-4-5",
                "drafter": "anthropic/claude-sonnet-4-5",
                "gatekeeper": "anthropic/claude-haiku-4-5",
            },
            "identities": {"dev": {"type": "myself", "label": "Dev"}},
            "content_strategies": {"bp": {"audience": "devs"}},
        }
        config_path.write_text(yaml.dump(base))

        # Add new sections
        updates = {
            "platform_credentials": {
                "x-app": {"platform": "x", "client_id": "id123"},
            },
            "accounts": {
                "my-x": {"platform": "x", "identity": "dev"},
            },
            "targets": {
                "feed": {
                    "account": "my-x",
                    "strategy": "bp",
                    "primary": True,
                },
            },
        }
        save_config(updates, config_path)

        # Reload and verify
        config = load_config(config_path)
        assert "x-app" in config.platform_credentials
        assert "my-x" in config.accounts
        assert "feed" in config.targets


class TestParsingErrors:
    """Test that invalid configs produce clear errors."""

    def test_account_missing_platform(self, tmp_path):
        config_data = {
            "models": {
                "evaluator": "anthropic/claude-opus-4-5",
                "drafter": "anthropic/claude-sonnet-4-5",
                "gatekeeper": "anthropic/claude-haiku-4-5",
            },
            "accounts": {"bad": {"tier": "free"}},
        }
        config_path = _write_config(tmp_path, config_data)
        with pytest.raises(ConfigError, match="missing required field 'platform'"):
            load_config(config_path)

    def test_target_missing_account_and_platform(self, tmp_path):
        config_data = {
            "models": {
                "evaluator": "anthropic/claude-opus-4-5",
                "drafter": "anthropic/claude-sonnet-4-5",
                "gatekeeper": "anthropic/claude-haiku-4-5",
            },
            "targets": {"bad": {"strategy": "bp"}},
        }
        config_path = _write_config(tmp_path, config_data)
        with pytest.raises(ConfigError, match="must have either 'account' or 'platform'"):
            load_config(config_path)

    def test_credential_missing_platform(self, tmp_path):
        config_data = {
            "models": {
                "evaluator": "anthropic/claude-opus-4-5",
                "drafter": "anthropic/claude-sonnet-4-5",
                "gatekeeper": "anthropic/claude-haiku-4-5",
            },
            "platform_credentials": {"bad": {"client_id": "x"}},
        }
        config_path = _write_config(tmp_path, config_data)
        with pytest.raises(ConfigError, match="missing required field 'platform'"):
            load_config(config_path)

    def test_invalid_tier(self, tmp_path):
        config_data = {
            "models": {
                "evaluator": "anthropic/claude-opus-4-5",
                "drafter": "anthropic/claude-sonnet-4-5",
                "gatekeeper": "anthropic/claude-haiku-4-5",
            },
            "accounts": {"bad": {"platform": "x", "tier": "ultra"}},
        }
        config_path = _write_config(tmp_path, config_data)
        with pytest.raises(ConfigError, match="invalid tier 'ultra'"):
            load_config(config_path)

    def test_strategy_requires_not_list(self, tmp_path):
        config_data = {
            "models": {
                "evaluator": "anthropic/claude-opus-4-5",
                "drafter": "anthropic/claude-sonnet-4-5",
                "gatekeeper": "anthropic/claude-haiku-4-5",
            },
            "content_strategies": {
                "bad": {"requires": "playwright"},
            },
        }
        config_path = _write_config(tmp_path, config_data)
        with pytest.raises(ConfigError, match="requires must be a list"):
            load_config(config_path)

    def test_unknown_keys_in_account(self, tmp_path):
        """Unknown keys should trigger a warning (check_unknown_keys logs, doesn't raise)."""
        config_data = {
            "models": {
                "evaluator": "anthropic/claude-opus-4-5",
                "drafter": "anthropic/claude-sonnet-4-5",
                "gatekeeper": "anthropic/claude-haiku-4-5",
            },
            "accounts": {
                "my-x": {"platform": "x", "bogus_field": True},
            },
        }
        config_path = _write_config(tmp_path, config_data)
        # check_unknown_keys logs a warning but doesn't raise by default
        config = load_config(config_path)
        assert "my-x" in config.accounts


class TestOptionalDefaults:
    """Test that missing optional fields default correctly."""

    def test_empty_sections_default(self, tmp_path):
        """Config with no targets/accounts sections has empty dicts."""
        config_data = {
            "models": {
                "evaluator": "anthropic/claude-opus-4-5",
                "drafter": "anthropic/claude-sonnet-4-5",
                "gatekeeper": "anthropic/claude-haiku-4-5",
            },
        }
        config_path = _write_config(tmp_path, config_data)
        config = load_config(config_path)

        assert config.platform_credentials == {}
        assert config.accounts == {}
        assert config.targets == {}
        assert config.platform_settings == {}
        assert config.max_targets == 3

    def test_default_max_targets(self):
        config = Config()
        assert config.max_targets == 3

    def test_target_optional_fields(self, tmp_path):
        config_data = {
            "models": {
                "evaluator": "anthropic/claude-opus-4-5",
                "drafter": "anthropic/claude-sonnet-4-5",
                "gatekeeper": "anthropic/claude-haiku-4-5",
            },
            "identities": {"dev": {"type": "myself", "label": "Dev"}},
            "content_strategies": {"bp": {"audience": "devs"}},
            "accounts": {"my-x": {"platform": "x", "identity": "dev"}},
            "targets": {
                "feed": {
                    "account": "my-x",
                    "strategy": "bp",
                },
            },
        }
        config_path = _write_config(tmp_path, config_data)
        config = load_config(config_path)
        tgt = config.targets["feed"]
        assert tgt.destination == "timeline"
        assert tgt.primary is False
        assert tgt.source is None
        assert tgt.community_id is None
        assert tgt.share_with_followers is False
        assert tgt.frequency is None
        assert tgt.scheduling is None


class TestContextConfigCommitAnalysisInterval:
    """Test that commit_analysis_interval is parsed from context config."""

    def test_default_value(self):
        from social_hook.config.project import ContextConfig

        ctx = ContextConfig()
        assert ctx.commit_analysis_interval == 1

    def test_parsed_from_yaml(self, tmp_path):
        from social_hook.config.project import load_project_config

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        config_dir = project_dir / ".social-hook"
        config_dir.mkdir()
        (config_dir / "content-config.yaml").write_text(
            yaml.dump({"context": {"commit_analysis_interval": 3}})
        )
        pc = load_project_config(project_dir)
        assert pc.context.commit_analysis_interval == 3
