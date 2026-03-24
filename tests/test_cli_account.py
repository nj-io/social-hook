"""Tests for CLI account subcommands — list, add, validate, remove."""

import json
import sqlite3
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from social_hook.cli import app

runner = CliRunner()


@pytest.fixture()
def db_env(tmp_path):
    """Set up isolated DB."""
    from social_hook.db.connection import init_database

    db_path = tmp_path / "social_hook.db"
    conn = init_database(str(db_path))
    conn.commit()
    conn.close()
    return {"tmp_path": tmp_path, "db_path": db_path}


@pytest.fixture()
def db_env_with_account(db_env):
    """DB with an oauth_tokens row."""
    conn = sqlite3.connect(str(db_env["db_path"]))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """INSERT INTO oauth_tokens (account_name, platform, access_token, refresh_token, expires_at, updated_at)
        VALUES ('lead', 'x', 'tok_abc', 'ref_abc', '2099-01-01T00:00:00+00:00', '2026-03-01T12:00:00')"""
    )
    conn.commit()
    conn.close()
    return db_env


@pytest.fixture()
def db_env_with_expired(db_env):
    """DB with an expired token."""
    conn = sqlite3.connect(str(db_env["db_path"]))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """INSERT INTO oauth_tokens (account_name, platform, access_token, refresh_token, expires_at, updated_at)
        VALUES ('old', 'x', 'tok', 'ref', '2020-01-01T00:00:00+00:00', '2020-01-01T00:00:00')"""
    )
    conn.commit()
    conn.close()
    return db_env


def _patch_paths(db_env):
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(patch("social_hook.filesystem.get_db_path", return_value=db_env["db_path"]))
    return stack


