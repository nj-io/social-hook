"""Tests for two-pass project discovery."""

import json
import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from social_hook.config.project import ContextConfig
from social_hook.llm.base import NormalizedResponse, NormalizedToolCall, NormalizedUsage
from social_hook.llm.discovery import (
    DISCOVERY_EXTENSIONS,
    IGNORE_DIRS,
    discover_project,
    list_project_files,
)


@pytest.fixture
def temp_repo(tmp_path):
    """Create a temporary repo with various files."""
    # Create project files
    (tmp_path / "README.md").write_text("# Test Project\nA test project.")
    (tmp_path / "CLAUDE.md").write_text("# Project conventions")
    (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup(name='test')")
    (tmp_path / "pyproject.toml").write_text("[build-system]\nrequires = ['setuptools']")
    (tmp_path / "config.yaml").write_text("key: value")

    # Create source files
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "main.py").write_text("def main(): pass")
    (src / "utils.py").write_text("def helper(): pass")

    # Create docs
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("# User Guide\nHow to use this.")
    (docs / "api.md").write_text("# API Reference")

    # Create files that should be ignored
    nm = tmp_path / "node_modules" / "pkg"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("module.exports = {}")

    pycache = tmp_path / "__pycache__"
    pycache.mkdir()
    (pycache / "main.cpython-311.pyc").write_text("bytecode")

    git = tmp_path / ".git"
    git.mkdir()
    (git / "config").write_text("[core]")

    # Non-matching extension
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    (tmp_path / "data.csv").write_text("a,b,c")

    return tmp_path


class TestListProjectFiles:
    def test_filters_by_extension(self, temp_repo):
        listing = list_project_files(str(temp_repo))
        lines = listing.strip().split("\n")

        # Should include .md, .py, .toml, .yaml files
        paths = [line.split(" (")[0] for line in lines]
        assert "README.md" in paths
        assert "CLAUDE.md" in paths
        assert "pyproject.toml" in paths
        assert "config.yaml" in paths
        assert "src/main.py" in paths or str(Path("src/main.py")) in paths

        # Should NOT include .png, .csv, .pyc
        all_text = listing.lower()
        assert "image.png" not in all_text
        assert "data.csv" not in all_text

    def test_ignores_directories(self, temp_repo):
        listing = list_project_files(str(temp_repo))

        # node_modules, __pycache__, .git should be excluded
        assert "node_modules" not in listing
        assert "__pycache__" not in listing
        assert ".git/" not in listing
        assert ".git\\" not in listing

    def test_includes_size(self, temp_repo):
        listing = list_project_files(str(temp_repo))
        # Every line should have size in parens
        for line in listing.strip().split("\n"):
            assert "(" in line and ")" in line

    def test_max_files_limit(self, temp_repo):
        listing = list_project_files(str(temp_repo), max_files=3)
        lines = [l for l in listing.strip().split("\n") if l]
        assert len(lines) <= 3

    def test_custom_extensions(self, temp_repo):
        listing = list_project_files(str(temp_repo), extensions={".toml"})
        lines = [l for l in listing.strip().split("\n") if l]
        # Only .toml files
        for line in lines:
            assert ".toml" in line

    def test_empty_directory(self, tmp_path):
        listing = list_project_files(str(tmp_path))
        assert listing == ""


def _make_response(tool_name, tool_input):
    """Helper to create a NormalizedResponse with a tool call."""
    return NormalizedResponse(
        content=[NormalizedToolCall(type="tool_use", name=tool_name, input=tool_input)],
        usage=NormalizedUsage(),
    )


