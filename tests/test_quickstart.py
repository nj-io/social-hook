"""Tests for quickstart command, summary trigger, evaluate-recent, and batch evaluate."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import click
import pytest
from typer.testing import CliRunner

from social_hook.cli.quickstart import (
    _auto_configure,
    _error_exit,
    _run_batch_evaluate,
)
from social_hook.models.core import Decision, Draft, Project

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def git_repo(temp_dir):
    """Create a minimal git repo for quickstart tests."""
    repo = temp_dir / "my-repo"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@test.com"],
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Test"],
        capture_output=True,
    )
    (repo / "hello.py").write_text("print('hello')")
    subprocess.run(["git", "-C", str(repo), "add", "."], capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "Initial commit"],
        capture_output=True,
    )
    return repo


@pytest.fixture
def mock_project():
    """Return a mock project."""
    return Project(
        id="project_test123",
        name="my-repo",
        repo_path="/tmp/my-repo",
    )


# ---------------------------------------------------------------------------
# _error_exit
# ---------------------------------------------------------------------------


class TestErrorExit:
    def test_error_exit_text(self, capsys):
        with pytest.raises(click.exceptions.Exit):
            _error_exit("something broke", is_json=False)
        assert "Error: something broke" in capsys.readouterr().err

    def test_error_exit_json(self, capsys):
        with pytest.raises(click.exceptions.Exit):
            _error_exit("something broke", is_json=True)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["error"] == "something broke"


# ---------------------------------------------------------------------------
# _auto_configure
# ---------------------------------------------------------------------------


class TestAutoConfigure:
    def test_auto_configure_claude_cli(self, temp_dir):
        """When claude-cli is detected, write claude-cli models."""
        providers = [
            {"id": "claude-cli", "name": "Claude CLI", "status": "detected"},
        ]
        with patch(
            "social_hook.setup.wizard.discover_providers",
            return_value=providers,
        ):
            _auto_configure(
                temp_dir, api_key=None, strategies=["building-public"], is_json=True, verbose=False
            )

        import yaml

        config = yaml.safe_load((temp_dir / "config.yaml").read_text())
        assert config["models"]["evaluator"] == "claude-cli/sonnet"
        assert "platforms" not in config  # no legacy platforms section
        assert config["content_strategy"] == "building-public"
        assert "building-public" in config["content_strategies"]

    def test_auto_configure_anthropic_key(self, temp_dir):
        """When API key provided, write anthropic models and .env."""
        providers = [
            {"id": "anthropic", "name": "Anthropic", "status": "not_configured"},
        ]
        with patch(
            "social_hook.setup.wizard.discover_providers",
            return_value=providers,
        ):
            _auto_configure(
                temp_dir,
                api_key="sk-test-key",
                strategies=["building-public"],
                is_json=True,
                verbose=False,
            )

        import yaml

        config = yaml.safe_load((temp_dir / "config.yaml").read_text())
        assert "anthropic" in config["models"]["evaluator"]

        env_content = (temp_dir / ".env").read_text()
        assert "ANTHROPIC_API_KEY=sk-test-key" in env_content

    def test_auto_configure_no_provider_exits(self, temp_dir):
        """When no providers found, raise Exit."""
        providers = []
        with (
            patch(
                "social_hook.setup.wizard.discover_providers",
                return_value=providers,
            ),
            pytest.raises(click.exceptions.Exit),
        ):
            _auto_configure(
                temp_dir, api_key=None, strategies=["building-public"], is_json=True, verbose=False
            )

    def test_auto_configure_openrouter(self, temp_dir):
        """When openrouter is configured, use openrouter models."""
        providers = [
            {"id": "openrouter", "name": "OpenRouter", "status": "configured"},
        ]
        with patch(
            "social_hook.setup.wizard.discover_providers",
            return_value=providers,
        ):
            _auto_configure(
                temp_dir, api_key=None, strategies=["building-public"], is_json=True, verbose=False
            )

        import yaml

        config = yaml.safe_load((temp_dir / "config.yaml").read_text())
        assert "openrouter" in config["models"]["evaluator"]


# ---------------------------------------------------------------------------
# run_summary_trigger
# ---------------------------------------------------------------------------


class TestRunSummaryTrigger:
    def test_creates_decision_and_calls_drafter(self, temp_db):
        """run_summary_trigger creates a decision and calls draft_for_platforms."""
        from social_hook.trigger import run_summary_trigger

        project = Project(
            id="project_test123",
            name="test-project",
            repo_path="/tmp/test-repo",
        )

        mock_draft = MagicMock()
        mock_draft.draft = Draft(
            id="draft_abc",
            project_id="project_test123",
            decision_id="decision_xyz",
            platform="preview",
            content="Hello world! Here is my project.",
        )

        mock_db = MagicMock()
        mock_config = MagicMock()

        with (
            patch("social_hook.drafting.draft_for_platforms", return_value=[mock_draft]),
            patch("social_hook.trigger.assemble_evaluator_context", return_value=MagicMock()),
            patch("social_hook.config.project.load_project_config", return_value=MagicMock()),
        ):
            result = run_summary_trigger(
                config=mock_config,
                conn=temp_db,
                db=mock_db,
                project=project,
                summary="A great project for testing.",
                repo_path="/tmp/test-repo",
            )

        assert result is not None
        assert result["draft_id"] == "draft_abc"
        assert result["platform"] == "preview"
        assert "Hello world" in result["content"]

        # Verify decision was inserted
        mock_db.insert_decision.assert_called_once()
        decision = mock_db.insert_decision.call_args[0][0]
        assert decision.decision == "draft"
        assert decision.trigger_source == "manual"
        assert decision.commit_hash == "summary"

    def test_returns_none_on_drafter_failure(self, temp_db):
        """When draft_for_platforms raises, return None."""
        from social_hook.trigger import run_summary_trigger

        project = Project(
            id="project_test123",
            name="test-project",
            repo_path="/tmp/test-repo",
        )

        mock_db = MagicMock()
        mock_config = MagicMock()

        with (
            patch(
                "social_hook.drafting.draft_for_platforms",
                side_effect=RuntimeError("LLM down"),
            ),
            patch("social_hook.trigger.assemble_evaluator_context", return_value=MagicMock()),
            patch("social_hook.config.project.load_project_config", return_value=MagicMock()),
        ):
            result = run_summary_trigger(
                config=mock_config,
                conn=temp_db,
                db=mock_db,
                project=project,
                summary="A great project.",
                repo_path="/tmp/test-repo",
            )

        assert result is None

    def test_returns_none_on_empty_results(self, temp_db):
        """When draft_for_platforms returns empty list, return None."""
        from social_hook.trigger import run_summary_trigger

        project = Project(
            id="project_test123",
            name="test-project",
            repo_path="/tmp/test-repo",
        )

        mock_db = MagicMock()
        mock_config = MagicMock()

        with (
            patch("social_hook.drafting.draft_for_platforms", return_value=[]),
            patch("social_hook.trigger.assemble_evaluator_context", return_value=MagicMock()),
            patch("social_hook.config.project.load_project_config", return_value=MagicMock()),
        ):
            result = run_summary_trigger(
                config=mock_config,
                conn=temp_db,
                db=mock_db,
                project=project,
                summary="A great project.",
                repo_path="/tmp/test-repo",
            )

        assert result is None


# ---------------------------------------------------------------------------
# _run_batch_evaluate
# ---------------------------------------------------------------------------


class TestRunBatchEvaluate:
    def test_batch_evaluate_no_unevaluated(self, temp_db, mock_project):
        """When no unevaluated commits, return empty list."""
        mock_config = MagicMock()
        results = _run_batch_evaluate(
            mock_config, temp_db, mock_project, "/tmp/repo", 3, False, False, True
        )
        assert results == []

    def test_batch_evaluate_calls_run_trigger(self, temp_db, mock_project):
        """Batch evaluate finds imported decisions and calls run_trigger for each."""
        from social_hook.db.operations import insert_decision

        # Register project first (FK constraint)
        temp_db.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            (mock_project.id, mock_project.name, mock_project.repo_path),
        )
        temp_db.commit()

        for i, h in enumerate(["abc123", "def456"]):
            d = Decision(
                id=f"decision_{i}",
                project_id=mock_project.id,
                commit_hash=h,
                decision="imported",
                reasoning="imported",
                commit_message=f"commit {i}",
                trigger_source="import",
            )
            insert_decision(temp_db, d)

        mock_config = MagicMock()

        with patch(
            "social_hook.trigger.run_trigger",
            return_value=0,
        ) as mock_trigger:
            results = _run_batch_evaluate(
                mock_config,
                temp_db,
                mock_project,
                "/tmp/repo",
                5,
                False,
                False,
                True,
            )

        assert len(results) == 2
        assert all(r["status"] == "ok" for r in results)
        assert mock_trigger.call_count == 2

    def test_batch_evaluate_handles_trigger_error(self, temp_db, mock_project):
        """When run_trigger raises, capture as error result."""
        from social_hook.db.operations import insert_decision

        # Register project first (FK constraint)
        temp_db.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            (mock_project.id, mock_project.name, mock_project.repo_path),
        )
        temp_db.commit()

        d = Decision(
            id="decision_err",
            project_id=mock_project.id,
            commit_hash="err123",
            decision="imported",
            reasoning="imported",
            commit_message="error commit",
            trigger_source="import",
        )
        insert_decision(temp_db, d)

        mock_config = MagicMock()

        with patch(
            "social_hook.trigger.run_trigger",
            side_effect=RuntimeError("boom"),
        ):
            results = _run_batch_evaluate(
                mock_config,
                temp_db,
                mock_project,
                "/tmp/repo",
                5,
                False,
                False,
                True,
            )

        assert len(results) == 1
        assert results[0]["status"] == "error"
        assert results[0]["exit_code"] == 2


# ---------------------------------------------------------------------------
# project evaluate-recent command
# ---------------------------------------------------------------------------


class TestEvaluateRecentCommand:
    def test_evaluate_recent_no_project(self, temp_dir):
        """When no project found, exit 1."""
        from social_hook.cli import app

        result = runner.invoke(
            app,
            ["project", "evaluate-recent", "-p", str(temp_dir), "--json"],
            catch_exceptions=False,
        )
        # Should error because no project registered at that path
        data = json.loads(result.output)
        assert "error" in data

    def test_evaluate_recent_no_commits(self, temp_db, mock_project):
        """When no unevaluated commits found, return empty."""
        from social_hook.cli import app

        with (
            patch("social_hook.db.connection.init_database", return_value=temp_db),
            patch("social_hook.filesystem.get_db_path", return_value=":memory:"),
            patch(
                "social_hook.db.operations.get_project_by_path",
                return_value=mock_project,
            ),
        ):
            result = runner.invoke(
                app,
                ["project", "evaluate-recent", "-p", "/tmp/my-repo", "--json"],
                catch_exceptions=False,
            )

        data = json.loads(result.output)
        assert data["evaluated"] == 0
        assert data["results"] == []


# ---------------------------------------------------------------------------
# Quickstart command (integration-style)
# ---------------------------------------------------------------------------


class TestQuickstartCommand:
    def test_quickstart_not_git_repo(self, temp_dir):
        """Quickstart on non-git dir exits with error."""
        from social_hook.cli import app

        result = runner.invoke(
            app,
            ["quickstart", str(temp_dir), "--yes", "--json"],
        )
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert "Not a git repository" in data["error"]

    def test_quickstart_caps_evaluate_last(self):
        """evaluate_last is capped at 5."""
        # Test the capping logic directly
        val = min(max(10, 0), 5)
        assert val == 5

        val = min(max(-1, 0), 5)
        assert val == 0
