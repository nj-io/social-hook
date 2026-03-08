"""Tests for hook installer (T32)."""

import json
import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from social_hook.setup.install import (
    COMMIT_HOOK_COMMAND,
    GIT_HOOK_MARKER_START,
    check_git_hook_installed,
    check_hook_installed,
    install_git_hook,
    install_hook,
    uninstall_git_hook,
    uninstall_hook,
)


class TestInstallHook:
    """Tests for install_hook."""

    def test_install_new(self, temp_dir):
        hooks_file = temp_dir / "settings.json"
        success, msg = install_hook(hooks_file)
        assert success is True
        assert "installed" in msg.lower()

        data = json.loads(hooks_file.read_text())
        assert "hooks" in data
        assert "PostToolUse" in data["hooks"]
        assert len(data["hooks"]["PostToolUse"]) == 1
        # New nested format: rule group has "hooks" array
        rule_group = data["hooks"]["PostToolUse"][0]
        assert "hooks" in rule_group
        assert rule_group["hooks"][0]["command"] == COMMIT_HOOK_COMMAND

    def test_install_idempotent(self, temp_dir):
        hooks_file = temp_dir / "settings.json"
        install_hook(hooks_file)
        success, msg = install_hook(hooks_file)
        assert success is True
        assert "already installed" in msg.lower()

        data = json.loads(hooks_file.read_text())
        assert len(data["hooks"]["PostToolUse"]) == 1

    def test_install_preserves_existing_hooks(self, temp_dir):
        hooks_file = temp_dir / "settings.json"
        existing = {
            "hooks": {
                "PostToolUse": [{"hooks": [{"type": "command", "command": "other-tool run"}]}]
            }
        }
        hooks_file.write_text(json.dumps(existing))

        install_hook(hooks_file)
        data = json.loads(hooks_file.read_text())
        assert len(data["hooks"]["PostToolUse"]) == 2

    def test_install_creates_parent_dirs(self, temp_dir):
        hooks_file = temp_dir / "sub" / "dir" / "settings.json"
        success, _ = install_hook(hooks_file)
        assert success is True
        assert hooks_file.exists()

    def test_install_creates_backup(self, temp_dir):
        hooks_file = temp_dir / "settings.json"
        hooks_file.write_text('{"hooks": {}}')
        install_hook(hooks_file)
        assert (temp_dir / "settings.json.bak").exists()

    def test_install_handles_invalid_json(self, temp_dir):
        hooks_file = temp_dir / "settings.json"
        hooks_file.write_text("not json")
        success, _ = install_hook(hooks_file)
        assert success is True
        data = json.loads(hooks_file.read_text())
        assert len(data["hooks"]["PostToolUse"]) == 1


class TestUninstallHook:
    """Tests for uninstall_hook."""

    def test_uninstall(self, temp_dir):
        hooks_file = temp_dir / "settings.json"
        install_hook(hooks_file)
        success, msg = uninstall_hook(hooks_file)
        assert success is True
        assert "removed" in msg.lower()

        data = json.loads(hooks_file.read_text())
        assert len(data["hooks"]["PostToolUse"]) == 0

    def test_uninstall_not_installed(self, temp_dir):
        hooks_file = temp_dir / "settings.json"
        hooks_file.write_text('{"hooks": {}}')
        success, msg = uninstall_hook(hooks_file)
        assert success is True
        assert "not installed" in msg.lower()

    def test_uninstall_no_file(self, temp_dir):
        hooks_file = temp_dir / "nonexistent.json"
        success, msg = uninstall_hook(hooks_file)
        assert success is True

    def test_uninstall_preserves_other_hooks(self, temp_dir):
        hooks_file = temp_dir / "settings.json"
        existing = {
            "hooks": {
                "PostToolUse": [
                    {"hooks": [{"type": "command", "command": "other-tool"}]},
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": COMMIT_HOOK_COMMAND}],
                    },
                ]
            }
        }
        hooks_file.write_text(json.dumps(existing))
        uninstall_hook(hooks_file)
        data = json.loads(hooks_file.read_text())
        assert len(data["hooks"]["PostToolUse"]) == 1
        assert data["hooks"]["PostToolUse"][0]["hooks"][0]["command"] == "other-tool"


