"""Tests for journey_capture config and narratives filesystem."""

import pytest

from social_hook.config.yaml import JourneyCaptureConfig, load_config
from social_hook.errors import ConfigError
from social_hook.filesystem import get_narratives_path, init_filesystem


class TestJourneyCaptureConfig:
    """Journey capture configuration parsing tests."""

    def test_config_with_journey_capture_section(self, temp_dir):
        """Config with journey_capture section parses correctly."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            """\
journey_capture:
  enabled: true
  model: anthropic/claude-sonnet-4-5
"""
        )

        config = load_config(config_path)

        assert config.journey_capture.enabled is True
        assert config.journey_capture.model == "anthropic/claude-sonnet-4-5"

    def test_config_defaults_when_section_absent(self, temp_dir):
        """Config defaults when journey_capture section is absent."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            """\
models:
  evaluator: anthropic/claude-opus-4-5
"""
        )

        config = load_config(config_path)

        assert config.journey_capture.enabled is False
        assert config.journey_capture.model is None

    def test_default_config_has_journey_capture(self):
        """Default Config() includes journey_capture with defaults."""
        config = load_config(None)

        assert config.journey_capture.enabled is False
        assert config.journey_capture.model is None

    def test_model_none_default(self):
        """JourneyCaptureConfig with model=None uses default."""
        jc = JourneyCaptureConfig()

        assert jc.enabled is False
        assert jc.model is None

    def test_valid_model_string_passes(self, temp_dir):
        """Valid provider/model-id string passes validation."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            """\
journey_capture:
  enabled: true
  model: claude-cli/sonnet
"""
        )

        config = load_config(config_path)

        assert config.journey_capture.model == "claude-cli/sonnet"

    def test_invalid_model_string_raises(self, temp_dir):
        """Invalid model string (bare name) raises ConfigError."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            """\
journey_capture:
  enabled: true
  model: sonnet
"""
        )

        with pytest.raises(ConfigError) as exc_info:
            load_config(config_path)

        assert "Invalid model 'sonnet'" in str(exc_info.value)
        assert "journey_capture" in str(exc_info.value)

    def test_enabled_false_with_model(self, temp_dir):
        """journey_capture disabled but model set still parses."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            """\
journey_capture:
  enabled: false
  model: anthropic/claude-opus-4-5
"""
        )

        config = load_config(config_path)

        assert config.journey_capture.enabled is False
        assert config.journey_capture.model == "anthropic/claude-opus-4-5"


class TestNarrativesFilesystem:
    """Narratives directory filesystem tests."""

    def test_get_narratives_path(self):
        """get_narratives_path returns correct path."""
        path = get_narratives_path()

        assert path.name == "narratives"
        assert path.parent.name == ".social-hook"

    def test_init_filesystem_creates_narratives_dir(self, temp_dir):
        """init_filesystem creates narratives directory."""
        base = init_filesystem(temp_dir / ".social-hook")

        assert (base / "narratives").exists()
        assert (base / "narratives").is_dir()

    def test_init_filesystem_narratives_idempotent(self, temp_dir):
        """Running init_filesystem twice does not error on narratives dir."""
        base = temp_dir / ".social-hook"

        init_filesystem(base)
        init_filesystem(base)

        assert (base / "narratives").exists()

    def test_config_example_includes_journey_capture(self, temp_dir):
        """config.yaml.example includes journey_capture section."""
        base = init_filesystem(temp_dir / ".social-hook")

        config_example = (base / "config.yaml.example").read_text()

        assert "journey_capture:" in config_example
        assert "enabled: false" in config_example
