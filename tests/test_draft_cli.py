"""Tests for CLI draft subcommand."""

import json
import re
import sqlite3
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from social_hook.cli import app

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


runner = CliRunner()


@pytest.fixture()
def db_env(tmp_path):
    """Set up isolated DB with project, decision, and drafts in all statuses."""
    from social_hook.db.connection import init_database

    db_path = tmp_path / "social_hook.db"
    conn = init_database(str(db_path))

    # Insert a test project
    conn.execute(
        "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
        ("proj_test1", "test-project", str(tmp_path)),
    )

    # Insert a test decision
    conn.execute(
        "INSERT INTO decisions (id, project_id, commit_hash, decision, reasoning) VALUES (?, ?, ?, ?, ?)",
        ("dec_test1", "proj_test1", "abc123", "draft", "Good commit"),
    )

    # Insert drafts in all 8 statuses
    statuses = [
        "draft",
        "approved",
        "scheduled",
        "posted",
        "rejected",
        "failed",
        "superseded",
        "cancelled",
        "deferred",
    ]
    for status in statuses:
        media_spec = json.dumps({"prompt": "test"}) if status == "draft" else None
        media_type = "nano_banana_pro" if status == "draft" else None
        conn.execute(
            "INSERT INTO drafts (id, project_id, decision_id, platform, status, content, media_paths, media_type, media_spec) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"draft_{status}",
                "proj_test1",
                "dec_test1",
                "x",
                status,
                f"Content for {status} draft",
                "[]",
                media_type,
                media_spec,
            ),
        )

    # Insert preview-mode draft for preview guard tests
    conn.execute(
        "INSERT INTO drafts (id, project_id, decision_id, platform, status, content, media_paths, preview_mode) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("draft_preview", "proj_test1", "dec_test1", "x", "draft", "Preview content", "[]", 1),
    )

    conn.commit()
    conn.close()

    return {"tmp_path": tmp_path, "db_path": db_path}


def _patch_paths(db_env):
    """Return context manager patching filesystem paths."""
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(patch("social_hook.filesystem.get_db_path", return_value=db_env["db_path"]))
    return stack


class TestDraftApprove:
    def test_approve_draft(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "approve", "draft_draft"])
            assert result.exit_code == 0
            assert "approved" in result.output

        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT status FROM drafts WHERE id = ?", ("draft_draft",)).fetchone()
        conn.close()
        assert row["status"] == "approved"

    def test_approve_terminal_status(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "approve", "draft_posted"])
            assert result.exit_code == 1
            assert "posted" in result.output

    def test_approve_not_found(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "approve", "draft_missing"])
            assert result.exit_code == 1
            assert "not found" in result.output


class TestDraftReject:
    def test_reject_draft(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "reject", "draft_draft"])
            assert result.exit_code == 0
            assert "rejected" in result.output

    def test_reject_with_reason(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app, ["draft", "reject", "draft_approved", "--reason", "Not good enough"]
            )
            assert result.exit_code == 0

        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT last_error FROM drafts WHERE id = ?", ("draft_approved",)
        ).fetchone()
        conn.close()
        assert "Rejected: Not good enough" in row["last_error"]

    def test_reject_terminal_status(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "reject", "draft_cancelled"])
            assert result.exit_code == 1
            assert "cancelled" in result.output


class TestDraftSchedule:
    def test_schedule_with_time(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app, ["draft", "schedule", "draft_draft", "--time", "2026-03-05T14:00:00"]
            )
            assert result.exit_code == 0
            assert "scheduled" in result.output

        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT status, scheduled_time FROM drafts WHERE id = ?", ("draft_draft",)
        ).fetchone()
        conn.close()
        assert row["status"] == "scheduled"
        assert "2026-03-05" in row["scheduled_time"]

    def test_schedule_optimal_time(self, db_env):
        from datetime import datetime

        from social_hook.scheduling import ScheduleResult

        mock_result = ScheduleResult(
            datetime=datetime(2026, 3, 5, 14, 0),
            is_optimal_day=True,
            day_reason="test",
            time_reason="test",
        )

        with (
            _patch_paths(db_env),
            patch("social_hook.config.yaml.load_full_config") as mock_config,
            patch("social_hook.scheduling.calculate_optimal_time", return_value=mock_result),
        ):
            mock_config.return_value = MagicMock()
            result = runner.invoke(app, ["draft", "schedule", "draft_approved"])
            assert result.exit_code == 0
            assert "scheduled" in result.output

    def test_schedule_invalid_datetime(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app, ["draft", "schedule", "draft_draft", "--time", "not-a-date"]
            )
            assert result.exit_code == 1
            assert "Invalid datetime" in result.output

    def test_schedule_wrong_status(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "schedule", "draft_posted"])
            assert result.exit_code == 1
            assert "Cannot schedule" in result.output


