"""Hook and cron installation for social-hook."""

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from social_hook.constants import PROJECT_SLUG

logger = logging.getLogger(__name__)

# --- Commit hook constants ---
COMMIT_HOOK_EVENT = "PostToolUse"
COMMIT_HOOK_MATCHER = "Bash"
COMMIT_HOOK_COMMAND = f"{PROJECT_SLUG} commit-hook"

OUR_HOOK = {
    "type": "command",
    "event": COMMIT_HOOK_EVENT,
    "matcher": COMMIT_HOOK_MATCHER,
    "command": COMMIT_HOOK_COMMAND,
}

# --- Narrative hook constants ---
NARRATIVE_HOOK_EVENT = "PreCompact"
NARRATIVE_HOOK_COMMAND = f"{PROJECT_SLUG} narrative-capture"
NARRATIVE_HOOK_TIMEOUT = 120

# Marker to identify our hook in crontab
CRON_MARKER = f"# {PROJECT_SLUG} scheduler"

# --- Git hook constants ---
GIT_HOOK_MARKER_START = f"# >>> {PROJECT_SLUG} post-commit hook >>>"
GIT_HOOK_MARKER_END = f"# <<< {PROJECT_SLUG} post-commit hook <<<"

GIT_HOOK_SCRIPT = f"""{GIT_HOOK_MARKER_START}
# Skip in CI environments
if [ -n "$CI" ] || [ -n "$GITHUB_ACTIONS" ] || [ -n "$JENKINS_URL" ] || [ -n "$GITLAB_CI" ] || [ -n "$CIRCLECI" ] || [ -n "$TRAVIS" ]; then
    exit 0
fi
# Skip if explicitly disabled
if [ "$SOCIAL_HOOK_SKIP" = "1" ]; then
    exit 0
fi
# Run in background to avoid slowing git commit
nohup {PROJECT_SLUG} git-hook > /dev/null 2>&1 &
{GIT_HOOK_MARKER_END}
"""


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
        return json.loads(settings_file.read_text())  # type: ignore[no-any-return]
    except (json.JSONDecodeError, OSError):
        return {}


def _write_settings_atomic(settings_file: Path, data: dict) -> None:
    """Write settings.json atomically (temp file + os.replace)."""
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=2) + "\n"
    fd, tmp_path = tempfile.mkstemp(dir=str(settings_file.parent), suffix=".tmp")
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


def _find_our_rule_group(rule_groups: list, command_str: str) -> int | None:
    """Find the index of our rule group by scanning nested hooks for command_str."""
    for i, group in enumerate(rule_groups):
        for hook in group.get("hooks", []):
            if hook.get("command") == command_str:
                return i
    return None


# ---------------------------------------------------------------------------
# Commit hook
# ---------------------------------------------------------------------------


def install_hook(
    settings_file: Path | None = None,
    *,
    skip_conflict_check: bool = False,
    git_hook_repo_paths: list[str] | None = None,
) -> tuple[bool, str]:
    """Install the Claude Code post-commit hook.

    Refuses if any registered project has a git post-commit hook installed —
    only one commit detection method is allowed at a time.

    Args:
        settings_file: Path to settings.json (default: ~/.claude/settings.json)
        skip_conflict_check: If True, skip the git hook conflict check.
        git_hook_repo_paths: Repo paths to check for git hooks. Callers with
            DB access should pass all registered project repo_paths.

    Returns:
        (success, message) tuple
    """
    if not skip_conflict_check and git_hook_repo_paths:
        for rp in git_hook_repo_paths:
            if check_git_hook_installed(rp):
                return False, (
                    f"Git post-commit hook is installed in {rp}. "
                    "Only one commit detection method is allowed at a time. "
                    "Uninstall git hooks first (social-hook project uninstall-hook)."
                )

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

    # Build rule group
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
    settings_file: Path | None = None,
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
    settings_file: Path | None = None,
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
    settings_file: Path | None = None,
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
        return True, "Claude Code narrative hook already installed"

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
    return True, f"Claude Code narrative hook installed at {settings_file}"


