"""Tests for collect_git_stats and is_git_repo in trigger_git.py."""

import subprocess

from social_hook.trigger_git import collect_git_stats, is_git_repo


class TestIsGitRepo:
    def test_git_repo(self, tmp_path):
        subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
        assert is_git_repo(str(tmp_path)) is True

    def test_non_git_directory(self, tmp_path):
        assert is_git_repo(str(tmp_path)) is False

    def test_nonexistent_directory(self):
        assert is_git_repo("/tmp/nonexistent_dir_12345") is False


class TestCollectGitStats:
    def test_returns_none_for_non_git(self, tmp_path):
        assert collect_git_stats(str(tmp_path)) is None

    def test_collects_stats_from_git_repo(self, tmp_path):
        # Initialize a git repo with a commit
        subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.email", "test@test.com"],
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.name", "Test"],
            capture_output=True,
        )
        (tmp_path / "README.md").write_text("# Test")
        subprocess.run(["git", "-C", str(tmp_path), "add", "."], capture_output=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "Initial commit"],
            capture_output=True,
        )

        stats = collect_git_stats(str(tmp_path))
        assert stats is not None
        assert stats["commit_count"] >= 1
        assert stats["contributor_count"] >= 1
        assert "first_commit_date" in stats
        assert "latest_commit_date" in stats
        assert stats["active_branch_count"] >= 1

    def test_returns_none_for_nonexistent_path(self):
        assert collect_git_stats("/tmp/nonexistent_path_12345") is None
