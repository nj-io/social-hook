"""Tests for hook installer (T32)."""

import json
from pathlib import Path

import pytest

from social_hook.setup.install import (
    OUR_HOOK,
    check_hook_installed,
    install_hook,
    uninstall_hook,
)


class TestInstallHook:
    """Tests for install_hook."""

    def test_install_new(self, temp_dir):
        hooks_file = temp_dir / "hooks.json"
        success, msg = install_hook(hooks_file)
        assert success is True
        assert "installed" in msg.lower()

        data = json.loads(hooks_file.read_text())
        assert "hooks" in data
        assert "PostToolUse" in data["hooks"]
        assert len(data["hooks"]["PostToolUse"]) == 1
        assert data["hooks"]["PostToolUse"][0]["command"] == OUR_HOOK["command"]

    def test_install_idempotent(self, temp_dir):
        hooks_file = temp_dir / "hooks.json"
        install_hook(hooks_file)
        success, msg = install_hook(hooks_file)
        assert success is True
        assert "already installed" in msg.lower()

        data = json.loads(hooks_file.read_text())
        assert len(data["hooks"]["PostToolUse"]) == 1

    def test_install_preserves_existing_hooks(self, temp_dir):
        hooks_file = temp_dir / "hooks.json"
        existing = {
            "hooks": {
                "PostToolUse": [
                    {"type": "command", "command": "other-tool run"}
                ]
            }
        }
        hooks_file.write_text(json.dumps(existing))

        install_hook(hooks_file)
        data = json.loads(hooks_file.read_text())
        assert len(data["hooks"]["PostToolUse"]) == 2

    def test_install_creates_parent_dirs(self, temp_dir):
        hooks_file = temp_dir / "sub" / "dir" / "hooks.json"
        success, _ = install_hook(hooks_file)
        assert success is True
        assert hooks_file.exists()

    def test_install_creates_backup(self, temp_dir):
        hooks_file = temp_dir / "hooks.json"
        hooks_file.write_text('{"hooks": {}}')
        install_hook(hooks_file)
        assert (temp_dir / "hooks.json.bak").exists()

    def test_install_handles_invalid_json(self, temp_dir):
        hooks_file = temp_dir / "hooks.json"
        hooks_file.write_text("not json")
        success, _ = install_hook(hooks_file)
        assert success is True
        data = json.loads(hooks_file.read_text())
        assert len(data["hooks"]["PostToolUse"]) == 1


class TestUninstallHook:
    """Tests for uninstall_hook."""

    def test_uninstall(self, temp_dir):
        hooks_file = temp_dir / "hooks.json"
        install_hook(hooks_file)
        success, msg = uninstall_hook(hooks_file)
        assert success is True
        assert "removed" in msg.lower()

        data = json.loads(hooks_file.read_text())
        assert len(data["hooks"]["PostToolUse"]) == 0

    def test_uninstall_not_installed(self, temp_dir):
        hooks_file = temp_dir / "hooks.json"
        hooks_file.write_text('{"hooks": {}}')
        success, msg = uninstall_hook(hooks_file)
        assert success is True
        assert "not installed" in msg.lower()

    def test_uninstall_no_file(self, temp_dir):
        hooks_file = temp_dir / "nonexistent.json"
        success, msg = uninstall_hook(hooks_file)
        assert success is True

    def test_uninstall_preserves_other_hooks(self, temp_dir):
        hooks_file = temp_dir / "hooks.json"
        existing = {
            "hooks": {
                "PostToolUse": [
                    {"type": "command", "command": "other-tool"},
                    OUR_HOOK,
                ]
            }
        }
        hooks_file.write_text(json.dumps(existing))
        uninstall_hook(hooks_file)
        data = json.loads(hooks_file.read_text())
        assert len(data["hooks"]["PostToolUse"]) == 1
        assert data["hooks"]["PostToolUse"][0]["command"] == "other-tool"


class TestCheckHookInstalled:
    """Tests for check_hook_installed."""

    def test_installed(self, temp_dir):
        hooks_file = temp_dir / "hooks.json"
        install_hook(hooks_file)
        assert check_hook_installed(hooks_file) is True

    def test_not_installed(self, temp_dir):
        hooks_file = temp_dir / "hooks.json"
        hooks_file.write_text('{"hooks": {}}')
        assert check_hook_installed(hooks_file) is False

    def test_no_file(self, temp_dir):
        hooks_file = temp_dir / "nonexistent.json"
        assert check_hook_installed(hooks_file) is False
