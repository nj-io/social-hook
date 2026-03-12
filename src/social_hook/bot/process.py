"""PID file management for the bot daemon."""

import os
import signal
from pathlib import Path

from social_hook.filesystem import get_base_path


def get_pid_file() -> Path:
    """Get the path to the bot PID file."""
    return get_base_path() / "bot.pid"


def write_pid(pid_file: Path | None = None) -> None:
    """Write current PID to the PID file."""
    if pid_file is None:
        pid_file = get_pid_file()
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()))


def read_pid(pid_file: Path | None = None) -> int | None:
    """Read PID from the PID file.

    Returns:
        PID as int, or None if file doesn't exist or is invalid
    """
    if pid_file is None:
        pid_file = get_pid_file()
    if not pid_file.exists():
        return None
    try:
        content = pid_file.read_text().strip()
        return int(content)
    except (ValueError, OSError):
        return None


def remove_pid(pid_file: Path | None = None) -> None:
    """Remove the PID file."""
    if pid_file is None:
        pid_file = get_pid_file()
    pid_file.unlink(missing_ok=True)


def is_pid_alive(pid: int) -> bool:
    """Check if a process with given PID is alive.

    Args:
        pid: Process ID to check

    Returns:
        True if process exists
    """
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # Process exists but we can't signal it


def is_running(pid_file: Path | None = None) -> bool:
    """Check if the bot daemon is running.

    Returns:
        True if bot is running (PID file exists and process alive)
    """
    pid = read_pid(pid_file)
    if pid is None:
        return False
    if is_pid_alive(pid):
        return True
    # Stale PID file - clean up
    remove_pid(pid_file)
    return False


def stop_bot(pid_file: Path | None = None) -> bool:
    """Stop the bot daemon by sending SIGTERM.

    Returns:
        True if the bot was stopped
    """
    pid = read_pid(pid_file)
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
        remove_pid(pid_file)
        return True
    except ProcessLookupError:
        remove_pid(pid_file)
        return False
    except PermissionError:
        return False
