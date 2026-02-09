"""Tests for setup wizard (T22)."""

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from social_hook.setup.wizard import (
    _save_env,
    _validate_existing,
    _validate_not_empty,
    run_wizard,
)


class TestRunWizard:
    """Tests for run_wizard."""

    @patch("social_hook.setup.wizard._validate_existing")
    def test_validate_mode(self, mock_validate):
        mock_validate.return_value = True
        result = run_wizard(validate=True)
        assert result is True
        mock_validate.assert_called_once()

    @patch("social_hook.setup.wizard._show_summary")
    @patch("social_hook.setup.wizard._save_config_yaml")
    @patch("social_hook.setup.wizard._setup_installations")
    @patch("social_hook.setup.wizard._setup_scheduling")
    @patch("social_hook.setup.wizard._setup_image_gen")
    @patch("social_hook.setup.wizard._setup_models")
    @patch("social_hook.setup.wizard._setup_linkedin")
    @patch("social_hook.setup.wizard._setup_x")
    @patch("social_hook.setup.wizard._setup_telegram")
    @patch("social_hook.setup.wizard._setup_voice_style")
    @patch("social_hook.setup.wizard._setup_anthropic")
    @patch("social_hook.setup.wizard._save_env")
    @patch("social_hook.filesystem.init_filesystem")
    def test_full_wizard(self, mock_init, mock_save, mock_anthropic, mock_voice,
                         mock_telegram, mock_x, mock_linkedin, mock_models,
                         mock_image, mock_sched, mock_install, mock_yaml,
                         mock_summary):
        mock_init.return_value = Path("/tmp/test")
        result = run_wizard()
        assert result is True
        mock_init.assert_called_once()
        mock_voice.assert_called_once()
        mock_models.assert_called_once()
        mock_image.assert_called_once()

    @patch("social_hook.filesystem.init_filesystem")
    def test_keyboard_interrupt(self, mock_init):
        mock_init.side_effect = KeyboardInterrupt()
        result = run_wizard()
        assert result is False

    @patch("social_hook.setup.wizard._setup_anthropic")
    @patch("social_hook.setup.wizard._save_env")
    @patch("social_hook.filesystem.init_filesystem")
    def test_only_anthropic(self, mock_init, mock_save, mock_anthropic):
        mock_init.return_value = Path("/tmp/test")
        result = run_wizard(only="anthropic")
        assert result is True
        mock_anthropic.assert_called_once()

    @patch("social_hook.setup.wizard._setup_voice_style")
    @patch("social_hook.setup.wizard._save_env")
    @patch("social_hook.filesystem.init_filesystem")
    def test_only_voice(self, mock_init, mock_save, mock_voice):
        mock_init.return_value = Path("/tmp/test")
        result = run_wizard(only="voice")
        assert result is True
        mock_voice.assert_called_once()

    @patch("social_hook.setup.wizard._setup_models")
    @patch("social_hook.setup.wizard._save_env")
    @patch("social_hook.filesystem.init_filesystem")
    def test_only_models(self, mock_init, mock_save, mock_models):
        mock_init.return_value = Path("/tmp/test")
        result = run_wizard(only="models")
        assert result is True
        mock_models.assert_called_once()

    @patch("social_hook.setup.wizard._setup_image_gen")
    @patch("social_hook.setup.wizard._save_env")
    @patch("social_hook.filesystem.init_filesystem")
    def test_only_image(self, mock_init, mock_save, mock_image):
        mock_init.return_value = Path("/tmp/test")
        result = run_wizard(only="image")
        assert result is True
        mock_image.assert_called_once()


class TestWelcomePanel:
    """Tests for welcome panel rendering."""

    @patch("social_hook.setup.wizard._show_summary")
    @patch("social_hook.setup.wizard._save_config_yaml")
    @patch("social_hook.setup.wizard._setup_installations")
    @patch("social_hook.setup.wizard._setup_scheduling")
    @patch("social_hook.setup.wizard._setup_image_gen")
    @patch("social_hook.setup.wizard._setup_models")
    @patch("social_hook.setup.wizard._setup_linkedin")
    @patch("social_hook.setup.wizard._setup_x")
    @patch("social_hook.setup.wizard._setup_telegram")
    @patch("social_hook.setup.wizard._setup_voice_style")
    @patch("social_hook.setup.wizard._setup_anthropic")
    @patch("social_hook.setup.wizard._save_env")
    @patch("social_hook.filesystem.init_filesystem")
    def test_welcome_panel_renders(self, mock_init, mock_save, *mocks):
        """Welcome panel renders without error."""
        mock_init.return_value = Path("/tmp/test")
        result = run_wizard()
        assert result is True

    @patch("social_hook.setup.wizard._setup_installations")
    @patch("social_hook.setup.wizard._setup_scheduling")
    @patch("social_hook.setup.wizard._setup_image_gen")
    @patch("social_hook.setup.wizard._setup_models")
    @patch("social_hook.setup.wizard._setup_linkedin")
    @patch("social_hook.setup.wizard._setup_x")
    @patch("social_hook.setup.wizard._setup_telegram")
    @patch("social_hook.setup.wizard._setup_voice_style")
    @patch("social_hook.setup.wizard._setup_anthropic")
    @patch("social_hook.setup.wizard._save_env")
    @patch("social_hook.filesystem.init_filesystem")
    def test_welcome_fallback_on_import_error(self, mock_init, mock_save, *mocks):
        """Falls back to plain text if Rich not available."""
        mock_init.return_value = Path("/tmp/test")
        with patch.dict("sys.modules", {"rich.console": None, "rich.panel": None}):
            # Should not raise (falls back to plain echo)
            result = run_wizard()
            assert result is True


