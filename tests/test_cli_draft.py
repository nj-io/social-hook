"""Tests for the `social-hook draft media` subapp (CLI).

Covers the five media subcommands (list / regen / edit / remove / add)
introduced by feat/multi-media. All addressing is by stable
``media_<12hex>`` id — ``--index`` is explicitly rejected. Every
command supports ``--json`` + forgiving flag placement + ``--project/-p``,
destructive ``remove`` takes ``--yes`` for non-interactive use.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from social_hook.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixture — isolated DB + project + draft with two media slots
# ---------------------------------------------------------------------------


@pytest.fixture()
def media_env(tmp_path):
    """DB seeded with one project + draft carrying two media slots.

    Two slots lets us distinguish per-id addressing (regen/edit/remove
    target one; add appends a third).
    """
    from social_hook.db.connection import init_database

    db_path = tmp_path / "social_hook.db"
    conn = init_database(str(db_path))

    conn.execute(
        "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
        ("proj_media", "media-test", str(tmp_path)),
    )
    conn.execute(
        "INSERT INTO decisions (id, project_id, commit_hash, decision, reasoning)"
        " VALUES (?, ?, ?, ?, ?)",
        ("dec_media", "proj_media", "abc123", "draft", "seed"),
    )

    specs = [
        {
            "id": "media_aaa000111222",
            "tool": "mermaid",
            "spec": {"diagram": "A-->B"},
            "caption": None,
            "user_uploaded": False,
        },
        {
            "id": "media_bbb333444555",
            "tool": "ray_so",
            "spec": {"code": "print(1)", "language": "python"},
            "caption": "hello",
            "user_uploaded": False,
        },
    ]
    conn.execute(
        "INSERT INTO drafts (id, project_id, decision_id, platform, status, content,"
        " media_specs, media_paths, media_errors, media_specs_used) VALUES"
        " (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "draft_media",
            "proj_media",
            "dec_media",
            "x",
            "draft",
            "body",
            json.dumps(specs),
            json.dumps(["", ""]),
            json.dumps([None, None]),
            json.dumps([{}, {}]),
        ),
    )
    # Second project used only for --project mismatch rejection test.
    other_repo = tmp_path / "other_repo"
    other_repo.mkdir()
    conn.execute(
        "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
        ("proj_other", "other-project", str(other_repo)),
    )

    conn.commit()
    conn.close()
    return {"tmp_path": tmp_path, "db_path": db_path, "other_repo": other_repo}


def _patch_paths(env):
    """Patch filesystem.get_db_path for the duration of one CLI invocation."""
    stack = ExitStack()
    stack.enter_context(patch("social_hook.filesystem.get_db_path", return_value=env["db_path"]))
    return stack


# ---------------------------------------------------------------------------
# media list
# ---------------------------------------------------------------------------


class TestMediaList:
    def test_list_json_returns_structured_items(self, media_env):
        with _patch_paths(media_env):
            result = runner.invoke(
                app, ["draft", "media", "list", "--draft", "draft_media", "--json"]
            )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["draft_id"] == "draft_media"
        assert len(data["media"]) == 2
        ids = [item["id"] for item in data["media"]]
        assert ids == ["media_aaa000111222", "media_bbb333444555"]
        # tool + caption + user_uploaded surfaced per-item
        tools = [item["tool"] for item in data["media"]]
        assert tools == ["mermaid", "ray_so"]
        assert data["media"][1]["caption"] == "hello"
        assert all(item["user_uploaded"] is False for item in data["media"])

    def test_list_text_output(self, media_env):
        with _patch_paths(media_env):
            result = runner.invoke(app, ["draft", "media", "list", "--draft", "draft_media"])
        assert result.exit_code == 0, result.output
        assert "media_aaa000111222" in result.output
        assert "mermaid" in result.output

    def test_list_empty_draft(self, media_env):
        """Draft with no media slots: exit 0, friendly message."""
        conn = sqlite3.connect(str(media_env["db_path"]))
        conn.execute(
            "INSERT INTO drafts (id, project_id, decision_id, platform, status, content,"
            " media_specs, media_paths, media_errors, media_specs_used)"
            " VALUES ('draft_empty', 'proj_media', 'dec_media', 'x', 'draft', 'e', '[]', '[]', '[]', '[]')"
        )
        conn.commit()
        conn.close()

        with _patch_paths(media_env):
            result = runner.invoke(app, ["draft", "media", "list", "--draft", "draft_empty"])
        assert result.exit_code == 0, result.output
        assert "No media" in result.output

    def test_list_rejects_index_flag(self, media_env):
        """--index is explicitly rejected — ID-only addressing."""
        with _patch_paths(media_env):
            result = runner.invoke(
                app,
                ["draft", "media", "list", "--draft", "draft_media", "--index", "0"],
            )
        assert result.exit_code == 1, result.output
        assert "--index is not supported" in result.output

    def test_list_json_flag_forgiving_placement_before_subcommand(self, media_env):
        """Global `social-hook --json draft media list --draft ...` must work too."""
        with _patch_paths(media_env):
            result = runner.invoke(
                app, ["--json", "draft", "media", "list", "--draft", "draft_media"]
            )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["draft_id"] == "draft_media"

    def test_list_project_mismatch_rejects(self, media_env):
        """--project pointing at a different repo than the draft's project exits 1."""
        with _patch_paths(media_env):
            result = runner.invoke(
                app,
                [
                    "draft",
                    "media",
                    "list",
                    "--draft",
                    "draft_media",
                    "--project",
                    str(media_env["other_repo"]),
                ],
            )
        assert result.exit_code == 1, result.output
        assert "does not belong" in result.output