def uninstall_narrative_hook(
    settings_file: Path | None = None,
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
        return True, "Claude Code narrative hook was not installed"

    pre_compact.pop(idx)
    data["hooks"][NARRATIVE_HOOK_EVENT] = pre_compact

    _write_settings_atomic(settings_file, data)
    return True, "Claude Code narrative hook removed"


def check_narrative_hook_installed(
    settings_file: Path | None = None,
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
    binary = shutil.which(PROJECT_SLUG) or PROJECT_SLUG
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
        lines = [line for line in existing.splitlines() if CRON_MARKER not in line]
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


# ---------------------------------------------------------------------------
# Git post-commit hook
# ---------------------------------------------------------------------------


def _resolve_hooks_dir(repo_path: Path, git_dir: Path) -> Path:
    """Resolve the git hooks directory, respecting core.hooksPath."""
    result = subprocess.run(
        ["git", "-C", str(repo_path), "config", "--get", "core.hooksPath"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        hooks_dir = Path(result.stdout.strip())
        if not hooks_dir.is_absolute():
            hooks_dir = repo_path / hooks_dir
        return hooks_dir
    return git_dir / "hooks"


def _get_hook_file(repo_path: str | Path) -> tuple[Path | None, str | None]:
    """Resolve the post-commit hook file path for a git repo.

    Returns:
        (hook_file, error_message) — hook_file is None on error.
    """
    repo_path = Path(repo_path)
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            check=True,
        )
        git_dir = Path(result.stdout.strip())
        if not git_dir.is_absolute():
            git_dir = repo_path / git_dir
    except (subprocess.CalledProcessError, OSError):
        return None, f"Not a git repository: {repo_path}"
    hooks_dir = _resolve_hooks_dir(repo_path, git_dir)
    return hooks_dir / "post-commit", None


def install_git_hook(repo_path: str | Path) -> tuple[bool, str]:
    """Install the git post-commit hook in a repository.

    Refuses if the Claude Code commit hook is already installed — only one
    commit detection method is allowed at a time to avoid duplicate evaluations.

    Returns:
        (success, message) tuple
    """
    if check_hook_installed():
        return False, (
            "Claude Code commit hook is already installed. "
            "Only one commit detection method is allowed at a time. "
            "Uninstall the Claude Code hook first (social-hook setup uninstall commit_hook)."
        )
    hook_file, err = _get_hook_file(repo_path)
    if err:
        return False, err
    hook_file.parent.mkdir(parents=True, exist_ok=True)
    if hook_file.exists():
        existing = hook_file.read_text()
        if GIT_HOOK_MARKER_START in existing:
            return True, "Git hook already installed"
        new_content = existing.rstrip() + "\n\n" + GIT_HOOK_SCRIPT
    else:
        new_content = "#!/bin/sh\n" + GIT_HOOK_SCRIPT
    hook_file.write_text(new_content)
    hook_file.chmod(0o755)
    return True, f"Git hook installed at {hook_file}"


def uninstall_git_hook(repo_path: str | Path) -> tuple[bool, str]:
    """Remove the git post-commit hook from a repository.

    Returns:
        (success, message) tuple
    """
    hook_file, err = _get_hook_file(repo_path)
    if err:
        return False, err
    if not hook_file.exists():
        return True, "No post-commit hook found"
    content = hook_file.read_text()
    if GIT_HOOK_MARKER_START not in content:
        return True, "Git hook was not installed"
    pattern = (
        r"\n{0,2}"
        + re.escape(GIT_HOOK_MARKER_START)
        + r".*?"
        + re.escape(GIT_HOOK_MARKER_END)
        + r"\n{0,2}"
    )
    cleaned = re.sub(pattern, "", content, flags=re.DOTALL).strip()
    if not cleaned or cleaned == "#!/bin/sh":
        hook_file.unlink()
    else:
        hook_file.write_text(cleaned + "\n")
        hook_file.chmod(0o755)
    return True, "Git hook removed"


def check_git_hook_installed(repo_path: str | Path) -> bool:
    """Check if the git post-commit hook is installed in a repository."""
    hook_file, err = _get_hook_file(repo_path)
    if err:
        return False
    return hook_file.exists() and GIT_HOOK_MARKER_START in hook_file.read_text()