class TestValidateNotEmpty:
    """Tests for _validate_not_empty input validator."""

    def test_rejects_empty_string(self):
        result = _validate_not_empty("")
        assert result != True
        assert "empty" in result.lower()

    def test_rejects_whitespace(self):
        result = _validate_not_empty("   ")
        assert result != True

    def test_rejects_single_y(self):
        result = _validate_not_empty("y")
        assert result != True
        assert "y" in result.lower() or "n" in result.lower()

    def test_rejects_single_n(self):
        result = _validate_not_empty("n")
        assert result != True

    def test_accepts_valid_input(self):
        assert _validate_not_empty("sk-ant-abc123") is True

    def test_accepts_short_valid_input(self):
        assert _validate_not_empty("ok") is True


class TestVoiceStyleStep:
    """Tests for _setup_voice_style."""

    @patch("social_hook.setup.wizard._prompt")
    @patch("social_hook.setup.wizard._confirm")
    def test_creates_social_context_md(self, mock_confirm, mock_prompt, temp_dir):
        from social_hook.setup.wizard import _setup_voice_style

        mock_confirm.return_value = True
        mock_prompt.side_effect = ["Witty and technical", "Developers", "Python, AI", "Buzzwords"]

        _setup_voice_style(temp_dir)

        context_path = temp_dir / "social-context.md"
        assert context_path.exists()
        content = context_path.read_text()
        assert "Witty and technical" in content
        assert "Developers" in content
        assert "Python, AI" in content
        assert "Buzzwords" in content

    @patch("social_hook.setup.wizard._confirm")
    def test_skips_when_declined(self, mock_confirm, temp_dir):
        from social_hook.setup.wizard import _setup_voice_style

        mock_confirm.return_value = False
        _setup_voice_style(temp_dir)

        context_path = temp_dir / "social-context.md"
        assert not context_path.exists()


class TestModelSelection:
    """Tests for _setup_models."""

    @patch("social_hook.setup.wizard._select")
    @patch("social_hook.setup.wizard._confirm")
    def test_default_models(self, mock_confirm, mock_select):
        from social_hook.setup.wizard import _setup_models

        mock_confirm.return_value = True
        mock_select.side_effect = ["claude-opus-4-5", "claude-opus-4-5", "claude-haiku-4-5"]

        yaml_config = {}
        _setup_models(yaml_config)

        assert yaml_config["models"]["evaluator"] == "claude-opus-4-5"
        assert yaml_config["models"]["drafter"] == "claude-opus-4-5"
        assert yaml_config["models"]["gatekeeper"] == "claude-haiku-4-5"

    @patch("social_hook.setup.wizard._confirm")
    def test_skips_when_declined(self, mock_confirm):
        from social_hook.setup.wizard import _setup_models

        mock_confirm.return_value = False
        yaml_config = {}
        _setup_models(yaml_config)

        assert "models" not in yaml_config