# ---------------------------------------------------------------------------
# media regen
# ---------------------------------------------------------------------------


class TestMediaRegen:
    def _mock_adapter(self, output_path="/tmp/regen.png"):
        adapter = MagicMock()
        adapter.generate.return_value = MagicMock(success=True, file_path=output_path, error=None)
        return adapter

    def test_regen_by_id_success(self, media_env):
        mock_adapter = self._mock_adapter()
        with (
            _patch_paths(media_env),
            patch("social_hook.config.yaml.load_full_config") as mock_config,
            patch("social_hook.adapters.registry.get_media_adapter", return_value=mock_adapter),
        ):
            mock_config.return_value = MagicMock()
            result = runner.invoke(
                app,
                [
                    "draft",
                    "media",
                    "regen",
                    "--draft",
                    "draft_media",
                    "--id",
                    "media_aaa000111222",
                ],
            )
        assert result.exit_code == 0, result.output
        assert "Regenerated" in result.output

    def test_regen_all(self, media_env):
        """--all regenerates every non-uploaded item on the draft."""
        mock_adapter = self._mock_adapter()
        with (
            _patch_paths(media_env),
            patch("social_hook.config.yaml.load_full_config") as mock_config,
            patch("social_hook.adapters.registry.get_media_adapter", return_value=mock_adapter),
        ):
            mock_config.return_value = MagicMock()
            result = runner.invoke(
                app,
                ["draft", "media", "regen", "--draft", "draft_media", "--all"],
            )
        assert result.exit_code == 0, result.output
        # Two slots regenerated.
        assert mock_adapter.generate.call_count == 2

    def test_regen_mutex_both_rejected(self, media_env):
        """--id and --all together must error out."""
        with _patch_paths(media_env):
            result = runner.invoke(
                app,
                [
                    "draft",
                    "media",
                    "regen",
                    "--draft",
                    "draft_media",
                    "--id",
                    "media_aaa000111222",
                    "--all",
                ],
            )
        assert result.exit_code == 1, result.output
        assert "exactly one of --id" in result.output

    def test_regen_mutex_neither_rejected(self, media_env):
        """--id nor --all → error."""
        with _patch_paths(media_env):
            result = runner.invoke(
                app,
                ["draft", "media", "regen", "--draft", "draft_media"],
            )
        assert result.exit_code == 1, result.output
        assert "exactly one of --id" in result.output

    def test_regen_id_not_found(self, media_env):
        with _patch_paths(media_env):
            result = runner.invoke(
                app,
                [
                    "draft",
                    "media",
                    "regen",
                    "--draft",
                    "draft_media",
                    "--id",
                    "media_missing",
                ],
            )
        assert result.exit_code == 1, result.output
        assert "not found" in result.output.lower()

    def test_regen_rejects_index(self, media_env):
        with _patch_paths(media_env):
            result = runner.invoke(
                app,
                [
                    "draft",
                    "media",
                    "regen",
                    "--draft",
                    "draft_media",
                    "--all",
                    "--index",
                    "0",
                ],
            )
        assert result.exit_code == 1, result.output
        assert "--index is not supported" in result.output


