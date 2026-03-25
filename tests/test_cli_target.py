"""Tests for CLI target subcommands — list, add, disable, enable."""

import json
from unittest.mock import patch

import pytest
import yaml
from typer.testing import CliRunner

from social_hook.cli import app
from social_hook.constants import CONFIG_DIR_NAME

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
def db_env_with_target(db_env):
    """DB env with a content-config.yaml containing one target."""
    config_dir = db_env["tmp_path"] / CONFIG_DIR_NAME
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "content-config.yaml"
    config_path.write_text(
        yaml.dump(
            {
                "targets": [
                    {
                        "account": "product",
                        "destination": "timeline",
                        "strategy": "product-news",
                        "status": "active",
                    }
                ]
            }
        )
    )
    return db_env


def _patch_paths(db_env):
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(patch("social_hook.filesystem.get_db_path", return_value=db_env["db_path"]))
    return stack


class TestTargetList:
    def test_list_no_targets(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["target", "list", "-p", str(db_env["tmp_path"])])
            assert result.exit_code == 0
            assert "No targets" in result.output

    def test_list_with_targets(self, db_env_with_target):
        with _patch_paths(db_env_with_target):
            result = runner.invoke(
                app, ["target", "list", "-p", str(db_env_with_target["tmp_path"])]
            )
            assert result.exit_code == 0
            assert "product" in result.output
            assert "timeline" in result.output

    def test_list_json(self, db_env_with_target):
        with _patch_paths(db_env_with_target):
            result = runner.invoke(
                app,
                ["target", "list", "-p", str(db_env_with_target["tmp_path"]), "--json"],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["project"] == "test-project"
            assert len(data["targets"]) == 1
            assert data["targets"][0]["account"] == "product"

    def test_list_no_project(self, db_env):
        """No registered project at path exits 1."""
        with _patch_paths(db_env):
            result = runner.invoke(app, ["target", "list", "-p", "/nonexistent/path"])
            assert result.exit_code == 1


class TestTargetAdd:
    def test_add_creates_target(self, db_env):
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
                    "-p",
                    str(db_env["tmp_path"]),
                ],
            )
            assert result.exit_code == 0
            assert "Added" in result.output

        # Verify file written
        config_path = db_env["tmp_path"] / CONFIG_DIR_NAME / "content-config.yaml"
        data = yaml.safe_load(config_path.read_text())
        assert len(data["targets"]) == 1
        assert data["targets"][0]["account"] == "lead"

    def test_add_json(self, db_env):
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
                    "bp",
                    "-p",
                    str(db_env["tmp_path"]),
                    "--json",
                ],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["added"] is True
            assert data["target"]["account"] == "lead"

    def test_add_duplicate_fails(self, db_env_with_target):
        with _patch_paths(db_env_with_target):
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
                    "-p",
                    str(db_env_with_target["tmp_path"]),
                ],
            )
            assert result.exit_code == 1
            assert "already exists" in result.output

    def test_add_duplicate_json(self, db_env_with_target):
        with _patch_paths(db_env_with_target):
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
                    "-p",
                    str(db_env_with_target["tmp_path"]),
                    "--json",
                ],
            )
            assert result.exit_code == 1
            data = json.loads(result.output)
            assert "error" in data