class TestXTierSelection:
    """Tests for X tier selection in _setup_x."""

    @patch("social_hook.setup.wizard._prompt")
    @patch("social_hook.setup.wizard._select")
    @patch("social_hook.setup.wizard._confirm")
    def test_stores_free_tier(self, mock_confirm, mock_select, mock_prompt):
        from social_hook.setup.wizard import _setup_x

        mock_confirm.return_value = True
        mock_prompt.side_effect = ["key", "secret", "token", "tsecret"]
        mock_select.return_value = "free (280 chars)"

        env_vars = {}
        yaml_config = {}
        _setup_x(env_vars, yaml_config)

        assert yaml_config["platforms"]["x"]["account_tier"] == "free"
        assert yaml_config["platforms"]["x"]["enabled"] is True

    @patch("social_hook.setup.wizard._prompt")
    @patch("social_hook.setup.wizard._select")
    @patch("social_hook.setup.wizard._confirm")
    def test_stores_premium_tier(self, mock_confirm, mock_select, mock_prompt):
        from social_hook.setup.wizard import _setup_x

        mock_confirm.return_value = True
        mock_prompt.side_effect = ["key", "secret", "token", "tsecret"]
        mock_select.return_value = "premium (25,000 chars)"

        env_vars = {}
        yaml_config = {}
        _setup_x(env_vars, yaml_config)

        assert yaml_config["platforms"]["x"]["account_tier"] == "premium"

    @patch("social_hook.setup.wizard._prompt")
    @patch("social_hook.setup.wizard._select")
    @patch("social_hook.setup.wizard._confirm")
    def test_stores_basic_tier(self, mock_confirm, mock_select, mock_prompt):
        from social_hook.setup.wizard import _setup_x

        mock_confirm.return_value = True
        mock_prompt.side_effect = ["key", "secret", "token", "tsecret"]
        mock_select.return_value = "basic (25,000 chars)"

        env_vars = {}
        yaml_config = {}
        _setup_x(env_vars, yaml_config)

        assert yaml_config["platforms"]["x"]["account_tier"] == "basic"

    @patch("social_hook.setup.wizard._prompt")
    @patch("social_hook.setup.wizard._select")
    @patch("social_hook.setup.wizard._confirm")
    def test_stores_premium_plus_tier(self, mock_confirm, mock_select, mock_prompt):
        from social_hook.setup.wizard import _setup_x

        mock_confirm.return_value = True
        mock_prompt.side_effect = ["key", "secret", "token", "tsecret"]
        mock_select.return_value = "premium_plus (25,000 chars)"

        env_vars = {}
        yaml_config = {}
        _setup_x(env_vars, yaml_config)

        assert yaml_config["platforms"]["x"]["account_tier"] == "premium_plus"


class TestImageGenStep:
    """Tests for _setup_image_gen."""

    @patch("social_hook.setup.wizard._spinner")
    @patch("social_hook.setup.wizard._prompt")
    @patch("social_hook.setup.wizard._select")
    @patch("social_hook.setup.wizard._confirm")
    def test_calls_validate_image_gen(self, mock_confirm, mock_select, mock_prompt, mock_spinner):
        from social_hook.setup.wizard import _setup_image_gen

        mock_confirm.return_value = True
        mock_select.return_value = "nano_banana_pro"
        mock_prompt.return_value = "gemini-key-123"
        mock_spinner.return_value = (True, "Connected")

        env_vars = {}
        yaml_config = {}
        _setup_image_gen(env_vars, yaml_config)

        assert yaml_config["image_generation"]["enabled"] is True
        assert yaml_config["image_generation"]["service"] == "nano_banana_pro"
        assert env_vars["GEMINI_API_KEY"] == "gemini-key-123"
        mock_spinner.assert_called_once()

    @patch("social_hook.setup.wizard._confirm")
    def test_disabled_when_declined(self, mock_confirm):
        from social_hook.setup.wizard import _setup_image_gen

        mock_confirm.return_value = False
        yaml_config = {}
        _setup_image_gen({}, yaml_config)

        assert yaml_config["image_generation"]["enabled"] is False


class TestTimezoneSelector:
    """Tests for timezone selector in scheduling."""

    @patch("social_hook.setup.wizard._prompt")
    @patch("social_hook.setup.wizard._select")
    def test_defaults_to_utc_on_detection_failure(self, mock_select, mock_prompt):
        from social_hook.setup.wizard import _setup_scheduling

        mock_select.return_value = "UTC"
        mock_prompt.side_effect = ["3", "30"]

        yaml_config = {}
        _setup_scheduling(Path("/tmp"), yaml_config)

        assert yaml_config["scheduling"]["timezone"] == "UTC"
        mock_select.assert_called_once()

    @patch("social_hook.setup.wizard._prompt")
    @patch("social_hook.setup.wizard._select")
    def test_system_tz_added_if_not_in_list(self, mock_select, mock_prompt):
        from social_hook.setup.wizard import _setup_scheduling, COMMON_TIMEZONES

        mock_select.return_value = "Asia/Kolkata"
        mock_prompt.side_effect = ["2", "60"]

        # zoneinfo is imported inside the function body, so we mock the module
        import zoneinfo as zi_mod
        original_zi = zi_mod.ZoneInfo
        try:
            zi_mod.ZoneInfo = lambda name: type("TZ", (), {"__str__": lambda self: "Asia/Kolkata"})()
            yaml_config = {}
            _setup_scheduling(Path("/tmp"), yaml_config)
        finally:
            zi_mod.ZoneInfo = original_zi

        assert yaml_config["scheduling"]["timezone"] == "Asia/Kolkata"


