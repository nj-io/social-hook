"""Section R: Git Hooks & Web Registration scenarios."""

import tempfile
from pathlib import Path


def run(harness, runner):
    """R1-R6: Git hooks and project registration scenarios."""
    from social_hook.setup.install import (
        GIT_HOOK_MARKER_START,
        check_git_hook_installed,
        install_git_hook,
        uninstall_git_hook,
    )

    # R1: Install git post-commit hook
    def r1():
        success, msg = install_git_hook(str(harness.repo_path))
        assert success is True, f"install_git_hook failed: {msg}"
        assert check_git_hook_installed(str(harness.repo_path)), "Hook not detected after install"
        return msg

    runner.run_scenario("R1", "Install git post-commit hook", r1)

    # R2: Git hook install is idempotent
    def r2():
        success, msg = install_git_hook(str(harness.repo_path))
        assert success is True, f"idempotent install failed: {msg}"
        assert "already installed" in msg.lower(), f"Expected 'already installed', got: {msg}"
        # Verify marker appears exactly once
        hook_file = Path(harness.repo_path) / ".git" / "hooks" / "post-commit"
        content = hook_file.read_text()
        assert content.count(GIT_HOOK_MARKER_START) == 1, "Marker duplicated"
        return "Idempotent: OK"

    runner.run_scenario("R2", "Git hook install is idempotent", r2)

    # R3: Uninstall git post-commit hook
    def r3():
        success, msg = uninstall_git_hook(str(harness.repo_path))
        assert success is True, f"uninstall failed: {msg}"
        assert not check_git_hook_installed(str(harness.repo_path)), "Hook still detected"
        return msg

    runner.run_scenario("R3", "Uninstall git post-commit hook", r3)

    # R4: Hook preserves existing post-commit content
    def r4():
        hooks_dir = Path(harness.repo_path) / ".git" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        hook_file = hooks_dir / "post-commit"
        hook_file.write_text("#!/bin/sh\necho 'existing user hook'\n")
        hook_file.chmod(0o755)

        success, _ = install_git_hook(str(harness.repo_path))
        assert success is True
        content = hook_file.read_text()
        assert "echo 'existing user hook'" in content, "Existing content lost"
        assert GIT_HOOK_MARKER_START in content, "Our marker not added"

        # Uninstall should preserve user content
        success, _ = uninstall_git_hook(str(harness.repo_path))
        assert success is True
        content = hook_file.read_text()
        assert "echo 'existing user hook'" in content, "User content lost after uninstall"
        assert GIT_HOOK_MARKER_START not in content, "Our marker not removed"
        return "Preserved existing hook content through install/uninstall"

    runner.run_scenario("R4", "Hook preserves existing post-commit content", r4)

    # R5: Register project via CLI (use tempfile.TemporaryDirectory)
    def r5():
        import subprocess as sp

        from typer.testing import CliRunner

        from social_hook.cli import app

        cli = CliRunner()

        with tempfile.TemporaryDirectory() as td:
            repo_dir = Path(td) / "test-project"
            repo_dir.mkdir()
            sp.run(["git", "init", str(repo_dir)], capture_output=True, check=True)
            # Create minimal config
            config_dir = repo_dir / ".social-hook"
            config_dir.mkdir()
            (config_dir / "social-context.md").write_text("# Test\n")
            (config_dir / "content-config.yaml").write_text("platforms:\n  x:\n    enabled: true\n")

            result = cli.invoke(app, ["project", "register", str(repo_dir)])
            assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
            assert "registered" in result.output.lower() or "proj_" in result.output.lower()
            return "Registered temp project via CLI"

    runner.run_scenario("R5", "Register project via CLI (temp dir)", r5)

    # R6: Duplicate project registration fails
    def r6():
        import subprocess as sp

        from typer.testing import CliRunner

        from social_hook.cli import app

        cli = CliRunner()

        # Use a fresh temp repo — register it once, then try again
        with tempfile.TemporaryDirectory() as td:
            repo_dir = Path(td) / "dup-test"
            repo_dir.mkdir()
            sp.run(["git", "init", str(repo_dir)], capture_output=True, check=True)
            config_dir = repo_dir / ".social-hook"
            config_dir.mkdir()
            (config_dir / "social-context.md").write_text("# Test\n")
            (config_dir / "content-config.yaml").write_text("platforms:\n  x:\n    enabled: true\n")

            # First registration succeeds
            result = cli.invoke(app, ["project", "register", str(repo_dir), "--no-git-hook"])
            assert result.exit_code == 0, f"First register failed: {result.output}"

            # Second registration should fail with exit 1
            result = cli.invoke(app, ["project", "register", str(repo_dir)])
            assert result.exit_code == 1, f"Expected exit 1, got {result.exit_code}"
            assert "already" in result.output.lower(), f"Expected 'already' in: {result.output}"
            return "Blocked: duplicate registration"

    runner.run_scenario("R6", "Duplicate project registration fails", r6)
