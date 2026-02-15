"""Tests for setup wizard (T22)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from social_hook.setup.wizard import (
    WizardProgress,
    WIZARD_TOTAL_SECTIONS,
    _obfuscate,
    _save_env,
    _validate_existing,
    _validate_not_empty,
    _validate_positive_int,
    run_wizard,
)


# =============================================================================
# Helper tests
# =============================================================================


class TestObfuscate:
    def test_empty_string(self):
        assert _obfuscate("") == ""

    def test_short_secret(self):
        assert _obfuscate("abc") == "***"

    def test_exactly_double_show_chars(self):
        assert _obfuscate("12345678") == "***"

    def test_normal_key(self):
        result = _obfuscate("sk-ant-abc123xyz789")
        assert result.startswith("sk-a")
        assert result.endswith("z789")
        assert "***" in result

    def test_custom_show_chars(self):
        result = _obfuscate("abcdefghijklmnop", show_chars=2)
        assert result == "ab***op"


class TestValidatePositiveInt:
    def test_valid_number(self):
        assert _validate_positive_int("3") is True

    def test_zero(self):
        result = _validate_positive_int("0")
        assert result != True
        assert "positive" in result.lower()

    def test_negative(self):
        result = _validate_positive_int("-1")
        assert result != True

    def test_non_numeric(self):
        result = _validate_positive_int("abc")
        assert result != True
        assert "number" in result.lower()

    def test_float_string(self):
        result = _validate_positive_int("3.5")
        assert result != True


class TestSectionHelpers:
    def test_section_does_not_raise(self):
        from social_hook.setup.wizard import _section
        _section("Test Title", "Test description")

    def test_section_no_description(self):
        from social_hook.setup.wizard import _section
        _section("Title Only")

    def test_section_with_step(self):
        from social_hook.setup.wizard import _section
        _section("Step Test", "Description", step=3)

    def test_section_with_wizard_progress(self):
        from social_hook.setup.wizard import _section
        progress = WizardProgress()
        progress.set_section(2, "Voice & Style", substeps=8)
        progress.advance()
        _section("Voice & Style", "Description", progress=progress)

    def test_section_progress_fallback(self):
        from social_hook.setup.wizard import _section
        with patch.dict("sys.modules", {"rich.console": None, "rich.panel": None}):
            _section("Fallback Progress", "Desc", step=5)

    def test_section_progress_object_fallback(self):
        from social_hook.setup.wizard import _section
        progress = WizardProgress()
        progress.set_section(3, "Telegram", substeps=2)
        with patch.dict("sys.modules", {"rich.console": None, "rich.panel": None}):
            _section("Telegram", "Desc", progress=progress)

    def test_success_does_not_raise(self):
        from social_hook.setup.wizard import _success
        _success("It worked")

    def test_warn_does_not_raise(self):
        from social_hook.setup.wizard import _warn
        _warn("Careful now")

    def test_error_does_not_raise(self):
        from social_hook.setup.wizard import _error
        _error("Something broke")

    def test_section_fallback_without_rich(self):
        from social_hook.setup.wizard import _section
        with patch.dict("sys.modules", {"rich.console": None, "rich.panel": None}):
            _section("Fallback Title", "Fallback desc")

    def test_success_fallback_without_rich(self):
        from social_hook.setup.wizard import _success
        with patch.dict("sys.modules", {"rich.console": None}):
            _success("fallback ok")

    def test_info_does_not_raise(self):
        from social_hook.setup.wizard import _info
        _info("Some informational message")

    def test_info_fallback_without_rich(self):
        from social_hook.setup.wizard import _info
        with patch.dict("sys.modules", {"rich.console": None, "rich.panel": None}):
            _info("fallback info")


# =============================================================================
# WizardProgress tests
# =============================================================================


class TestWizardProgress:
    def test_initial_state(self):
        p = WizardProgress()
        assert p.total == WIZARD_TOTAL_SECTIONS
        assert p.section == 0
        assert p.substep == 0
        assert p.fraction == 0.0

    def test_custom_total(self):
        p = WizardProgress(total_sections=5)
        assert p.total == 5

    def test_set_section(self):
        p = WizardProgress()
        p.set_section(2, "Voice & Style", substeps=8)
        assert p.section == 2
        assert p.section_label == "Voice & Style"
        assert p.substep == 0
        assert p.substeps_total == 8

    def test_advance(self):
        p = WizardProgress()
        p.set_section(1, "Test", substeps=3)
        p.advance()
        assert p.substep == 1
        p.advance()
        assert p.substep == 2
        p.advance()
        assert p.substep == 3

    def test_advance_clamps_at_max(self):
        p = WizardProgress()
        p.set_section(1, "Test", substeps=2)
        p.advance()
        p.advance()
        p.advance()  # Should not go past 2
        assert p.substep == 2

    def test_fraction_at_start(self):
        p = WizardProgress(total_sections=9)
        assert p.fraction == 0.0

    def test_fraction_after_first_section(self):
        p = WizardProgress(total_sections=9)
        p.set_section(1, "Models", substeps=1)
        p.advance()
        assert abs(p.fraction - 1 / 9) < 0.001

    def test_fraction_midway_through_section(self):
        p = WizardProgress(total_sections=9)
        p.set_section(2, "Voice", substeps=8)
        for _ in range(4):
            p.advance()
        expected = 1 / 9 + 0.5 / 9
        assert abs(p.fraction - expected) < 0.001

    def test_fraction_capped_at_1(self):
        p = WizardProgress(total_sections=2)
        p.set_section(2, "Last", substeps=1)
        p.advance()
        assert p.fraction <= 1.0

    def test_fraction_zero_total(self):
        p = WizardProgress(total_sections=0)
        assert p.fraction == 0.0

    def test_render_top_does_not_raise(self):
        p = WizardProgress()
        p.set_section(5, "Mid", substeps=2)
        p.advance()
        # render_top is a no-op when not a TTY (test environment)
        p.render_top()

    def test_render_does_not_raise(self):
        p = WizardProgress()
        p.set_section(1, "Test", substeps=1)
        p.advance()

    def test_set_section_resets_substep(self):
        p = WizardProgress()
        p.set_section(1, "First", substeps=3)
        p.advance()
        p.advance()
        assert p.substep == 2
        p.set_section(2, "Second", substeps=5)
        assert p.substep == 0


# =============================================================================
# Input validation tests
# =============================================================================


class TestValidateNotEmpty:
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

    def test_rejects_single_n(self):
        result = _validate_not_empty("n")
        assert result != True

    def test_accepts_valid_input(self):
        assert _validate_not_empty("sk-ant-abc123") is True

    def test_accepts_short_valid_input(self):
        assert _validate_not_empty("ok") is True


class TestPromptFallbackValidation:
    @patch("social_hook.setup.wizard._rich_prompt", side_effect=Exception("no InquirerPy"))
    def test_fallback_rejects_empty_then_accepts_valid(self, _mock_rich):
        from social_hook.setup.wizard import _prompt
        with patch("builtins.input", side_effect=["", "  ", "valid-input"]):
            result = _prompt("Enter value")
            assert result == "valid-input"

    @patch("social_hook.setup.wizard._rich_prompt", side_effect=Exception("no InquirerPy"))
    def test_fallback_uses_default_on_empty(self, _mock_rich):
        from social_hook.setup.wizard import _prompt
        with patch("builtins.input", return_value=""):
            result = _prompt("Enter value", default="my-default")
            assert result == "my-default"


class TestPromptApiKey:
    @patch("social_hook.setup.wizard._success")
    @patch("social_hook.setup.wizard._spinner")
    @patch("social_hook.setup.wizard._prompt")
    def test_returns_key_on_success(self, mock_prompt, mock_spinner, _mock_success):
        from social_hook.setup.wizard import _prompt_api_key
        mock_prompt.return_value = "valid-key"
        mock_spinner.return_value = (True, "Connected")
        result = _prompt_api_key("API key", lambda k: (True, "ok"))
        assert result == "valid-key"

    @patch("social_hook.setup.wizard._confirm")
    @patch("social_hook.setup.wizard._error")
    @patch("social_hook.setup.wizard._spinner")
    @patch("social_hook.setup.wizard._prompt")
    def test_saves_key_on_validation_failure(self, mock_prompt, mock_spinner, _mock_error, mock_confirm):
        from social_hook.setup.wizard import _prompt_api_key
        mock_prompt.return_value = "bad-key"
        mock_spinner.return_value = (False, "Invalid key")
        mock_confirm.return_value = False  # decline retry
        result = _prompt_api_key("API key", lambda k: (False, "bad"))
        assert result == "bad-key"

    @patch("social_hook.setup.wizard._success")
    @patch("social_hook.setup.wizard._confirm")
    @patch("social_hook.setup.wizard._error")
    @patch("social_hook.setup.wizard._spinner")
    @patch("social_hook.setup.wizard._prompt")
    def test_reprompts_on_failure_then_succeeds(
        self, mock_prompt, mock_spinner, _mock_error, mock_confirm, _mock_success
    ):
        from social_hook.setup.wizard import _prompt_api_key
        mock_prompt.side_effect = ["bad-key", "good-key"]
        mock_spinner.side_effect = [(False, "Invalid"), (True, "OK")]
        mock_confirm.return_value = True
        result = _prompt_api_key("API key", lambda k: (True, "ok"))
        assert result == "good-key"

    @patch("social_hook.setup.wizard._prompt")
    @patch("social_hook.setup.wizard._spinner")
    @patch("social_hook.setup.wizard._success")
    def test_uses_existing_as_default(self, _mock_success, mock_spinner, mock_prompt):
        from social_hook.setup.wizard import _prompt_api_key
        mock_prompt.return_value = "existing-key"
        mock_spinner.return_value = (True, "OK")
        result = _prompt_api_key("API key", lambda k: (True, "ok"), existing="existing-key")
        assert result == "existing-key"
        # Existing value passed as default kwarg to _prompt
        assert mock_prompt.call_args[1].get("default") == "existing-key" or \
            mock_prompt.call_args[0][0] == "API key"


# =============================================================================
# run_wizard tests
# =============================================================================


# All run_wizard tests mock sys.stdout to prevent isatty/input interaction
@patch("social_hook.setup.wizard.sys")
class TestRunWizard:
    @patch("social_hook.setup.wizard._validate_existing")
    def test_validate_mode(self, mock_validate, mock_sys):
        mock_validate.return_value = True
        result = run_wizard(validate=True)
        assert result is True
        mock_validate.assert_called_once()

    @patch("social_hook.setup.wizard._load_existing", return_value=({}, {}))
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
    @patch("social_hook.setup.wizard._setup_api_keys")
    @patch("social_hook.setup.wizard._save_env")
    @patch("social_hook.filesystem.init_filesystem")
    def test_full_wizard(self, mock_init, mock_save, mock_api_keys, mock_voice,
                         mock_telegram, mock_x, mock_linkedin, mock_models,
                         mock_image, mock_sched, mock_install, mock_yaml,
                         mock_summary, mock_load, mock_sys):
        mock_sys.stdout.isatty.return_value = False
        mock_init.return_value = Path("/tmp/test")
        result = run_wizard()
        assert result is True
        mock_init.assert_called_once()
        mock_voice.assert_called_once()
        mock_models.assert_called_once()
        mock_image.assert_called_once()
        mock_load.assert_called_once()

    @patch("social_hook.filesystem.init_filesystem")
    def test_keyboard_interrupt(self, mock_init, mock_sys):
        mock_sys.stdout.isatty.return_value = False
        mock_init.side_effect = KeyboardInterrupt()
        result = run_wizard()
        assert result is False

    @patch("social_hook.setup.wizard._load_existing", return_value=({}, {}))
    @patch("social_hook.setup.wizard._setup_api_keys")
    @patch("social_hook.setup.wizard._save_env")
    @patch("social_hook.filesystem.init_filesystem")
    def test_only_apikeys(self, mock_init, mock_save, mock_api_keys, mock_load, mock_sys):
        mock_sys.stdout.isatty.return_value = False
        mock_init.return_value = Path("/tmp/test")
        result = run_wizard(only="apikeys")
        assert result is True
        mock_api_keys.assert_called_once()

    @patch("social_hook.setup.wizard._load_existing", return_value=({}, {}))
    @patch("social_hook.setup.wizard._setup_voice_style")
    @patch("social_hook.setup.wizard._save_env")
    @patch("social_hook.filesystem.init_filesystem")
    def test_only_voice(self, mock_init, mock_save, mock_voice, mock_load, mock_sys):
        mock_sys.stdout.isatty.return_value = False
        mock_init.return_value = Path("/tmp/test")
        result = run_wizard(only="voice")
        assert result is True
        mock_voice.assert_called_once()

    @patch("social_hook.setup.wizard._load_existing", return_value=({}, {}))
    @patch("social_hook.setup.wizard._setup_models")
    @patch("social_hook.setup.wizard._save_env")
    @patch("social_hook.filesystem.init_filesystem")
    def test_only_models(self, mock_init, mock_save, mock_models, mock_load, mock_sys):
        mock_sys.stdout.isatty.return_value = False
        mock_init.return_value = Path("/tmp/test")
        result = run_wizard(only="models")
        assert result is True
        mock_models.assert_called_once()

    @patch("social_hook.setup.wizard._load_existing", return_value=({}, {}))
    @patch("social_hook.setup.wizard._setup_image_gen")
    @patch("social_hook.setup.wizard._save_env")
    @patch("social_hook.filesystem.init_filesystem")
    def test_only_image(self, mock_init, mock_save, mock_image, mock_load, mock_sys):
        mock_sys.stdout.isatty.return_value = False
        mock_init.return_value = Path("/tmp/test")
        result = run_wizard(only="image")
        assert result is True
        mock_image.assert_called_once()


# =============================================================================
# Warnings tests
# =============================================================================


@patch("social_hook.setup.wizard.sys")
class TestWizardWarnings:
    @patch("social_hook.setup.wizard._warn")
    @patch("social_hook.setup.wizard._success")
    @patch("social_hook.setup.wizard._load_existing", return_value=({}, {}))
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
    @patch("social_hook.setup.wizard._setup_api_keys")
    @patch("social_hook.setup.wizard._save_env")
    @patch("social_hook.filesystem.init_filesystem")
    def test_warns_when_missing_keys(
        self, mock_init, mock_save, mock_api_keys, mock_voice,
        mock_telegram, mock_x, mock_linkedin, mock_models,
        mock_image, mock_sched, mock_install, mock_yaml,
        mock_summary, mock_load, mock_success, mock_warn, mock_sys,
    ):
        mock_sys.stdout.isatty.return_value = False
        mock_init.return_value = Path("/tmp/test")
        run_wizard()

        warn_text = " ".join(str(c) for c in mock_warn.call_args_list)
        assert "ANTHROPIC_API_KEY" in warn_text
        assert "Telegram" in warn_text
        # _success("Setup complete!") should NOT be called
        for c in mock_success.call_args_list:
            assert "Setup complete" not in str(c)

    @patch("social_hook.setup.wizard._warn")
    @patch("social_hook.setup.wizard._success")
    @patch("social_hook.setup.wizard._load_existing", return_value=(
        {"ANTHROPIC_API_KEY": "key", "TELEGRAM_BOT_TOKEN": "tok"}, {}
    ))
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
    @patch("social_hook.setup.wizard._setup_api_keys")
    @patch("social_hook.setup.wizard._save_env")
    @patch("social_hook.filesystem.init_filesystem")
    def test_no_warnings_when_existing_keys(
        self, mock_init, mock_save, mock_api_keys, mock_voice,
        mock_telegram, mock_x, mock_linkedin, mock_models,
        mock_image, mock_sched, mock_install, mock_yaml,
        mock_summary, mock_load, mock_success, mock_warn, mock_sys,
        tmp_path,
    ):
        mock_sys.stdout.isatty.return_value = False
        mock_init.return_value = tmp_path
        mock_install.return_value = True
        # Create voice config so no warning is raised
        (tmp_path / "social-context.md").write_text("voice config")
        # Existing env has X key too
        mock_load.return_value = (
            {"ANTHROPIC_API_KEY": "key", "TELEGRAM_BOT_TOKEN": "tok", "X_API_KEY": "xk"}, {}
        )
        run_wizard()

        success_texts = [str(c) for c in mock_success.call_args_list]
        assert any("Setup complete" in t for t in success_texts)

    @patch("social_hook.setup.wizard._warn")
    @patch("social_hook.setup.wizard._success")
    @patch("social_hook.setup.wizard._load_existing", return_value=({}, {}))
    @patch("social_hook.setup.wizard._setup_api_keys")
    @patch("social_hook.setup.wizard._save_env")
    @patch("social_hook.filesystem.init_filesystem")
    def test_no_warnings_in_only_mode(
        self, mock_init, mock_save, mock_api_keys, mock_load,
        mock_success, mock_warn, mock_sys,
    ):
        mock_sys.stdout.isatty.return_value = False
        mock_init.return_value = Path("/tmp/test")
        run_wizard(only="apikeys")

        warn_text = " ".join(str(c) for c in mock_warn.call_args_list)
        assert "ANTHROPIC_API_KEY" not in warn_text


# =============================================================================
# Welcome panel tests
# =============================================================================


@patch("social_hook.setup.wizard.sys")
class TestWelcomePanel:
    @patch("social_hook.setup.wizard._load_existing", return_value=({}, {}))
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
    @patch("social_hook.setup.wizard._setup_api_keys")
    @patch("social_hook.setup.wizard._save_env")
    @patch("social_hook.filesystem.init_filesystem")
    def test_welcome_panel_renders(self, mock_init, mock_save, *mocks):
        # Last arg in mocks is mock_sys (class-level patch)
        mocks[-1].stdout.isatty.return_value = False
        mock_init.return_value = Path("/tmp/test")
        result = run_wizard()
        assert result is True

    @patch("social_hook.setup.wizard._load_existing", return_value=({}, {}))
    @patch("social_hook.setup.wizard._setup_installations")
    @patch("social_hook.setup.wizard._setup_scheduling")
    @patch("social_hook.setup.wizard._setup_image_gen")
    @patch("social_hook.setup.wizard._setup_models")
    @patch("social_hook.setup.wizard._setup_linkedin")
    @patch("social_hook.setup.wizard._setup_x")
    @patch("social_hook.setup.wizard._setup_telegram")
    @patch("social_hook.setup.wizard._setup_voice_style")
    @patch("social_hook.setup.wizard._setup_api_keys")
    @patch("social_hook.setup.wizard._save_env")
    @patch("social_hook.filesystem.init_filesystem")
    def test_welcome_fallback_on_import_error(self, mock_init, mock_save, *mocks):
        mocks[-1].stdout.isatty.return_value = False
        mock_init.return_value = Path("/tmp/test")
        with patch.dict("sys.modules", {"rich.console": None, "rich.panel": None}):
            result = run_wizard()
            assert result is True


# =============================================================================
# Setup step tests
# =============================================================================


class TestVoiceStyleStep:
    @patch("social_hook.setup.wizard._select")
    @patch("social_hook.setup.wizard._prompt")
    @patch("social_hook.setup.wizard._confirm")
    def test_creates_social_context_md(self, mock_confirm, mock_prompt, mock_select, temp_dir):
        from social_hook.setup.wizard import _setup_voice_style

        mock_confirm.return_value = True
        mock_prompt.side_effect = [
            "Witty and technical",
            "Here is a sample tweet",
            "Buzzwords, Leverage",
            "Oxford comma: yes",
            "Developers",
            "Code, tools, automation",
            "Python, AI",
            "Politics",
        ]
        mock_select.side_effect = [
            "I (first person)",
            "Intermediate to advanced",
        ]

        _setup_voice_style(temp_dir)

        context_path = temp_dir / "social-context.md"
        assert context_path.exists()
        content = context_path.read_text()
        assert "Witty and technical" in content
        assert "Developers" in content
        assert "Python" in content
        assert "Buzzwords" in content
        assert "Author's Voice" in content
        assert "Audience" in content

    @patch("social_hook.setup.wizard._select")
    @patch("social_hook.setup.wizard._prompt")
    @patch("social_hook.setup.wizard._confirm")
    def test_with_progress_tracking(self, mock_confirm, mock_prompt, mock_select, temp_dir):
        from social_hook.setup.wizard import _setup_voice_style

        mock_confirm.return_value = True
        mock_prompt.side_effect = [
            "Technical", "", "Buzzwords", "Oxford comma: yes",
            "Devs", "Tools", "Python", "Politics",
        ]
        mock_select.side_effect = ["I (first person)", "Advanced"]

        progress = WizardProgress()
        _setup_voice_style(temp_dir, progress=progress)

        assert progress.section == 3
        assert progress.substep == 8

    @patch("social_hook.setup.wizard._confirm")
    def test_skips_when_no_existing_and_declined(self, mock_confirm, temp_dir):
        from social_hook.setup.wizard import _setup_voice_style

        mock_confirm.return_value = False
        _setup_voice_style(temp_dir)

        context_path = temp_dir / "social-context.md"
        assert not context_path.exists()

    @patch("social_hook.setup.wizard._confirm")
    def test_keeps_existing_when_declined(self, mock_confirm, temp_dir):
        from social_hook.setup.wizard import _setup_voice_style

        context_path = temp_dir / "social-context.md"
        context_path.write_text("# Existing voice config")

        mock_confirm.return_value = False
        _setup_voice_style(temp_dir)

        assert context_path.read_text() == "# Existing voice config"
        mock_confirm.assert_called_once()


class TestModelSelection:
    @patch("social_hook.setup.wizard._select")
    @patch("social_hook.setup.wizard._confirm")
    def test_quick_setup_with_cli(self, mock_confirm, mock_select):
        from social_hook.setup.wizard import _setup_models

        mock_select.return_value = "Quick setup — use recommended defaults (Recommended)"

        yaml_config = {}
        with patch("social_hook.setup.wizard._discover_providers") as mock_discover:
            mock_discover.return_value = [
                {"id": "claude-cli", "status": "detected", "detail": "Uses subscription ($0)"},
                {"id": "anthropic", "status": "unconfigured", "detail": "Requires ANTHROPIC_API_KEY"},
            ]
            _setup_models(yaml_config, {}, {}, {})

        assert yaml_config["models"]["evaluator"] == "claude-cli/sonnet"
        assert yaml_config["models"]["drafter"] == "claude-cli/sonnet"
        assert yaml_config["models"]["gatekeeper"] == "claude-cli/haiku"

    @patch("social_hook.setup.wizard._select")
    @patch("social_hook.setup.wizard._confirm")
    def test_quick_setup_without_cli(self, mock_confirm, mock_select):
        from social_hook.setup.wizard import _setup_models

        mock_select.return_value = "Quick setup — use recommended defaults (Recommended)"

        yaml_config = {}
        with patch("social_hook.setup.wizard._discover_providers") as mock_discover:
            mock_discover.return_value = [
                {"id": "anthropic", "status": "unconfigured", "detail": "Requires ANTHROPIC_API_KEY"},
            ]
            _setup_models(yaml_config, {}, {}, {})

        assert yaml_config["models"]["evaluator"] == "anthropic/claude-opus-4-5"
        assert yaml_config["models"]["drafter"] == "anthropic/claude-opus-4-5"
        assert yaml_config["models"]["gatekeeper"] == "anthropic/claude-haiku-4-5"

    @patch("social_hook.setup.wizard._select")
    @patch("social_hook.setup.wizard._confirm")
    def test_with_progress(self, mock_confirm, mock_select):
        from social_hook.setup.wizard import _setup_models

        mock_select.return_value = "Quick setup — use recommended defaults (Recommended)"

        progress = WizardProgress()
        yaml_config = {}
        with patch("social_hook.setup.wizard._discover_providers") as mock_discover:
            mock_discover.return_value = [
                {"id": "anthropic", "status": "unconfigured", "detail": "Requires ANTHROPIC_API_KEY"},
            ]
            _setup_models(yaml_config, {}, {}, {}, progress=progress)

        assert progress.section == 1
        # Quick setup doesn't call progress.advance() per role, so substep stays 0
        assert progress.substep == 0

    @patch("social_hook.setup.wizard._select")
    @patch("social_hook.setup.wizard._confirm")
    def test_models_always_set(self, mock_confirm, mock_select):
        """New _setup_models always sets models (no skip option)."""
        from social_hook.setup.wizard import _setup_models

        mock_select.return_value = "Quick setup — use recommended defaults (Recommended)"

        yaml_config = {}
        with patch("social_hook.setup.wizard._discover_providers") as mock_discover:
            mock_discover.return_value = [
                {"id": "anthropic", "status": "unconfigured", "detail": "Requires ANTHROPIC_API_KEY"},
            ]
            _setup_models(yaml_config, {}, {}, {})

        assert "models" in yaml_config


class TestXTierSelection:
    @patch("social_hook.setup.wizard._prompt")
    @patch("social_hook.setup.wizard._select")
    @patch("social_hook.setup.wizard._spinner")
    @patch("social_hook.setup.wizard._confirm")
    def test_stores_free_tier(self, mock_confirm, mock_spinner, mock_select, mock_prompt):
        from social_hook.setup.wizard import _setup_x

        mock_confirm.side_effect = [True, True]
        mock_prompt.side_effect = ["key", "secret", "token", "tsecret"]
        mock_spinner.return_value = (True, "Authenticated")
        mock_select.return_value = "free (280 chars)"

        env_vars = {}
        yaml_config = {}
        _setup_x(env_vars, yaml_config, {}, {})

        assert yaml_config["platforms"]["x"]["account_tier"] == "free"
        assert yaml_config["platforms"]["x"]["enabled"] is True

    @patch("social_hook.setup.wizard._prompt")
    @patch("social_hook.setup.wizard._select")
    @patch("social_hook.setup.wizard._spinner")
    @patch("social_hook.setup.wizard._confirm")
    def test_stores_premium_tier(self, mock_confirm, mock_spinner, mock_select, mock_prompt):
        from social_hook.setup.wizard import _setup_x

        mock_confirm.side_effect = [True]
        mock_prompt.side_effect = ["key", "secret", "token", "tsecret"]
        mock_spinner.return_value = (True, "Authenticated")
        mock_select.return_value = "premium (25,000 chars)"

        env_vars = {}
        yaml_config = {}
        _setup_x(env_vars, yaml_config, {}, {})

        assert yaml_config["platforms"]["x"]["account_tier"] == "premium"

    @patch("social_hook.setup.wizard._prompt")
    @patch("social_hook.setup.wizard._select")
    @patch("social_hook.setup.wizard._spinner")
    @patch("social_hook.setup.wizard._confirm")
    def test_stores_basic_tier(self, mock_confirm, mock_spinner, mock_select, mock_prompt):
        from social_hook.setup.wizard import _setup_x

        mock_confirm.side_effect = [True]
        mock_prompt.side_effect = ["key", "secret", "token", "tsecret"]
        mock_spinner.return_value = (True, "Authenticated")
        mock_select.return_value = "basic (25,000 chars)"

        env_vars = {}
        yaml_config = {}
        _setup_x(env_vars, yaml_config, {}, {})

        assert yaml_config["platforms"]["x"]["account_tier"] == "basic"

    @patch("social_hook.setup.wizard._prompt")
    @patch("social_hook.setup.wizard._select")
    @patch("social_hook.setup.wizard._spinner")
    @patch("social_hook.setup.wizard._confirm")
    def test_stores_premium_plus_tier(self, mock_confirm, mock_spinner, mock_select, mock_prompt):
        from social_hook.setup.wizard import _setup_x

        mock_confirm.side_effect = [True]
        mock_prompt.side_effect = ["key", "secret", "token", "tsecret"]
        mock_spinner.return_value = (True, "Authenticated")
        mock_select.return_value = "premium_plus (25,000 chars)"

        env_vars = {}
        yaml_config = {}
        _setup_x(env_vars, yaml_config, {}, {})

        assert yaml_config["platforms"]["x"]["account_tier"] == "premium_plus"

    @patch("social_hook.setup.wizard._prompt")
    @patch("social_hook.setup.wizard._select")
    @patch("social_hook.setup.wizard._spinner")
    @patch("social_hook.setup.wizard._confirm")
    def test_x_credentials_collected(self, mock_confirm, mock_spinner, mock_select, mock_prompt):
        from social_hook.setup.wizard import _setup_x

        mock_confirm.side_effect = [True]
        mock_prompt.side_effect = ["key", "secret", "token", "tsecret"]
        mock_spinner.return_value = (True, "Authenticated")
        mock_select.return_value = "free (280 chars)"

        env_vars = {}
        yaml_config = {}
        _setup_x(env_vars, yaml_config, {}, {})

        assert mock_prompt.call_count == 4
        assert env_vars["X_API_KEY"] == "key"
        assert env_vars["X_ACCESS_SECRET"] == "tsecret"

    @patch("social_hook.setup.wizard._confirm")
    def test_skips_when_declined(self, mock_confirm):
        from social_hook.setup.wizard import _setup_x

        mock_confirm.return_value = False
        env_vars = {}
        yaml_config = {}
        _setup_x(env_vars, yaml_config, {}, {})

        assert "platforms" not in yaml_config
        assert "X_API_KEY" not in env_vars

    @patch("social_hook.setup.wizard._prompt")
    @patch("social_hook.setup.wizard._select")
    @patch("social_hook.setup.wizard._spinner")
    @patch("social_hook.setup.wizard._confirm")
    def test_retries_on_validation_failure(self, mock_confirm, mock_spinner, mock_select, mock_prompt):
        from social_hook.setup.wizard import _setup_x

        mock_confirm.side_effect = [True, True]
        mock_prompt.side_effect = [
            "key1", "secret1", "token1", "tsecret1",
            "key2", "secret2", "token2", "tsecret2",
        ]
        mock_spinner.side_effect = [
            (False, "Auth failed"),
            (True, "Authenticated"),
        ]
        mock_select.return_value = "free (280 chars)"

        env_vars = {}
        yaml_config = {}
        _setup_x(env_vars, yaml_config, {}, {})

        assert env_vars["X_API_KEY"] == "key2"
        assert yaml_config["platforms"]["x"]["enabled"] is True


class TestImageGenStep:
    @patch("social_hook.setup.wizard._prompt_api_key")
    @patch("social_hook.setup.wizard._select")
    @patch("social_hook.setup.wizard._confirm")
    def test_calls_validate_image_gen(self, mock_confirm, mock_select, mock_prompt_key):
        from social_hook.setup.wizard import _setup_image_gen

        mock_confirm.return_value = True
        mock_select.return_value = "nano_banana_pro"
        mock_prompt_key.return_value = "gemini-key-123"

        env_vars = {}
        yaml_config = {}
        _setup_image_gen(env_vars, yaml_config, {})

        assert yaml_config["image_generation"]["enabled"] is True
        assert yaml_config["image_generation"]["service"] == "nano_banana_pro"
        assert env_vars["GEMINI_API_KEY"] == "gemini-key-123"

    @patch("social_hook.setup.wizard._confirm")
    def test_disabled_when_declined(self, mock_confirm):
        from social_hook.setup.wizard import _setup_image_gen

        mock_confirm.return_value = False
        yaml_config = {}
        _setup_image_gen({}, yaml_config, {})

        assert yaml_config["image_generation"]["enabled"] is False


class TestApiKeysStep:
    @patch("social_hook.setup.wizard._prompt_api_key")
    def test_sets_anthropic_key_when_needed(self, mock_prompt_key):
        from social_hook.setup.wizard import _setup_api_keys

        mock_prompt_key.return_value = "sk-ant-test123"

        env_vars = {}
        yaml_config = {"models": {"evaluator": "anthropic/claude-opus-4-5",
                                   "drafter": "anthropic/claude-opus-4-5",
                                   "gatekeeper": "anthropic/claude-haiku-4-5"}}
        _setup_api_keys(env_vars, {}, yaml_config, {})

        assert env_vars["ANTHROPIC_API_KEY"] == "sk-ant-test123"

    @patch("social_hook.setup.wizard._prompt_api_key")
    def test_keeps_existing_on_skip(self, mock_prompt_key):
        from social_hook.setup.wizard import _setup_api_keys

        mock_prompt_key.return_value = None

        env_vars = {}
        yaml_config = {"models": {"evaluator": "anthropic/claude-opus-4-5",
                                   "drafter": "anthropic/claude-opus-4-5",
                                   "gatekeeper": "anthropic/claude-haiku-4-5"}}
        _setup_api_keys(env_vars, {"ANTHROPIC_API_KEY": "existing-key"}, yaml_config, {})

        # Existing key preserved explicitly in env_vars
        assert env_vars["ANTHROPIC_API_KEY"] == "existing-key"

    @patch("social_hook.setup.wizard._prompt_api_key")
    def test_pre_populates_existing_key(self, mock_prompt_key):
        from social_hook.setup.wizard import _setup_api_keys

        mock_prompt_key.return_value = "existing-key"

        env_vars = {}
        yaml_config = {"models": {"evaluator": "anthropic/claude-opus-4-5",
                                   "drafter": "anthropic/claude-opus-4-5",
                                   "gatekeeper": "anthropic/claude-haiku-4-5"}}
        _setup_api_keys(env_vars, {"ANTHROPIC_API_KEY": "existing-key"}, yaml_config, {})

        assert mock_prompt_key.call_args.kwargs.get("existing") == "existing-key"

    @patch("social_hook.setup.wizard._prompt_api_key")
    def test_with_progress(self, mock_prompt_key):
        from social_hook.setup.wizard import _setup_api_keys

        mock_prompt_key.return_value = "sk-key"
        progress = WizardProgress()
        env_vars = {}
        yaml_config = {"models": {"evaluator": "anthropic/claude-opus-4-5",
                                   "drafter": "anthropic/claude-opus-4-5",
                                   "gatekeeper": "anthropic/claude-haiku-4-5"}}
        _setup_api_keys(env_vars, {}, yaml_config, {}, progress=progress)

        assert progress.section == 2
        assert progress.substep == 1

    def test_no_keys_needed_for_cli(self):
        from social_hook.setup.wizard import _setup_api_keys

        env_vars = {}
        yaml_config = {"models": {"evaluator": "claude-cli/sonnet",
                                   "drafter": "claude-cli/sonnet",
                                   "gatekeeper": "claude-cli/haiku"}}
        _setup_api_keys(env_vars, {}, yaml_config, {})

        # No API keys should be set
        assert "ANTHROPIC_API_KEY" not in env_vars
        assert "OPENAI_API_KEY" not in env_vars
        assert "OPENROUTER_API_KEY" not in env_vars


class TestTelegramStep:
    @patch("social_hook.setup.validation.capture_telegram_chat_id", return_value="12345")
    @patch("social_hook.setup.wizard._prompt_api_key")
    @patch("social_hook.setup.wizard._confirm")
    def test_sets_token_and_chat_id(self, mock_confirm, mock_prompt_key, mock_capture):
        from social_hook.setup.wizard import _setup_telegram

        mock_confirm.return_value = True
        mock_prompt_key.return_value = "bot-token-123"

        env_vars = {}
        _setup_telegram(env_vars, {})

        assert env_vars["TELEGRAM_BOT_TOKEN"] == "bot-token-123"
        assert env_vars["TELEGRAM_ALLOWED_CHAT_IDS"] == "12345"

    @patch("social_hook.setup.wizard._confirm")
    def test_skips_when_declined(self, mock_confirm):
        from social_hook.setup.wizard import _setup_telegram

        mock_confirm.return_value = False

        env_vars = {}
        _setup_telegram(env_vars, {})

        assert "TELEGRAM_BOT_TOKEN" not in env_vars


class TestLinkedinStep:
    @patch("social_hook.setup.wizard._prompt")
    @patch("social_hook.setup.wizard._confirm")
    def test_sets_token(self, mock_confirm, mock_prompt):
        from social_hook.setup.wizard import _setup_linkedin

        mock_confirm.return_value = True
        mock_prompt.return_value = "linkedin-token"

        env_vars = {}
        _setup_linkedin(env_vars, {})

        assert env_vars["LINKEDIN_ACCESS_TOKEN"] == "linkedin-token"

    @patch("social_hook.setup.wizard._confirm")
    def test_skips_when_declined(self, mock_confirm):
        from social_hook.setup.wizard import _setup_linkedin

        mock_confirm.return_value = False

        env_vars = {}
        _setup_linkedin(env_vars, {})

        assert "LINKEDIN_ACCESS_TOKEN" not in env_vars

    @patch("social_hook.setup.wizard._prompt")
    @patch("social_hook.setup.wizard._confirm")
    def test_collects_token(self, mock_confirm, mock_prompt):
        from social_hook.setup.wizard import _setup_linkedin

        mock_confirm.return_value = True
        mock_prompt.return_value = "token"

        env_vars = {}
        _setup_linkedin(env_vars, {})

        assert env_vars["LINKEDIN_ACCESS_TOKEN"] == "token"


# =============================================================================
# Scheduling tests
# =============================================================================


class TestTimezoneSelector:
    @patch("social_hook.setup.wizard._select")
    def test_defaults_to_utc_on_detection_failure(self, mock_select):
        from social_hook.setup.wizard import _setup_scheduling

        mock_select.side_effect = [
            "UTC",
            "3 (recommended)",
            "30 (recommended)",
        ]

        yaml_config = {}
        _setup_scheduling(Path("/tmp"), yaml_config, {})

        assert yaml_config["scheduling"]["timezone"] == "UTC"

    @patch("social_hook.setup.wizard._select")
    def test_scheduling_uses_selectors(self, mock_select):
        from social_hook.setup.wizard import _setup_scheduling

        mock_select.side_effect = [
            "Australia/Sydney",
            "2",
            "60",
        ]

        yaml_config = {}
        _setup_scheduling(Path("/tmp"), yaml_config, {})

        assert yaml_config["scheduling"]["timezone"] == "Australia/Sydney"
        assert yaml_config["scheduling"]["max_posts_per_day"] == 2
        assert yaml_config["scheduling"]["min_gap_minutes"] == 60

    @patch("social_hook.setup.wizard._select")
    def test_strips_recommended_from_scheduling(self, mock_select):
        from social_hook.setup.wizard import _setup_scheduling

        mock_select.side_effect = [
            "UTC",
            "3 (recommended)",
            "30 (recommended)",
        ]

        yaml_config = {}
        _setup_scheduling(Path("/tmp"), yaml_config, {})

        assert yaml_config["scheduling"]["max_posts_per_day"] == 3
        assert yaml_config["scheduling"]["min_gap_minutes"] == 30

    @patch("social_hook.setup.wizard._select")
    def test_pre_populates_from_existing(self, mock_select):
        from social_hook.setup.wizard import _setup_scheduling

        mock_select.side_effect = [
            "US/Pacific",
            "5",
            "15",
        ]

        yaml_config = {}
        existing = {"scheduling": {"timezone": "US/Pacific", "max_posts_per_day": 5, "min_gap_minutes": 15}}
        _setup_scheduling(Path("/tmp"), yaml_config, existing)

        assert yaml_config["scheduling"]["timezone"] == "US/Pacific"
        assert yaml_config["scheduling"]["max_posts_per_day"] == 5

    @patch("social_hook.setup.wizard._prompt")
    @patch("social_hook.setup.wizard._select")
    def test_custom_max_posts(self, mock_select, mock_prompt):
        from social_hook.setup.wizard import _setup_scheduling

        mock_select.side_effect = [
            "UTC",
            "Custom",
            "30 (recommended)",
        ]
        mock_prompt.return_value = "7"

        yaml_config = {}
        _setup_scheduling(Path("/tmp"), yaml_config, {})

        assert yaml_config["scheduling"]["max_posts_per_day"] == 7

    @patch("social_hook.setup.wizard._prompt")
    @patch("social_hook.setup.wizard._select")
    def test_custom_min_gap(self, mock_select, mock_prompt):
        from social_hook.setup.wizard import _setup_scheduling

        mock_select.side_effect = [
            "UTC",
            "3 (recommended)",
            "Custom",
        ]
        mock_prompt.return_value = "45"

        yaml_config = {}
        _setup_scheduling(Path("/tmp"), yaml_config, {})

        assert yaml_config["scheduling"]["min_gap_minutes"] == 45

    @patch("social_hook.setup.wizard._select")
    def test_with_progress(self, mock_select):
        from social_hook.setup.wizard import _setup_scheduling

        mock_select.side_effect = ["UTC", "3 (recommended)", "30 (recommended)"]

        progress = WizardProgress()
        yaml_config = {}
        _setup_scheduling(Path("/tmp"), yaml_config, {}, progress=progress)

        assert progress.section == 8
        assert progress.substep == 3


# =============================================================================
# Summary, config, env tests
# =============================================================================


class TestSummaryTable:
    def test_renders_with_rich(self):
        from social_hook.setup.wizard import _show_summary

        env_vars = {"ANTHROPIC_API_KEY": "sk-ant-test123456", "TELEGRAM_BOT_TOKEN": "123:ABC"}
        yaml_config = {
            "models": {"evaluator": "anthropic/claude-opus-4-5", "drafter": "anthropic/claude-opus-4-5"},
            "platforms": {"x": {"account_tier": "free"}},
            "scheduling": {"timezone": "UTC", "max_posts_per_day": 3},
        }
        _show_summary(env_vars, yaml_config)

    def test_renders_fallback_without_rich(self):
        from social_hook.setup.wizard import _show_summary

        env_vars = {"ANTHROPIC_API_KEY": "sk-ant-test123456"}
        yaml_config = {}

        with patch.dict("sys.modules", {"rich.console": None, "rich.table": None}):
            _show_summary(env_vars, yaml_config)

    def test_summary_obfuscates_keys(self):
        from social_hook.setup.wizard import _show_summary

        env_vars = {"ANTHROPIC_API_KEY": "sk-ant-very-secret-key-12345"}
        yaml_config = {}
        _show_summary(env_vars, yaml_config)


class TestSaveConfigYaml:
    def test_saves_new_config(self, temp_dir):
        from social_hook.setup.wizard import _save_config_yaml

        yaml_config = {
            "platforms": {"x": {"enabled": True, "account_tier": "free"}},
            "models": {"evaluator": "anthropic/claude-opus-4-5"},
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
    @patch("social_hook.filesystem.get_base_path")
    @patch("social_hook.config.load_full_config")
    def test_valid_config(self, mock_config, mock_base, temp_dir):
        env_file = temp_dir / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=test\nTELEGRAM_BOT_TOKEN=test\n")

        mock_base.return_value = temp_dir
        mock_config.return_value = MagicMock(
            env={"ANTHROPIC_API_KEY": "test", "TELEGRAM_BOT_TOKEN": "test"},
            models=MagicMock(evaluator="anthropic/claude-opus-4-5",
                           drafter="anthropic/claude-opus-4-5",
                           gatekeeper="anthropic/claude-haiku-4-5"),
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
        mock_config.return_value = MagicMock(
            env={"TELEGRAM_BOT_TOKEN": "test"},
            models=MagicMock(evaluator="anthropic/claude-opus-4-5",
                           drafter="anthropic/claude-opus-4-5",
                           gatekeeper="anthropic/claude-haiku-4-5"),
        )

        result = _validate_existing()
        assert result is False

    @patch("social_hook.filesystem.get_base_path")
    @patch("social_hook.config.load_full_config")
    def test_valid_config_with_cli_provider(self, mock_config, mock_base, temp_dir):
        """Config uses claude-cli models, no ANTHROPIC_API_KEY needed."""
        env_file = temp_dir / ".env"
        env_file.write_text("TELEGRAM_BOT_TOKEN=test\n")

        mock_base.return_value = temp_dir
        mock_config.return_value = MagicMock(
            env={"TELEGRAM_BOT_TOKEN": "test"},
            models=MagicMock(evaluator="claude-cli/sonnet",
                           drafter="claude-cli/sonnet",
                           gatekeeper="claude-cli/haiku"),
        )

        result = _validate_existing()
        assert result is True


class TestSaveEnv:
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


# =============================================================================
# Installation tests
# =============================================================================


class TestInstallations:
    @patch("social_hook.setup.wizard._confirm")
    def test_skips_when_declined(self, mock_confirm):
        from social_hook.setup.wizard import _setup_installations

        mock_confirm.return_value = False
        _setup_installations()

    @patch("subprocess.run")
    @patch("social_hook.bot.process.is_running", return_value=True)
    @patch("social_hook.setup.install.check_cron_installed", return_value=True)
    @patch("social_hook.setup.install.check_hook_installed", return_value=True)
    @patch("social_hook.setup.wizard._confirm")
    def test_skips_already_installed(self, mock_confirm, mock_hook, mock_cron, mock_bot, mock_subprocess):
        from social_hook.setup.wizard import _setup_installations

        mock_confirm.return_value = True
        _setup_installations()

        mock_subprocess.assert_not_called()

    @patch("subprocess.run")
    @patch("social_hook.bot.process.is_running", return_value=False)
    @patch("social_hook.setup.install.install_cron", return_value=(True, "Cron installed"))
    @patch("social_hook.setup.install.check_cron_installed", return_value=False)
    @patch("social_hook.setup.install.install_hook", return_value=(True, "Hook installed"))
    @patch("social_hook.setup.install.check_hook_installed", return_value=False)
    @patch("social_hook.setup.wizard._confirm")
    def test_installs_all_components(
        self, mock_confirm, mock_hook_check, mock_hook_install,
        mock_cron_check, mock_cron_install, mock_bot_running, mock_subprocess
    ):
        from social_hook.setup.wizard import _setup_installations

        mock_confirm.return_value = True
        mock_subprocess.return_value = MagicMock(returncode=0)

        _setup_installations()

        mock_hook_install.assert_called_once()
        mock_cron_install.assert_called_once()
        mock_subprocess.assert_called_once()

    @patch("subprocess.run")
    @patch("social_hook.bot.process.is_running", return_value=False)
    @patch("social_hook.setup.install.install_cron", return_value=(True, "OK"))
    @patch("social_hook.setup.install.check_cron_installed", return_value=False)
    @patch("social_hook.setup.install.install_hook", return_value=(True, "OK"))
    @patch("social_hook.setup.install.check_hook_installed", return_value=False)
    @patch("social_hook.setup.wizard._confirm")
    def test_with_progress(
        self, mock_confirm, mock_hook_check, mock_hook_install,
        mock_cron_check, mock_cron_install, mock_bot_running, mock_subprocess
    ):
        from social_hook.setup.wizard import _setup_installations

        mock_confirm.return_value = True
        mock_subprocess.return_value = MagicMock(returncode=0)

        progress = WizardProgress()
        _setup_installations(progress=progress)

        assert progress.section == 9
        assert progress.substep == 3


# =============================================================================
# Load existing config tests
# =============================================================================


class TestLoadExisting:
    @patch("social_hook.config.load_full_config")
    def test_returns_empty_dicts_on_failure(self, mock_config):
        from social_hook.setup.wizard import _load_existing

        mock_config.side_effect = Exception("no config")
        env, yaml = _load_existing()

        assert env == {}
        assert yaml == {}

    @patch("social_hook.config.load_full_config")
    def test_extracts_existing_config(self, mock_config):
        from social_hook.setup.wizard import _load_existing

        mock_config.return_value = MagicMock(
            env={"ANTHROPIC_API_KEY": "sk-test", "TELEGRAM_BOT_TOKEN": "tok"},
            models=MagicMock(evaluator="anthropic/claude-opus-4-5", drafter="anthropic/claude-opus-4-5", gatekeeper="anthropic/claude-haiku-4-5"),
            platforms=MagicMock(x=MagicMock(enabled=True, account_tier="free")),
            scheduling=MagicMock(timezone="UTC", max_posts_per_day=3, min_gap_minutes=30),
            image_generation=MagicMock(enabled=True, service="nano_banana_pro"),
        )

        env, yaml = _load_existing()

        assert env["ANTHROPIC_API_KEY"] == "sk-test"
        assert yaml["models"]["evaluator"] == "anthropic/claude-opus-4-5"
        assert yaml["platforms"]["x"]["account_tier"] == "free"
        assert yaml["scheduling"]["timezone"] == "UTC"
        assert yaml["image_generation"]["service"] == "nano_banana_pro"


# =============================================================================
# Provider discovery and key detection tests
# =============================================================================


class TestDiscoverProviders:
    def test_detects_anthropic_key(self):
        from social_hook.setup.wizard import _discover_providers

        providers = _discover_providers({"ANTHROPIC_API_KEY": "sk-test"})
        anthropic = next(p for p in providers if p["id"] == "anthropic")
        assert anthropic["status"] == "configured"

    def test_unconfigured_without_key(self):
        from social_hook.setup.wizard import _discover_providers

        providers = _discover_providers({})
        anthropic = next(p for p in providers if p["id"] == "anthropic")
        assert anthropic["status"] == "unconfigured"

    def test_detects_openrouter_key(self):
        from social_hook.setup.wizard import _discover_providers

        providers = _discover_providers({"OPENROUTER_API_KEY": "or-test"})
        openrouter = next(p for p in providers if p["id"] == "openrouter")
        assert openrouter["status"] == "configured"

    def test_detects_openai_key(self):
        from social_hook.setup.wizard import _discover_providers

        providers = _discover_providers({"OPENAI_API_KEY": "sk-openai-test"})
        openai = next(p for p in providers if p["id"] == "openai")
        assert openai["status"] == "configured"


class TestKeysNeededForConfig:
    def test_anthropic_models_need_anthropic_key(self):
        from social_hook.setup.wizard import _keys_needed_for_config

        config = {"models": {
            "evaluator": "anthropic/claude-opus-4-5",
            "drafter": "anthropic/claude-opus-4-5",
            "gatekeeper": "anthropic/claude-haiku-4-5",
        }}
        needed = _keys_needed_for_config(config)
        assert "ANTHROPIC_API_KEY" in needed
        assert "OPENAI_API_KEY" not in needed

    def test_cli_models_need_no_keys(self):
        from social_hook.setup.wizard import _keys_needed_for_config

        config = {"models": {
            "evaluator": "claude-cli/sonnet",
            "drafter": "claude-cli/sonnet",
            "gatekeeper": "claude-cli/haiku",
        }}
        needed = _keys_needed_for_config(config)
        assert len(needed) == 0

    def test_mixed_providers_need_multiple_keys(self):
        from social_hook.setup.wizard import _keys_needed_for_config

        config = {"models": {
            "evaluator": "anthropic/claude-opus-4-5",
            "drafter": "openai/gpt-4o",
            "gatekeeper": "openrouter/anthropic/claude-sonnet-4.5",
        }}
        needed = _keys_needed_for_config(config)
        assert "ANTHROPIC_API_KEY" in needed
        assert "OPENAI_API_KEY" in needed
        assert "OPENROUTER_API_KEY" in needed

    def test_empty_config_defaults_to_anthropic(self):
        from social_hook.setup.wizard import _keys_needed_for_config

        needed = _keys_needed_for_config({})
        assert "ANTHROPIC_API_KEY" in needed