# ---------------------------------------------------------------------------
# media edit
# ---------------------------------------------------------------------------


class TestMediaEdit:
    def test_edit_updates_spec(self, media_env):
        new_payload = {"diagram": "X-->Y"}
        with _patch_paths(media_env):
            result = runner.invoke(
                app,
                [
                    "draft",
                    "media",
                    "edit",
                    "--draft",
                    "draft_media",
                    "--id",
                    "media_aaa000111222",
                    "--spec",
                    json.dumps(new_payload),
                ],
            )
        assert result.exit_code == 0, result.output
        assert "Updated spec" in result.output

        conn = sqlite3.connect(str(media_env["db_path"]))
        row = conn.execute("SELECT media_specs FROM drafts WHERE id = 'draft_media'").fetchone()
        conn.close()
        specs = json.loads(row[0])
        target = next(s for s in specs if s["id"] == "media_aaa000111222")
        assert target["spec"] == new_payload
        # Tool preserved — edit should NOT change tool.
        assert target["tool"] == "mermaid"

    def test_edit_invalid_json(self, media_env):
        with _patch_paths(media_env):
            result = runner.invoke(
                app,
                [
                    "draft",
                    "media",
                    "edit",
                    "--draft",
                    "draft_media",
                    "--id",
                    "media_aaa000111222",
                    "--spec",
                    "not valid json",
                ],
            )
        assert result.exit_code == 1, result.output
        assert "Invalid JSON" in result.output

    def test_edit_non_object_spec_rejected(self, media_env):
        with _patch_paths(media_env):
            result = runner.invoke(
                app,
                [
                    "draft",
                    "media",
                    "edit",
                    "--draft",
                    "draft_media",
                    "--id",
                    "media_aaa000111222",
                    "--spec",
                    "[1, 2, 3]",
                ],
            )
        assert result.exit_code == 1, result.output
        assert "must be a JSON object" in result.output

    def test_edit_id_not_found(self, media_env):
        with _patch_paths(media_env):
            result = runner.invoke(
                app,
                [
                    "draft",
                    "media",
                    "edit",
                    "--draft",
                    "draft_media",
                    "--id",
                    "media_missing",
                    "--spec",
                    "{}",
                ],
            )
        assert result.exit_code == 1, result.output
        assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# media remove
# ---------------------------------------------------------------------------


