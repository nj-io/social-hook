"""Tests for deep context assembly: resolve_commits diffs and resolve_topic_commits."""

import json
import sqlite3
from unittest.mock import MagicMock, patch

from social_hook.content_sources import (
    _assemble_diffs,
    _get_commit_diff,
    content_sources,
    resolve_commits,
    resolve_topic_commits,
)
from social_hook.db import operations as ops
from social_hook.filesystem import generate_id
from social_hook.models import ContentTopic, Decision, Project


class TestGetCommitDiff:
    """Tests for _get_commit_diff helper."""

    @patch("social_hook.content_sources.subprocess.run")
    def test_returns_diff_on_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="commit abc123\n\ndiff --git a/foo.py b/foo.py\n+new line\n",
        )
        result = _get_commit_diff("/tmp/repo", "abc123", 256000)
        assert result is not None
        assert "diff --git" in result
        mock_run.assert_called_once_with(
            ["git", "-C", "/tmp/repo", "show", "--stat", "--patch", "abc123"],
            capture_output=True,
            text=True,
            timeout=10,
        )

    @patch("social_hook.content_sources.subprocess.run")
    def test_returns_none_on_git_failure(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=128,
            stderr="fatal: bad object abc123",
        )
        result = _get_commit_diff("/tmp/repo", "abc123", 256000)
        assert result is None

    @patch("social_hook.content_sources.subprocess.run")
    def test_returns_none_on_timeout(self, mock_run):
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=10)
        result = _get_commit_diff("/tmp/repo", "abc123", 256000)
        assert result is None

    @patch("social_hook.content_sources.subprocess.run")
    def test_returns_none_when_git_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError("git not found")
        result = _get_commit_diff("/tmp/repo", "abc123", 256000)
        assert result is None

    @patch("social_hook.content_sources.subprocess.run")
    def test_truncates_at_max_file_size(self, mock_run):
        large_diff = "x" * 1000
        mock_run.return_value = MagicMock(returncode=0, stdout=large_diff)
        result = _get_commit_diff("/tmp/repo", "abc123", 500)
        assert result is not None
        assert len(result) < 1000
        assert "truncated at file size limit" in result


class TestAssembleDiffs:
    """Tests for _assemble_diffs token budget enforcement."""

    def test_empty_diffs_returns_empty(self):
        assert _assemble_diffs([], 10000) == ""

    def test_single_diff_included(self):
        result = _assemble_diffs([("abc12345", "diff content here")], 10000)
        assert "## Recent Commit Diffs" in result
        assert "abc12345" in result
        assert "diff content here" in result

    def test_token_budget_truncates_large_diff(self):
        """A very large diff gets truncated to fit within token budget."""
        large_diff = "x" * 50000
        # max_doc_tokens=100 -> max_chars=400 (100 * 4)
        result = _assemble_diffs([("abc12345", large_diff)], 100)
        assert "truncated at token budget" in result
        # Total output should be roughly within budget
        assert len(result) < 600  # Some overhead for headers

    def test_token_budget_drops_later_diffs(self):
        """When budget is exhausted, later diffs are dropped entirely."""
        diffs = [
            ("commit1a", "a" * 200),
            ("commit2b", "b" * 200),
            ("commit3c", "c" * 200),
        ]
        # Very small budget: 100 tokens = 400 chars
        result = _assemble_diffs(diffs, 100)
        # Should include at least the first commit but not all three
        assert "commit1a" in result
        # Third commit likely dropped
        assert result.count("```diff") <= 2