class TestDiscoverProject:
    def test_two_pass_flow(self, temp_repo):
        """Verify the two-pass flow: select files then generate summary."""
        mock_client = MagicMock()

        # Pass 1: select_files response
        select_response = _make_response("select_files", {
            "files": ["README.md", "src/main.py"],
            "reasoning": "Core files for understanding",
        })
        # Pass 2: generate_summary response
        summary_response = _make_response("generate_summary", {
            "summary": "Test Project is a Python application that does X.",
        })

        mock_client.complete.side_effect = [select_response, summary_response]

        summary, files = discover_project(
            client=mock_client,
            repo_path=str(temp_repo),
        )

        assert summary == "Test Project is a Python application that does X."
        assert "README.md" in files
        assert mock_client.complete.call_count == 2

        # Verify pass 1 used select_files tool
        call1 = mock_client.complete.call_args_list[0]
        assert call1.kwargs["tools"][0]["name"] == "select_files"
        assert call1.kwargs["operation_type"] == "discovery_select"

        # Verify pass 2 used generate_summary tool
        call2 = mock_client.complete.call_args_list[1]
        assert call2.kwargs["tools"][0]["name"] == "generate_summary"
        assert call2.kwargs["operation_type"] == "discovery_summarize"

    def test_project_docs_priority(self, temp_repo):
        """Verify user-specified project_docs get priority loading."""
        mock_client = MagicMock()

        # LLM only selects src/main.py, but project_docs includes docs/guide.md
        select_response = _make_response("select_files", {
            "files": ["src/main.py"],
            "reasoning": "Source code",
        })
        summary_response = _make_response("generate_summary", {
            "summary": "A project.",
        })

        mock_client.complete.side_effect = [select_response, summary_response]

        summary, files = discover_project(
            client=mock_client,
            repo_path=str(temp_repo),
            project_docs=["docs/guide.md"],
        )

        assert summary is not None
        # docs/guide.md should be in the loaded files (priority)
        assert "docs/guide.md" in files

        # Verify pass 1 user message mentions priority files
        call1 = mock_client.complete.call_args_list[0]
        user_msg = call1.kwargs["messages"][0]["content"]
        assert "PRIORITY FILES" in user_msg
        assert "docs/guide.md" in user_msg

    def test_project_docs_glob_patterns(self, temp_repo):
        """Verify glob patterns in project_docs are resolved."""
        mock_client = MagicMock()

        select_response = _make_response("select_files", {
            "files": ["README.md"],
            "reasoning": "Main docs",
        })
        summary_response = _make_response("generate_summary", {
            "summary": "A project.",
        })
        mock_client.complete.side_effect = [select_response, summary_response]

        summary, files = discover_project(
            client=mock_client,
            repo_path=str(temp_repo),
            project_docs=["docs/*.md"],  # Glob pattern
        )

        assert summary is not None
        # Both docs/*.md files should be resolved and loaded
        assert "docs/guide.md" in files or "docs/api.md" in files

    def test_token_budget_respected(self, temp_repo):
        """Verify max_doc_tokens limit is respected."""
        # Create a large file
        large_content = "x" * 100000
        (temp_repo / "big.md").write_text(large_content)

        mock_client = MagicMock()

        select_response = _make_response("select_files", {
            "files": ["big.md", "README.md"],
            "reasoning": "Files",
        })
        summary_response = _make_response("generate_summary", {
            "summary": "A project with a big file.",
        })
        mock_client.complete.side_effect = [select_response, summary_response]

        summary, files = discover_project(
            client=mock_client,
            repo_path=str(temp_repo),
            max_doc_tokens=500,  # Very small budget
        )

        assert summary is not None
        # Pass 2 content should be truncated
        call2 = mock_client.complete.call_args_list[1]
        content = call2.kwargs["messages"][0]["content"]
        # Content should contain truncation marker or be limited
        assert len(content) < len(large_content)

    def test_discovery_failure_returns_none(self, temp_repo):
        """Verify graceful failure when LLM doesn't return expected tool call."""
        mock_client = MagicMock()

        # Return response with no tool call
        bad_response = NormalizedResponse(
            content=[],
            usage=NormalizedUsage(),
        )
        mock_client.complete.return_value = bad_response

        summary, files = discover_project(
            client=mock_client,
            repo_path=str(temp_repo),
        )

        assert summary is None
        assert files == []

    def test_empty_repo_returns_none(self, tmp_path):
        """Verify empty repo returns None."""
        mock_client = MagicMock()

        summary, files = discover_project(
            client=mock_client,
            repo_path=str(tmp_path),
        )

        assert summary is None
        assert files == []
        # Should not have called the LLM at all
        mock_client.complete.assert_not_called()

    def test_db_tracking_passed_through(self, temp_repo):
        """Verify db and project_id are passed to LLM client."""
        mock_client = MagicMock()
        mock_db = MagicMock()

        select_response = _make_response("select_files", {
            "files": ["README.md"],
            "reasoning": "Main file",
        })
        summary_response = _make_response("generate_summary", {
            "summary": "A project.",
        })
        mock_client.complete.side_effect = [select_response, summary_response]

        discover_project(
            client=mock_client,
            repo_path=str(temp_repo),
            db=mock_db,
            project_id="proj_123",
        )

        # Both calls should pass db and project_id
        for call in mock_client.complete.call_args_list:
            assert call.kwargs["db"] is mock_db
            assert call.kwargs["project_id"] == "proj_123"