class TestMediaRemove:
    def test_remove_yes_splices(self, media_env):
        """--yes skips confirmation; splice drops one slot from all 4 arrays."""
        with _patch_paths(media_env):
            result = runner.invoke(
                app,
                [
                    "draft",
                    "media",
                    "remove",
                    "--draft",
                    "draft_media",
                    "--id",
                    "media_aaa000111222",
                    "--yes",
                ],
            )
        assert result.exit_code == 0, result.output
        assert "Removed" in result.output

        conn = sqlite3.connect(str(media_env["db_path"]))
        row = conn.execute(
            "SELECT media_specs, media_paths, media_errors, media_specs_used"
            " FROM drafts WHERE id = 'draft_media'"
        ).fetchone()
        conn.close()
        specs = json.loads(row[0])
        # Only the second slot remains.
        assert len(specs) == 1
        assert specs[0]["id"] == "media_bbb333444555"
        # All four arrays spliced in lockstep.
        assert len(json.loads(row[1])) == 1
        assert len(json.loads(row[2])) == 1
        assert len(json.loads(row[3])) == 1

    def test_remove_writes_draft_change_with_id_format(self, media_env):
        """DraftChange field must be f'media_spec:{media_id}' — never aggregated."""
        with _patch_paths(media_env):
            runner.invoke(
                app,
                [
                    "draft",
                    "media",
                    "remove",
                    "--draft",
                    "draft_media",
                    "--id",
                    "media_aaa000111222",
                    "--yes",
                ],
            )
        conn = sqlite3.connect(str(media_env["db_path"]))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM draft_changes WHERE draft_id = ? AND field = ?",
            ("draft_media", "media_spec:media_aaa000111222"),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["new_value"] == "null"

    def test_remove_id_not_found(self, media_env):
        with _patch_paths(media_env):
            result = runner.invoke(
                app,
                [
                    "draft",
                    "media",
                    "remove",
                    "--draft",
                    "draft_media",
                    "--id",
                    "media_missing",
                    "--yes",
                ],
            )
        assert result.exit_code == 1, result.output
        assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# media add
# ---------------------------------------------------------------------------


class TestMediaAdd:
    def test_add_appends_slot_and_prints_id(self, media_env):
        with _patch_paths(media_env):
            result = runner.invoke(
                app,
                [
                    "draft",
                    "media",
                    "add",
                    "--draft",
                    "draft_media",
                    "--tool",
                    "nano_banana_pro",
                    "--spec",
                    json.dumps({"prompt": "hero shot"}),
                    "--json",
                ],
            )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["draft_id"] == "draft_media"
        new_id = data["media_id"]
        assert new_id.startswith("media_")

        conn = sqlite3.connect(str(media_env["db_path"]))
        row = conn.execute("SELECT media_specs FROM drafts WHERE id = 'draft_media'").fetchone()
        conn.close()
        specs = json.loads(row[0])
        # 2 original + 1 appended = 3
        assert len(specs) == 3
        appended = specs[2]
        assert appended["id"] == new_id
        assert appended["tool"] == "nano_banana_pro"
        assert appended["spec"] == {"prompt": "hero shot"}
        assert appended["user_uploaded"] is False

    def test_add_legacy_upload_marks_user_uploaded(self, media_env):
        """tool='legacy_upload' flags the slot as user-uploaded."""
        with _patch_paths(media_env):
            result = runner.invoke(
                app,
                [
                    "draft",
                    "media",
                    "add",
                    "--draft",
                    "draft_media",
                    "--tool",
                    "legacy_upload",
                    "--spec",
                    json.dumps({"path": "/tmp/user.png"}),
                    "--json",
                ],
            )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        new_id = data["media_id"]

        conn = sqlite3.connect(str(media_env["db_path"]))
        row = conn.execute("SELECT media_specs FROM drafts WHERE id = 'draft_media'").fetchone()
        conn.close()
        specs = json.loads(row[0])
        appended = next(s for s in specs if s["id"] == new_id)
        assert appended["user_uploaded"] is True

    def test_add_rejects_invalid_json_spec(self, media_env):
        with _patch_paths(media_env):
            result = runner.invoke(
                app,
                [
                    "draft",
                    "media",
                    "add",
                    "--draft",
                    "draft_media",
                    "--tool",
                    "mermaid",
                    "--spec",
                    "not valid json",
                ],
            )
        assert result.exit_code == 1, result.output
        assert "Invalid JSON" in result.output

    def test_add_forgiving_json_placement_after_subcommand(self, media_env):
        """--json anywhere after the subcommand must still produce JSON output."""
        with _patch_paths(media_env):
            result = runner.invoke(
                app,
                [
                    "draft",
                    "media",
                    "add",
                    "--draft",
                    "draft_media",
                    "--tool",
                    "mermaid",
                    "--spec",
                    json.dumps({"diagram": "A-->B"}),
                    "--json",
                ],
            )
        assert result.exit_code == 0, result.output
        # Output must be valid JSON.
        data = json.loads(result.output)
        assert "media_id" in data