class TestDraftCancel:
    def test_cancel_draft(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "cancel", "draft_draft"])
            assert result.exit_code == 0
            assert "cancelled" in result.output

        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT status FROM drafts WHERE id = ?", ("draft_draft",)).fetchone()
        conn.close()
        assert row["status"] == "cancelled"

    def test_cancel_terminal_status(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "cancel", "draft_rejected"])
            assert result.exit_code == 1
            assert "rejected" in result.output


class TestDraftRetry:
    def test_retry_failed(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "retry", "draft_failed"])
            assert result.exit_code == 0
            assert "retried" in result.output

        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT status, retry_count FROM drafts WHERE id = ?", ("draft_failed",)
        ).fetchone()
        conn.close()
        assert row["status"] == "scheduled"
        assert row["retry_count"] == 0

    def test_retry_non_failed(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "retry", "draft_draft"])
            assert result.exit_code == 1
            assert "must be 'failed'" in result.output


class TestDraftQuickApprove:
    def test_quick_approve(self, db_env):
        from datetime import datetime

        from social_hook.scheduling import ScheduleResult

        mock_result = ScheduleResult(
            datetime=datetime(2026, 3, 5, 14, 0),
            is_optimal_day=True,
            day_reason="test",
            time_reason="test",
        )

        with (
            _patch_paths(db_env),
            patch("social_hook.config.yaml.load_full_config") as mock_config,
            patch("social_hook.scheduling.calculate_optimal_time", return_value=mock_result),
        ):
            mock_config.return_value = MagicMock()
            result = runner.invoke(app, ["draft", "quick-approve", "draft_draft"])
            assert result.exit_code == 0
            assert "approved and scheduled" in result.output

    def test_quick_approve_terminal_status(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "quick-approve", "draft_posted"])
            assert result.exit_code == 1
            assert "Cannot quick-approve" in result.output


class TestDraftEdit:
    def test_edit_content(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app, ["draft", "edit", "draft_draft", "--content", "New content here"]
            )
            assert result.exit_code == 0
            assert "updated" in result.output

        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT content FROM drafts WHERE id = ?", ("draft_draft",)).fetchone()
        conn.close()
        assert row["content"] == "New content here"

    def test_edit_creates_change_record(self, db_env):
        with _patch_paths(db_env):
            runner.invoke(app, ["draft", "edit", "draft_draft", "--content", "Updated content"])

        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM draft_changes WHERE draft_id = ?", ("draft_draft",)
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["field"] == "content"
        assert row["new_value"] == "Updated content"
        assert row["changed_by"] == "human"

    def test_edit_empty_content(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "edit", "draft_draft", "--content", "   "])
            assert result.exit_code == 1
            assert "empty" in result.output

    def test_edit_not_found(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "edit", "draft_missing", "--content", "test"])
            assert result.exit_code == 1
            assert "not found" in result.output


