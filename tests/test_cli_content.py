"""Tests for CLI content subcommands — suggest, list, dismiss, combine, hero-launch."""

import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from social_hook.cli import app

runner = CliRunner()


@pytest.fixture()
def db_env(tmp_path):
    """Set up isolated DB with a registered project."""
    from social_hook.db.connection import init_database

    db_path = tmp_path / "social_hook.db"
    conn = init_database(str(db_path))
    conn.execute(
        "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
        ("proj_test1", "test-project", str(tmp_path)),
    )
    conn.commit()
    conn.close()
    return {"tmp_path": tmp_path, "db_path": db_path}


@pytest.fixture()
def db_env_with_suggestion(db_env):
    """DB with a content suggestion."""
    conn = sqlite3.connect(str(db_env["db_path"]))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """INSERT INTO content_suggestions (id, project_id, strategy, idea, status, source)
        VALUES ('suggestion_test1', 'proj_test1', 'building-public', 'Test idea', 'pending', 'operator')"""
    )
    conn.commit()
    conn.close()
    return db_env


def _patch_paths(db_env):
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(patch("social_hook.filesystem.get_db_path", return_value=db_env["db_path"]))
    return stack


class TestContentSuggest:
    def test_suggest_creates(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                [
                    "content",
                    "suggest",
                    "--idea",
                    "Show the dashboard",
                    "-p",
                    str(db_env["tmp_path"]),
                ],
            )
            assert result.exit_code == 0
            assert "Suggestion created" in result.output
            assert "evaluator will assign" in result.output

    def test_suggest_with_strategy(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                [
                    "content",
                    "suggest",
                    "--idea",
                    "Launch post",
                    "--strategy",
                    "brand-primary",
                    "-p",
                    str(db_env["tmp_path"]),
                ],
            )
            assert result.exit_code == 0
            assert "brand-primary" in result.output

    def test_suggest_json(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                [
                    "content",
                    "suggest",
                    "--idea",
                    "New feature",
                    "-p",
                    str(db_env["tmp_path"]),
                    "--json",
                ],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["idea"] == "New feature"
            assert data["source"] == "operator"
            assert data["status"] == "pending"

    def test_suggest_no_project(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app, ["content", "suggest", "--idea", "Test", "-p", "/nonexistent"]
            )
            assert result.exit_code == 1


class TestContentList:
    def test_list_empty(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["content", "list", "-p", str(db_env["tmp_path"])])
            assert result.exit_code == 0
            assert "No content suggestions" in result.output

    def test_list_with_suggestions(self, db_env_with_suggestion):
        with _patch_paths(db_env_with_suggestion):
            result = runner.invoke(
                app, ["content", "list", "-p", str(db_env_with_suggestion["tmp_path"])]
            )
            assert result.exit_code == 0
            assert "Test idea" in result.output

    def test_list_json(self, db_env_with_suggestion):
        with _patch_paths(db_env_with_suggestion):
            result = runner.invoke(
                app, ["content", "list", "-p", str(db_env_with_suggestion["tmp_path"]), "--json"]
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data["suggestions"]) == 1
            assert data["suggestions"][0]["idea"] == "Test idea"


class TestContentDismiss:
    def test_dismiss_with_yes(self, db_env_with_suggestion):
        with _patch_paths(db_env_with_suggestion):
            result = runner.invoke(
                app,
                [
                    "content",
                    "dismiss",
                    "suggestion_test1",
                    "--yes",
                    "-p",
                    str(db_env_with_suggestion["tmp_path"]),
                ],
            )
            assert result.exit_code == 0
            assert "dismissed" in result.output

    def test_dismiss_json(self, db_env_with_suggestion):
        with _patch_paths(db_env_with_suggestion):
            result = runner.invoke(
                app,
                [
                    "content",
                    "dismiss",
                    "suggestion_test1",
                    "--yes",
                    "--json",
                    "-p",
                    str(db_env_with_suggestion["tmp_path"]),
                ],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["dismissed"] is True

    def test_dismiss_not_found(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                ["content", "dismiss", "nonexistent", "--yes", "-p", str(db_env["tmp_path"])],
            )
            assert result.exit_code == 1
            assert "not found" in result.output

    def test_dismiss_not_found_json(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                [
                    "content",
                    "dismiss",
                    "nonexistent",
                    "--yes",
                    "--json",
                    "-p",
                    str(db_env["tmp_path"]),
                ],
            )
            assert result.exit_code == 1
            data = json.loads(result.output)
            assert "error" in data

    def test_dismiss_requires_confirmation(self, db_env_with_suggestion):
        with _patch_paths(db_env_with_suggestion):
            result = runner.invoke(
                app,
                [
                    "content",
                    "dismiss",
                    "suggestion_test1",
                    "-p",
                    str(db_env_with_suggestion["tmp_path"]),
                ],
                input="n\n",
            )
            assert result.exit_code == 0
            assert "Cancelled" in result.output

    def test_dismiss_already_dismissed(self, db_env_with_suggestion):
        """Dismissing an already-dismissed suggestion is a no-op."""
        conn = sqlite3.connect(str(db_env_with_suggestion["db_path"]))
        conn.execute(
            "UPDATE content_suggestions SET status = 'dismissed' WHERE id = 'suggestion_test1'"
        )
        conn.commit()
        conn.close()

        with _patch_paths(db_env_with_suggestion):
            result = runner.invoke(
                app,
                [
                    "content",
                    "dismiss",
                    "suggestion_test1",
                    "--yes",
                    "-p",
                    str(db_env_with_suggestion["tmp_path"]),
                ],
            )
            assert result.exit_code == 0
            assert "already dismissed" in result.output

    def test_dismiss_wrong_project(self, db_env):
        """Suggestion belonging to a different project."""
        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.execute(
            """INSERT INTO content_suggestions (id, project_id, strategy, idea, status, source)
            VALUES ('suggestion_other', 'proj_other', 'bp', 'Other idea', 'pending', 'operator')"""
        )
        conn.commit()
        conn.close()

        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                [
                    "content",
                    "dismiss",
                    "suggestion_other",
                    "--yes",
                    "-p",
                    str(db_env["tmp_path"]),
                ],
            )
            assert result.exit_code == 1
            assert "does not belong" in result.output


class TestContentCombine:
    def test_combine_success(self, db_env):
        with (
            _patch_paths(db_env),
            patch(
                "social_hook.content.operations.combine_candidates",
                return_value="draft_combined1",
            ),
            patch("social_hook.config.yaml.load_full_config", return_value=MagicMock()),
        ):
            result = runner.invoke(
                app,
                [
                    "content",
                    "combine",
                    "-t",
                    "topic_a",
                    "-t",
                    "topic_b",
                    "-p",
                    str(db_env["tmp_path"]),
                ],
            )
            assert result.exit_code == 0
            assert "Combined draft created" in result.output

    def test_combine_json(self, db_env):
        with (
            _patch_paths(db_env),
            patch(
                "social_hook.content.operations.combine_candidates",
                return_value="draft_combined1",
            ),
            patch("social_hook.config.yaml.load_full_config", return_value=MagicMock()),
        ):
            result = runner.invoke(
                app,
                [
                    "content",
                    "combine",
                    "-t",
                    "topic_a",
                    "-t",
                    "topic_b",
                    "-p",
                    str(db_env["tmp_path"]),
                    "--json",
                ],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["draft_id"] == "draft_combined1"
            assert data["topic_ids"] == ["topic_a", "topic_b"]

    def test_combine_error(self, db_env):
        with (
            _patch_paths(db_env),
            patch(
                "social_hook.content.operations.combine_candidates",
                side_effect=ValueError("Need at least 2 topics"),
            ),
            patch("social_hook.config.yaml.load_full_config", return_value=MagicMock()),
        ):
            result = runner.invoke(
                app,
                [
                    "content",
                    "combine",
                    "-t",
                    "topic_a",
                    "-p",
                    str(db_env["tmp_path"]),
                ],
            )
            assert result.exit_code == 1
            assert "Need at least 2" in result.output

    def test_combine_error_json(self, db_env):
        with (
            _patch_paths(db_env),
            patch(
                "social_hook.content.operations.combine_candidates",
                side_effect=ValueError("Need at least 2 topics"),
            ),
            patch("social_hook.config.yaml.load_full_config", return_value=MagicMock()),
        ):
            result = runner.invoke(
                app,
                [
                    "content",
                    "combine",
                    "-t",
                    "topic_a",
                    "-p",
                    str(db_env["tmp_path"]),
                    "--json",
                ],
            )
            assert result.exit_code == 1
            data = json.loads(result.output)
            assert "error" in data


class TestContentHeroLaunch:
    def test_hero_launch_success(self, db_env):
        with (
            _patch_paths(db_env),
            patch(
                "social_hook.content.operations.trigger_hero_launch",
                return_value="draft_hero1",
            ),
            patch("social_hook.config.yaml.load_full_config", return_value=MagicMock()),
        ):
            result = runner.invoke(
                app,
                ["content", "hero-launch", "-p", str(db_env["tmp_path"])],
            )
            assert result.exit_code == 0
            assert "Hero launch draft created" in result.output

    def test_hero_launch_json(self, db_env):
        with (
            _patch_paths(db_env),
            patch(
                "social_hook.content.operations.trigger_hero_launch",
                return_value="draft_hero1",
            ),
            patch("social_hook.config.yaml.load_full_config", return_value=MagicMock()),
        ):
            result = runner.invoke(
                app,
                ["content", "hero-launch", "-p", str(db_env["tmp_path"]), "--json"],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["draft_id"] == "draft_hero1"
            assert data["project"] == "test-project"

    def test_hero_launch_error(self, db_env):
        with (
            _patch_paths(db_env),
            patch(
                "social_hook.content.operations.trigger_hero_launch",
                side_effect=RuntimeError("No candidates"),
            ),
            patch("social_hook.config.yaml.load_full_config", return_value=MagicMock()),
        ):
            result = runner.invoke(
                app,
                ["content", "hero-launch", "-p", str(db_env["tmp_path"])],
            )
            assert result.exit_code == 2
            assert "No candidates" in result.output

    def test_hero_launch_error_json(self, db_env):
        with (
            _patch_paths(db_env),
            patch(
                "social_hook.content.operations.trigger_hero_launch",
                side_effect=RuntimeError("No candidates"),
            ),
            patch("social_hook.config.yaml.load_full_config", return_value=MagicMock()),
        ):
            result = runner.invoke(
                app,
                ["content", "hero-launch", "-p", str(db_env["tmp_path"]), "--json"],
            )
            assert result.exit_code == 2
            data = json.loads(result.output)
            assert "error" in data