class TestResolveCommitsDeepContext:
    """Tests for the replacement resolve_commits that returns actual diffs."""

    def _seed_project(self, conn: sqlite3.Connection, repo_path: str = "/tmp/test") -> str:
        project = Project(
            id=generate_id("proj"),
            name="test-project",
            repo_path=repo_path,
        )
        ops.insert_project(conn, project)
        return project.id

    def _seed_decision(
        self, conn: sqlite3.Connection, project_id: str, commit_hash: str
    ) -> Decision:
        decision = Decision(
            id=generate_id("dec"),
            project_id=project_id,
            commit_hash=commit_hash,
            decision="draft",
            reasoning="Test reasoning",
        )
        ops.insert_decision(conn, decision)
        return decision

    @patch("social_hook.content_sources._get_commit_diff")
    @patch("social_hook.config.project.load_project_config")
    def test_returns_diff_content(self, mock_load_config, mock_get_diff, temp_db):
        """resolve_commits returns actual diff content, not reasoning strings."""
        from social_hook.config.project import ContextConfig, ProjectConfig

        mock_load_config.return_value = ProjectConfig(
            repo_path="/tmp/test",
            context=ContextConfig(max_doc_tokens=10000, max_file_size=256000),
        )
        mock_get_diff.return_value = "diff --git a/auth.py b/auth.py\n+def login():"

        project_id = self._seed_project(temp_db)
        self._seed_decision(temp_db, project_id, "abc12345678")

        result = resolve_commits(conn=temp_db, project_id=project_id)
        assert "diff --git" in result
        assert "login" in result
        # Should NOT contain reasoning strings
        assert "Test reasoning" not in result

    def test_returns_empty_no_project(self, temp_db):
        """Returns empty when project doesn't exist."""
        result = resolve_commits(conn=temp_db, project_id="nonexistent")
        assert result == ""

    def test_returns_empty_no_decisions(self, temp_db):
        """Returns empty when no decisions exist."""
        project_id = self._seed_project(temp_db)
        result = resolve_commits(conn=temp_db, project_id=project_id)
        assert result == ""

    @patch("social_hook.content_sources._get_commit_diff")
    @patch("social_hook.config.project.load_project_config")
    def test_skips_missing_commits(self, mock_load_config, mock_get_diff, temp_db):
        """Missing commit hashes are skipped with warning, not crashing."""
        from social_hook.config.project import ContextConfig, ProjectConfig

        mock_load_config.return_value = ProjectConfig(
            repo_path="/tmp/test",
            context=ContextConfig(max_doc_tokens=10000, max_file_size=256000),
        )
        # First commit exists, second doesn't
        mock_get_diff.side_effect = [
            "diff --git a/foo.py\n+line1",
            None,  # missing commit
        ]

        project_id = self._seed_project(temp_db)
        self._seed_decision(temp_db, project_id, "good_commit1")
        self._seed_decision(temp_db, project_id, "bad_commit2")

        result = resolve_commits(conn=temp_db, project_id=project_id)
        assert "good_com" in result
        # Should not crash, and should still return the good commit

    @patch("social_hook.content_sources._get_commit_diff")
    @patch("social_hook.config.project.load_project_config")
    def test_prioritizes_significant_commits(self, mock_load_config, mock_get_diff, temp_db):
        """Notable/significant commits appear before routine/trivial."""
        from social_hook.config.project import ContextConfig, ProjectConfig

        mock_load_config.return_value = ProjectConfig(
            repo_path="/tmp/test",
            context=ContextConfig(max_doc_tokens=10000, max_file_size=256000),
        )
        mock_get_diff.side_effect = lambda repo_path, commit_hash, max_file_size: (
            f"diff for {commit_hash}"
        )

        project_id = self._seed_project(temp_db)
        # Create two decisions
        self._seed_decision(temp_db, project_id, "trivial_hash")
        self._seed_decision(temp_db, project_id, "notable_hash")

        # Insert evaluation cycles with classification data
        temp_db.execute(
            """INSERT INTO evaluation_cycles (id, project_id, trigger_type, trigger_ref, commit_analysis_json)
            VALUES (?, ?, 'commit', ?, ?)""",
            (
                "cycle1",
                project_id,
                "trivial_hash",
                json.dumps({"commit_analysis": {"classification": "trivial"}}),
            ),
        )
        temp_db.execute(
            """INSERT INTO evaluation_cycles (id, project_id, trigger_type, trigger_ref, commit_analysis_json)
            VALUES (?, ?, 'commit', ?, ?)""",
            (
                "cycle2",
                project_id,
                "notable_hash",
                json.dumps({"commit_analysis": {"classification": "notable"}}),
            ),
        )
        temp_db.commit()

        result = resolve_commits(conn=temp_db, project_id=project_id)
        # Notable should appear before trivial
        notable_pos = result.find("notable_")
        trivial_pos = result.find("trivial_")
        assert notable_pos < trivial_pos