class TestDraftMediaRemove:
    def test_remove_media(self, db_env):
        # First set some media paths
        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.execute(
            "UPDATE drafts SET media_paths = ? WHERE id = ?",
            (json.dumps(["/tmp/test.png"]), "draft_draft"),
        )
        conn.commit()
        conn.close()

        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "media-remove", "draft_draft"])
            assert result.exit_code == 0
            assert "removed" in result.output

        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT media_paths FROM drafts WHERE id = ?", ("draft_draft",)
        ).fetchone()
        conn.close()
        assert json.loads(row["media_paths"]) == []

    def test_remove_media_creates_change(self, db_env):
        with _patch_paths(db_env):
            runner.invoke(app, ["draft", "media-remove", "draft_draft"])

        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM draft_changes WHERE draft_id = ? AND field = ?",
            ("draft_draft", "media_paths"),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["new_value"] == "[]"

    def test_remove_media_not_found(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "media-remove", "draft_missing"])
            assert result.exit_code == 1
            assert "not found" in result.output


class TestDraftMediaRegen:
    def test_media_regen_success(self, db_env):
        mock_adapter = MagicMock()
        mock_adapter.generate.return_value = MagicMock(
            success=True, file_path="/tmp/test.png", error=None
        )

        with (
            _patch_paths(db_env),
            patch("social_hook.config.yaml.load_full_config") as mock_config,
            patch("social_hook.adapters.registry.get_media_adapter", return_value=mock_adapter),
        ):
            mock_config.return_value = MagicMock()
            result = runner.invoke(app, ["draft", "media-regen", "draft_draft"])
            assert result.exit_code == 0
            assert "regenerated" in result.output

    def test_media_regen_missing_spec(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "media-regen", "draft_approved"])
            assert result.exit_code == 1
            assert "No media spec" in result.output


