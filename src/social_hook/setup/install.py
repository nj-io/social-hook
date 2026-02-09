"""Hook and cron installation for social-hook."""

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# The Claude Code hook we install
OUR_HOOK = {
    "type": "command",
    "event": "PostToolUse",
    "matcher": {
        "tool": "Bash",
        "command_pattern": r"^git\s+(commit|merge|rebase|cherry-pick)",
    },
    "command": "social-hook trigger --commit $(git rev-parse HEAD) --repo $(pwd)",
}

# Marker to identify our hook in crontab
CRON_MARKER = "# social-hook scheduler"


def get_hooks_path() -> Path:
    """Get the Claude Code hooks.json path."""
    return Path.home() / ".claude" / "hooks.json"


def install_hook(hooks_file: Optional[Path] = None) -> tuple[bool, str]:
    """Install the Claude Code post-commit hook.

    Args:
        hooks_file: Path to hooks.json (default: ~/.claude/hooks.json)

    Returns:
        (success, message) tuple
    """
    if hooks_file is None:
        hooks_file = get_hooks_path()

    # Ensure parent directory exists
    hooks_file.parent.mkdir(parents=True, exist_ok=True)

    # Load existing hooks
    if hooks_file.exists():
        try:
            data = json.loads(hooks_file.read_text())
        except (json.JSONDecodeError, OSError):
            data = {"hooks": {}}

        # Backup existing file
        backup = hooks_file.with_suffix(".json.bak")
        shutil.copy2(hooks_file, backup)
    else:
        data = {"hooks": {}}

    # Ensure structure
    if "hooks" not in data:
        data["hooks"] = {}

    # Get or create PostToolUse list
    post_tool_use = data["hooks"].get("PostToolUse", [])

    # Check idempotency
    for hook in post_tool_use:
        if hook.get("command") == OUR_HOOK["command"]:
            return True, "Hook already installed"

    # Add our hook
    post_tool_use.append(OUR_HOOK)
    data["hooks"]["PostToolUse"] = post_tool_use

    # Write
    hooks_file.write_text(json.dumps(data, indent=2) + "\n")
    return True, f"Hook installed at {hooks_file}"


def uninstall_hook(hooks_file: Optional[Path] = None) -> tuple[bool, str]:
    """Remove the social-hook from Claude Code hooks.

    Returns:
        (success, message) tuple
    """
    if hooks_file is None:
        hooks_file = get_hooks_path()

    if not hooks_file.exists():
        return True, "No hooks file found"

    try:
        data = json.loads(hooks_file.read_text())
    except (json.JSONDecodeError, OSError):
        return False, "Could not read hooks file"

    post_tool_use = data.get("hooks", {}).get("PostToolUse", [])
    original_len = len(post_tool_use)

    post_tool_use = [
        h for h in post_tool_use if h.get("command") != OUR_HOOK["command"]
    ]

    if len(post_tool_use) == original_len:
        return True, "Hook was not installed"

    data["hooks"]["PostToolUse"] = post_tool_use
    hooks_file.write_text(json.dumps(data, indent=2) + "\n")
    return True, "Hook removed"


def check_hook_installed(hooks_file: Optional[Path] = None) -> bool:
    """Check if the social-hook is installed in Claude Code hooks."""
    if hooks_file is None:
        hooks_file = get_hooks_path()

    if not hooks_file.exists():
        return False

    try:
        data = json.loads(hooks_file.read_text())
        for hook in data.get("hooks", {}).get("PostToolUse", []):
            if hook.get("command") == OUR_HOOK["command"]:
                return True
    except (json.JSONDecodeError, OSError):
        pass
    return False


def get_cron_entry() -> str:
    """Get the crontab entry for the scheduler.

    Returns:
        Crontab line string
    """
    binary = shutil.which("social-hook") or "social-hook"
    from social_hook.filesystem import get_base_path

    log_dir = get_base_path() / "logs"
    return f"*/1 * * * * {binary} scheduler-tick >> {log_dir}/scheduler.log 2>&1 {CRON_MARKER}"


def install_cron() -> tuple[bool, str]:
    """Install the scheduler cron job.

    Returns:
        (success, message) tuple
    """
    try:
        # Read existing crontab
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
        )
        existing = result.stdout if result.returncode == 0 else ""

        # Check idempotency
        if CRON_MARKER in existing:
            return True, "Cron job already installed"

        # Add our entry
        new_entry = get_cron_entry()
        new_crontab = existing.rstrip() + "\n" + new_entry + "\n"

        # Write via crontab -
        process = subprocess.run(
            ["crontab", "-"],
            input=new_crontab,
            capture_output=True,
            text=True,
        )
        if process.returncode == 0:
            return True, "Cron job installed"
        return False, f"crontab write failed: {process.stderr}"
    except FileNotFoundError:
        return False, "crontab command not found"
    except Exception as e:
        return False, f"Error: {e}"


def uninstall_cron() -> tuple[bool, str]:
    """Remove the scheduler cron job.

    Returns:
        (success, message) tuple
    """
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return True, "No crontab found"

        existing = result.stdout
        if CRON_MARKER not in existing:
            return True, "Cron job was not installed"

        # Remove our line
        lines = [
            line for line in existing.splitlines()
            if CRON_MARKER not in line
        ]
        new_crontab = "\n".join(lines) + "\n" if lines else ""

        process = subprocess.run(
            ["crontab", "-"],
            input=new_crontab,
            capture_output=True,
            text=True,
        )
        if process.returncode == 0:
            return True, "Cron job removed"
        return False, f"crontab write failed: {process.stderr}"
    except FileNotFoundError:
        return False, "crontab command not found"
    except Exception as e:
        return False, f"Error: {e}"


def check_cron_installed() -> bool:
    """Check if the scheduler cron job is installed."""
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and CRON_MARKER in result.stdout
    except (FileNotFoundError, Exception):
        return False