class TestSummaryTable:
    """Tests for _show_summary."""

    def test_renders_with_rich(self):
        from social_hook.setup.wizard import _show_summary

        env_vars = {"ANTHROPIC_API_KEY": "key", "TELEGRAM_BOT_TOKEN": "tok"}
        yaml_config = {
            "models": {"evaluator": "opus", "drafter": "opus"},
            "platforms": {"x": {"account_tier": "free"}},
            "scheduling": {"timezone": "UTC"},
        }
        # Should not raise
        _show_summary(env_vars, yaml_config)

    def test_renders_fallback_without_rich(self):
        from social_hook.setup.wizard import _show_summary

        env_vars = {"ANTHROPIC_API_KEY": "key"}
        yaml_config = {}

        with patch.dict("sys.modules", {"rich.console": None, "rich.table": None}):
            # Should not raise (falls back to plain echo)
            _show_summary(env_vars, yaml_config)


class TestSaveConfigYaml:
    """Tests for _save_config_yaml."""

    def test_saves_new_config(self, temp_dir):
        from social_hook.setup.wizard import _save_config_yaml

        yaml_config = {
            "platforms": {"x": {"enabled": True, "account_tier": "free"}},
            "models": {"evaluator": "opus"},
        }
        _save_config_yaml(temp_dir, yaml_config)

        config_path = temp_dir / "config.yaml"
        assert config_path.exists()
        import yaml
        loaded = yaml.safe_load(config_path.read_text())
        assert loaded["platforms"]["x"]["account_tier"] == "free"

    def test_merges_with_existing(self, temp_dir):
        import yaml

        config_path = temp_dir / "config.yaml"
        config_path.write_text(yaml.dump({"existing": "value", "platforms": {"x": {"enabled": True}}}))

        from social_hook.setup.wizard import _save_config_yaml

        _save_config_yaml(temp_dir, {"platforms": {"x": {"account_tier": "premium"}}})

        loaded = yaml.safe_load(config_path.read_text())
        assert loaded["existing"] == "value"
        assert loaded["platforms"]["x"]["account_tier"] == "premium"

    def test_noop_for_empty_config(self, temp_dir):
        from social_hook.setup.wizard import _save_config_yaml

        _save_config_yaml(temp_dir, {})
        config_path = temp_dir / "config.yaml"
        assert not config_path.exists()


class TestValidateExisting:
    """Tests for _validate_existing."""

    @patch("social_hook.filesystem.get_base_path")
    @patch("social_hook.config.load_full_config")
    def test_valid_config(self, mock_config, mock_base, temp_dir):
        env_file = temp_dir / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=test\nTELEGRAM_BOT_TOKEN=test\n")

        mock_base.return_value = temp_dir
        mock_config.return_value = MagicMock(
            env={"ANTHROPIC_API_KEY": "test", "TELEGRAM_BOT_TOKEN": "test"}
        )

        result = _validate_existing()
        assert result is True

    @patch("social_hook.config.load_full_config")
    def test_config_error(self, mock_config):
        mock_config.side_effect = Exception("bad config")
        result = _validate_existing()
        assert result is False

    @patch("social_hook.filesystem.get_base_path")
    @patch("social_hook.config.load_full_config")
    def test_missing_api_key(self, mock_config, mock_base, temp_dir):
        env_file = temp_dir / ".env"
        env_file.write_text("TELEGRAM_BOT_TOKEN=test\n")

        mock_base.return_value = temp_dir
        mock_config.return_value = MagicMock(env={"TELEGRAM_BOT_TOKEN": "test"})

        result = _validate_existing()
        assert result is False


class TestSaveEnv:
    """Tests for _save_env."""

    def test_save_new(self, temp_dir):
        _save_env(temp_dir, {"KEY1": "value1", "KEY2": "value2"})
        env_file = temp_dir / ".env"
        assert env_file.exists()
        content = env_file.read_text()
        assert "KEY1=value1" in content
        assert "KEY2=value2" in content

    def test_merge_existing(self, temp_dir):
        env_file = temp_dir / ".env"
        env_file.write_text("EXISTING=keep\n")

        _save_env(temp_dir, {"NEW": "added"})
        content = env_file.read_text()
        assert "EXISTING=keep" in content
        assert "NEW=added" in content

    def test_overwrite_existing(self, temp_dir):
        env_file = temp_dir / ".env"
        env_file.write_text("KEY=old\n")

        _save_env(temp_dir, {"KEY": "new"})
        content = env_file.read_text()
        assert "KEY=new" in content
        assert "KEY=old" not in content
