"""Hook and cron installation for social-hook."""

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# --- Commit hook constants ---
COMMIT_HOOK_EVENT = "PostToolUse"
COMMIT_HOOK_MATCHER = {
    "tool": "Bash",
    "command_pattern": r"^git\s+(commit|merge|rebase|cherry-pick)",
}
COMMIT_HOOK_COMMAND = (
    "social-hook trigger --commit $(git rev-parse HEAD) --repo $(pwd)"
)

# Backward-compat: OUR_HOOK kept for existing test imports
OUR_HOOK = {
    "type": "command",
    "event": COMMIT_HOOK_EVENT,
    "matcher": COMMIT_HOOK_MATCHER,
    "command": COMMIT_HOOK_COMMAND,
}

# --- Narrative hook constants ---
NARRATIVE_HOOK_EVENT = "PreCompact"
NARRATIVE_HOOK_COMMAND = "social-hook narrative-capture"
NARRATIVE_HOOK_TIMEOUT = 120

# Marker to identify our hook in crontab
CRON_MARKER = "# social-hook scheduler"


def get_hooks_path() -> Path:
    """Get the Claude Code settings.json path."""
    return Path.home() / ".claude" / "settings.json"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_settings(settings_file: Path) -> dict:
    """Read settings.json, returning empty dict on missing/invalid file."""
    if not settings_file.exists():
        return {}
    try:
        return json.loads(settings_file.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _write_settings_atomic(settings_file: Path, data: dict) -> None:
    """Write settings.json atomically (temp file + os.replace)."""
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=2) + "\n"
    fd, tmp_path = tempfile.mkstemp(
        dir=str(settings_file.parent), suffix=".tmp"
    )
    closed = False
    try:
        os.write(fd, content.encode())
        os.close(fd)
        closed = True
        os.replace(tmp_path, str(settings_file))
    except Exception:
        if not closed:
            os.close(fd)
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _find_our_rule_group(
    rule_groups: list, command_str: str
) -> Optional[int]:
    """Find the index of our rule group by scanning nested hooks for command_str.

    Handles both the correct nested format and the old flat format.
    """
    for i, group in enumerate(rule_groups):
        # New nested format: group has "hooks" list of hook dicts
        for hook in group.get("hooks", []):
            if hook.get("command") == command_str:
                return i
        # Old flat format: group itself has "command" key
        if group.get("command") == command_str:
            return i
    return None


# ---------------------------------------------------------------------------
# Commit hook
# ---------------------------------------------------------------------------

def install_hook(
    settings_file: Optional[Path] = None,
) -> tuple[bool, str]:
    """Install the Claude Code post-commit hook.

    Args:
        settings_file: Path to settings.json (default: ~/.claude/settings.json)

    Returns:
        (success, message) tuple
    """
    if settings_file is None:
        settings_file = get_hooks_path()

    settings_file.parent.mkdir(parents=True, exist_ok=True)

    data = _read_settings(settings_file)

    # Backup existing file
    if settings_file.exists():
        backup = settings_file.with_suffix(".json.bak")
        shutil.copy2(settings_file, backup)

    # Ensure hooks structure
    if "hooks" not in data:
        data["hooks"] = {}

    post_tool_use = data["hooks"].get(COMMIT_HOOK_EVENT, [])

    # Check idempotency
    if _find_our_rule_group(post_tool_use, COMMIT_HOOK_COMMAND) is not None:
        return True, "Hook already installed"

    # Build rule group in correct nested format
    rule_group = {
        "matcher": COMMIT_HOOK_MATCHER,
        "hooks": [
            {"type": "command", "command": COMMIT_HOOK_COMMAND},
        ],
    }

    post_tool_use.append(rule_group)
    data["hooks"][COMMIT_HOOK_EVENT] = post_tool_use

    _write_settings_atomic(settings_file, data)
    return True, f"Hook installed at {settings_file}"