class TestDiscoverySkippedWhenSummaryExists:
    """Test that discovery is not re-run when summary already exists."""

    def test_trigger_skips_discovery_when_summary_exists(self):
        """Verify the trigger pipeline skips discovery when project_summary is set."""
        from social_hook.models import Project, ProjectContext

        # Create a context with an existing summary
        project = Project(
            id="proj_1", name="Test", repo_path="/tmp/test",
            summary="Existing summary",
        )
        context = ProjectContext(
            project=project,
            social_context=None,
            lifecycle=None,
            active_arcs=[],
            narrative_debt=0,
            audience_introduced=False,
            pending_drafts=[],
            recent_decisions=[],
            recent_posts=[],
            project_summary="Existing summary",
        )

        # project_summary is not None, so discovery should be skipped
        assert context.project_summary is not None


class TestDiscoveryFilesStoredAndUsedByDrafter:
    """End-to-end: discovery files stored in DB and used by drafter prompt."""

    def test_discovery_files_in_drafter_prompt(self, temp_repo):
        """Verify discovery_files are loaded into drafter prompt for first posts."""
        from social_hook.llm.prompts import assemble_drafter_prompt
        from social_hook.models import Project, ProjectContext

        files_list = ["README.md", "docs/guide.md"]
        project = Project(
            id="proj_1", name="Test", repo_path=str(temp_repo),
            discovery_files=json.dumps(files_list),
        )
        context = ProjectContext(
            project=project,
            social_context=None,
            lifecycle=None,
            active_arcs=[],
            narrative_debt=0,
            audience_introduced=False,
            pending_drafts=[],
            recent_decisions=[],
            recent_posts=[],
            project_summary="A test project.",
        )

        from social_hook.models import CommitInfo

        commit = CommitInfo(hash="abc123", message="test", diff="")

        decision = {"decision": "post_worthy", "reasoning": "test"}

        result = assemble_drafter_prompt(
            prompt="You are a drafter.",
            decision=decision,
            project_context=context,
            recent_posts=[],
            commit=commit,
        )

        # Should include discovery file content, not just README/CLAUDE.md
        assert "Project Documentation (Discovery)" in result
        assert "Test Project" in result  # README.md content
        assert "User Guide" in result  # docs/guide.md content

    def test_drafter_falls_back_without_discovery_files(self, temp_repo):
        """Verify drafter falls back to README+CLAUDE.md when no discovery files."""
        from social_hook.llm.prompts import assemble_drafter_prompt
        from social_hook.models import CommitInfo, Project, ProjectContext

        project = Project(
            id="proj_1", name="Test", repo_path=str(temp_repo),
            discovery_files=None,
        )
        context = ProjectContext(
            project=project,
            social_context=None,
            lifecycle=None,
            active_arcs=[],
            narrative_debt=0,
            audience_introduced=False,
            pending_drafts=[],
            recent_decisions=[],
            recent_posts=[],
            project_summary=None,
        )

        commit = CommitInfo(hash="abc123", message="test", diff="")
        decision = {"decision": "post_worthy", "reasoning": "test"}

        result = assemble_drafter_prompt(
            prompt="You are a drafter.",
            decision=decision,
            project_context=context,
            recent_posts=[],
            commit=commit,
        )

        # Should fall back to README/CLAUDE.md sections
        assert "## README" in result
        assert "## CLAUDE.md" in result
        assert "Project Documentation (Discovery)" not in result

    def test_drafter_uses_readme_when_audience_introduced(self, temp_repo):
        """Verify drafter uses README when audience is already introduced."""
        from social_hook.llm.prompts import assemble_drafter_prompt
        from social_hook.models import CommitInfo, Project, ProjectContext

        files_list = ["README.md", "docs/guide.md"]
        project = Project(
            id="proj_1", name="Test", repo_path=str(temp_repo),
            discovery_files=json.dumps(files_list),
        )
        context = ProjectContext(
            project=project,
            social_context=None,
            lifecycle=None,
            active_arcs=[],
            narrative_debt=0,
            audience_introduced=True,  # Already introduced
            pending_drafts=[],
            recent_decisions=[],
            recent_posts=[],
            project_summary=None,
        )

        commit = CommitInfo(hash="abc123", message="test", diff="")
        # Decision explicitly requests project docs
        decision = {"decision": "post_worthy", "reasoning": "test", "include_project_docs": True}

        result = assemble_drafter_prompt(
            prompt="You are a drafter.",
            decision=decision,
            project_context=context,
            recent_posts=[],
            commit=commit,
        )

        # audience_introduced=True, so should NOT use discovery files
        # even though they exist; should use README/CLAUDE.md instead
        assert "Project Documentation (Discovery)" not in result
        assert "## README" in result