class TestDraftList:
    def test_list_all(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "list"])
            assert result.exit_code == 0
            assert "draft_draft" in result.output or "draft" in result.output

    def test_list_by_status(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "list", "--status", "approved"])
            assert result.exit_code == 0
            assert "approved" in result.output

    def test_list_by_project(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "list", "--project", "proj_test1"])
            assert result.exit_code == 0

    def test_list_empty(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "list", "--project", "nonexistent_project"])
            assert result.exit_code == 0
            assert "No drafts found" in result.output

    def test_list_json_output(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["--json", "draft", "list", "--project", "proj_test1"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert isinstance(data, list)
            assert len(data) == 10  # All 9 statuses + preview draft


class TestDraftShow:
    def test_show_draft(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "show", "draft_draft"])
            assert result.exit_code == 0
            assert "draft_draft" in result.output
            assert "Content for draft draft" in result.output

    def test_show_not_found(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "show", "draft_missing"])
            assert result.exit_code == 1
            assert "not found" in result.output

    def test_show_json_output(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["--json", "draft", "show", "draft_draft"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["id"] == "draft_draft"
            assert "changes" in data
            assert "tweets" in data


class TestHelpJson:
    def test_help_json_valid_structure(self):
        result = runner.invoke(app, ["help", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "name" in data
        assert "commands" in data
        assert "global_options" in data
        assert "draft" in data["commands"]

    def test_help_specific_command(self):
        result = runner.invoke(app, ["help", "draft"])
        assert result.exit_code == 0
        assert "approve" in result.output
        assert "reject" in result.output

    def test_help_subcommand(self):
        result = runner.invoke(app, ["help", "draft", "approve"])
        assert result.exit_code == 0
        assert "DRAFT_ID" in strip_ansi(result.output)

    def test_help_subcommand_with_options(self):
        result = runner.invoke(app, ["help", "draft", "schedule"])
        assert result.exit_code == 0
        assert "--time" in strip_ansi(result.output)

    def test_help_json_group(self):
        result = runner.invoke(app, ["help", "--json", "draft"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["name"] == "draft"
        assert "commands" in data
        assert "approve" in data["commands"]

    def test_help_json_subcommand(self):
        result = runner.invoke(app, ["help", "--json", "draft", "schedule"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["name"] == "schedule"
        assert "options" in data
        assert any(o["name"] == "--time" for o in data["options"])

    def test_help_unknown_command(self):
        result = runner.invoke(app, ["help", "nonexistent"])
        assert result.exit_code == 1
        assert "Unknown command" in result.output

    def test_help_unknown_subcommand(self):
        result = runner.invoke(app, ["help", "draft", "nonexistent"])
        assert result.exit_code == 1
        assert "Unknown command" in result.output


class TestDraftRedraft:
    def test_redraft_calls_expert(self, db_env):
        mock_result = MagicMock()
        mock_result.refined_content = "Redrafted content here"
        mock_result.refined_media_spec = None
        mock_result.reasoning = "Applied new angle"
        mock_result.action = MagicMock()
        mock_result.action.value = "refine_draft"

        mock_expert_instance = MagicMock()
        mock_expert_instance.handle.return_value = mock_result

        with (
            _patch_paths(db_env),
            patch("social_hook.config.yaml.load_full_config") as mock_config,
            patch("social_hook.llm.factory.create_client") as mock_create,
            patch("social_hook.llm.expert.Expert", return_value=mock_expert_instance),
        ):
            mock_config.return_value = MagicMock()
            mock_create.return_value = MagicMock()
            result = runner.invoke(
                app,
                ["draft", "redraft", "draft_draft", "--angle", "focus on performance"],
            )
            assert result.exit_code == 0, result.output
            assert "redrafted" in result.output

        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT content FROM drafts WHERE id = ?", ("draft_draft",)).fetchone()
        conn.close()
        assert row["content"] == "Redrafted content here"

    def test_redraft_terminal_status_fails(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                ["draft", "redraft", "draft_rejected", "--angle", "new angle"],
            )
            assert result.exit_code == 1
            assert "Cannot redraft" in result.output

    def test_redraft_expert_no_content(self, db_env):
        mock_result = MagicMock()
        mock_result.refined_content = None
        mock_result.refined_media_spec = None
        mock_result.reasoning = "Could not find a better angle"
        mock_result.action = MagicMock()
        mock_result.action.value = "refine_draft"

        mock_expert_instance = MagicMock()
        mock_expert_instance.handle.return_value = mock_result

        with (
            _patch_paths(db_env),
            patch("social_hook.config.yaml.load_full_config") as mock_config,
            patch("social_hook.llm.factory.create_client") as mock_create,
            patch("social_hook.llm.expert.Expert", return_value=mock_expert_instance),
        ):
            mock_config.return_value = MagicMock()
            mock_create.return_value = MagicMock()
            result = runner.invoke(
                app,
                ["draft", "redraft", "draft_draft", "--angle", "new angle"],
            )
            assert result.exit_code == 1
            assert "could not refine" in result.output


class TestDraftRejectMemory:
    def test_reject_with_reason_saves_memory(self, db_env):
        with (
            _patch_paths(db_env),
            patch("social_hook.config.project.save_memory") as mock_save,
        ):
            result = runner.invoke(
                app,
                ["draft", "reject", "draft_draft", "--reason", "too technical"],
            )
            assert result.exit_code == 0
            assert "rejected" in result.output
            mock_save.assert_called_once_with(
                str(db_env["tmp_path"]),
                context="Rejected x draft",
                feedback="too technical",
                draft_id="draft_draft",
            )

    def test_reject_without_reason_no_memory(self, db_env):
        with (
            _patch_paths(db_env),
            patch("social_hook.config.project.save_memory") as mock_save,
        ):
            result = runner.invoke(app, ["draft", "reject", "draft_approved"])
            assert result.exit_code == 0
            mock_save.assert_not_called()


class TestDeferredStatusAccepted:
    """Verify deferred status is accepted by pending filter, schedule, and quick-approve."""

    def test_pending_filter_includes_deferred(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "list", "--pending"])
            assert result.exit_code == 0
            output = result.output
            assert "draft_deferred" in output

    def test_schedule_accepts_deferred(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app, ["draft", "schedule", "draft_deferred", "--time", "2026-03-10T10:00:00"]
            )
            assert result.exit_code == 0
            assert "scheduled" in result.output

    def test_quick_approve_accepts_deferred(self, db_env):
        from datetime import datetime

        from social_hook.scheduling import ScheduleResult

        mock_result = ScheduleResult(
            datetime=datetime(2026, 3, 10, 14, 0),
            is_optimal_day=True,
            day_reason="test",
            time_reason="test",
        )

        with (
            _patch_paths(db_env),
            patch("social_hook.config.yaml.load_full_config") as mock_config,
            patch("social_hook.scheduling.calculate_optimal_time", return_value=mock_result),
        ):
            mock_config.return_value = MagicMock()
            result = runner.invoke(app, ["draft", "quick-approve", "draft_deferred"])
            assert result.exit_code == 0
            assert "approved and scheduled" in result.output


class TestPostNow:
    def test_post_now_not_found(self, db_env):
        """post-now should exit 1 when draft not found."""
        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "post-now", "draft_nonexistent", "--yes"])
        assert result.exit_code == 1

    def test_post_now_preview_blocked(self, db_env):
        """post-now should reject preview-mode drafts."""
        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "post-now", "draft_preview", "--yes"])
        assert result.exit_code == 1
        assert "account" in result.output.lower()

    def test_post_now_terminal_status(self, db_env):
        """post-now should reject terminal status drafts."""
        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "post-now", "draft_posted", "--yes"])
        assert result.exit_code == 1
        assert "Cannot post" in result.output

    def test_post_now_dry_run(self, db_env):
        """--dry-run should skip posting."""
        with _patch_paths(db_env):
            result = runner.invoke(app, ["--dry-run", "draft", "post-now", "draft_draft"])
        assert result.exit_code == 0
        assert "dry run" in result.output.lower() or "dry_run" in result.output.lower()

    def test_post_now_json_preview_blocked(self, db_env):
        """--json should produce valid JSON on error."""
        # Insert a second preview draft to avoid state issues
        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.execute(
            "INSERT OR IGNORE INTO drafts (id, project_id, decision_id, platform, status, content, media_paths, preview_mode) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("draft_preview2", "proj_test1", "dec_test1", "x", "draft", "Preview", "[]", 1),
        )
        conn.commit()
        conn.close()

        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "post-now", "draft_preview2", "--yes", "--json"])
        data = json.loads(result.output)
        assert "error" in data