class TestResolveTopicCommits:
    """Tests for resolve_topic_commits with topic_commits table data."""

    def _seed_project(self, conn: sqlite3.Connection, repo_path: str = "/tmp/test") -> str:
        project = Project(
            id=generate_id("proj"),
            name="test-project",
            repo_path=repo_path,
        )
        ops.insert_project(conn, project)
        return project.id

    def _seed_topic(
        self, conn: sqlite3.Connection, project_id: str, topic_name: str = "auth system"
    ) -> str:
        topic = ContentTopic(
            id=generate_id("topic"),
            project_id=project_id,
            strategy="building-public",
            topic=topic_name,
            description="Auth system topic",
        )
        ops.insert_content_topic(conn, topic)
        return topic.id

    def test_returns_empty_no_topic_id(self, temp_db):
        """Returns empty when no topic_id provided."""
        result = resolve_topic_commits(conn=temp_db, project_id="proj-1")
        assert result == ""

    def test_returns_empty_no_project(self, temp_db):
        """Returns empty when project doesn't exist."""
        result = resolve_topic_commits(conn=temp_db, project_id="nonexistent", topic_id="t-1")
        assert result == ""

    @patch("social_hook.content_sources._get_commit_diff")
    @patch("social_hook.config.project.load_project_config")
    def test_returns_diffs_for_topic(self, mock_load_config, mock_get_diff, temp_db):
        """Returns consolidated diffs from topic_commits table."""
        from social_hook.config.project import ContextConfig, ProjectConfig

        mock_load_config.return_value = ProjectConfig(
            repo_path="/tmp/test",
            context=ContextConfig(max_doc_tokens=10000, max_file_size=256000),
        )
        mock_get_diff.side_effect = lambda repo_path, commit_hash, max_file_size: (
            f"diff --git a/auth.py\n+code for {commit_hash}"
        )

        project_id = self._seed_project(temp_db)
        topic_id = self._seed_topic(temp_db, project_id, "auth system")

        # Insert topic_commits
        temp_db.execute(
            "INSERT INTO topic_commits (topic_id, commit_hash, matched_tag) VALUES (?, ?, ?)",
            (topic_id, "commit_aaa", "auth"),
        )
        temp_db.execute(
            "INSERT INTO topic_commits (topic_id, commit_hash, matched_tag) VALUES (?, ?, ?)",
            (topic_id, "commit_bbb", "auth"),
        )
        temp_db.commit()

        result = resolve_topic_commits(conn=temp_db, project_id=project_id, topic_id=topic_id)
        assert "auth system" in result
        assert "2 commits" in result
        assert "commit_a" in result
        assert "commit_b" in result

    @patch("social_hook.content_sources._get_commit_diff")
    @patch("social_hook.config.project.load_project_config")
    def test_returns_empty_no_topic_commits(self, mock_load_config, mock_get_diff, temp_db):
        """Returns empty when topic has no commits in topic_commits table."""
        from social_hook.config.project import ContextConfig, ProjectConfig

        mock_load_config.return_value = ProjectConfig(
            repo_path="/tmp/test",
            context=ContextConfig(max_doc_tokens=10000, max_file_size=256000),
        )

        project_id = self._seed_project(temp_db)
        topic_id = self._seed_topic(temp_db, project_id)

        result = resolve_topic_commits(conn=temp_db, project_id=project_id, topic_id=topic_id)
        assert result == ""

    @patch("social_hook.content_sources._get_commit_diff")
    @patch("social_hook.config.project.load_project_config")
    def test_skips_missing_commits(self, mock_load_config, mock_get_diff, temp_db):
        """Missing commits are skipped gracefully."""
        from social_hook.config.project import ContextConfig, ProjectConfig

        mock_load_config.return_value = ProjectConfig(
            repo_path="/tmp/test",
            context=ContextConfig(max_doc_tokens=10000, max_file_size=256000),
        )
        # Query orders by matched_at DESC, so bad_hash (inserted second) comes first
        mock_get_diff.side_effect = [
            None,  # bad_hash — missing commit
            "diff --git a/good.py\n+good code",  # good_hash
        ]

        project_id = self._seed_project(temp_db)
        topic_id = self._seed_topic(temp_db, project_id)

        temp_db.execute(
            "INSERT INTO topic_commits (topic_id, commit_hash, matched_tag) VALUES (?, ?, ?)",
            (topic_id, "good_hash", "tag1"),
        )
        temp_db.execute(
            "INSERT INTO topic_commits (topic_id, commit_hash, matched_tag) VALUES (?, ?, ?)",
            (topic_id, "bad_hash", "tag1"),
        )
        temp_db.commit()

        result = resolve_topic_commits(conn=temp_db, project_id=project_id, topic_id=topic_id)
        assert "good_has" in result
        assert "1 commits" in result


class TestRegistrySingleton:
    """Verify new resolvers are registered on the module singleton."""

    def test_topic_commits_registered(self):
        assert "topic_commits" in content_sources._resolvers

    def test_all_resolvers_present(self):
        expected = {"brief", "commits", "topic", "topic_commits", "operator_suggestion"}
        assert set(content_sources._resolvers.keys()) == expected