class TestAccountList:
    def test_list_empty(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["account", "list"])
            assert result.exit_code == 0
            assert "No accounts" in result.output

    def test_list_with_valid_account(self, db_env_with_account):
        with _patch_paths(db_env_with_account):
            result = runner.invoke(app, ["account", "list"])
            assert result.exit_code == 0
            assert "lead" in result.output
            assert "valid" in result.output

    def test_list_with_expired_account(self, db_env_with_expired):
        with _patch_paths(db_env_with_expired):
            result = runner.invoke(app, ["account", "list"])
            assert result.exit_code == 0
            assert "old" in result.output
            assert "expired" in result.output

    def test_list_json_empty(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["account", "list", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["accounts"] == []

    def test_list_json_with_account(self, db_env_with_account):
        with _patch_paths(db_env_with_account):
            result = runner.invoke(app, ["account", "list", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data["accounts"]) == 1
            assert data["accounts"][0]["name"] == "lead"
            assert data["accounts"][0]["token_status"] == "valid"

    def test_list_global_json_flag(self, db_env):
        """--json on the global level works too."""
        with _patch_paths(db_env):
            result = runner.invoke(app, ["--json", "account", "list"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "accounts" in data


class TestAccountAdd:
    def test_add_unknown_platform(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app, ["account", "add", "--platform", "mastodon", "--name", "test"]
            )
            assert result.exit_code == 1
            assert "Unknown platform" in result.output

    def test_add_unknown_platform_json(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app, ["account", "add", "--platform", "mastodon", "--name", "test", "--json"]
            )
            assert result.exit_code == 1
            data = json.loads(result.output)
            assert "error" in data

    def test_add_existing_account(self, db_env_with_account):
        with _patch_paths(db_env_with_account):
            result = runner.invoke(app, ["account", "add", "--platform", "x", "--name", "lead"])
            assert result.exit_code == 1
            assert "already exists" in result.output

    def test_add_existing_account_json(self, db_env_with_account):
        with _patch_paths(db_env_with_account):
            result = runner.invoke(
                app, ["account", "add", "--platform", "x", "--name", "lead", "--json"]
            )
            assert result.exit_code == 1
            data = json.loads(result.output)
            assert "error" in data

    def test_add_missing_credentials(self, db_env):
        """Platform credentials not in .env."""
        with (
            _patch_paths(db_env),
            patch("social_hook.config.env.load_env", return_value={}),
        ):
            result = runner.invoke(app, ["account", "add", "--platform", "x", "--name", "new"])
            assert result.exit_code == 1
            assert "Missing credentials" in result.output

    def test_add_missing_credentials_json(self, db_env):
        with (
            _patch_paths(db_env),
            patch("social_hook.config.env.load_env", return_value={}),
        ):
            result = runner.invoke(
                app, ["account", "add", "--platform", "x", "--name", "new", "--json"]
            )
            assert result.exit_code == 1
            data = json.loads(result.output)
            assert "error" in data

    def test_add_env_load_error(self, db_env):
        with (
            _patch_paths(db_env),
            patch("social_hook.config.env.load_env", side_effect=RuntimeError("no .env")),
        ):
            result = runner.invoke(app, ["account", "add", "--platform", "x", "--name", "new"])
            assert result.exit_code == 1

    def test_add_env_load_error_json(self, db_env):
        with (
            _patch_paths(db_env),
            patch("social_hook.config.env.load_env", side_effect=RuntimeError("no .env")),
        ):
            result = runner.invoke(
                app, ["account", "add", "--platform", "x", "--name", "new", "--json"]
            )
            assert result.exit_code == 1
            data = json.loads(result.output)
            assert "error" in data

    def test_add_success_prints_guidance(self, db_env):
        """When credentials present, prints PKCE guidance."""
        env_vars = {"X_CLIENT_ID": "id123", "X_CLIENT_SECRET": "sec123"}
        with (
            _patch_paths(db_env),
            patch("social_hook.config.env.load_env", return_value=env_vars),
        ):
            result = runner.invoke(app, ["account", "add", "--platform", "x", "--name", "new"])
            assert result.exit_code == 0
            assert "PKCE" in result.output or "OAuth" in result.output

    def test_add_success_json(self, db_env):
        """JSON output contains pending status (preceded by guidance text)."""
        env_vars = {"X_CLIENT_ID": "id123", "X_CLIENT_SECRET": "sec123"}
        with (
            _patch_paths(db_env),
            patch("social_hook.config.env.load_env", return_value=env_vars),
        ):
            result = runner.invoke(
                app, ["account", "add", "--platform", "x", "--name", "new", "--json"]
            )
            assert result.exit_code == 0
            # Command prints guidance text then JSON — extract last JSON object
            lines = result.output.strip().split("\n")
            json_start = next(i for i, line in enumerate(lines) if line.strip().startswith("{"))
            data = json.loads("\n".join(lines[json_start:]))
            assert data["status"] == "pending"
            assert data["platform"] == "x"


class TestAccountValidate:
    def test_validate_empty(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["account", "validate"])
            assert result.exit_code == 0
            assert "No accounts" in result.output

    def test_validate_valid_token(self, db_env_with_account):
        with _patch_paths(db_env_with_account):
            result = runner.invoke(app, ["account", "validate"])
            assert result.exit_code == 0
            assert "valid" in result.output
            assert "All account tokens valid" in result.output

    def test_validate_expired_token(self, db_env_with_expired):
        with _patch_paths(db_env_with_expired):
            result = runner.invoke(app, ["account", "validate"])
            assert result.exit_code == 0
            assert "expired" in result.output
            assert "Some accounts have issues" in result.output

    def test_validate_invalid_expiry(self, db_env):
        """Token with invalid expires_at is flagged."""
        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.execute(
            """INSERT INTO oauth_tokens (account_name, platform, access_token, refresh_token, expires_at, updated_at)
            VALUES ('bad', 'x', 'tok', 'ref', 'not-a-date', '2026-01-01')"""
        )
        conn.commit()
        conn.close()

        with _patch_paths(db_env):
            result = runner.invoke(app, ["account", "validate"])
            assert result.exit_code == 0
            assert "invalid expiry" in result.output

    def test_validate_json(self, db_env_with_account):
        with _patch_paths(db_env_with_account):
            result = runner.invoke(app, ["account", "validate", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["valid"] is True
            assert len(data["accounts"]) == 1

    def test_validate_json_expired(self, db_env_with_expired):
        with _patch_paths(db_env_with_expired):
            result = runner.invoke(app, ["account", "validate", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["valid"] is False


class TestAccountRemove:
    def test_remove_not_found(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["account", "remove", "missing", "--yes"])
            assert result.exit_code == 1
            assert "not found" in result.output

    def test_remove_not_found_json(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["account", "remove", "missing", "--yes", "--json"])
            assert result.exit_code == 1
            data = json.loads(result.output)
            assert "error" in data

    def test_remove_requires_confirmation(self, db_env_with_account):
        with _patch_paths(db_env_with_account):
            result = runner.invoke(app, ["account", "remove", "lead"], input="n\n")
            assert result.exit_code == 0
            assert "Cancelled" in result.output

    def test_remove_with_yes(self, db_env_with_account):
        with _patch_paths(db_env_with_account):
            result = runner.invoke(app, ["account", "remove", "lead", "--yes"])
            assert result.exit_code == 0
            assert "removed" in result.output

        # Verify token deleted
        conn = sqlite3.connect(str(db_env_with_account["db_path"]))
        row = conn.execute("SELECT * FROM oauth_tokens WHERE account_name = 'lead'").fetchone()
        conn.close()
        assert row is None

    def test_remove_json(self, db_env_with_account):
        with _patch_paths(db_env_with_account):
            result = runner.invoke(app, ["account", "remove", "lead", "--yes", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["removed"] is True
            assert data["platform"] == "x"
