"""Tests for cron installer (T33)."""

from unittest.mock import MagicMock, patch

from social_hook.constants import PROJECT_SLUG
from social_hook.setup.install import (
    CRON_MARKER,
    check_cron_installed,
    get_cron_entry,
    install_cron,
    uninstall_cron,
)


class TestGetCronEntry:
    """Tests for get_cron_entry."""

    def test_format(self):
        entry = get_cron_entry()
        assert "*/1 * * * *" in entry
        assert "scheduler-tick" in entry
        assert CRON_MARKER in entry

    def test_includes_log_redirect(self):
        entry = get_cron_entry()
        assert "scheduler.log" in entry
        assert "2>&1" in entry


class TestInstallCron:
    """Tests for install_cron."""

    @patch("social_hook.setup.install.subprocess.run")
    def test_fresh_install(self, mock_run):
        # crontab -l returns empty
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout=""),  # crontab -l (no crontab)
            MagicMock(returncode=0),  # crontab -
        ]
        success, msg = install_cron()
        assert success is True
        assert "installed" in msg.lower()

    @patch("social_hook.setup.install.subprocess.run")
    def test_already_installed(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=f"* * * * * something {CRON_MARKER}",
        )
        success, msg = install_cron()
        assert success is True
        assert "already installed" in msg.lower()

    @patch("social_hook.setup.install.subprocess.run")
    def test_preserves_existing_entries(self, mock_run):
        existing = "0 * * * * /usr/local/bin/backup\n"
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=existing),
            MagicMock(returncode=0),
        ]
        success, _ = install_cron()
        assert success is True
        # Verify the second call (crontab -) includes both old and new
        write_call = mock_run.call_args_list[1]
        written_content = write_call[1]["input"]
        assert "backup" in written_content
        assert CRON_MARKER in written_content

    @patch("social_hook.setup.install.subprocess.run")
    def test_crontab_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        success, msg = install_cron()
        assert success is False
        assert "not found" in msg.lower()


class TestUninstallCron:
    """Tests for uninstall_cron."""

    @patch("social_hook.setup.install.subprocess.run")
    def test_uninstall(self, mock_run):
        entry = f"*/1 * * * * {PROJECT_SLUG} scheduler-tick {CRON_MARKER}"
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=entry),
            MagicMock(returncode=0),
        ]
        success, msg = uninstall_cron()
        assert success is True
        assert "removed" in msg.lower()

    @patch("social_hook.setup.install.subprocess.run")
    def test_not_installed(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="0 * * * * /usr/local/bin/backup\n",
        )
        success, msg = uninstall_cron()
        assert success is True
        assert "not installed" in msg.lower()

    @patch("social_hook.setup.install.subprocess.run")
    def test_no_crontab(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        success, msg = uninstall_cron()
        assert success is True


class TestCheckCronInstalled:
    """Tests for check_cron_installed."""

    @patch("social_hook.setup.install.subprocess.run")
    def test_installed(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=f"*/1 * * * * {PROJECT_SLUG} {CRON_MARKER}",
        )
        assert check_cron_installed() is True

    @patch("social_hook.setup.install.subprocess.run")
    def test_not_installed(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        assert check_cron_installed() is False

    @patch("social_hook.setup.install.subprocess.run")
    def test_no_crontab(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        assert check_cron_installed() is False
