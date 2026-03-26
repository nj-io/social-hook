"""Tests for targets CLI command groups.

Tests: credentials, account, target, strategy, topics, brief, content, cycles, system.
"""

import json
import sqlite3
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from social_hook.cli import app

runner = CliRunner()


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture()
def db_env(tmp_path):
    """Set up isolated DB with project, topics, and suggestions tables."""
    from social_hook.db.connection import init_database

    db_path = tmp_path / "social_hook.db"
    conn = init_database(str(db_path))

    # Insert a test project
    conn.execute(
        "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
        ("proj_test1", "test-project", str(tmp_path)),
    )
    conn.commit()
    conn.close()

    return {"tmp_path": tmp_path, "db_path": db_path}


@pytest.fixture()
def db_env_with_topic(db_env):
    """DB env with a pre-inserted topic."""
    conn = sqlite3.connect(str(db_env["db_path"]))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """INSERT INTO content_topics (id, project_id, strategy, topic, description, status, priority_rank)
        VALUES ('topic_test1', 'proj_test1', 'building-public', 'test topic', 'A test topic', 'uncovered', 5)"""
    )
    conn.commit()
    conn.close()
    return db_env


@pytest.fixture()
def db_env_with_suggestion(db_env):
    """DB env with a pre-inserted suggestion."""
    conn = sqlite3.connect(str(db_env["db_path"]))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """INSERT INTO content_suggestions (id, project_id, strategy, idea, status, source)
        VALUES ('suggestion_test1', 'proj_test1', 'building-public', 'Test idea', 'pending', 'operator')"""
    )
    conn.commit()
    conn.close()
    return db_env


@pytest.fixture()
def db_env_with_cycle(db_env):
    """DB env with a pre-inserted evaluation cycle."""
    conn = sqlite3.connect(str(db_env["db_path"]))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """INSERT INTO evaluation_cycles (id, project_id, trigger_type, trigger_ref)
        VALUES ('cycle_test1', 'proj_test1', 'commit', 'abc123')"""
    )
    conn.commit()
    conn.close()
    return db_env


@pytest.fixture()
def db_env_with_errors(db_env):
    """DB env with pre-inserted system errors."""
    conn = sqlite3.connect(str(db_env["db_path"]))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """INSERT INTO system_errors (id, severity, message, source)
        VALUES ('err_test1', 'error', 'Test error message', 'scheduler')"""
    )
    conn.execute(
        """INSERT INTO system_errors (id, severity, message, source)
        VALUES ('err_test2', 'warning', 'Test warning', 'cli')"""
    )
    conn.commit()
    conn.close()
    return db_env


def _patch_paths(db_env):
    """Return context manager patching filesystem paths."""
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(patch("social_hook.filesystem.get_db_path", return_value=db_env["db_path"]))
    return stack


def _patch_env(db_env, env_content=""):
    """Return context manager patching both DB and env paths."""
    from contextlib import ExitStack

    env_path = db_env["tmp_path"] / ".env"
    env_path.write_text(env_content)

    stack = ExitStack()
    stack.enter_context(patch("social_hook.filesystem.get_db_path", return_value=db_env["db_path"]))
    stack.enter_context(patch("social_hook.filesystem.get_env_path", return_value=env_path))
    stack.enter_context(
        patch("social_hook.config.env.load_env", return_value=dict(_parse_env(env_content)))
    )
    return stack


def _parse_env(content):
    """Parse key=value lines."""
    result = {}
    for line in content.strip().split("\n"):
        if "=" in line:
            key, val = line.split("=", 1)
            result[key.strip()] = val.strip()
    return result


# =============================================================================
# Credentials
# =============================================================================


