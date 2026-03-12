"""Tests for hook installer: commit hook (nested format) and narrative hook."""

import json

from social_hook.setup.install import (
    COMMIT_HOOK_COMMAND,
    COMMIT_HOOK_MATCHER,
    NARRATIVE_HOOK_COMMAND,
    NARRATIVE_HOOK_TIMEOUT,
    check_hook_installed,
    check_narrative_hook_installed,
    install_hook,
    install_narrative_hook,
    uninstall_hook,
    uninstall_narrative_hook,
)


class TestCommitHookInstall:
    """Commit hook creates correct nested structure in settings.json."""

    def test_install_creates_nested_structure(self, temp_dir):
        sf = temp_dir / "settings.json"
        success, msg = install_hook(sf)
        assert success is True
        assert "installed" in msg.lower()

        data = json.loads(sf.read_text())
        assert "hooks" in data
        groups = data["hooks"]["PostToolUse"]
        assert len(groups) == 1
        group = groups[0]
        # Rule group has matcher + hooks list
        assert group["matcher"] == COMMIT_HOOK_MATCHER
        assert len(group["hooks"]) == 1
        assert group["hooks"][0]["type"] == "command"
        assert group["hooks"][0]["command"] == COMMIT_HOOK_COMMAND

    def test_install_idempotent(self, temp_dir):
        sf = temp_dir / "settings.json"
        install_hook(sf)
        success, msg = install_hook(sf)
        assert success is True
        assert "already installed" in msg.lower()

        data = json.loads(sf.read_text())
        assert len(data["hooks"]["PostToolUse"]) == 1

    def test_install_preserves_existing_hooks(self, temp_dir):
        sf = temp_dir / "settings.json"
        existing = {
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": "other-tool run"}],
                    }
                ]
            }
        }
        sf.write_text(json.dumps(existing))

        install_hook(sf)
        data = json.loads(sf.read_text())
        assert len(data["hooks"]["PostToolUse"]) == 2

    def test_install_creates_parent_dirs(self, temp_dir):
        sf = temp_dir / "sub" / "dir" / "settings.json"
        success, _ = install_hook(sf)
        assert success is True
        assert sf.exists()

    def test_install_creates_backup(self, temp_dir):
        sf = temp_dir / "settings.json"
        sf.write_text('{"hooks": {}}')
        install_hook(sf)
        assert (temp_dir / "settings.json.bak").exists()

    def test_install_handles_invalid_json(self, temp_dir):
        sf = temp_dir / "settings.json"
        sf.write_text("not json")
        success, _ = install_hook(sf)
        assert success is True
        data = json.loads(sf.read_text())
        assert len(data["hooks"]["PostToolUse"]) == 1

    def test_install_no_existing_file(self, temp_dir):
        sf = temp_dir / "settings.json"
        assert not sf.exists()
        success, _ = install_hook(sf)
        assert success is True
        assert sf.exists()
        data = json.loads(sf.read_text())
        assert len(data["hooks"]["PostToolUse"]) == 1


class TestCommitHookUninstall:
    """Commit hook uninstall removes the hook."""

    def test_uninstall(self, temp_dir):
        sf = temp_dir / "settings.json"
        install_hook(sf)
        success, msg = uninstall_hook(sf)
        assert success is True
        assert "removed" in msg.lower()

        data = json.loads(sf.read_text())
        assert len(data["hooks"]["PostToolUse"]) == 0

    def test_uninstall_not_installed(self, temp_dir):
        sf = temp_dir / "settings.json"
        sf.write_text('{"hooks": {}}')
        success, msg = uninstall_hook(sf)
        assert success is True
        assert "not installed" in msg.lower()

    def test_uninstall_no_file(self, temp_dir):
        sf = temp_dir / "nonexistent.json"
        success, msg = uninstall_hook(sf)
        assert success is True

    def test_uninstall_preserves_other_hooks(self, temp_dir):
        sf = temp_dir / "settings.json"
        existing = {
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": "other-tool"}],
                    },
                ]
            }
        }
        sf.write_text(json.dumps(existing))
        install_hook(sf)
        # Now we have 2 rule groups
        uninstall_hook(sf)
        data = json.loads(sf.read_text())
        assert len(data["hooks"]["PostToolUse"]) == 1
        assert data["hooks"]["PostToolUse"][0]["hooks"][0]["command"] == "other-tool"


class TestCommitHookCheckInstalled:
    """check_hook_installed works with nested structure."""

    def test_installed(self, temp_dir):
        sf = temp_dir / "settings.json"
        install_hook(sf)
        assert check_hook_installed(sf) is True

    def test_not_installed(self, temp_dir):
        sf = temp_dir / "settings.json"
        sf.write_text('{"hooks": {}}')
        assert check_hook_installed(sf) is False

    def test_no_file(self, temp_dir):
        sf = temp_dir / "nonexistent.json"
        assert check_hook_installed(sf) is False


