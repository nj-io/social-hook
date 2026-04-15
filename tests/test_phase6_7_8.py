"""Tests for Phase 6 (Non-Git), Phase 7 (Create Flow), Phase 8a/8c (Vehicle UX)."""

import sqlite3

import pytest

from social_hook.bot.notifications import format_draft_review
from social_hook.llm.prompts import assemble_expert_prompt

# =============================================================================
# Phase 6: Non-Git Project Registration
# =============================================================================


class TestRegisterProjectNonGit:
    """register_project() should work for both git and non-git dirs."""

    def _setup_db(self, conn):
        """Minimal schema for project registration tests."""
        from social_hook.db.schema import SCHEMA_DDL

        conn.executescript(SCHEMA_DDL)

    def test_register_git_project(self, tmp_path):
        """Git project: extracts origin, returns repo_origin."""
        import subprocess

        # Create a real git repo
        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.email", "test@test.com"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.name", "Test"],
            check=True,
            capture_output=True,
        )
        # Add a remote
        subprocess.run(
            [
                "git",
                "-C",
                str(tmp_path),
                "remote",
                "add",
                "origin",
                "https://github.com/test/repo.git",
            ],
            check=True,
            capture_output=True,
        )

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        self._setup_db(conn)

        from social_hook.db.operations import register_project

        project, repo_origin = register_project(conn, str(tmp_path), "my-git-project")
        assert project.name == "my-git-project"
        assert repo_origin == "https://github.com/test/repo.git"
        conn.close()

    def test_register_non_git_project(self, tmp_path):
        """Non-git directory: no ValueError, repo_origin=None."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        self._setup_db(conn)

        from social_hook.db.operations import register_project

        project, repo_origin = register_project(conn, str(tmp_path), "plain-dir")
        assert project.name == "plain-dir"
        assert repo_origin is None
        assert project.repo_path == str(tmp_path.resolve())
        conn.close()

    def test_register_non_git_no_name(self, tmp_path):
        """Non-git directory with no name: uses directory name."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        self._setup_db(conn)

        from social_hook.db.operations import register_project

        project, repo_origin = register_project(conn, str(tmp_path))
        assert project.name == tmp_path.name
        assert repo_origin is None
        conn.close()

    def test_register_duplicate_raises(self, tmp_path):
        """Duplicate path raises ValueError."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        self._setup_db(conn)

        from social_hook.db.operations import register_project

        register_project(conn, str(tmp_path), "first")
        with pytest.raises(ValueError, match="already registered"):
            register_project(conn, str(tmp_path), "second")
        conn.close()


# =============================================================================
# Phase 8a: Vehicle in Notification Header
# =============================================================================


class TestVehicleInNotification:
    """format_draft_review() shows vehicle in the platform line."""

    def test_vehicle_thread_in_header(self):
        msg = format_draft_review(
            project_name="test",
            commit_hash="abc1234",
            commit_message="feat: add thread",
            platform="x",
            content="Thread content here",
            vehicle="thread",
        )
        # Vehicle should appear in platform line
        assert "x \u00b7 thread" in msg

    def test_vehicle_article_in_header(self):
        msg = format_draft_review(
            project_name="test",
            commit_hash="abc1234",
            commit_message="feat: add article",
            platform="x",
            content="Article content here",
            vehicle="article",
        )
        assert "x \u00b7 article" in msg

    def test_vehicle_single_shown(self):
        """Single vehicle should be shown in platform line."""
        msg = format_draft_review(
            project_name="test",
            commit_hash="abc1234",
            commit_message="feat: single",
            platform="x",
            content="Single post",
            vehicle="single",
        )
        assert "x \u00b7 single" in msg

    def test_vehicle_none_defaults_to_single(self):
        """No vehicle defaults to single in platform line."""
        msg = format_draft_review(
            project_name="test",
            commit_hash="abc1234",
            commit_message="feat",
            platform="x",
            content="Some post",
            vehicle=None,
        )
        assert "x \u00b7 single" in msg

    def test_article_truncation(self):
        """Article content >500 chars should be truncated."""
        long_content = "x" * 600
        msg = format_draft_review(
            project_name="test",
            commit_hash="abc",
            commit_message="msg",
            platform="x",
            content=long_content,
            vehicle="article",
        )
        assert "view full in dashboard" in msg
        # Should have 500 chars of x, not all 600
        assert "x" * 501 not in msg

    def test_non_article_no_truncation(self):
        """Non-article content should not be truncated even if long."""
        long_content = "x" * 600
        msg = format_draft_review(
            project_name="test",
            commit_hash="abc",
            commit_message="msg",
            platform="x",
            content=long_content,
            vehicle="thread",
        )
        assert "view full in dashboard" not in msg
        assert "x" * 600 in msg


# =============================================================================
# Phase 8a: Vehicle in Expert Prompt
# =============================================================================


class TestVehicleInExpertPrompt:
    """assemble_expert_prompt() includes vehicle in Current Draft section."""

    def test_vehicle_included(self):
        class MockDraft:
            platform = "x"
            vehicle = "thread"
            content = "Thread content"
            media_type = None
            media_spec = None

        prompt = assemble_expert_prompt(
            prompt="Base prompt",
            draft=MockDraft(),
            user_message="Make this better",
            escalation_reason="User requested edit",
        )
        assert "Vehicle: thread" in prompt
        assert "Platform: x" in prompt

    def test_vehicle_none_not_shown(self):
        class MockDraft:
            platform = "x"
            vehicle = None
            content = "Single post"
            media_type = None
            media_spec = None

        prompt = assemble_expert_prompt(
            prompt="Base prompt",
            draft=MockDraft(),
            user_message="Edit this",
            escalation_reason="Escalated",
        )
        assert "Vehicle:" not in prompt

    def test_vehicle_missing_attr_not_shown(self):
        """Draft without vehicle attribute should not crash."""

        class MockDraft:
            platform = "x"
            content = "Old draft"

        prompt = assemble_expert_prompt(
            prompt="Base prompt",
            draft=MockDraft(),
            user_message="Edit this",
            escalation_reason="Escalated",
        )
        assert "Vehicle:" not in prompt
        assert "Platform: x" in prompt


# =============================================================================
# Phase 7: Create Content Endpoint
# =============================================================================


class TestCreateContentEndpoint:
    """Tests for POST /api/projects/{id}/create-content."""

    def _setup_db(self, conn):
        from social_hook.db.schema import SCHEMA_DDL

        conn.executescript(SCHEMA_DDL)

    def test_create_content_rejects_unknown_keys(self):
        """check_unknown_keys(strict=True) should reject unknown fields."""
        from social_hook.errors import ConfigError
        from social_hook.parsing import check_unknown_keys

        known_keys = {"idea", "vehicle", "reference_files", "target_id"}
        with pytest.raises(ConfigError):
            check_unknown_keys(
                {"idea": "test", "unknown_field": "bad"},
                known_keys,
                "create_content",
                strict=True,
            )

    def test_create_content_accepts_valid_keys(self):
        """Valid keys should pass check_unknown_keys."""
        from social_hook.parsing import check_unknown_keys

        known_keys = {"idea", "vehicle", "reference_files", "target_id"}
        # Should not raise
        check_unknown_keys(
            {"idea": "test", "vehicle": "article"},
            known_keys,
            "create_content",
            strict=True,
        )

    def test_commit_info_from_operator_input(self):
        """CommitInfo.from_operator_input creates valid synthetic commit."""
        from social_hook.models.core import CommitInfo

        commit = CommitInfo.from_operator_input("My idea", reference_context="ref text")
        assert commit.message == "My idea"
        assert commit.diff == "ref text"
        assert commit.hash.startswith("op_")
        assert commit.files_changed == []

    def test_commit_info_unique_hashes(self):
        """Each call to from_operator_input produces a unique hash."""
        from social_hook.models.core import CommitInfo

        c1 = CommitInfo.from_operator_input("idea 1")
        c2 = CommitInfo.from_operator_input("idea 2")
        assert c1.hash != c2.hash

    def test_drafting_intent_direct_construction(self):
        """DraftingIntent can be constructed directly for create flow."""
        from social_hook.drafting import DraftingIntent

        intent = DraftingIntent(
            decision="draft",
            vehicle="article",
            angle="Test idea",
            reasoning="Test idea",
            include_project_docs=True,
            decision_id="dec_123",
            platforms=[],
            content_source_context={"reference_files": "file content"},
        )
        assert intent.decision == "draft"
        assert intent.vehicle == "article"
        assert intent.include_project_docs is True
        assert intent.content_source_context == {"reference_files": "file content"}