class TestCredentialsList:
    def test_list_help(self):
        result = runner.invoke(app, ["credentials", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output

    def test_list_empty(self, db_env):
        with _patch_env(db_env, ""):
            result = runner.invoke(app, ["credentials", "list"])
            assert result.exit_code == 0

    def test_list_json(self, db_env):
        with _patch_env(db_env, "X_CLIENT_ID=test\nX_CLIENT_SECRET=secret"):
            result = runner.invoke(app, ["credentials", "list", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "credentials" in data


class TestCredentialsValidate:
    def test_validate(self, db_env):
        with _patch_env(db_env, "X_CLIENT_ID=test\nX_CLIENT_SECRET=secret"):
            result = runner.invoke(app, ["credentials", "validate"])
            assert result.exit_code == 0

    def test_validate_json(self, db_env):
        with _patch_env(db_env, "X_CLIENT_ID=test\nX_CLIENT_SECRET=secret"):
            result = runner.invoke(app, ["credentials", "validate", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "valid" in data


class TestCredentialsRemove:
    def test_remove_requires_yes(self, db_env):
        with _patch_env(db_env, "X_CLIENT_ID=test\nX_CLIENT_SECRET=secret"):
            result = runner.invoke(app, ["credentials", "remove", "x"], input="n\n")
            assert result.exit_code == 0
            assert "Cancelled" in result.output

    def test_remove_unknown(self, db_env):
        with _patch_env(db_env, ""):
            result = runner.invoke(app, ["credentials", "remove", "unknown", "--yes"])
            assert result.exit_code == 1

    def test_remove_with_yes(self, db_env):
        env_content = "X_CLIENT_ID=test\nX_CLIENT_SECRET=secret\n"
        env_path = db_env["tmp_path"] / ".env"
        env_path.write_text(env_content)
        with (
            _patch_paths(db_env),
            patch("social_hook.filesystem.get_env_path", return_value=env_path),
        ):
            result = runner.invoke(app, ["credentials", "remove", "x", "--yes"])
            assert result.exit_code == 0
            assert "Removed" in result.output


# =============================================================================
# Account
# =============================================================================


class TestAccountList:
    def test_list_empty(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["account", "list"])
            assert result.exit_code == 0
            assert "No accounts" in result.output

    def test_list_json_empty(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["account", "list", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["accounts"] == []

    def test_list_with_account(self, db_env):
        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.execute(
            """INSERT INTO oauth_tokens (account_name, platform, access_token, refresh_token, expires_at, updated_at)
            VALUES ('lead', 'x', 'tok', 'ref', '2099-01-01T00:00:00+00:00', '2026-01-01T00:00:00')"""
        )
        conn.commit()
        conn.close()

        with _patch_paths(db_env):
            result = runner.invoke(app, ["account", "list"])
            assert result.exit_code == 0
            assert "lead" in result.output
            assert "valid" in result.output


class TestAccountRemove:
    def test_remove_not_found(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["account", "remove", "missing", "--yes"])
            assert result.exit_code == 1

    def test_remove_requires_yes(self, db_env):
        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.execute(
            """INSERT INTO oauth_tokens (account_name, platform, access_token, refresh_token, expires_at, updated_at)
            VALUES ('lead', 'x', 'tok', 'ref', '2099-01-01T00:00:00+00:00', '2026-01-01')"""
        )
        conn.commit()
        conn.close()

        with _patch_paths(db_env):
            result = runner.invoke(app, ["account", "remove", "lead"], input="n\n")
            assert result.exit_code == 0
            assert "Cancelled" in result.output


class TestAccountValidate:
    def test_validate_empty(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["account", "validate"])
            assert result.exit_code == 0
            assert "No accounts" in result.output

    def test_validate_json(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["account", "validate", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "valid" in data


# =============================================================================
# Target
# =============================================================================


class TestTargetList:
    def test_list_empty(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["target", "list", "--project", str(db_env["tmp_path"])])
            assert result.exit_code == 0
            assert "No targets" in result.output

    def test_list_json(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app, ["target", "list", "--project", str(db_env["tmp_path"]), "--json"]
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "targets" in data


class TestTargetAdd:
    def test_add_target(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                [
                    "target",
                    "add",
                    "--account",
                    "product",
                    "--destination",
                    "timeline",
                    "--strategy",
                    "product-news",
                    "--project",
                    str(db_env["tmp_path"]),
                ],
            )
            assert result.exit_code == 0
            assert "Added" in result.output

    def test_add_target_json(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                [
                    "target",
                    "add",
                    "--account",
                    "lead",
                    "--destination",
                    "timeline",
                    "--strategy",
                    "building-public",
                    "--project",
                    str(db_env["tmp_path"]),
                    "--json",
                ],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["added"] is True


# =============================================================================
# Strategy
# =============================================================================


class TestStrategyList:
    def test_list(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["strategy", "list", "--project", str(db_env["tmp_path"])])
            assert result.exit_code == 0
            # Should show built-in templates
            assert "building-public" in result.output or "template" in result.output

    def test_list_json(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app, ["strategy", "list", "--project", str(db_env["tmp_path"]), "--json"]
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "strategies" in data
            # Should include built-in templates
            names = [s["name"] for s in data["strategies"]]
            assert "building-public" in names


class TestStrategyShow:
    def test_show(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                ["strategy", "show", "building-public", "--project", str(db_env["tmp_path"])],
            )
            assert result.exit_code == 0
            assert "building-public" in result.output

    def test_show_not_found(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                ["strategy", "show", "nonexistent", "--project", str(db_env["tmp_path"])],
            )
            assert result.exit_code == 1

    def test_show_json(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                [
                    "strategy",
                    "show",
                    "building-public",
                    "--project",
                    str(db_env["tmp_path"]),
                    "--json",
                ],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["name"] == "building-public"


class TestStrategyEdit:
    def test_edit_no_editor(self, db_env):
        """Test edit fails gracefully when no changes."""
        with _patch_paths(db_env), patch.dict("os.environ", {"EDITOR": "true"}, clear=False):
            result = runner.invoke(
                app,
                [
                    "strategy",
                    "edit",
                    "building-public",
                    "--project",
                    str(db_env["tmp_path"]),
                ],
            )
            assert result.exit_code == 0
            assert "No changes" in result.output

    def test_edit_not_found(self, db_env):
        with _patch_paths(db_env), patch.dict("os.environ", {"EDITOR": "true"}, clear=False):
            result = runner.invoke(
                app,
                [
                    "strategy",
                    "edit",
                    "nonexistent",
                    "--project",
                    str(db_env["tmp_path"]),
                ],
            )
            assert result.exit_code == 1


class TestStrategyReset:
    def test_reset_requires_yes(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                [
                    "strategy",
                    "reset",
                    "building-public",
                    "--project",
                    str(db_env["tmp_path"]),
                ],
                input="n\n",
            )
            assert result.exit_code == 0
            assert "Cancelled" in result.output

    def test_reset_non_template(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                [
                    "strategy",
                    "reset",
                    "custom-strategy",
                    "--project",
                    str(db_env["tmp_path"]),
                    "--yes",
                ],
            )
            assert result.exit_code == 1

    def test_reset_with_yes(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                [
                    "strategy",
                    "reset",
                    "building-public",
                    "--project",
                    str(db_env["tmp_path"]),
                    "--yes",
                ],
            )
            assert result.exit_code == 0
            assert "reset" in result.output.lower()


# =============================================================================
# Topics
# =============================================================================


class TestTopicsList:
    def test_list_empty(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["topics", "list", "--project", str(db_env["tmp_path"])])
            assert result.exit_code == 0
            assert "No topics" in result.output

    def test_list_with_topics(self, db_env_with_topic):
        with _patch_paths(db_env_with_topic):
            result = runner.invoke(
                app, ["topics", "list", "--project", str(db_env_with_topic["tmp_path"])]
            )
            assert result.exit_code == 0
            assert "test topic" in result.output

    def test_list_json(self, db_env_with_topic):
        with _patch_paths(db_env_with_topic):
            result = runner.invoke(
                app,
                ["topics", "list", "--project", str(db_env_with_topic["tmp_path"]), "--json"],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data["topics"]) == 1
            assert data["topics"][0]["topic"] == "test topic"

    def test_list_filter_strategy(self, db_env_with_topic):
        with _patch_paths(db_env_with_topic):
            result = runner.invoke(
                app,
                [
                    "topics",
                    "list",
                    "--strategy",
                    "building-public",
                    "--project",
                    str(db_env_with_topic["tmp_path"]),
                ],
            )
            assert result.exit_code == 0
            assert "test topic" in result.output

    def test_list_filter_no_match(self, db_env_with_topic):
        with _patch_paths(db_env_with_topic):
            result = runner.invoke(
                app,
                [
                    "topics",
                    "list",
                    "--strategy",
                    "nonexistent",
                    "--project",
                    str(db_env_with_topic["tmp_path"]),
                ],
            )
            assert result.exit_code == 0
            assert "No topics" in result.output


class TestTopicsAdd:
    def test_add(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                [
                    "topics",
                    "add",
                    "--strategy",
                    "building-public",
                    "--topic",
                    "new topic",
                    "--description",
                    "A new topic",
                    "--project",
                    str(db_env["tmp_path"]),
                ],
            )
            assert result.exit_code == 0
            assert "Added" in result.output

    def test_add_json(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                [
                    "topics",
                    "add",
                    "--strategy",
                    "building-public",
                    "--topic",
                    "pipeline design",
                    "--project",
                    str(db_env["tmp_path"]),
                    "--json",
                ],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["topic"] == "pipeline design"
            assert data["strategy"] == "building-public"


class TestTopicsStatus:
    def test_status_valid(self, db_env_with_topic):
        with _patch_paths(db_env_with_topic):
            result = runner.invoke(
                app,
                [
                    "topics",
                    "status",
                    "topic_test1",
                    "holding",
                    "--project",
                    str(db_env_with_topic["tmp_path"]),
                ],
            )
            assert result.exit_code == 0
            assert "holding" in result.output

    def test_status_invalid(self, db_env_with_topic):
        with _patch_paths(db_env_with_topic):
            result = runner.invoke(
                app,
                [
                    "topics",
                    "status",
                    "topic_test1",
                    "invalid_status",
                    "--project",
                    str(db_env_with_topic["tmp_path"]),
                ],
            )
            assert result.exit_code == 1

    def test_status_not_found(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                [
                    "topics",
                    "status",
                    "nonexistent",
                    "covered",
                    "--project",
                    str(db_env["tmp_path"]),
                ],
            )
            assert result.exit_code == 1

    def test_status_json(self, db_env_with_topic):
        with _patch_paths(db_env_with_topic):
            result = runner.invoke(
                app,
                [
                    "topics",
                    "status",
                    "topic_test1",
                    "partial",
                    "--project",
                    str(db_env_with_topic["tmp_path"]),
                    "--json",
                ],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["status"] == "partial"


class TestTopicsReorder:
    def test_reorder(self, db_env_with_topic):
        with _patch_paths(db_env_with_topic):
            result = runner.invoke(
                app,
                [
                    "topics",
                    "reorder",
                    "--strategy",
                    "building-public",
                    "--id",
                    "topic_test1",
                    "--rank",
                    "10",
                    "--project",
                    str(db_env_with_topic["tmp_path"]),
                ],
            )
            assert result.exit_code == 0
            assert "rank 10" in result.output

    def test_reorder_not_found(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                [
                    "topics",
                    "reorder",
                    "--strategy",
                    "building-public",
                    "--id",
                    "nonexistent",
                    "--rank",
                    "1",
                    "--project",
                    str(db_env["tmp_path"]),
                ],
            )
            assert result.exit_code == 1


class TestTopicsDraftNow:
    def _set_topic_holding(self, db_env):
        """Set the test topic to 'holding' status so draft-now can proceed."""
        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.execute("UPDATE content_topics SET status = 'holding' WHERE id = 'topic_test1'")
        conn.commit()
        conn.close()

    def test_draft_now(self, db_env_with_topic):
        self._set_topic_holding(db_env_with_topic)
        with (
            _patch_paths(db_env_with_topic),
            patch("social_hook.topics.force_draft_topic", return_value="cycle_mock1"),
            patch("social_hook.config.yaml.load_full_config"),
        ):
            result = runner.invoke(
                app,
                [
                    "topics",
                    "draft-now",
                    "topic_test1",
                    "--project",
                    str(db_env_with_topic["tmp_path"]),
                ],
            )
            assert result.exit_code == 0
            assert "cycle_mock1" in result.output

    def test_draft_now_json(self, db_env_with_topic):
        self._set_topic_holding(db_env_with_topic)
        with (
            _patch_paths(db_env_with_topic),
            patch("social_hook.topics.force_draft_topic", return_value="cycle_mock1"),
            patch("social_hook.config.yaml.load_full_config"),
        ):
            result = runner.invoke(
                app,
                [
                    "topics",
                    "draft-now",
                    "topic_test1",
                    "--project",
                    str(db_env_with_topic["tmp_path"]),
                    "--json",
                ],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["cycle_id"] == "cycle_mock1"
            assert data["topic_id"] == "topic_test1"

    def test_draft_now_wrong_status(self, db_env_with_topic):
        """Topic with non-draftable status should be rejected."""
        # Set status to 'covered' — not draftable
        conn = sqlite3.connect(str(db_env_with_topic["db_path"]))
        conn.execute("UPDATE content_topics SET status = 'covered' WHERE id = 'topic_test1'")
        conn.commit()
        conn.close()

        with _patch_paths(db_env_with_topic):
            result = runner.invoke(
                app,
                [
                    "topics",
                    "draft-now",
                    "topic_test1",
                    "--project",
                    str(db_env_with_topic["tmp_path"]),
                ],
            )
            assert result.exit_code == 1
            assert "Only held or uncovered topics" in result.output

    def test_draft_now_not_found(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                [
                    "topics",
                    "draft-now",
                    "nonexistent",
                    "--project",
                    str(db_env["tmp_path"]),
                ],
            )
            assert result.exit_code == 1


# =============================================================================
# Brief
# =============================================================================


class TestBriefShow:
    def test_show_empty(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["brief", "show", "--project", str(db_env["tmp_path"])])
            assert result.exit_code == 0
            assert "No brief" in result.output

    def test_show_with_brief(self, db_env):
        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.execute(
            "UPDATE projects SET summary = ? WHERE id = ?",
            ("Test project summary", "proj_test1"),
        )
        conn.commit()
        conn.close()

        with _patch_paths(db_env):
            result = runner.invoke(app, ["brief", "show", "--project", str(db_env["tmp_path"])])
            assert result.exit_code == 0
            assert "Test project summary" in result.output

    def test_show_json(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app, ["brief", "show", "--project", str(db_env["tmp_path"]), "--json"]
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "brief" in data


class TestBriefEdit:
    def test_edit_no_changes(self, db_env):
        with _patch_paths(db_env), patch.dict("os.environ", {"EDITOR": "true"}, clear=False):
            result = runner.invoke(app, ["brief", "edit", "--project", str(db_env["tmp_path"])])
            assert result.exit_code == 0
            assert "No changes" in result.output


# =============================================================================
# Content
# =============================================================================


class TestContentSuggest:
    def test_suggest(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                [
                    "content",
                    "suggest",
                    "--idea",
                    "Show the new feature",
                    "--project",
                    str(db_env["tmp_path"]),
                ],
            )
            assert result.exit_code == 0
            assert "Suggestion created" in result.output

    def test_suggest_with_strategy(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                [
                    "content",
                    "suggest",
                    "--idea",
                    "Launch announcement",
                    "--strategy",
                    "brand-primary",
                    "--project",
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
                    "Test idea",
                    "--project",
                    str(db_env["tmp_path"]),
                    "--json",
                ],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["idea"] == "Test idea"


class TestContentList:
    def test_list_empty(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["content", "list", "--project", str(db_env["tmp_path"])])
            assert result.exit_code == 0
            assert "No content suggestions" in result.output

    def test_list_with_suggestions(self, db_env_with_suggestion):
        with _patch_paths(db_env_with_suggestion):
            result = runner.invoke(
                app, ["content", "list", "--project", str(db_env_with_suggestion["tmp_path"])]
            )
            assert result.exit_code == 0
            assert "Test idea" in result.output

    def test_list_json(self, db_env_with_suggestion):
        with _patch_paths(db_env_with_suggestion):
            result = runner.invoke(
                app,
                [
                    "content",
                    "list",
                    "--project",
                    str(db_env_with_suggestion["tmp_path"]),
                    "--json",
                ],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data["suggestions"]) == 1


class TestContentDismiss:
    def test_dismiss_requires_yes(self, db_env_with_suggestion):
        with _patch_paths(db_env_with_suggestion):
            result = runner.invoke(
                app,
                [
                    "content",
                    "dismiss",
                    "suggestion_test1",
                    "--project",
                    str(db_env_with_suggestion["tmp_path"]),
                ],
                input="n\n",
            )
            assert result.exit_code == 0
            assert "Cancelled" in result.output

    def test_dismiss_with_yes(self, db_env_with_suggestion):
        with _patch_paths(db_env_with_suggestion):
            result = runner.invoke(
                app,
                [
                    "content",
                    "dismiss",
                    "suggestion_test1",
                    "--yes",
                    "--project",
                    str(db_env_with_suggestion["tmp_path"]),
                ],
            )
            assert result.exit_code == 0
            assert "dismissed" in result.output

    def test_dismiss_not_found(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                [
                    "content",
                    "dismiss",
                    "nonexistent",
                    "--yes",
                    "--project",
                    str(db_env["tmp_path"]),
                ],
            )
            assert result.exit_code == 1

    def test_dismiss_json(self, db_env_with_suggestion):
        with _patch_paths(db_env_with_suggestion):
            result = runner.invoke(
                app,
                [
                    "content",
                    "dismiss",
                    "suggestion_test1",
                    "--yes",
                    "--project",
                    str(db_env_with_suggestion["tmp_path"]),
                    "--json",
                ],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["dismissed"] is True


class TestContentHeroLaunch:
    def test_hero_launch(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                ["content", "hero-launch", "--project", str(db_env["tmp_path"])],
            )
            assert result.exit_code == 0
            assert "Hero launch draft created" in result.output

    def test_hero_launch_json(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                [
                    "content",
                    "hero-launch",
                    "--project",
                    str(db_env["tmp_path"]),
                    "--json",
                ],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "draft_id" in data


# =============================================================================
# Cycles
# =============================================================================


class TestCyclesList:
    def test_list_empty(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["cycles", "list", "--project", str(db_env["tmp_path"])])
            assert result.exit_code == 0
            assert "No evaluation cycles" in result.output

    def test_list_with_cycles(self, db_env_with_cycle):
        with _patch_paths(db_env_with_cycle):
            result = runner.invoke(
                app, ["cycles", "list", "--project", str(db_env_with_cycle["tmp_path"])]
            )
            assert result.exit_code == 0
            assert "commit" in result.output

    def test_list_json(self, db_env_with_cycle):
        with _patch_paths(db_env_with_cycle):
            result = runner.invoke(
                app,
                [
                    "cycles",
                    "list",
                    "--project",
                    str(db_env_with_cycle["tmp_path"]),
                    "--json",
                ],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data["cycles"]) == 1


class TestCyclesShow:
    def test_show(self, db_env_with_cycle):
        with _patch_paths(db_env_with_cycle):
            result = runner.invoke(
                app,
                [
                    "cycles",
                    "show",
                    "cycle_test1",
                    "--project",
                    str(db_env_with_cycle["tmp_path"]),
                ],
            )
            assert result.exit_code == 0
            assert "cycle_test1" in result.output

    def test_show_not_found(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                [
                    "cycles",
                    "show",
                    "nonexistent",
                    "--project",
                    str(db_env["tmp_path"]),
                ],
            )
            assert result.exit_code == 1

    def test_show_json(self, db_env_with_cycle):
        with _patch_paths(db_env_with_cycle):
            result = runner.invoke(
                app,
                [
                    "cycles",
                    "show",
                    "cycle_test1",
                    "--project",
                    str(db_env_with_cycle["tmp_path"]),
                    "--json",
                ],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["cycle"]["id"] == "cycle_test1"


# =============================================================================
# System
# =============================================================================


class TestSystemErrors:
    def test_errors_empty(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["system", "errors"])
            assert result.exit_code == 0
            assert "No system errors" in result.output

    def test_errors_with_records(self, db_env_with_errors):
        with _patch_paths(db_env_with_errors):
            result = runner.invoke(app, ["system", "errors"])
            assert result.exit_code == 0
            assert "Test error message" in result.output

    def test_errors_json(self, db_env_with_errors):
        with _patch_paths(db_env_with_errors):
            result = runner.invoke(app, ["system", "errors", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data["errors"]) == 2

    def test_errors_limit(self, db_env_with_errors):
        with _patch_paths(db_env_with_errors):
            result = runner.invoke(app, ["system", "errors", "--limit", "1", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data["errors"]) == 1


class TestSystemHealth:
    def test_health_empty(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["system", "health"])
            assert result.exit_code == 0
            assert "healthy" in result.output

    def test_health_json(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["system", "health", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["status"] == "healthy"
            assert "by_severity" in data

    def test_health_with_errors(self, db_env_with_errors):
        with _patch_paths(db_env_with_errors):
            result = runner.invoke(app, ["system", "health"])
            assert result.exit_code == 0
            # Errors in last 24h should show some status


# =============================================================================
# Help text
# =============================================================================


class TestHelpTexts:
    """Verify all new command groups have proper help text."""

    @pytest.mark.parametrize(
        "cmd",
        [
            ["credentials", "--help"],
            ["account", "--help"],
            ["target", "--help"],
            ["strategy", "--help"],
            ["topics", "--help"],
            ["brief", "--help"],
            ["content", "--help"],
            ["cycles", "--help"],
            ["system", "--help"],
        ],
    )
    def test_help_available(self, cmd):
        result = runner.invoke(app, cmd)
        assert result.exit_code == 0

    def test_all_groups_in_main_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        for group in [
            "credentials",
            "account",
            "target",
            "strategy",
            "topics",
            "brief",
            "content",
            "cycles",
            "system",
        ]:
            assert group in result.output, f"'{group}' not found in main help"


# =============================================================================
# Dry-run
# =============================================================================


class TestDryRun:
    def test_topics_list_with_dry_run(self, db_env_with_topic):
        """--dry-run should produce no DB writes on read-only commands."""
        with _patch_paths(db_env_with_topic):
            result = runner.invoke(
                app,
                [
                    "--dry-run",
                    "topics",
                    "list",
                    "--project",
                    str(db_env_with_topic["tmp_path"]),
                ],
            )
            assert result.exit_code == 0
            assert "test topic" in result.output