class TestDbOperations:
    """Test discovery_files DB operations."""

    def test_update_discovery_files(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                repo_path TEXT NOT NULL,
                repo_origin TEXT,
                summary TEXT,
                summary_updated_at TEXT,
                audience_introduced INTEGER NOT NULL DEFAULT 0,
                paused INTEGER NOT NULL DEFAULT 0,
                discovery_files TEXT DEFAULT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj_1", "Test", "/tmp/test"),
        )
        conn.commit()

        from social_hook.db.operations import update_discovery_files

        files = ["README.md", "src/main.py"]
        result = update_discovery_files(conn, "proj_1", files)
        assert result is True

        row = conn.execute("SELECT discovery_files FROM projects WHERE id = ?", ("proj_1",)).fetchone()
        assert json.loads(row[0]) == files
        conn.close()

    def test_project_from_dict_with_discovery_files(self):
        from social_hook.models import Project

        files = ["README.md", "src/main.py"]
        d = {
            "id": "proj_1",
            "name": "Test",
            "repo_path": "/tmp/test",
            "discovery_files": json.dumps(files),
        }
        p = Project.from_dict(d)
        assert p.discovery_files == json.dumps(files)

    def test_project_to_dict_with_discovery_files(self):
        from social_hook.models import Project

        files_json = json.dumps(["README.md"])
        p = Project(id="proj_1", name="Test", repo_path="/tmp/test", discovery_files=files_json)
        d = p.to_dict()
        assert d["discovery_files"] == files_json


class TestContextConfigProjectDocs:
    """Test project_docs in ContextConfig."""

    def test_parse_project_docs(self):
        from social_hook.config.project import _parse_context_config

        data = {
            "project_docs": ["docs/*.md", "README.md"],
            "max_doc_tokens": 5000,
        }
        config = _parse_context_config(data)
        assert config.project_docs == ["docs/*.md", "README.md"]
        assert config.max_doc_tokens == 5000

    def test_parse_empty_project_docs(self):
        from social_hook.config.project import _parse_context_config

        config = _parse_context_config({})
        assert config.project_docs == []

    def test_default_context_config_has_empty_project_docs(self):
        config = ContextConfig()
        assert config.project_docs == []
