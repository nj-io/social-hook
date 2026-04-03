"""Tests for CLI credentials subcommands — list, add, validate, remove."""

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


def _patch_paths(db_env):
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(patch("social_hook.filesystem.get_db_path", return_value=db_env["db_path"]))
    return stack


def _patch_env(db_env, env_vars):
    """Patch both DB path and load_env."""
    from contextlib import ExitStack

    env_path = db_env["tmp_path"] / ".env"
    lines = [f"{k}={v}" for k, v in env_vars.items()]
    env_path.write_text("\n".join(lines) + "\n" if lines else "")

    stack = ExitStack()
    stack.enter_context(patch("social_hook.filesystem.get_db_path", return_value=db_env["db_path"]))
    stack.enter_context(patch("social_hook.filesystem.get_env_path", return_value=env_path))
    stack.enter_context(patch("social_hook.config.env.load_env", return_value=dict(env_vars)))
    return stack


class TestCredentialsList:
    def test_list_none_configured(self, db_env):
        with _patch_env(db_env, {}):
            result = runner.invoke(app, ["credentials", "list"])
            assert result.exit_code == 0
            assert "not_configured" in result.output or "Platform" in result.output

    def test_list_configured(self, db_env):
        env_vars = {"X_CLIENT_ID": "id123", "X_CLIENT_SECRET": "sec123"}
        with _patch_env(db_env, env_vars):
            result = runner.invoke(app, ["credentials", "list"])
            assert result.exit_code == 0
            assert "configured" in result.output

    def test_list_partial(self, db_env):
        env_vars = {"X_CLIENT_ID": "id123"}
        with _patch_env(db_env, env_vars):
            result = runner.invoke(app, ["credentials", "list"])
            assert result.exit_code == 0
            assert "partial" in result.output

    def test_list_json(self, db_env):
        env_vars = {"X_CLIENT_ID": "id123", "X_CLIENT_SECRET": "sec123"}
        with _patch_env(db_env, env_vars):
            result = runner.invoke(app, ["credentials", "list", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "credentials" in data
            x_entry = next(c for c in data["credentials"] if c["platform"] == "x")
            assert x_entry["status"] == "configured"
            assert x_entry["configured_keys"] == 2

    def test_list_env_load_error(self, db_env):
        with (
            _patch_paths(db_env),
            patch("social_hook.config.env.load_env", side_effect=RuntimeError("bad env")),
        ):
            result = runner.invoke(app, ["credentials", "list"])
            assert result.exit_code == 1

    def test_list_env_load_error_json(self, db_env):
        with (
            _patch_paths(db_env),
            patch("social_hook.config.env.load_env", side_effect=RuntimeError("bad env")),
        ):
            result = runner.invoke(app, ["credentials", "list", "--json"])
            assert result.exit_code == 1
            data = json.loads(result.output)
            assert "error" in data


class TestCredentialsAdd:
    def test_add_unknown_platform(self, db_env):
        with _patch_env(db_env, {}):
            result = runner.invoke(app, ["credentials", "add", "--platform", "mastodon"])
            assert result.exit_code == 1
            assert "Unknown platform" in result.output

    def test_add_unknown_platform_json(self, db_env):
        with _patch_env(db_env, {}):
            result = runner.invoke(app, ["credentials", "add", "--platform", "mastodon", "--json"])
            assert result.exit_code == 1
            data = json.loads(result.output)
            assert "error" in data

    def test_add_no_changes(self, db_env):
        """If user enters empty for all prompts, no changes made."""
        with _patch_env(db_env, {}):
            # Empty input for both X_CLIENT_ID and X_CLIENT_SECRET
            result = runner.invoke(app, ["credentials", "add", "--platform", "x"], input="\n\n")
            assert result.exit_code == 0
            assert "No changes" in result.output

    def test_add_writes_env(self, db_env):
        """Entering values writes to .env file."""
        env_path = db_env["tmp_path"] / ".env"
        env_path.write_text("")

        with (
            _patch_paths(db_env),
            patch("social_hook.filesystem.get_env_path", return_value=env_path),
            patch("social_hook.config.env.load_env", return_value={}),
        ):
            result = runner.invoke(
                app,
                ["credentials", "add", "--platform", "x"],
                input="my_client_id\nmy_client_secret\n",
            )
            assert result.exit_code == 0
            assert "Updated" in result.output

        content = env_path.read_text()
        assert "X_CLIENT_ID=my_client_id" in content
        assert "X_CLIENT_SECRET=my_client_secret" in content

    def test_add_json_output(self, db_env):
        env_path = db_env["tmp_path"] / ".env"
        env_path.write_text("")

        with (
            _patch_paths(db_env),
            patch("social_hook.filesystem.get_env_path", return_value=env_path),
            patch("social_hook.config.env.load_env", return_value={}),
        ):
            result = runner.invoke(
                app,
                ["credentials", "add", "--platform", "x", "--json"],
                input="id1\nsec1\n",
            )
            assert result.exit_code == 0
            # Prompt lines precede the JSON — extract last JSON object
            lines = result.output.strip().split("\n")
            json_start = next(i for i, line in enumerate(lines) if line.strip().startswith("{"))
            data = json.loads("\n".join(lines[json_start:]))
            assert data["added"] is True
            assert data["platform"] == "x"

    def test_add_updates_existing(self, db_env):
        """Updating an existing key replaces it in-place."""
        env_path = db_env["tmp_path"] / ".env"
        env_path.write_text("X_CLIENT_ID=old_id\nX_CLIENT_SECRET=old_sec\n")

        with (
            _patch_paths(db_env),
            patch("social_hook.filesystem.get_env_path", return_value=env_path),
            patch(
                "social_hook.config.env.load_env",
                return_value={"X_CLIENT_ID": "old_id", "X_CLIENT_SECRET": "old_sec"},
            ),
        ):
            result = runner.invoke(
                app,
                ["credentials", "add", "--platform", "x"],
                input="new_id\n\n",  # update first, skip second
            )
            assert result.exit_code == 0
            assert "Updated 1 key" in result.output

        content = env_path.read_text()
        assert "X_CLIENT_ID=new_id" in content
        # Second key remains unchanged
        assert "X_CLIENT_SECRET=old_sec" in content


class TestCredentialsValidate:
    def test_validate_all_present(self, db_env):
        env_vars = {
            "X_CLIENT_ID": "id",
            "X_CLIENT_SECRET": "sec",
            "LINKEDIN_CLIENT_ID": "lid",
            "LINKEDIN_CLIENT_SECRET": "lsec",
            "TELEGRAM_BOT_TOKEN": "tok",
        }
        with _patch_env(db_env, env_vars):
            result = runner.invoke(app, ["credentials", "validate"])
            assert result.exit_code == 0
            assert "All credentials valid" in result.output

    def test_validate_missing(self, db_env):
        with _patch_env(db_env, {"TELEGRAM_BOT_TOKEN": "tok"}):
            result = runner.invoke(app, ["credentials", "validate"])
            assert result.exit_code == 0
            assert "missing" in result.output
            assert "Some credentials are missing" in result.output

    def test_validate_json_all_valid(self, db_env):
        env_vars = {
            "X_CLIENT_ID": "id",
            "X_CLIENT_SECRET": "sec",
            "LINKEDIN_CLIENT_ID": "lid",
            "LINKEDIN_CLIENT_SECRET": "lsec",
            "TELEGRAM_BOT_TOKEN": "tok",
        }
        with _patch_env(db_env, env_vars):
            result = runner.invoke(app, ["credentials", "validate", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["valid"] is True
            assert all(p["valid"] for p in data["platforms"])

    def test_validate_json_missing(self, db_env):
        with _patch_env(db_env, {}):
            result = runner.invoke(app, ["credentials", "validate", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["valid"] is False

    def test_validate_env_load_error(self, db_env):
        with (
            _patch_paths(db_env),
            patch("social_hook.config.env.load_env", side_effect=RuntimeError("err")),
        ):
            result = runner.invoke(app, ["credentials", "validate"])
            assert result.exit_code == 1

    def test_validate_env_load_error_json(self, db_env):
        with (
            _patch_paths(db_env),
            patch("social_hook.config.env.load_env", side_effect=RuntimeError("err")),
        ):
            result = runner.invoke(app, ["credentials", "validate", "--json"])
            assert result.exit_code == 1
            data = json.loads(result.output)
            assert "error" in data


class TestCredentialsRemove:
    def test_remove_unknown_platform(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["credentials", "remove", "mastodon", "--yes"])
            assert result.exit_code == 1
            assert "Unknown credential" in result.output

    def test_remove_unknown_platform_json(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["credentials", "remove", "mastodon", "--yes", "--json"])
            assert result.exit_code == 1
            data = json.loads(result.output)
            assert "error" in data

    def test_remove_blocked_by_accounts(self, db_env):
        """Cannot remove if accounts reference the credential."""
        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.execute(
            """INSERT INTO oauth_tokens (account_name, platform, access_token, refresh_token, expires_at, updated_at)
            VALUES ('lead', 'x', 'tok', 'ref', '2099-01-01T00:00:00+00:00', '2026-01-01')"""
        )
        conn.commit()
        conn.close()

        with _patch_paths(db_env):
            result = runner.invoke(app, ["credentials", "remove", "x", "--yes"])
            assert result.exit_code == 1
            assert "accounts reference" in result.output

    def test_remove_blocked_json(self, db_env):
        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.execute(
            """INSERT INTO oauth_tokens (account_name, platform, access_token, refresh_token, expires_at, updated_at)
            VALUES ('lead', 'x', 'tok', 'ref', '2099-01-01T00:00:00+00:00', '2026-01-01')"""
        )
        conn.commit()
        conn.close()

        with _patch_paths(db_env):
            result = runner.invoke(app, ["credentials", "remove", "x", "--yes", "--json"])
            assert result.exit_code == 1
            data = json.loads(result.output)
            assert "error" in data
            assert "lead" in data["accounts"]

    def test_remove_requires_confirmation(self, db_env):
        env_path = db_env["tmp_path"] / ".env"
        env_path.write_text("X_CLIENT_ID=id\nX_CLIENT_SECRET=sec\n")

        with (
            _patch_paths(db_env),
            patch("social_hook.filesystem.get_env_path", return_value=env_path),
        ):
            result = runner.invoke(app, ["credentials", "remove", "x"], input="n\n")
            assert result.exit_code == 0
            assert "Cancelled" in result.output

    def test_remove_with_yes(self, db_env):
        env_path = db_env["tmp_path"] / ".env"
        env_path.write_text("X_CLIENT_ID=id123\nX_CLIENT_SECRET=sec456\nOTHER=keep\n")

        with (
            _patch_paths(db_env),
            patch("social_hook.filesystem.get_env_path", return_value=env_path),
        ):
            result = runner.invoke(app, ["credentials", "remove", "x", "--yes"])
            assert result.exit_code == 0
            assert "Removed" in result.output

        content = env_path.read_text()
        assert "X_CLIENT_ID" not in content
        assert "X_CLIENT_SECRET" not in content
        assert "OTHER=keep" in content

    def test_remove_json(self, db_env):
        env_path = db_env["tmp_path"] / ".env"
        env_path.write_text("X_CLIENT_ID=id\nX_CLIENT_SECRET=sec\n")

        with (
            _patch_paths(db_env),
            patch("social_hook.filesystem.get_env_path", return_value=env_path),
        ):
            result = runner.invoke(app, ["credentials", "remove", "x", "--yes", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["removed"] is True
            assert data["keys_removed"] == 2

    def test_remove_no_env_file(self, db_env):
        env_path = db_env["tmp_path"] / ".env"
        # Ensure file does not exist
        if env_path.exists():
            env_path.unlink()

        with (
            _patch_paths(db_env),
            patch("social_hook.filesystem.get_env_path", return_value=env_path),
        ):
            result = runner.invoke(app, ["credentials", "remove", "x", "--yes"])
            assert result.exit_code == 0
            assert "No .env file" in result.output