class TestCheckHookInstalled:
    """Tests for check_hook_installed."""

    def test_installed(self, temp_dir):
        hooks_file = temp_dir / "settings.json"
        install_hook(hooks_file)
        assert check_hook_installed(hooks_file) is True

    def test_not_installed(self, temp_dir):
        hooks_file = temp_dir / "settings.json"
        hooks_file.write_text('{"hooks": {}}')
        assert check_hook_installed(hooks_file) is False

    def test_no_file(self, temp_dir):
        hooks_file = temp_dir / "nonexistent.json"
        assert check_hook_installed(hooks_file) is False


# ---------------------------------------------------------------------------
# Git post-commit hook tests
# ---------------------------------------------------------------------------


def _git_init(path: Path) -> Path:
    """Create a bare git repo at path and return it."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", str(path)], capture_output=True, check=True)
    return path


class TestInstallGitHook:
    """Tests for install_git_hook."""

    def test_install_new(self, tmp_path):
        repo = _git_init(tmp_path / "repo")
        success, msg = install_git_hook(repo)
        assert success is True
        assert "installed" in msg.lower()
        hook_file = repo / ".git" / "hooks" / "post-commit"
        assert hook_file.exists()
        content = hook_file.read_text()
        assert GIT_HOOK_MARKER_START in content
        assert "#!/bin/sh" in content

    def test_install_idempotent(self, tmp_path):
        repo = _git_init(tmp_path / "repo")
        install_git_hook(repo)
        success, msg = install_git_hook(repo)
        assert success is True
        assert "already installed" in msg.lower()
        # Marker appears exactly once
        content = (repo / ".git" / "hooks" / "post-commit").read_text()
        assert content.count(GIT_HOOK_MARKER_START) == 1

    def test_preserves_existing_hook(self, tmp_path):
        repo = _git_init(tmp_path / "repo")
        hooks_dir = repo / ".git" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        existing_hook = hooks_dir / "post-commit"
        existing_hook.write_text("#!/bin/sh\necho 'existing hook'\n")
        existing_hook.chmod(0o755)

        success, _ = install_git_hook(repo)
        assert success is True
        content = existing_hook.read_text()
        assert "echo 'existing hook'" in content
        assert GIT_HOOK_MARKER_START in content

    def test_not_a_git_repo(self, tmp_path):
        not_repo = tmp_path / "not-a-repo"
        not_repo.mkdir()
        success, msg = install_git_hook(not_repo)
        assert success is False
        assert "not a git repository" in msg.lower()


class TestUninstallGitHook:
    """Tests for uninstall_git_hook."""

    def test_uninstall(self, tmp_path):
        repo = _git_init(tmp_path / "repo")
        install_git_hook(repo)
        success, msg = uninstall_git_hook(repo)
        assert success is True
        assert "removed" in msg.lower()
        # Hook file should be deleted (was sole content)
        assert not (repo / ".git" / "hooks" / "post-commit").exists()

    def test_preserves_other_content(self, tmp_path):
        repo = _git_init(tmp_path / "repo")
        hooks_dir = repo / ".git" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        existing_hook = hooks_dir / "post-commit"
        existing_hook.write_text("#!/bin/sh\necho 'keep me'\n")
        existing_hook.chmod(0o755)

        install_git_hook(repo)
        success, msg = uninstall_git_hook(repo)
        assert success is True
        assert "removed" in msg.lower()
        content = existing_hook.read_text()
        assert "echo 'keep me'" in content
        assert GIT_HOOK_MARKER_START not in content

    def test_no_hook_file(self, tmp_path):
        repo = _git_init(tmp_path / "repo")
        success, msg = uninstall_git_hook(repo)
        assert success is True
        assert "no post-commit hook" in msg.lower()

    def test_hook_not_ours(self, tmp_path):
        repo = _git_init(tmp_path / "repo")
        hooks_dir = repo / ".git" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        (hooks_dir / "post-commit").write_text("#!/bin/sh\necho 'other'\n")
        success, msg = uninstall_git_hook(repo)
        assert success is True
        assert "not installed" in msg.lower()


class TestCheckGitHookInstalled:
    """Tests for check_git_hook_installed."""

    def test_installed(self, tmp_path):
        repo = _git_init(tmp_path / "repo")
        install_git_hook(repo)
        assert check_git_hook_installed(repo) is True

    def test_not_installed(self, tmp_path):
        repo = _git_init(tmp_path / "repo")
        assert check_git_hook_installed(repo) is False

    def test_no_hook_file(self, tmp_path):
        repo = _git_init(tmp_path / "repo")
        assert check_git_hook_installed(repo) is False


class TestGitHookCommand:
    """Tests for the git-hook CLI command."""

    @patch("social_hook.trigger.run_trigger")
    @patch("subprocess.run")
    def test_git_hook_calls_trigger(self, mock_subprocess, mock_trigger):
        """git-hook command detects repo and commit, calls run_trigger."""
        from social_hook.cli import app

        mock_subprocess.side_effect = [
            MagicMock(returncode=0, stdout="/tmp/repo\n", stderr=""),  # --show-toplevel
            MagicMock(returncode=0, stdout="abc123def\n", stderr=""),  # rev-parse HEAD
        ]
        mock_trigger.return_value = 0

        cli_runner = CliRunner()
        with patch("social_hook.filesystem.get_base_path", return_value=Path("/tmp/fake-base")):
            result = cli_runner.invoke(app, ["git-hook"])

        assert result.exit_code == 0
        mock_trigger.assert_called_once_with(commit_hash="abc123def", repo_path="/tmp/repo")

    @patch("subprocess.run")
    def test_git_hook_handles_not_a_repo(self, mock_subprocess):
        """git-hook exits gracefully when not in a git repo."""
        from social_hook.cli import app

        mock_subprocess.return_value = MagicMock(
            returncode=128, stdout="", stderr="not a git repository"
        )

        cli_runner = CliRunner()
        with patch("social_hook.filesystem.get_base_path", return_value=Path("/tmp/fake-base")):
            result = cli_runner.invoke(app, ["git-hook"])

        # Should not crash
        assert result.exit_code == 0


@pytest.mark.perf
class TestGitHookPerformance:
    """Timed performance tests for git hook operations."""

    def test_install_git_hook_under_1s(self, tmp_path):
        repo = _git_init(tmp_path / "repo")
        start = time.monotonic()
        install_git_hook(repo)
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, f"install_git_hook took {elapsed:.2f}s (limit: 1s)"

    def test_check_git_hook_under_100ms(self, tmp_path):
        repo = _git_init(tmp_path / "repo")
        install_git_hook(repo)
        start = time.monotonic()
        check_git_hook_installed(repo)
        elapsed = time.monotonic() - start
        assert elapsed < 0.1, f"check_git_hook_installed took {elapsed:.3f}s (limit: 0.1s)"

    def test_git_hook_cold_start_under_5s(self, tmp_path):
        """Run social-hook git-hook via subprocess in a real git repo."""
        import shutil

        repo = _git_init(tmp_path / "repo")
        # Create an initial commit so HEAD exists
        (repo / "README.md").write_text("test")
        subprocess.run(["git", "-C", str(repo), "add", "."], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "init", "--no-verify"],
            capture_output=True,
            check=True,
            env={
                **__import__("os").environ,
                "GIT_AUTHOR_NAME": "Test",
                "GIT_AUTHOR_EMAIL": "t@t",
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "t@t",
            },
        )

        binary = shutil.which("social-hook")
        if not binary:
            pytest.skip("social-hook not on PATH")

        start = time.monotonic()
        subprocess.run(
            [binary, "git-hook"],
            capture_output=True,
            text=True,
            cwd=str(repo),
            timeout=10,
        )
        elapsed = time.monotonic() - start
        assert elapsed < 5.0, f"git-hook cold start took {elapsed:.2f}s (limit: 5s)"
