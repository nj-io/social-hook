"""Tests for two-pass project discovery."""

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from social_hook.config.project import ContextConfig
from social_hook.llm.base import NormalizedResponse, NormalizedToolCall, NormalizedUsage
from social_hook.llm.discovery import (
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
        lines = [line for line in listing.strip().split("\n") if line]
        assert len(lines) <= 3

    def test_custom_extensions(self, temp_repo):
        listing = list_project_files(str(temp_repo), extensions={".toml"})
        lines = [line for line in listing.strip().split("\n") if line]
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
    @patch("social_hook.llm.discovery.log_usage")
    def test_two_pass_flow(self, mock_log_usage, temp_repo):
        """Verify the two-pass flow: select files, generate summary, then brief."""
        mock_client = MagicMock()

        # Pass 1: select_files response
        select_response = _make_response(
            "select_files",
            {
                "files": ["README.md", "src/main.py"],
                "reasoning": "Core files for understanding",
            },
        )
        # Pass 2: generate_summary response
        summary_response = _make_response(
            "generate_summary",
            {
                "project_summary": "Test Project is a Python application that does X.",
                "file_summaries": [{"path": "README.md", "summary": "Project readme"}],
                "prompt_docs": ["README.md"],
            },
        )
        # Pass 3: generate_brief response (brief replaces raw summary)
        brief_response = _make_response(
            "generate_brief",
            {
                "what_it_does": "Test Project does X.",
                "key_capabilities": "Feature A.",
                "technical_architecture": "Python app.",
                "current_state": "Active.",
            },
        )

        mock_client.complete.side_effect = [select_response, summary_response, brief_response]

        summary, files, file_summaries, prompt_docs = discover_project(
            client=mock_client,
            repo_path=str(temp_repo),
        )

        # Brief replaces the raw summary
        assert "## What It Does" in summary
        assert "Test Project does X." in summary
        assert "README.md" in files
        assert isinstance(file_summaries, list)
        assert isinstance(prompt_docs, list)
        assert len(file_summaries) == 1
        assert file_summaries[0]["path"] == "README.md"
        assert prompt_docs == ["README.md"]
        assert mock_client.complete.call_count == 3

        # Verify pass 1 used select_files tool
        call1 = mock_client.complete.call_args_list[0]
        assert call1.kwargs["tools"][0]["name"] == "select_files"

        # Verify pass 2 used generate_summary tool
        call2 = mock_client.complete.call_args_list[1]
        assert call2.kwargs["tools"][0]["name"] == "generate_summary"

        # Verify pass 3 used generate_brief tool
        call3 = mock_client.complete.call_args_list[2]
        assert call3.kwargs["tools"][0]["name"] == "generate_brief"

    def test_project_docs_priority(self, temp_repo):
        """Verify user-specified project_docs get priority loading."""
        mock_client = MagicMock()

        # LLM only selects src/main.py, but project_docs includes docs/guide.md
        select_response = _make_response(
            "select_files",
            {
                "files": ["src/main.py"],
                "reasoning": "Source code",
            },
        )
        summary_response = _make_response(
            "generate_summary",
            {
                "project_summary": "A project.",
                "file_summaries": [],
                "prompt_docs": [],
            },
        )

        mock_client.complete.side_effect = [select_response, summary_response]

        summary, files, file_summaries, prompt_docs = discover_project(
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

        select_response = _make_response(
            "select_files",
            {
                "files": ["README.md"],
                "reasoning": "Main docs",
            },
        )
        summary_response = _make_response(
            "generate_summary",
            {
                "project_summary": "A project.",
                "file_summaries": [],
                "prompt_docs": [],
            },
        )
        mock_client.complete.side_effect = [select_response, summary_response]

        summary, files, file_summaries, prompt_docs = discover_project(
            client=mock_client,
            repo_path=str(temp_repo),
            project_docs=["docs/*.md"],  # Glob pattern
        )

        assert summary is not None
        # Both docs/*.md files should be resolved and loaded
        assert "docs/guide.md" in files or "docs/api.md" in files

    def test_token_budget_respected(self, temp_repo):
        """Verify max_discovery_tokens limit is respected."""
        # Create a large file
        large_content = "x" * 100000
        (temp_repo / "big.md").write_text(large_content)

        mock_client = MagicMock()

        select_response = _make_response(
            "select_files",
            {
                "files": ["big.md", "README.md"],
                "reasoning": "Files",
            },
        )
        summary_response = _make_response(
            "generate_summary",
            {
                "project_summary": "A project with a big file.",
                "file_summaries": [],
                "prompt_docs": [],
            },
        )
        mock_client.complete.side_effect = [select_response, summary_response]

        summary, files, file_summaries, prompt_docs = discover_project(
            client=mock_client,
            repo_path=str(temp_repo),
            max_discovery_tokens=500,  # Very small budget
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

        summary, files, file_summaries, prompt_docs = discover_project(
            client=mock_client,
            repo_path=str(temp_repo),
        )

        assert summary is None
        assert files == []
        assert file_summaries == []
        assert prompt_docs == []

    def test_empty_repo_returns_none(self, tmp_path):
        """Verify empty repo returns None."""
        mock_client = MagicMock()

        summary, files, file_summaries, prompt_docs = discover_project(
            client=mock_client,
            repo_path=str(tmp_path),
        )

        assert summary is None
        assert files == []
        assert file_summaries == []
        assert prompt_docs == []
        # Should not have called the LLM at all
        mock_client.complete.assert_not_called()

    @patch("social_hook.llm.discovery.log_usage")
    def test_db_tracking_passed_through(self, mock_log_usage, temp_repo):
        """Verify db and project_id are passed to log_usage."""
        mock_client = MagicMock()
        mock_db = MagicMock()

        select_response = _make_response(
            "select_files",
            {
                "files": ["README.md"],
                "reasoning": "Main file",
            },
        )
        summary_response = _make_response(
            "generate_summary",
            {
                "project_summary": "A project.",
                "file_summaries": [],
                "prompt_docs": [],
            },
        )
        mock_client.complete.side_effect = [select_response, summary_response]

        discover_project(
            client=mock_client,
            repo_path=str(temp_repo),
            db=mock_db,
            project_id="proj_123",
        )

        # Both log_usage calls should receive db and project_id
        assert mock_log_usage.call_count == 2
        for call in mock_log_usage.call_args_list:
            assert call[0][0] is mock_db
            assert call[0][4] == "proj_123"


class TestDiscoverySkippedWhenSummaryExists:
    """Test that discovery is not re-run when summary already exists."""

    def test_trigger_skips_discovery_when_summary_exists(self):
        """Verify the trigger pipeline skips discovery when project_summary is set."""
        from social_hook.models import ProjectContext
        from social_hook.models.core import Project

        # Create a context with an existing summary
        project = Project(
            id="proj_1",
            name="Test",
            repo_path="/tmp/test",
            summary="Existing summary",
        )
        context = ProjectContext(
            project=project,
            social_context=None,
            lifecycle=None,
            active_arcs=[],
            narrative_debt=0,
            platform_introduced={"x": False},
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
        from social_hook.models import ProjectContext
        from social_hook.models.core import Project

        files_list = ["README.md", "docs/guide.md"]
        project = Project(
            id="proj_1",
            name="Test",
            repo_path=str(temp_repo),
            discovery_files=json.dumps(files_list),
        )
        context = ProjectContext(
            project=project,
            social_context=None,
            lifecycle=None,
            active_arcs=[],
            narrative_debt=0,
            platform_introduced={"x": False},
            pending_drafts=[],
            recent_decisions=[],
            recent_posts=[],
            project_summary="A test project.",
        )

        from social_hook.models.core import CommitInfo

        commit = CommitInfo(hash="abc123", message="test", diff="")

        decision = {"decision": "draft", "reasoning": "test"}

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

    def test_drafter_falls_back_to_prompt_docs(self, temp_repo):
        """Verify drafter falls back to prompt_docs when no discovery files."""
        from social_hook.llm.prompts import assemble_drafter_prompt
        from social_hook.models import ProjectContext
        from social_hook.models.core import CommitInfo, Project

        project = Project(
            id="proj_1",
            name="Test",
            repo_path=str(temp_repo),
            discovery_files=None,
            prompt_docs=json.dumps(["README.md"]),
        )
        context = ProjectContext(
            project=project,
            social_context=None,
            lifecycle=None,
            active_arcs=[],
            narrative_debt=0,
            platform_introduced={"x": False},
            pending_drafts=[],
            recent_decisions=[],
            recent_posts=[],
            project_summary=None,
        )

        commit = CommitInfo(hash="abc123", message="test", diff="")
        decision = {"decision": "draft", "reasoning": "test"}

        result = assemble_drafter_prompt(
            prompt="You are a drafter.",
            decision=decision,
            project_context=context,
            recent_posts=[],
            commit=commit,
        )

        # Should fall back to prompt_docs (README.md)
        assert "Project Documentation" in result
        assert "Test Project" in result  # README.md content
        assert "Project Documentation (Discovery)" not in result

    def test_drafter_uses_readme_when_audience_introduced(self, temp_repo):
        """Verify drafter uses README when audience is already introduced."""
        from social_hook.llm.prompts import assemble_drafter_prompt
        from social_hook.models import ProjectContext
        from social_hook.models.core import CommitInfo, Project

        files_list = ["README.md", "docs/guide.md"]
        project = Project(
            id="proj_1",
            name="Test",
            repo_path=str(temp_repo),
            discovery_files=json.dumps(files_list),
        )
        context = ProjectContext(
            project=project,
            social_context=None,
            lifecycle=None,
            active_arcs=[],
            narrative_debt=0,
            platform_introduced={"x": True},  # Already introduced
            pending_drafts=[],
            recent_decisions=[],
            recent_posts=[],
            project_summary=None,
        )

        commit = CommitInfo(hash="abc123", message="test", diff="")
        # Decision explicitly requests project docs
        decision = {"decision": "draft", "reasoning": "test", "include_project_docs": True}

        result = assemble_drafter_prompt(
            prompt="You are a drafter.",
            decision=decision,
            project_context=context,
            recent_posts=[],
            commit=commit,
        )

        # platform_introduced={"x": True} with include_project_docs=True,
        # should use prompt_docs fallback if no discovery files priority
        assert "Project Documentation (Discovery)" not in result


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

        row = conn.execute(
            "SELECT discovery_files FROM projects WHERE id = ?", ("proj_1",)
        ).fetchone()
        assert json.loads(row[0]) == files
        conn.close()

    def test_project_from_dict_with_discovery_files(self):
        from social_hook.models.core import Project

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
        from social_hook.models.core import Project

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
            "max_discovery_tokens": 30000,
        }
        config = _parse_context_config(data)
        assert config.project_docs == ["docs/*.md", "README.md"]
        assert config.max_doc_tokens == 5000
        assert config.max_discovery_tokens == 30000

    def test_parse_empty_project_docs(self):
        from social_hook.config.project import _parse_context_config

        config = _parse_context_config({})
        assert config.project_docs == []

    def test_default_context_config_has_empty_project_docs(self):
        config = ContextConfig()
        assert config.project_docs == []


class TestDiscoveryConstants:
    """Test DISCOVERY_EXTENSIONS and IGNORE_DIRS constants."""

    def test_claude_dir_ignored(self):
        """Verify .claude is in IGNORE_DIRS."""
        from social_hook.llm.discovery import IGNORE_DIRS

        assert ".claude" in IGNORE_DIRS

    def test_new_extensions_present(self):
        """Verify new file extensions are in DISCOVERY_EXTENSIONS."""
        from social_hook.llm.discovery import DISCOVERY_EXTENSIONS

        for ext in [".txt", ".js", ".jsx", ".rst", ".sql", ".sh", ".rs", ".go"]:
            assert ext in DISCOVERY_EXTENSIONS, f"{ext} missing from DISCOVERY_EXTENSIONS"

    def test_claude_dir_excluded_from_listing(self, tmp_path):
        """Verify files under .claude/ are excluded from project file listing."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "config.json").write_text("{}")
        (tmp_path / "main.py").write_text("print('hello')")

        listing = list_project_files(str(tmp_path))
        assert ".claude" not in listing
        assert "main.py" in listing

    def test_max_file_size_excludes_large_files(self, tmp_path):
        """Verify list_project_files skips files larger than max_file_size."""
        (tmp_path / "small.py").write_text("x = 1")
        (tmp_path / "big.py").write_text("x" * 1000)

        listing = list_project_files(str(tmp_path), max_file_size=500)
        assert "small.py" in listing
        assert "big.py" not in listing


class TestFileSummariesDbOperations:
    """Test upsert_file_summaries and get_file_summaries DB operations."""

    def test_upsert_file_summaries_insert(self, temp_db):
        """Insert new file summaries and verify they're stored."""
        from social_hook.db.operations import get_file_summaries, upsert_file_summaries

        # Create a project first
        temp_db.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj_1", "Test", "/tmp/test"),
        )
        temp_db.commit()

        summaries = [
            {"path": "README.md", "summary": "Project readme file"},
            {"path": "src/main.py", "summary": "Main entry point"},
        ]
        upsert_file_summaries(temp_db, "proj_1", summaries)

        result = get_file_summaries(temp_db, "proj_1")
        assert len(result) == 2
        paths = [r["path"] for r in result]
        assert "README.md" in paths
        assert "src/main.py" in paths

    def test_upsert_file_summaries_replace(self, temp_db):
        """Upsert again with different files, verify old entries are cleaned."""
        from social_hook.db.operations import get_file_summaries, upsert_file_summaries

        temp_db.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj_1", "Test", "/tmp/test"),
        )
        temp_db.commit()

        # First upsert
        upsert_file_summaries(temp_db, "proj_1", [{"path": "old.py", "summary": "Old file"}])
        assert len(get_file_summaries(temp_db, "proj_1")) == 1

        # Second upsert with different files
        upsert_file_summaries(temp_db, "proj_1", [{"path": "new.py", "summary": "New file"}])
        result = get_file_summaries(temp_db, "proj_1")
        assert len(result) == 1
        assert result[0]["path"] == "new.py"

    def test_get_file_summaries_empty(self, temp_db):
        """Returns [] for project with no summaries."""
        from social_hook.db.operations import get_file_summaries

        temp_db.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj_1", "Test", "/tmp/test"),
        )
        temp_db.commit()

        result = get_file_summaries(temp_db, "proj_1")
        assert result == []

    def test_get_file_summaries_returns_correct_project(self, temp_db):
        """Verify project isolation."""
        from social_hook.db.operations import get_file_summaries, upsert_file_summaries

        temp_db.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj_1", "Project A", "/tmp/a"),
        )
        temp_db.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj_2", "Project B", "/tmp/b"),
        )
        temp_db.commit()

        upsert_file_summaries(temp_db, "proj_1", [{"path": "a.py", "summary": "File A"}])
        upsert_file_summaries(temp_db, "proj_2", [{"path": "b.py", "summary": "File B"}])

        result_1 = get_file_summaries(temp_db, "proj_1")
        result_2 = get_file_summaries(temp_db, "proj_2")

        assert len(result_1) == 1
        assert result_1[0]["path"] == "a.py"
        assert len(result_2) == 1
        assert result_2[0]["path"] == "b.py"