class TestDraftPreviewGuards:
    def test_approve_preview_blocked(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "approve", "draft_preview"])
            assert result.exit_code == 1
            assert "account" in result.output.lower()

    def test_schedule_preview_blocked(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app, ["draft", "schedule", "draft_preview", "--time", "2026-03-15T14:00:00"]
            )
            assert result.exit_code == 1
            assert "account" in result.output.lower()

    def test_quick_approve_preview_blocked(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "quick-approve", "draft_preview"])
            assert result.exit_code == 1
            assert "account" in result.output.lower()

    def test_edit_preview_allowed(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app, ["draft", "edit", "draft_preview", "--content", "Updated preview"]
            )
            assert result.exit_code == 0

    def test_reject_preview_allowed(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "reject", "draft_preview"])
            assert result.exit_code == 0


class TestDraftPromote:
    def test_promote_non_preview_rejected(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "promote", "draft_draft", "--platform", "x"])
            assert result.exit_code == 1
            assert "not in preview mode" in result.output.lower()

    def test_promote_terminal_status_rejected(self, db_env):
        # Set preview draft to superseded
        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.execute("UPDATE drafts SET status = 'superseded' WHERE id = 'draft_preview'")
        conn.commit()
        conn.close()

        with _patch_paths(db_env):
            result = runner.invoke(app, ["draft", "promote", "draft_preview", "--platform", "x"])
            assert result.exit_code == 1
            assert "Cannot promote" in result.output

    def test_promote_platform_not_enabled_rejected(self, db_env):
        # Reset preview draft status
        conn = sqlite3.connect(str(db_env["db_path"]))
        conn.execute("UPDATE drafts SET status = 'draft' WHERE id = 'draft_preview'")
        conn.commit()
        conn.close()

        mock_config = MagicMock()
        mock_config.platforms = {}

        with (
            _patch_paths(db_env),
            patch("social_hook.config.yaml.load_full_config", return_value=mock_config),
        ):
            result = runner.invoke(app, ["draft", "promote", "draft_preview", "--platform", "x"])
            assert result.exit_code == 1
            assert "not enabled" in result.output.lower()
