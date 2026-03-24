"""Tests for social_hook.terminal — clipboard, getch, pause_with_url."""

import contextlib
import sys
from unittest.mock import MagicMock, patch

from social_hook.terminal import copy_to_clipboard, pause_with_url


class TestCopyToClipboard:
    @patch("social_hook.terminal.subprocess.run")
    def test_pbcopy_success(self, mock_run):
        """pbcopy available: returns True and calls with encoded text."""
        result = copy_to_clipboard("hello world")

        assert result is True
        mock_run.assert_called_once_with(["pbcopy"], input=b"hello world", check=True)

    @patch("social_hook.terminal.subprocess.run")
    def test_pbcopy_missing_falls_back_to_xclip(self, mock_run):
        """pbcopy not found: tries xclip and returns True on success."""
        mock_run.side_effect = [FileNotFoundError, None]

        result = copy_to_clipboard("some text")

        assert result is True
        assert mock_run.call_count == 2
        mock_run.assert_called_with(
            ["xclip", "-selection", "clipboard"],
            input=b"some text",
            check=True,
        )

    @patch("social_hook.terminal.subprocess.run")
    def test_both_clipboard_tools_missing(self, mock_run):
        """Neither pbcopy nor xclip available: returns False."""
        mock_run.side_effect = [FileNotFoundError, FileNotFoundError]

        result = copy_to_clipboard("anything")

        assert result is False
        assert mock_run.call_count == 2


class TestGetch:
    def test_reads_single_char(self):
        """getch reads one character in raw mode, then restores settings."""
        mock_termios = MagicMock()
        mock_termios.tcgetattr.return_value = ["old_settings"]
        mock_tty = MagicMock()
        mock_stdin = MagicMock()
        mock_stdin.fileno.return_value = 3
        mock_stdin.read.return_value = "q"

        with (
            patch.dict(sys.modules, {"termios": mock_termios, "tty": mock_tty}),
            patch.object(sys, "stdin", mock_stdin),
        ):
            # Re-import to pick up patched modules
            import importlib

            import social_hook.terminal as terminal_mod

            importlib.reload(terminal_mod)
            result = terminal_mod.getch()

        assert result == "q"
        mock_termios.tcgetattr.assert_called_once_with(3)
        mock_tty.setraw.assert_called_once_with(3)
        mock_stdin.read.assert_called_once_with(1)
        mock_termios.tcsetattr.assert_called_once_with(3, mock_termios.TCSADRAIN, ["old_settings"])

    def test_restores_on_exception(self):
        """Terminal settings are restored even if read raises."""
        mock_termios = MagicMock()
        mock_termios.tcgetattr.return_value = ["saved"]
        mock_tty = MagicMock()
        mock_stdin = MagicMock()
        mock_stdin.fileno.return_value = 5
        mock_stdin.read.side_effect = OSError("read error")

        with (
            patch.dict(sys.modules, {"termios": mock_termios, "tty": mock_tty}),
            patch.object(sys, "stdin", mock_stdin),
        ):
            import importlib

            import social_hook.terminal as terminal_mod

            importlib.reload(terminal_mod)
            with contextlib.suppress(OSError):
                terminal_mod.getch()

        mock_termios.tcsetattr.assert_called_once_with(5, mock_termios.TCSADRAIN, ["saved"])


class TestPauseWithUrl:
    @patch("social_hook.terminal.time.sleep")
    @patch("social_hook.terminal.copy_to_clipboard", return_value=True)
    @patch("social_hook.terminal.getch")
    def test_press_c_copies_url_then_enter_continues(self, mock_getch, mock_copy, mock_sleep):
        """Pressing 'c' copies URL, then any other key exits."""
        mock_getch.side_effect = ["c", "\r"]

        pause_with_url(url="https://example.com", action="continue")

        mock_copy.assert_called_once_with("https://example.com")
        mock_sleep.assert_called_once_with(0.8)

    @patch("social_hook.terminal.time.sleep")
    @patch("social_hook.terminal.copy_to_clipboard")
    @patch("social_hook.terminal.getch")
    def test_enter_immediately_no_copy(self, mock_getch, mock_copy, mock_sleep):
        """Pressing Enter immediately exits without copying."""
        mock_getch.return_value = "\r"

        pause_with_url(url="https://example.com", action="continue")

        mock_copy.assert_not_called()
        mock_sleep.assert_not_called()

    @patch("social_hook.terminal.time.sleep")
    @patch("social_hook.terminal.copy_to_clipboard")
    @patch("social_hook.terminal.getch")
    def test_no_url_skips_copy_option(self, mock_getch, mock_copy, mock_sleep):
        """With url=None, pressing 'c' exits (no copy option)."""
        mock_getch.return_value = "c"

        pause_with_url(url=None, action="continue")

        mock_copy.assert_not_called()

    @patch("social_hook.terminal.time.sleep")
    @patch("social_hook.terminal.copy_to_clipboard", return_value=False)
    @patch("social_hook.terminal.getch")
    def test_clipboard_unavailable_still_continues(self, mock_getch, mock_copy, mock_sleep):
        """If clipboard not available, shows message but loop continues."""
        mock_getch.side_effect = ["c", "\r"]

        pause_with_url(url="https://example.com", action="continue")

        mock_copy.assert_called_once_with("https://example.com")
        # Still sleeps to show the "not available" message
        mock_sleep.assert_called_once_with(0.8)