def uninstall_hook(
    settings_file: Optional[Path] = None,
) -> tuple[bool, str]:
    """Remove the social-hook commit hook from Claude Code settings.

    Returns:
        (success, message) tuple
    """
    if settings_file is None:
        settings_file = get_hooks_path()

    if not settings_file.exists():
        return True, "No settings file found"

    data = _read_settings(settings_file)
    if not data:
        return False, "Could not read settings file"

    post_tool_use = data.get("hooks", {}).get(COMMIT_HOOK_EVENT, [])
    idx = _find_our_rule_group(post_tool_use, COMMIT_HOOK_COMMAND)

    if idx is None:
        return True, "Hook was not installed"

    post_tool_use.pop(idx)
    data["hooks"][COMMIT_HOOK_EVENT] = post_tool_use

    _write_settings_atomic(settings_file, data)
    return True, "Hook removed"


def check_hook_installed(
    settings_file: Optional[Path] = None,
) -> bool:
    """Check if the social-hook commit hook is installed."""
    if settings_file is None:
        settings_file = get_hooks_path()

    if not settings_file.exists():
        return False

    data = _read_settings(settings_file)
    post_tool_use = data.get("hooks", {}).get(COMMIT_HOOK_EVENT, [])
    return _find_our_rule_group(post_tool_use, COMMIT_HOOK_COMMAND) is not None


# ---------------------------------------------------------------------------
# Narrative hook
# ---------------------------------------------------------------------------

def install_narrative_hook(
    settings_file: Optional[Path] = None,
) -> tuple[bool, str]:
    """Install the PreCompact narrative-capture hook.

    Args:
        settings_file: Path to settings.json (default: ~/.claude/settings.json)

    Returns:
        (success, message) tuple
    """
    if settings_file is None:
        settings_file = get_hooks_path()

    settings_file.parent.mkdir(parents=True, exist_ok=True)

    data = _read_settings(settings_file)

    # Backup existing file
    if settings_file.exists():
        backup = settings_file.with_suffix(".json.bak")
        shutil.copy2(settings_file, backup)

    if "hooks" not in data:
        data["hooks"] = {}

    pre_compact = data["hooks"].get(NARRATIVE_HOOK_EVENT, [])

    # Check idempotency
    if _find_our_rule_group(pre_compact, NARRATIVE_HOOK_COMMAND) is not None:
        return True, "Narrative hook already installed"

    # No matcher (runs on all compacts). Async because the LLM extraction
    # takes 10-20s and the transcript file survives compaction (append-only).
    rule_group = {
        "hooks": [
            {
                "type": "command",
                "command": NARRATIVE_HOOK_COMMAND,
                "timeout": NARRATIVE_HOOK_TIMEOUT,
                "async": True,
            },
        ],
    }

    pre_compact.append(rule_group)
    data["hooks"][NARRATIVE_HOOK_EVENT] = pre_compact

    _write_settings_atomic(settings_file, data)
    return True, f"Narrative hook installed at {settings_file}"


def uninstall_narrative_hook(
    settings_file: Optional[Path] = None,
) -> tuple[bool, str]:
    """Remove the narrative-capture hook from Claude Code settings.

    Returns:
        (success, message) tuple
    """
    if settings_file is None:
        settings_file = get_hooks_path()

    if not settings_file.exists():
        return True, "No settings file found"

    data = _read_settings(settings_file)
    if not data:
        return False, "Could not read settings file"

    pre_compact = data.get("hooks", {}).get(NARRATIVE_HOOK_EVENT, [])
    idx = _find_our_rule_group(pre_compact, NARRATIVE_HOOK_COMMAND)

    if idx is None:
        return True, "Narrative hook was not installed"

    pre_compact.pop(idx)
    data["hooks"][NARRATIVE_HOOK_EVENT] = pre_compact

    _write_settings_atomic(settings_file, data)
    return True, "Narrative hook removed"


def check_narrative_hook_installed(
    settings_file: Optional[Path] = None,
) -> bool:
    """Check if the narrative-capture hook is installed."""
    if settings_file is None:
        settings_file = get_hooks_path()

    if not settings_file.exists():
        return False

    data = _read_settings(settings_file)
    pre_compact = data.get("hooks", {}).get(NARRATIVE_HOOK_EVENT, [])
    return _find_our_rule_group(pre_compact, NARRATIVE_HOOK_COMMAND) is not None


# ---------------------------------------------------------------------------
# Cron installer (unchanged)
# ---------------------------------------------------------------------------

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
