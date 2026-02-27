"""Tests for CLI arc subcommand."""

import sqlite3
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from social_hook.cli import app

runner = CliRunner()


@pytest.fixture()
def db_env(tmp_path):
    """Set up isolated DB with project and arcs table."""
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


def _patch_paths(db_env):
    """Return context manager patching filesystem paths."""
    from contextlib import ExitStack
    stack = ExitStack()
    stack.enter_context(
        patch("social_hook.filesystem.get_db_path", return_value=db_env["db_path"])
    )
    return stack


class TestArcHelp:
    def test_arc_help(self):
        result = runner.invoke(app, ["arc", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "create" in result.output
        assert "complete" in result.output
        assert "abandon" in result.output


class TestArcList:
    def test_list_empty(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["arc", "list", "--project", str(db_env["tmp_path"])])
            assert result.exit_code == 0
            assert "No active arcs" in result.output

    def test_list_with_arcs(self, db_env):
        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.execute(
            "INSERT INTO arcs (id, project_id, theme, status, post_count) VALUES (?, ?, ?, ?, ?)",
            ("arc_001", "proj_test1", "Auth system", "active", 2),
        )
        conn.commit()
        conn.close()

        with _patch_paths(db_env):
            result = runner.invoke(app, ["arc", "list", "--project", str(db_env["tmp_path"])])
            assert result.exit_code == 0
            assert "Auth system" in result.output
            assert "2" in result.output

    def test_list_all_statuses(self, db_env):
        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.execute(
            "INSERT INTO arcs (id, project_id, theme, status) VALUES (?, ?, ?, ?)",
            ("arc_a", "proj_test1", "Active arc", "active"),
        )
        conn.execute(
            "INSERT INTO arcs (id, project_id, theme, status) VALUES (?, ?, ?, ?)",
            ("arc_c", "proj_test1", "Done arc", "completed"),
        )
        conn.commit()
        conn.close()

        with _patch_paths(db_env):
            result = runner.invoke(app, ["arc", "list", "--project", str(db_env["tmp_path"]), "--status", "all"])
            assert result.exit_code == 0
            assert "Active arc" in result.output
            assert "Done arc" in result.output

    def test_list_no_project(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["arc", "list", "--project", "/nonexistent"])
            assert result.exit_code == 1
            assert "No registered project" in result.output


class TestArcCreate:
    def test_create_arc(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["arc", "create", "Building auth", "--project", str(db_env["tmp_path"])])
            assert result.exit_code == 0
            assert "Created arc" in result.output
            assert "Building auth" in result.output

    def test_create_arc_with_notes(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, [
                "arc", "create", "Testing flow",
                "--project", str(db_env["tmp_path"]),
                "--notes", "Focus on e2e tests",
            ])
            assert result.exit_code == 0
            assert "Created arc" in result.output

        # Verify notes were saved
        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT notes FROM arcs WHERE theme = ?", ("Testing flow",)).fetchone()
        conn.close()
        assert row["notes"] == "Focus on e2e tests"

    def test_create_max_arcs_error(self, db_env):
        conn = sqlite3.connect(str(db_env["db_path"]))
        for i in range(3):
            conn.execute(
                "INSERT INTO arcs (id, project_id, theme, status) VALUES (?, ?, ?, ?)",
                (f"arc_{i}", "proj_test1", f"Arc {i}", "active"),
            )
        conn.commit()
        conn.close()

        with _patch_paths(db_env):
            result = runner.invoke(app, ["arc", "create", "One too many", "--project", str(db_env["tmp_path"])])
            assert result.exit_code == 1
            assert "Maximum 3" in result.output


class TestArcComplete:
    def test_complete_arc(self, db_env):
        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.execute(
            "INSERT INTO arcs (id, project_id, theme, status) VALUES (?, ?, ?, ?)",
            ("arc_comp", "proj_test1", "My arc", "active"),
        )
        conn.commit()
        conn.close()

        with _patch_paths(db_env):
            result = runner.invoke(app, ["arc", "complete", "arc_comp"])
            assert result.exit_code == 0
            assert "Completed arc" in result.output

        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT status FROM arcs WHERE id = ?", ("arc_comp",)).fetchone()
        conn.close()
        assert row["status"] == "completed"

    def test_complete_not_found(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["arc", "complete", "arc_missing"])
            assert result.exit_code == 1
            assert "not found" in result.output

    def test_complete_already_completed(self, db_env):
        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.execute(
            "INSERT INTO arcs (id, project_id, theme, status) VALUES (?, ?, ?, ?)",
            ("arc_done", "proj_test1", "Done", "completed"),
        )
        conn.commit()
        conn.close()

        with _patch_paths(db_env):
            result = runner.invoke(app, ["arc", "complete", "arc_done"])
            assert result.exit_code == 1
            assert "already completed" in result.output


class TestArcAbandon:
    def test_abandon_arc(self, db_env):
        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.execute(
            "INSERT INTO arcs (id, project_id, theme, status) VALUES (?, ?, ?, ?)",
            ("arc_abn", "proj_test1", "Old arc", "active"),
        )
        conn.commit()
        conn.close()

        with _patch_paths(db_env):
            result = runner.invoke(app, ["arc", "abandon", "arc_abn"])
            assert result.exit_code == 0
            assert "Abandoned arc" in result.output

        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT status FROM arcs WHERE id = ?", ("arc_abn",)).fetchone()
        conn.close()
        assert row["status"] == "abandoned"

    def test_abandon_with_notes(self, db_env):
        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.execute(
            "INSERT INTO arcs (id, project_id, theme, status) VALUES (?, ?, ?, ?)",
            ("arc_abn2", "proj_test1", "Another", "active"),
        )
        conn.commit()
        conn.close()

        with _patch_paths(db_env):
            result = runner.invoke(app, ["arc", "abandon", "arc_abn2", "--notes", "No longer relevant"])
            assert result.exit_code == 0

        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT notes FROM arcs WHERE id = ?", ("arc_abn2",)).fetchone()
        conn.close()
        assert row["notes"] == "No longer relevant"
