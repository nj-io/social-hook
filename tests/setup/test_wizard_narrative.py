"""Tests for Development Journey wizard integration (Chunk G)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from social_hook.setup.wizard import (
    WizardProgress,
    _load_existing,
    _setup_journey_capture,
    _show_summary,
    run_wizard,
)

# =============================================================================
# _setup_journey_capture tests
# =============================================================================


class TestSetupJourneyCapture:
    """Tests for _setup_journey_capture step."""

    @patch(
        "social_hook.setup.install.install_narrative_hook",
        return_value=(True, "Narrative hook installed"),
    )
    @patch("social_hook.setup.wizard._confirm", return_value=True)
    @patch("shutil.which", return_value="/usr/local/bin/claude")
    def test_claude_cli_detected_user_enables(self, mock_which, mock_confirm, mock_install):
        yaml_config = {}
        _setup_journey_capture(yaml_config)

        assert yaml_config["journey_capture"]["enabled"] is True
        mock_confirm.assert_called_once()
        mock_install.assert_called_once()

    @patch("social_hook.setup.wizard._confirm", return_value=False)
    @patch("shutil.which", return_value="/usr/local/bin/claude")
    def test_claude_cli_detected_user_disables(self, mock_which, mock_confirm):
        yaml_config = {}
        _setup_journey_capture(yaml_config)

        assert yaml_config["journey_capture"]["enabled"] is False
        mock_confirm.assert_called_once()

    @patch("social_hook.setup.wizard._confirm")
    @patch("shutil.which", return_value=None)
    def test_claude_cli_not_detected_skips_without_asking(self, mock_which, mock_confirm):
        yaml_config = {}
        _setup_journey_capture(yaml_config)

        assert yaml_config["journey_capture"]["enabled"] is False
        mock_confirm.assert_not_called()

    @patch("social_hook.setup.install.install_narrative_hook", return_value=(True, "OK"))
    @patch("social_hook.setup.wizard._confirm", return_value=True)
    @patch("shutil.which", return_value="/usr/local/bin/claude")
    def test_preserves_existing_yaml_keys(self, mock_which, mock_confirm, mock_install):
        yaml_config = {"models": {"evaluator": "claude-cli/sonnet"}}
        _setup_journey_capture(yaml_config)

        assert yaml_config["journey_capture"]["enabled"] is True
        assert yaml_config["models"]["evaluator"] == "claude-cli/sonnet"

    @patch(
        "social_hook.setup.install.install_narrative_hook",
        return_value=(False, "Permission denied"),
    )
    @patch("social_hook.setup.wizard._confirm", return_value=True)
    @patch("shutil.which", return_value="/usr/local/bin/claude")
    def test_hook_install_failure_still_enables(self, mock_which, mock_confirm, mock_install):
        """Journey is enabled even if hook install fails (user can retry)."""
        yaml_config = {}
        _setup_journey_capture(yaml_config)

        assert yaml_config["journey_capture"]["enabled"] is True

    @patch("social_hook.setup.install.install_narrative_hook", return_value=(True, "OK"))
    @patch("social_hook.setup.wizard._confirm", return_value=True)
    @patch("shutil.which", return_value="/usr/local/bin/claude")
    def test_with_progress_tracker(self, mock_which, mock_confirm, mock_install):
        yaml_config = {}
        progress = WizardProgress()
        _setup_journey_capture(yaml_config, progress=progress)

        assert yaml_config["journey_capture"]["enabled"] is True


# =============================================================================
# _load_existing preserves journey_capture
# =============================================================================


class TestLoadExistingJourneyCapture:
    """Tests that _load_existing extracts journey_capture settings."""

    @patch("social_hook.config.load_full_config")
    def test_extracts_journey_capture_enabled(self, mock_config):
        mock_config.return_value = MagicMock(
            env={},
            models=MagicMock(
                evaluator="claude-cli/sonnet",
                drafter="claude-cli/sonnet",
                gatekeeper="claude-cli/haiku",
            ),
            platforms=MagicMock(x=MagicMock(enabled=True, account_tier="free")),
            scheduling=MagicMock(timezone="UTC", max_posts_per_day=3, min_gap_minutes=30),
            media_generation=MagicMock(enabled=True, service="nano_banana_pro"),
            journey_capture=MagicMock(enabled=True, model=None),
        )

        _, yaml_data = _load_existing()

        assert yaml_data["journey_capture"]["enabled"] is True
        assert "model" not in yaml_data["journey_capture"]

    @patch("social_hook.config.load_full_config")
    def test_extracts_journey_capture_with_model(self, mock_config):
        mock_config.return_value = MagicMock(
            env={},
            models=MagicMock(
                evaluator="claude-cli/sonnet",
                drafter="claude-cli/sonnet",
                gatekeeper="claude-cli/haiku",
            ),
            platforms=MagicMock(x=MagicMock(enabled=True, account_tier="free")),
            scheduling=MagicMock(timezone="UTC", max_posts_per_day=3, min_gap_minutes=30),
            media_generation=MagicMock(enabled=True, service="nano_banana_pro"),
            journey_capture=MagicMock(enabled=True, model="anthropic/claude-opus-4-5"),
        )

        _, yaml_data = _load_existing()

        assert yaml_data["journey_capture"]["enabled"] is True
        assert yaml_data["journey_capture"]["model"] == "anthropic/claude-opus-4-5"

    @patch("social_hook.config.load_full_config")
    def test_extracts_journey_capture_disabled(self, mock_config):
        mock_config.return_value = MagicMock(
            env={},
            models=MagicMock(
                evaluator="claude-cli/sonnet",
                drafter="claude-cli/sonnet",
                gatekeeper="claude-cli/haiku",
            ),
            platforms=MagicMock(x=MagicMock(enabled=True, account_tier="free")),
            scheduling=MagicMock(timezone="UTC", max_posts_per_day=3, min_gap_minutes=30),
            media_generation=MagicMock(enabled=True, service="nano_banana_pro"),
            journey_capture=MagicMock(enabled=False, model=None),
        )

        _, yaml_data = _load_existing()

        assert yaml_data["journey_capture"]["enabled"] is False


# =============================================================================
# _show_summary includes journey capture
# =============================================================================


class TestShowSummaryJourneyCapture:
    """Tests that _show_summary displays Development Journey status."""

    def test_summary_shows_journey_enabled(self):
        yaml_config = {
            "journey_capture": {"enabled": True},
        }
        # Should not raise
        _show_summary({}, yaml_config)

    def test_summary_shows_journey_disabled(self):
        yaml_config = {
            "journey_capture": {"enabled": False},
        }
        _show_summary({}, yaml_config)

    def test_summary_shows_journey_when_missing(self):
        """When journey_capture key is absent, shows Disabled."""
        yaml_config = {}
        _show_summary({}, yaml_config)


# =============================================================================
# run_wizard with only="journey"
# =============================================================================


@patch("social_hook.setup.wizard.sys")
class TestRunWizardJourneyOnly:
    """Tests for run_wizard(only='journey') standalone path."""

    @patch("social_hook.setup.wizard._setup_journey_capture")
    @patch("social_hook.setup.wizard._load_existing", return_value=({}, {}))
    @patch("social_hook.setup.wizard._save_env")
    @patch("social_hook.filesystem.init_filesystem")
    def test_only_journey_calls_setup(
        self, mock_init, mock_save, mock_load, mock_journey, mock_sys
    ):
        mock_sys.stdout.isatty.return_value = False
        mock_init.return_value = Path("/tmp/test")
        result = run_wizard(only="journey")
        assert result is True
        mock_journey.assert_called_once()

    @patch("social_hook.setup.wizard._setup_journey_capture")
    @patch("social_hook.setup.wizard._setup_models")
    @patch("social_hook.setup.wizard._load_existing", return_value=({}, {}))
    @patch("social_hook.setup.wizard._save_env")
    @patch("social_hook.filesystem.init_filesystem")
    def test_only_journey_does_not_call_models(
        self, mock_init, mock_save, mock_load, mock_models, mock_journey, mock_sys
    ):
        """only='journey' should not trigger models setup."""
        mock_sys.stdout.isatty.return_value = False
        mock_init.return_value = Path("/tmp/test")
        run_wizard(only="journey")
        mock_models.assert_not_called()
        mock_journey.assert_called_once()