class TestNarrativeHookInstall:
    """Narrative hook install creates correct structure under PreCompact."""

    def test_install_creates_structure(self, temp_dir):
        sf = temp_dir / "settings.json"
        success, msg = install_narrative_hook(sf)
        assert success is True
        assert "installed" in msg.lower()

        data = json.loads(sf.read_text())
        groups = data["hooks"]["PreCompact"]
        assert len(groups) == 1
        group = groups[0]
        # No matcher for narrative hook
        assert "matcher" not in group
        assert len(group["hooks"]) == 1
        hook = group["hooks"][0]
        assert hook["type"] == "command"
        assert hook["command"] == NARRATIVE_HOOK_COMMAND
        assert hook["timeout"] == NARRATIVE_HOOK_TIMEOUT

    def test_install_idempotent(self, temp_dir):
        sf = temp_dir / "settings.json"
        install_narrative_hook(sf)
        success, msg = install_narrative_hook(sf)
        assert success is True
        assert "already installed" in msg.lower()

        data = json.loads(sf.read_text())
        assert len(data["hooks"]["PreCompact"]) == 1

    def test_install_no_existing_file(self, temp_dir):
        sf = temp_dir / "settings.json"
        assert not sf.exists()
        success, _ = install_narrative_hook(sf)
        assert success is True
        assert sf.exists()


class TestNarrativeHookUninstall:
    """Narrative hook uninstall removes the hook."""

    def test_uninstall(self, temp_dir):
        sf = temp_dir / "settings.json"
        install_narrative_hook(sf)
        success, msg = uninstall_narrative_hook(sf)
        assert success is True
        assert "removed" in msg.lower()

        data = json.loads(sf.read_text())
        assert len(data["hooks"]["PreCompact"]) == 0

    def test_uninstall_not_installed(self, temp_dir):
        sf = temp_dir / "settings.json"
        sf.write_text('{"hooks": {}}')
        success, msg = uninstall_narrative_hook(sf)
        assert success is True
        assert "not installed" in msg.lower()

    def test_uninstall_no_file(self, temp_dir):
        sf = temp_dir / "nonexistent.json"
        success, _ = uninstall_narrative_hook(sf)
        assert success is True


class TestNarrativeHookCheckInstalled:
    """check_narrative_hook_installed works."""

    def test_installed(self, temp_dir):
        sf = temp_dir / "settings.json"
        install_narrative_hook(sf)
        assert check_narrative_hook_installed(sf) is True

    def test_not_installed(self, temp_dir):
        sf = temp_dir / "settings.json"
        sf.write_text('{"hooks": {}}')
        assert check_narrative_hook_installed(sf) is False

    def test_no_file(self, temp_dir):
        sf = temp_dir / "nonexistent.json"
        assert check_narrative_hook_installed(sf) is False


class TestHooksCoexist:
    """Both hooks can coexist in the same settings.json."""

    def test_both_hooks_in_same_file(self, temp_dir):
        sf = temp_dir / "settings.json"
        install_hook(sf)
        install_narrative_hook(sf)

        data = json.loads(sf.read_text())
        assert "PostToolUse" in data["hooks"]
        assert "PreCompact" in data["hooks"]
        assert len(data["hooks"]["PostToolUse"]) == 1
        assert len(data["hooks"]["PreCompact"]) == 1

        assert check_hook_installed(sf) is True
        assert check_narrative_hook_installed(sf) is True

    def test_uninstall_one_preserves_other(self, temp_dir):
        sf = temp_dir / "settings.json"
        install_hook(sf)
        install_narrative_hook(sf)

        uninstall_hook(sf)
        assert check_hook_installed(sf) is False
        assert check_narrative_hook_installed(sf) is True

    def test_uninstall_other_preserves_one(self, temp_dir):
        sf = temp_dir / "settings.json"
        install_hook(sf)
        install_narrative_hook(sf)

        uninstall_narrative_hook(sf)
        assert check_hook_installed(sf) is True
        assert check_narrative_hook_installed(sf) is False


class TestAtomicWritePreservesKeys:
    """Atomic write: non-hook keys are preserved after install."""

    def test_preserves_env_key(self, temp_dir):
        sf = temp_dir / "settings.json"
        sf.write_text(
            json.dumps(
                {
                    "env": {"FOO": "bar"},
                    "enabledPlugins": ["plugin-a"],
                    "permissions": {"allow": ["read"]},
                }
            )
        )

        install_hook(sf)
        data = json.loads(sf.read_text())
        assert data["env"] == {"FOO": "bar"}
        assert data["enabledPlugins"] == ["plugin-a"]
        assert data["permissions"] == {"allow": ["read"]}
        assert "hooks" in data

    def test_preserves_keys_on_narrative_install(self, temp_dir):
        sf = temp_dir / "settings.json"
        sf.write_text(
            json.dumps(
                {
                    "env": {"KEY": "val"},
                    "hooks": {
                        "PostToolUse": [
                            {
                                "matcher": COMMIT_HOOK_MATCHER,
                                "hooks": [{"type": "command", "command": COMMIT_HOOK_COMMAND}],
                            }
                        ]
                    },
                }
            )
        )

        install_narrative_hook(sf)
        data = json.loads(sf.read_text())
        assert data["env"] == {"KEY": "val"}
        assert len(data["hooks"]["PostToolUse"]) == 1
        assert len(data["hooks"]["PreCompact"]) == 1