class TestTargetDisable:
    def test_disable_with_yes(self, db_env_with_target):
        with _patch_paths(db_env_with_target):
            result = runner.invoke(
                app,
                [
                    "target",
                    "disable",
                    "product/timeline",
                    "--yes",
                    "-p",
                    str(db_env_with_target["tmp_path"]),
                ],
            )
            assert result.exit_code == 0
            assert "disabled" in result.output

        # Verify config updated
        config_path = db_env_with_target["tmp_path"] / CONFIG_DIR_NAME / "content-config.yaml"
        data = yaml.safe_load(config_path.read_text())
        assert data["targets"][0]["status"] == "disabled"

    def test_disable_json(self, db_env_with_target):
        with _patch_paths(db_env_with_target):
            result = runner.invoke(
                app,
                [
                    "target",
                    "disable",
                    "product/timeline",
                    "--yes",
                    "--json",
                    "-p",
                    str(db_env_with_target["tmp_path"]),
                ],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["disabled"] is True

    def test_disable_not_found(self, db_env_with_target):
        with _patch_paths(db_env_with_target):
            result = runner.invoke(
                app,
                [
                    "target",
                    "disable",
                    "nonexistent/tl",
                    "--yes",
                    "-p",
                    str(db_env_with_target["tmp_path"]),
                ],
            )
            assert result.exit_code == 1
            assert "not found" in result.output

    def test_disable_not_found_json(self, db_env_with_target):
        with _patch_paths(db_env_with_target):
            result = runner.invoke(
                app,
                [
                    "target",
                    "disable",
                    "nonexistent",
                    "--yes",
                    "--json",
                    "-p",
                    str(db_env_with_target["tmp_path"]),
                ],
            )
            assert result.exit_code == 1
            data = json.loads(result.output)
            assert "error" in data

    def test_disable_already_disabled(self, db_env_with_target):
        # Manually set to disabled
        config_path = db_env_with_target["tmp_path"] / CONFIG_DIR_NAME / "content-config.yaml"
        data = yaml.safe_load(config_path.read_text())
        data["targets"][0]["status"] = "disabled"
        config_path.write_text(yaml.dump(data))

        with _patch_paths(db_env_with_target):
            result = runner.invoke(
                app,
                [
                    "target",
                    "disable",
                    "product/timeline",
                    "--yes",
                    "-p",
                    str(db_env_with_target["tmp_path"]),
                ],
            )
            assert result.exit_code == 0
            assert "already disabled" in result.output

    def test_disable_requires_confirmation(self, db_env_with_target):
        with _patch_paths(db_env_with_target):
            result = runner.invoke(
                app,
                [
                    "target",
                    "disable",
                    "product/timeline",
                    "-p",
                    str(db_env_with_target["tmp_path"]),
                ],
                input="n\n",
            )
            assert result.exit_code == 0
            assert "Cancelled" in result.output

    def test_disable_no_config_file(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                ["target", "disable", "product/tl", "--yes", "-p", str(db_env["tmp_path"])],
            )
            assert result.exit_code == 1
            assert "No targets" in result.output

    def test_disable_by_account_only(self, db_env_with_target):
        """Disable by account name alone (no /destination)."""
        with _patch_paths(db_env_with_target):
            result = runner.invoke(
                app,
                [
                    "target",
                    "disable",
                    "product",
                    "--yes",
                    "-p",
                    str(db_env_with_target["tmp_path"]),
                ],
            )
            assert result.exit_code == 0
            assert "disabled" in result.output


class TestTargetEnable:
    def _make_disabled(self, db_env_with_target):
        config_path = db_env_with_target["tmp_path"] / CONFIG_DIR_NAME / "content-config.yaml"
        data = yaml.safe_load(config_path.read_text())
        data["targets"][0]["status"] = "disabled"
        config_path.write_text(yaml.dump(data))

    def test_enable(self, db_env_with_target):
        self._make_disabled(db_env_with_target)
        with _patch_paths(db_env_with_target):
            result = runner.invoke(
                app,
                ["target", "enable", "product/timeline", "-p", str(db_env_with_target["tmp_path"])],
            )
            assert result.exit_code == 0
            assert "enabled" in result.output

    def test_enable_json(self, db_env_with_target):
        self._make_disabled(db_env_with_target)
        with _patch_paths(db_env_with_target):
            result = runner.invoke(
                app,
                [
                    "target",
                    "enable",
                    "product/timeline",
                    "--json",
                    "-p",
                    str(db_env_with_target["tmp_path"]),
                ],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["enabled"] is True

    def test_enable_already_active(self, db_env_with_target):
        with _patch_paths(db_env_with_target):
            result = runner.invoke(
                app,
                ["target", "enable", "product/timeline", "-p", str(db_env_with_target["tmp_path"])],
            )
            assert result.exit_code == 0
            assert "already active" in result.output

    def test_enable_not_found(self, db_env_with_target):
        with _patch_paths(db_env_with_target):
            result = runner.invoke(
                app,
                ["target", "enable", "nonexistent", "-p", str(db_env_with_target["tmp_path"])],
            )
            assert result.exit_code == 1
            assert "not found" in result.output

    def test_enable_not_found_json(self, db_env_with_target):
        with _patch_paths(db_env_with_target):
            result = runner.invoke(
                app,
                [
                    "target",
                    "enable",
                    "nonexistent",
                    "--json",
                    "-p",
                    str(db_env_with_target["tmp_path"]),
                ],
            )
            assert result.exit_code == 1
            data = json.loads(result.output)
            assert "error" in data

    def test_enable_no_config_file(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                ["target", "enable", "product/tl", "-p", str(db_env["tmp_path"])],
            )
            assert result.exit_code == 1
            assert "No targets" in result.output
