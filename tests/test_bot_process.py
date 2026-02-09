"""Tests for bot process management (T24)."""

import os
import signal
from pathlib import Path

import pytest

from social_hook.bot.process import (
    get_pid_file,
    is_pid_alive,
    is_running,
    read_pid,
    remove_pid,
    stop_bot,
    write_pid,
)


class TestWriteAndReadPid:
    """Tests for write_pid and read_pid."""

    def test_write_and_read(self, temp_dir):
        pid_file = temp_dir / "bot.pid"
        write_pid(pid_file)
        assert read_pid(pid_file) == os.getpid()

    def test_read_nonexistent(self, temp_dir):
        pid_file = temp_dir / "nonexistent.pid"
        assert read_pid(pid_file) is None

    def test_read_invalid_content(self, temp_dir):
        pid_file = temp_dir / "bot.pid"
        pid_file.write_text("not_a_number")
        assert read_pid(pid_file) is None

    def test_read_empty_file(self, temp_dir):
        pid_file = temp_dir / "bot.pid"
        pid_file.write_text("")
        assert read_pid(pid_file) is None

    def test_write_creates_parent_dirs(self, temp_dir):
        pid_file = temp_dir / "sub" / "dir" / "bot.pid"
        write_pid(pid_file)
        assert pid_file.exists()
        assert read_pid(pid_file) == os.getpid()


class TestRemovePid:
    """Tests for remove_pid."""

    def test_remove_existing(self, temp_dir):
        pid_file = temp_dir / "bot.pid"
        pid_file.write_text("12345")
        remove_pid(pid_file)
        assert not pid_file.exists()

    def test_remove_nonexistent(self, temp_dir):
        pid_file = temp_dir / "nonexistent.pid"
        # Should not raise
        remove_pid(pid_file)


class TestIsPidAlive:
    """Tests for is_pid_alive."""

    def test_own_pid_is_alive(self):
        assert is_pid_alive(os.getpid()) is True

    def test_nonexistent_pid(self):
        # Use a very high PID that shouldn't exist
        assert is_pid_alive(99999999) is False


class TestIsRunning:
    """Tests for is_running."""

    def test_running_with_live_pid(self, temp_dir):
        pid_file = temp_dir / "bot.pid"
        pid_file.write_text(str(os.getpid()))
        assert is_running(pid_file) is True

    def test_not_running_no_file(self, temp_dir):
        pid_file = temp_dir / "nonexistent.pid"
        assert is_running(pid_file) is False

    def test_stale_pid_cleaned_up(self, temp_dir):
        pid_file = temp_dir / "bot.pid"
        pid_file.write_text("99999999")
        assert is_running(pid_file) is False
        # Stale PID file should be removed
        assert not pid_file.exists()

    def test_invalid_pid_file(self, temp_dir):
        pid_file = temp_dir / "bot.pid"
        pid_file.write_text("garbage")
        assert is_running(pid_file) is False


class TestStopBot:
    """Tests for stop_bot."""

    def test_stop_no_pid_file(self, temp_dir):
        pid_file = temp_dir / "nonexistent.pid"
        assert stop_bot(pid_file) is False

    def test_stop_stale_pid(self, temp_dir):
        pid_file = temp_dir / "bot.pid"
        pid_file.write_text("99999999")
        assert stop_bot(pid_file) is False
        # PID file should be cleaned up
        assert not pid_file.exists()


class TestGetPidFile:
    """Tests for get_pid_file."""

    def test_returns_path(self):
        pid_file = get_pid_file()
        assert isinstance(pid_file, Path)
        assert pid_file.name == "bot.pid"
