"""Tests for CLI snapshot subcommand."""

import sqlite3
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from social_hook.cli import app

runner = CliRunner()


@pytest.fixture()
def db_env(tmp_path):
    """Set up isolated DB environment for snapshot tests."""
    from social_hook.db.connection import init_database

    db_path = tmp_path / "social_hook.db"
    conn = init_database(str(db_path))
    conn.close()

    return {"tmp_path": tmp_path, "db_path": db_path}


def _patch_paths(db_env):
    """Return context manager patching both get_db_path and get_base_path."""
    stack = ExitStack()
    stack.enter_context(
        patch("social_hook.filesystem.get_db_path", return_value=Path(db_env["db_path"]))
    )
    stack.enter_context(
        patch("social_hook.filesystem.get_base_path", return_value=Path(db_env["tmp_path"]))
    )
    # Skip API restore attempt (would hit a running web server and short-circuit file logic)
    stack.enter_context(patch("social_hook.cli.snapshot._try_api_restore", return_value=False))
    return stack


class TestSnapshotSave:
    def test_save_creates_snapshot(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["snapshot", "save", "test1"])
            assert result.exit_code == 0
            assert "Snapshot saved: test1" in result.output

        snap = db_env["tmp_path"] / "snapshots" / "test1.db"
        assert snap.exists()

    def test_save_overwrite_confirmed(self, db_env):
        snap_dir = db_env["tmp_path"] / "snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        (snap_dir / "dup.db").write_bytes(b"old")

        with _patch_paths(db_env):
            result = runner.invoke(app, ["snapshot", "save", "dup", "--yes"])
            assert result.exit_code == 0
            assert "Snapshot saved: dup" in result.output

        # Should have been replaced with real DB content
        assert (snap_dir / "dup.db").stat().st_size > 3

    def test_save_overwrite_cancelled(self, db_env):
        snap_dir = db_env["tmp_path"] / "snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        (snap_dir / "dup.db").write_bytes(b"old")

        with _patch_paths(db_env):
            result = runner.invoke(app, ["snapshot", "save", "dup"], input="n\n")
            assert result.exit_code == 0
            assert "Cancelled" in result.output

    def test_save_invalid_name(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["snapshot", "save", "bad name!"])
            assert result.exit_code == 1
            assert "Invalid name" in result.output

    def test_save_name_too_long(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["snapshot", "save", "a" * 65])
            assert result.exit_code == 1
            assert "too long" in result.output

    def test_save_json_output(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["--json", "snapshot", "save", "jsontest"])
            assert result.exit_code == 0
            import json

            data = json.loads(result.output)
            assert data["saved"] is True
            assert data["name"] == "jsontest"


class TestSnapshotRestore:
    def test_restore_success(self, db_env):
        # First save a snapshot
        snap_dir = db_env["tmp_path"] / "snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)

        from social_hook.db.connection import init_database

        snap_db = snap_dir / "good.db"
        conn = init_database(str(snap_db))
        conn.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj_snap", "snap-project", "/tmp/snap"),
        )
        conn.commit()
        conn.close()

        with _patch_paths(db_env):
            result = runner.invoke(app, ["snapshot", "restore", "good", "--yes"])
            assert result.exit_code == 0
            assert "Restored snapshot: good" in result.output

        # Verify backup was created
        assert (snap_dir / "_pre_restore.db").exists()

        # Verify restored DB has the project
        conn = sqlite3.connect(str(db_env["db_path"]))
        row = conn.execute("SELECT name FROM projects WHERE id = ?", ("proj_snap",)).fetchone()
        conn.close()
        assert row[0] == "snap-project"

    def test_restore_not_found(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["snapshot", "restore", "missing", "--yes"])
            assert result.exit_code == 1
            assert "not found" in result.output

    def test_restore_invalid_sqlite(self, db_env):
        snap_dir = db_env["tmp_path"] / "snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        (snap_dir / "corrupt.db").write_text("not a database")

        with _patch_paths(db_env):
            result = runner.invoke(app, ["snapshot", "restore", "corrupt", "--yes"])
            assert result.exit_code == 1
            assert "not a valid SQLite" in result.output

    def test_restore_cancelled(self, db_env):
        snap_dir = db_env["tmp_path"] / "snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)

        from social_hook.db.connection import init_database

        conn = init_database(str(snap_dir / "cancel.db"))
        conn.close()

        with _patch_paths(db_env):
            result = runner.invoke(app, ["snapshot", "restore", "cancel"], input="n\n")
            assert result.exit_code == 0
            assert "Cancelled" in result.output

    def test_restore_json_output(self, db_env):
        snap_dir = db_env["tmp_path"] / "snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)

        from social_hook.db.connection import init_database

        conn = init_database(str(snap_dir / "jtest.db"))
        conn.close()

        with _patch_paths(db_env):
            result = runner.invoke(app, ["--json", "snapshot", "restore", "jtest", "--yes"])
            assert result.exit_code == 0
            import json

            data = json.loads(result.output)
            assert data["restored"] is True
            assert data["name"] == "jtest"


