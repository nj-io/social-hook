"""PID file management for the bot daemon."""

import os
import signal
import subprocess
import time
from contextlib import suppress
from pathlib import Path


def get_pid_file() -> Path:
    """Get the path to the bot PID file.

    Always uses the main base path (~/.social-hook/bot.pid), not a
    worktree-specific path. Only one bot daemon can run per Telegram
    token, so all worktrees share the same PID file.
    """
    return Path.home() / ".social-hook" / "bot.pid"


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
    """Check if a process with given PID is alive (not a zombie).

    Args:
        pid: Process ID to check

    Returns:
        True if process exists and is not a zombie
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # Process exists but we can't signal it
    # os.kill(0) succeeds for zombie processes — check actual state
    try:
        result = subprocess.run(
            ["ps", "-o", "state=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=2,
        )
        state = result.stdout.strip()
        if state.startswith("Z"):
            return False
    except Exception:
        pass  # If ps fails, trust the kill(0) result
    return True


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
    """Stop the bot daemon by sending SIGTERM, with SIGKILL fallback.

    Waits up to 40s for graceful shutdown (TelegramRunner blocks on
    requests.get(timeout=35) during long-poll). If still alive, sends SIGKILL.

    Returns:
        True if the bot was stopped
    """
    pid = read_pid(pid_file)
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        remove_pid(pid_file)
        return False
    except PermissionError:
        return False
    # Wait up to 40s for graceful shutdown, then SIGKILL
    for _ in range(8):
        time.sleep(5)
        if not is_pid_alive(pid):
            remove_pid(pid_file)
            return True
    with suppress(ProcessLookupError, PermissionError):
        os.kill(pid, signal.SIGKILL)
    remove_pid(pid_file)
    return True