class TestSnapshotReset:
    def test_reset_creates_fresh_db(self, db_env):
        # Add some data to current DB
        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj_old", "old", "/tmp/old"),
        )
        conn.commit()
        conn.close()

        with _patch_paths(db_env):
            result = runner.invoke(app, ["snapshot", "reset", "--yes"])
            assert result.exit_code == 0
            assert "Database reset" in result.output

        # Backup should exist
        assert (db_env["tmp_path"] / "snapshots" / "_pre_reset.db").exists()

        # Fresh DB should have no projects
        conn = sqlite3.connect(str(db_env["db_path"]))
        row = conn.execute("SELECT COUNT(*) FROM projects").fetchone()
        conn.close()
        assert row[0] == 0

    def test_reset_cancelled(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["snapshot", "reset"], input="n\n")
            assert result.exit_code == 0
            assert "Cancelled" in result.output

    def test_reset_json_output(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["--json", "snapshot", "reset", "--yes"])
            assert result.exit_code == 0
            import json

            data = json.loads(result.output)
            assert data["reset"] is True


class TestSnapshotList:
    def test_list_empty(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["snapshot", "list"])
            assert result.exit_code == 0
            assert "No snapshots found" in result.output

    def test_list_with_snapshots(self, db_env):
        snap_dir = db_env["tmp_path"] / "snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        (snap_dir / "alpha.db").write_bytes(b"x" * 1024)
        (snap_dir / "beta.db").write_bytes(b"y" * 2048)

        with _patch_paths(db_env):
            result = runner.invoke(app, ["snapshot", "list"])
            assert result.exit_code == 0
            assert "alpha" in result.output
            assert "beta" in result.output

    def test_list_excludes_underscore_prefixed(self, db_env):
        snap_dir = db_env["tmp_path"] / "snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        (snap_dir / "visible.db").write_bytes(b"data")
        (snap_dir / "_pre_restore.db").write_bytes(b"backup")

        with _patch_paths(db_env):
            result = runner.invoke(app, ["snapshot", "list"])
            assert result.exit_code == 0
            assert "visible" in result.output
            assert "_pre_restore" not in result.output

    def test_list_json_output(self, db_env):
        snap_dir = db_env["tmp_path"] / "snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        (snap_dir / "one.db").write_bytes(b"x" * 512)

        with _patch_paths(db_env):
            result = runner.invoke(app, ["--json", "snapshot", "list"])
            assert result.exit_code == 0
            import json

            data = json.loads(result.output)
            assert len(data) == 1
            assert data[0]["name"] == "one"
            assert data[0]["size_bytes"] == 512


class TestSnapshotDelete:
    def test_delete_success(self, db_env):
        snap_dir = db_env["tmp_path"] / "snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        (snap_dir / "doomed.db").write_bytes(b"data")

        with _patch_paths(db_env):
            result = runner.invoke(app, ["snapshot", "delete", "doomed", "--yes"])
            assert result.exit_code == 0
            assert "Snapshot deleted: doomed" in result.output

        assert not (snap_dir / "doomed.db").exists()

    def test_delete_not_found(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["snapshot", "delete", "ghost", "--yes"])
            assert result.exit_code == 1
            assert "not found" in result.output

    def test_delete_cancelled(self, db_env):
        snap_dir = db_env["tmp_path"] / "snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        (snap_dir / "keep.db").write_bytes(b"data")

        with _patch_paths(db_env):
            result = runner.invoke(app, ["snapshot", "delete", "keep"], input="n\n")
            assert result.exit_code == 0
            assert "Cancelled" in result.output

        assert (snap_dir / "keep.db").exists()

    def test_delete_json_output(self, db_env):
        snap_dir = db_env["tmp_path"] / "snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        (snap_dir / "jdel.db").write_bytes(b"data")

        with _patch_paths(db_env):
            result = runner.invoke(app, ["--json", "snapshot", "delete", "jdel", "--yes"])
            assert result.exit_code == 0
            import json

            data = json.loads(result.output)
            assert data["deleted"] is True
            assert data["name"] == "jdel"


class TestSnapshotHelp:
    def test_snapshot_help(self):
        result = runner.invoke(app, ["snapshot", "--help"])
        assert result.exit_code == 0
        assert "save" in result.output
        assert "restore" in result.output
        assert "reset" in result.output
        assert "list" in result.output
        assert "delete" in result.output

    def test_save_help(self):
        result = runner.invoke(app, ["snapshot", "save", "--help"])
        assert result.exit_code == 0
        assert "Example" in result.output

    def test_restore_help(self):
        result = runner.invoke(app, ["snapshot", "restore", "--help"])
        assert result.exit_code == 0
        assert "Example" in result.output
