"""Tests for bot command handlers (T26)."""

import time
from unittest.mock import MagicMock, patch

import pytest

from social_hook.bot.commands import (
    _CONTEXT_TTL_SECONDS,
    _chat_draft_context,
    _parse_command,
    cmd_approve,
    cmd_cancel,
    cmd_help,
    cmd_pause,
    cmd_pending,
    cmd_projects,
    cmd_reject,
    cmd_resume,
    cmd_retry,
    cmd_schedule,
    cmd_scheduled,
    cmd_status,
    cmd_usage,
    get_chat_draft_context,
    handle_command,
    handle_message,
    set_chat_draft_context,
)
from social_hook.db import get_connection, init_database, insert_draft, insert_project
from social_hook.filesystem import generate_id
from social_hook.models import Draft, Project


@pytest.fixture(autouse=True)
def _clear_chat_context():
    """Clear chat draft context state between tests."""
    _chat_draft_context.clear()
    yield
    _chat_draft_context.clear()


class TestParseCommand:
    """Tests for _parse_command."""

    def test_simple_command(self):
        cmd, args = _parse_command("/status")
        assert cmd == "status"
        assert args == ""

    def test_command_with_args(self):
        cmd, args = _parse_command("/approve draft_abc")
        assert cmd == "approve"
        assert args == "draft_abc"

    def test_command_with_multiple_args(self):
        cmd, args = _parse_command("/schedule draft_abc 2026-02-10 14:00")
        assert cmd == "schedule"
        assert args == "draft_abc 2026-02-10 14:00"

    def test_command_with_bot_mention(self):
        cmd, args = _parse_command("/status@my_bot")
        assert cmd == "status"
        assert args == ""

    def test_command_uppercase(self):
        cmd, args = _parse_command("/STATUS")
        assert cmd == "status"
        assert args == ""

    def test_command_with_leading_spaces(self):
        cmd, args = _parse_command("  /help  ")
        assert cmd == "help"
        assert args == ""


class TestHandleCommand:
    """Tests for handle_command routing."""

    @patch("social_hook.bot.commands.cmd_help")
    def test_routes_help(self, mock_help):
        message = {"chat": {"id": 123}, "text": "/help"}
        handle_command(message, "token")
        mock_help.assert_called_once_with("token", "123", "", None)

    @patch("social_hook.bot.commands.cmd_status")
    def test_routes_status(self, mock_status):
        message = {"chat": {"id": 123}, "text": "/status"}
        handle_command(message, "token")
        mock_status.assert_called_once()

    @patch("social_hook.bot.commands.cmd_help")
    def test_start_routes_to_help(self, mock_help):
        message = {"chat": {"id": 123}, "text": "/start"}
        handle_command(message, "token")
        mock_help.assert_called_once()

    @patch("social_hook.bot.commands._send")
    def test_unknown_command(self, mock_send):
        message = {"chat": {"id": 123}, "text": "/nonsense"}
        handle_command(message, "token")
        mock_send.assert_called_once()
        assert "Unknown command" in mock_send.call_args[0][2]


class TestCmdHelp:
    """Tests for /help command."""

    @patch("social_hook.bot.commands._send")
    def test_sends_help_text(self, mock_send):
        cmd_help("token", "123", "", None)
        mock_send.assert_called_once()
        text = mock_send.call_args[0][2]
        assert "Social Hook Bot" in text
        assert "/status" in text
        assert "/approve" in text
        assert "/help" in text


class TestCmdStatus:
    """Tests for /status command."""

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_shows_status(self, mock_conn, mock_send, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)

        cmd_status("token", "123", "", None)
        text = mock_send.call_args[0][2]
        assert "System Status" in text
        assert "1 active" in text


class TestCmdPending:
    """Tests for /pending command."""

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_no_pending(self, mock_conn, mock_send, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        cmd_pending("token", "123", "", None)
        text = mock_send.call_args[0][2]
        assert "No pending" in text

    @patch("social_hook.bot.commands.send_notification_with_buttons")
    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_with_pending_drafts(self, mock_conn, mock_send, mock_send_buttons, temp_dir):
        from social_hook.db import insert_decision
        from social_hook.models import Decision

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc123",
            decision="post_worthy",
            reasoning="test",
        )
        insert_decision(conn, decision)

        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Test post content here",
            status="draft",
        )
        insert_draft(conn, draft)

        cmd_pending("token", "123", "", None)
        mock_send_buttons.assert_called_once()
        text = mock_send_buttons.call_args[0][2]
        assert "Test post content" in text


class TestCmdScheduled:
    """Tests for /scheduled command."""

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_no_scheduled(self, mock_conn, mock_send, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        cmd_scheduled("token", "123", "", None)
        text = mock_send.call_args[0][2]
        assert "No scheduled" in text


class TestCmdProjects:
    """Tests for /projects command."""

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_no_projects(self, mock_conn, mock_send, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        cmd_projects("token", "123", "", None)
        text = mock_send.call_args[0][2]
        assert "No registered" in text

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_with_projects(self, mock_conn, mock_send, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(id=generate_id("project"), name="my-project", repo_path="/tmp/test")
        insert_project(conn, project)

        cmd_projects("token", "123", "", None)
        text = mock_send.call_args[0][2]
        assert "Registered Projects" in text
        assert "my-project" in text


class TestCmdUsage:
    """Tests for /usage command."""

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_shows_usage(self, mock_conn, mock_send, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        cmd_usage("token", "123", "", None)
        text = mock_send.call_args[0][2]
        assert "Usage" in text


class TestCmdApprove:
    """Tests for /approve command."""

    @patch("social_hook.bot.commands._send")
    def test_no_draft_id(self, mock_send):
        cmd_approve("token", "123", "", None)
        text = mock_send.call_args[0][2]
        assert "Usage" in text

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_draft_not_found(self, mock_conn, mock_send, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        cmd_approve("token", "123", "nonexistent_id", None)
        text = mock_send.call_args[0][2]
        assert "not found" in text

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_approve_success(self, mock_conn, mock_send, temp_dir):
        from social_hook.db import get_draft, insert_decision
        from social_hook.models import Decision

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc",
            decision="post_worthy",
            reasoning="test",
        )
        insert_decision(conn, decision)

        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Test",
            status="draft",
        )
        insert_draft(conn, draft)

        cmd_approve("token", "123", draft.id, None)
        text = mock_send.call_args[0][2]
        assert "approved" in text

        # Re-open connection (command handler closes it)
        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.status == "approved"
        conn2.close()

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_approve_wrong_status(self, mock_conn, mock_send, temp_dir):
        from social_hook.db import insert_decision
        from social_hook.models import Decision

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc",
            decision="post_worthy",
            reasoning="test",
        )
        insert_decision(conn, decision)

        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Test",
            status="posted",
        )
        insert_draft(conn, draft)

        cmd_approve("token", "123", draft.id, None)
        text = mock_send.call_args[0][2]
        assert "Cannot approve" in text


class TestCmdReject:
    """Tests for /reject command."""

    @patch("social_hook.bot.commands._send")
    def test_no_draft_id(self, mock_send):
        cmd_reject("token", "123", "", None)
        assert "Usage" in mock_send.call_args[0][2]

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_reject_success(self, mock_conn, mock_send, temp_dir):
        from social_hook.db import get_draft, insert_decision
        from social_hook.models import Decision

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)
        decision = Decision(
            id=generate_id("decision"), project_id=project.id,
            commit_hash="abc", decision="post_worthy", reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"), project_id=project.id,
            decision_id=decision.id, platform="x", content="Test", status="draft",
        )
        insert_draft(conn, draft)

        cmd_reject("token", "123", draft.id, None)
        assert "rejected" in mock_send.call_args[0][2]
        conn2 = get_connection(db_path)
        assert get_draft(conn2, draft.id).status == "rejected"
        conn2.close()


class TestCmdSchedule:
    """Tests for /schedule command."""

    @patch("social_hook.bot.commands._send")
    def test_no_args(self, mock_send):
        cmd_schedule("token", "123", "", None)
        assert "Usage" in mock_send.call_args[0][2]

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_schedule_with_time(self, mock_conn, mock_send, temp_dir):
        from social_hook.db import get_draft, insert_decision
        from social_hook.models import Decision

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)
        decision = Decision(
            id=generate_id("decision"), project_id=project.id,
            commit_hash="abc", decision="post_worthy", reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"), project_id=project.id,
            decision_id=decision.id, platform="x", content="Test", status="draft",
        )
        insert_draft(conn, draft)

        cmd_schedule("token", "123", f"{draft.id} 2026-02-10T14:00:00", None)
        assert "scheduled" in mock_send.call_args[0][2]
        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.status == "scheduled"
        assert updated.scheduled_time is not None
        assert "2026-02-10" in str(updated.scheduled_time)
        conn2.close()


class TestCmdCancel:
    """Tests for /cancel command."""

    @patch("social_hook.bot.commands._send")
    def test_no_draft_id(self, mock_send):
        cmd_cancel("token", "123", "", None)
        assert "Usage" in mock_send.call_args[0][2]

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_cancel_success(self, mock_conn, mock_send, temp_dir):
        from social_hook.db import get_draft, insert_decision
        from social_hook.models import Decision

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)
        decision = Decision(
            id=generate_id("decision"), project_id=project.id,
            commit_hash="abc", decision="post_worthy", reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"), project_id=project.id,
            decision_id=decision.id, platform="x", content="Test", status="scheduled",
        )
        insert_draft(conn, draft)

        cmd_cancel("token", "123", draft.id, None)
        assert "cancelled" in mock_send.call_args[0][2]
        conn2 = get_connection(db_path)
        assert get_draft(conn2, draft.id).status == "cancelled"
        conn2.close()


class TestCmdRetry:
    """Tests for /retry command."""

    @patch("social_hook.bot.commands._send")
    def test_no_draft_id(self, mock_send):
        cmd_retry("token", "123", "", None)
        assert "Usage" in mock_send.call_args[0][2]

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_retry_failed_draft(self, mock_conn, mock_send, temp_dir):
        from social_hook.db import get_draft, insert_decision, update_draft
        from social_hook.models import Decision

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)
        decision = Decision(
            id=generate_id("decision"), project_id=project.id,
            commit_hash="abc", decision="post_worthy", reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"), project_id=project.id,
            decision_id=decision.id, platform="x", content="Test", status="failed",
        )
        insert_draft(conn, draft)

        cmd_retry("token", "123", draft.id, None)
        assert "retry" in mock_send.call_args[0][2]
        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.status == "scheduled"
        assert updated.retry_count == 0
        conn2.close()

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_retry_non_failed_draft(self, mock_conn, mock_send, temp_dir):
        from social_hook.db import insert_decision
        from social_hook.models import Decision

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)
        decision = Decision(
            id=generate_id("decision"), project_id=project.id,
            commit_hash="abc", decision="post_worthy", reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"), project_id=project.id,
            decision_id=decision.id, platform="x", content="Test", status="draft",
        )
        insert_draft(conn, draft)

        cmd_retry("token", "123", draft.id, None)
        text = mock_send.call_args[0][2]
        assert "only retry failed" in text.lower() or "Can only retry" in text


class TestCmdPause:
    """Tests for /pause command."""

    @patch("social_hook.bot.commands._send")
    def test_no_project_id(self, mock_send):
        cmd_pause("token", "123", "", None)
        assert "Usage" in mock_send.call_args[0][2]

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_pause_project(self, mock_conn, mock_send, temp_dir):
        from social_hook.db import get_project

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)

        cmd_pause("token", "123", project.id, None)
        assert "paused" in mock_send.call_args[0][2]

        conn2 = get_connection(db_path)
        updated = get_project(conn2, project.id)
        assert updated.paused is True
        conn2.close()

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_pause_already_paused(self, mock_conn, mock_send, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(
            id=generate_id("project"), name="test", repo_path="/tmp/test", paused=True
        )
        insert_project(conn, project)

        cmd_pause("token", "123", project.id, None)
        assert "already paused" in mock_send.call_args[0][2]

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_pause_not_found(self, mock_conn, mock_send, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        cmd_pause("token", "123", "nonexistent", None)
        assert "not found" in mock_send.call_args[0][2]


class TestCmdResume:
    """Tests for /resume command."""

    @patch("social_hook.bot.commands._send")
    def test_no_project_id(self, mock_send):
        cmd_resume("token", "123", "", None)
        assert "Usage" in mock_send.call_args[0][2]

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_resume_paused_project(self, mock_conn, mock_send, temp_dir):
        from social_hook.db import get_project

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(
            id=generate_id("project"), name="test", repo_path="/tmp/test", paused=True
        )
        insert_project(conn, project)

        cmd_resume("token", "123", project.id, None)
        assert "resumed" in mock_send.call_args[0][2]

        conn2 = get_connection(db_path)
        updated = get_project(conn2, project.id)
        assert updated.paused is False
        conn2.close()

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_resume_not_paused(self, mock_conn, mock_send, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)

        cmd_resume("token", "123", project.id, None)
        assert "not paused" in mock_send.call_args[0][2]


class TestCmdReview:
    """Tests for /review command."""

    @patch("social_hook.bot.commands._send")
    def test_review_no_args(self, mock_send):
        from social_hook.bot.commands import cmd_review
        cmd_review("token", "123", "", None)
        assert "Usage" in mock_send.call_args[0][2]

    @patch("social_hook.bot.commands.send_notification_with_buttons")
    @patch("social_hook.bot.commands._get_conn")
    def test_review_sends_formatted_with_buttons(self, mock_conn, mock_send_buttons, temp_dir):
        from social_hook.bot.commands import cmd_review
        from social_hook.db import insert_decision
        from social_hook.models import Decision

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(id=generate_id("project"), name="reviewproj", repo_path="/tmp/test")
        insert_project(conn, project)
        decision = Decision(
            id=generate_id("decision"), project_id=project.id,
            commit_hash="abc12345", decision="post_worthy", reasoning="Good commit",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"), project_id=project.id,
            decision_id=decision.id, platform="x", content="Review me", status="draft",
        )
        insert_draft(conn, draft)

        cmd_review("token", "123", draft.id, None)
        mock_send_buttons.assert_called_once()
        text = mock_send_buttons.call_args[0][2]
        assert "reviewproj" in text
        assert "Review me" in text
        # Check buttons passed
        buttons = mock_send_buttons.call_args[0][3]
        assert len(buttons) == 2  # Two rows of buttons


class TestCmdRegister:
    """Tests for /register command."""

    @patch("social_hook.bot.commands._send")
    def test_sends_terminal_instructions(self, mock_send):
        from social_hook.bot.commands import cmd_register
        cmd_register("token", "123", "", None)
        text = mock_send.call_args[0][2]
        assert "terminal" in text.lower()
        assert "social-hook register" in text


class TestCmdUsageDays:
    """Tests for /usage with days parameter."""

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_usage_7_days(self, mock_conn, mock_send, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        cmd_usage("token", "123", "7", None)
        text = mock_send.call_args[0][2]
        assert "7 days" in text

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_usage_default_30(self, mock_conn, mock_send, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        cmd_usage("token", "123", "", None)
        text = mock_send.call_args[0][2]
        assert "30 days" in text


class TestCmdRejectReason:
    """Tests for /reject with reason."""

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_reject_with_reason(self, mock_conn, mock_send, temp_dir):
        from social_hook.db import get_draft, insert_decision
        from social_hook.models import Decision

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)
        decision = Decision(
            id=generate_id("decision"), project_id=project.id,
            commit_hash="abc", decision="post_worthy", reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"), project_id=project.id,
            decision_id=decision.id, platform="x", content="Test", status="draft",
        )
        insert_draft(conn, draft)

        cmd_reject("token", "123", f"{draft.id} too informal", None)
        text = mock_send.call_args[0][2]
        assert "rejected" in text
        assert "too informal" in text

        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.status == "rejected"
        assert "too informal" in updated.last_error
        conn2.close()


class TestCmdHelpDetailed:
    """Tests for /help <command>."""

    @patch("social_hook.bot.commands._send")
    def test_help_approve(self, mock_send):
        cmd_help("token", "123", "approve", None)
        text = mock_send.call_args[0][2]
        assert "/approve" in text
        assert "Approve" in text

    @patch("social_hook.bot.commands._send")
    def test_help_unknown_command(self, mock_send):
        cmd_help("token", "123", "nonexistent", None)
        text = mock_send.call_args[0][2]
        assert "Unknown" in text

    @patch("social_hook.bot.commands._send")
    def test_help_no_args_shows_all(self, mock_send):
        cmd_help("token", "123", "", None)
        text = mock_send.call_args[0][2]
        assert "Social Hook Bot" in text


class TestHandleMessage:
    """Tests for free-text message handling."""

    @patch("social_hook.bot.commands._send")
    def test_no_config(self, mock_send):
        message = {"chat": {"id": 123}, "text": "Hello"}
        handle_message(message, "token", config=None)
        assert "not configured" in mock_send.call_args[0][2].lower() or "API key" in mock_send.call_args[0][2]

    @patch("social_hook.bot.commands._send")
    def test_empty_text(self, mock_send):
        message = {"chat": {"id": 123}, "text": ""}
        handle_message(message, "token")
        mock_send.assert_not_called()


class TestChatDraftContext:
    """Tests for chat draft context tracking."""

    def test_set_and_get(self):
        """Verify set/get round-trip for _chat_draft_context."""
        set_chat_draft_context("chat1", "draft_abc", "proj_123")
        result = get_chat_draft_context("chat1")
        assert result == ("draft_abc", "proj_123")

    def test_ttl_expiry(self):
        """Verify context expires after TTL."""
        _chat_draft_context["chat1"] = (
            "draft_abc", "proj_123", time.time() - _CONTEXT_TTL_SECONDS - 60
        )
        result = get_chat_draft_context("chat1")
        assert result is None
        assert "chat1" not in _chat_draft_context

    def test_missing(self):
        """Verify returns None for unknown chat_id."""
        assert get_chat_draft_context("unknown") is None


class TestPendingEditSaves:
    """Tests for pending edit save flow (handle_message → _save_edit)."""

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_pending_edit_saves_content(self, mock_conn, mock_send, temp_dir):
        """Mock pending edit, send message, verify update_draft called."""
        from social_hook.bot.buttons import _pending_edits
        from social_hook.db import get_draft, insert_decision
        from social_hook.models import Decision

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)
        decision = Decision(
            id=generate_id("decision"), project_id=project.id,
            commit_hash="abc", decision="post_worthy", reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"), project_id=project.id,
            decision_id=decision.id, platform="x",
            content="Old content", status="draft",
        )
        insert_draft(conn, draft)

        # Set pending edit
        _pending_edits["123"] = (draft.id, time.time())

        message = {"chat": {"id": 123}, "text": "Brand new content here"}
        handle_message(message, "token", config=None)

        # Verify content was updated
        text = mock_send.call_args[0][2]
        assert "updated" in text
        assert "Brand new content" in text

        # Verify DB was updated
        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.content == "Brand new content here"
        conn2.close()

        # Verify pending edit was cleared
        assert "123" not in _pending_edits

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_pending_edit_creates_audit_trail(self, mock_conn, mock_send, temp_dir):
        """Verify insert_draft_change called with changed_by='human'."""
        from social_hook.bot.buttons import _pending_edits
        from social_hook.db import insert_decision
        from social_hook.models import Decision

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)
        decision = Decision(
            id=generate_id("decision"), project_id=project.id,
            commit_hash="abc", decision="post_worthy", reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"), project_id=project.id,
            decision_id=decision.id, platform="x",
            content="Old content", status="draft",
        )
        insert_draft(conn, draft)

        _pending_edits["123"] = (draft.id, time.time())

        message = {"chat": {"id": 123}, "text": "New content"}
        handle_message(message, "token", config=None)

        # Verify audit trail
        conn2 = get_connection(db_path)
        rows = conn2.execute(
            "SELECT field, changed_by FROM draft_changes WHERE draft_id = ?",
            (draft.id,),
        ).fetchall()
        conn2.close()
        assert len(rows) == 1
        assert rows[0][0] == "content"
        assert rows[0][1] == "human"

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_pending_edit_draft_not_found(self, mock_conn, mock_send, temp_dir):
        """Verify error message when draft is gone."""
        from social_hook.bot.buttons import _pending_edits

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        _pending_edits["123"] = ("nonexistent_draft", time.time())

        message = {"chat": {"id": 123}, "text": "New content"}
        handle_message(message, "token", config=None)

        text = mock_send.call_args[0][2]
        assert "not found" in text


class TestSubstituteHandler:
    """Tests for Gatekeeper substitute operation handling."""

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_substitute_saves_content(self, mock_conn, mock_send, temp_dir):
        """Substitute operation saves content to DB."""
        from social_hook.db import get_draft, insert_decision
        from social_hook.models import Decision

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)
        decision = Decision(
            id=generate_id("decision"), project_id=project.id,
            commit_hash="abc", decision="post_worthy", reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"), project_id=project.id,
            decision_id=decision.id, platform="x",
            content="Old content", status="draft",
        )
        insert_draft(conn, draft)

        # Simulate gatekeeper route for substitute
        route = MagicMock()
        route.operation.value = "substitute"
        route.params = {"content": "Replaced content", "draft_id": draft.id}

        from social_hook.bot.commands import _handle_gatekeeper_direct

        _handle_gatekeeper_direct("token", "123", route, None)

        text = mock_send.call_args[0][2]
        assert "updated" in text

        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.content == "Replaced content"
        conn2.close()

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_substitute_uses_chat_context(self, mock_conn, mock_send, temp_dir):
        """Verify draft_id resolved from get_chat_draft_context when not in params."""
        from social_hook.db import get_draft, insert_decision
        from social_hook.models import Decision

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)
        decision = Decision(
            id=generate_id("decision"), project_id=project.id,
            commit_hash="abc", decision="post_worthy", reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"), project_id=project.id,
            decision_id=decision.id, platform="x",
            content="Old content", status="draft",
        )
        insert_draft(conn, draft)

        # Set chat context (no draft_id in params)
        set_chat_draft_context("123", draft.id, project.id)

        route = MagicMock()
        route.operation.value = "substitute"
        route.params = {"content": "New via context"}  # No draft_id

        from social_hook.bot.commands import _handle_gatekeeper_direct

        _handle_gatekeeper_direct("token", "123", route, None)

        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.content == "New via context"
        conn2.close()

    @patch("social_hook.bot.commands._send")
    def test_substitute_no_context_shows_error(self, mock_send):
        """Verify error message when no chat context and no draft_id in params."""
        route = MagicMock()
        route.operation.value = "substitute"
        route.params = {"content": "New content"}  # No draft_id

        from social_hook.bot.commands import _handle_gatekeeper_direct

        _handle_gatekeeper_direct("token", "123", route, None)

        text = mock_send.call_args[0][2]
        assert "No active draft" in text


class TestReviewEvaluatorContext:
    """Tests for enhanced /review with evaluator context."""

    @patch("social_hook.bot.commands.send_notification_with_buttons")
    @patch("social_hook.bot.commands._get_conn")
    def test_review_shows_evaluator_context(self, mock_conn, mock_send_buttons, temp_dir):
        """Verify angle, episode_type, post_category in formatted review output."""
        from social_hook.bot.commands import cmd_review
        from social_hook.db import insert_decision
        from social_hook.models import Decision

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(id=generate_id("project"), name="reviewproj", repo_path="/tmp/test")
        insert_project(conn, project)
        decision = Decision(
            id=generate_id("decision"), project_id=project.id,
            commit_hash="abc12345", decision="post_worthy",
            reasoning="Strong commit with clear narrative",
            episode_type="launch",
            post_category="arc",
            angle="Show how the new API simplifies integration",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"), project_id=project.id,
            decision_id=decision.id, platform="x",
            content="Check out our new API", status="draft",
        )
        insert_draft(conn, draft)

        cmd_review("token", "123", draft.id, None)
        mock_send_buttons.assert_called_once()
        text = mock_send_buttons.call_args[0][2]
        assert "Episode: launch" in text
        assert "Category: arc" in text
        assert "Angle:" in text
        assert "simplifies integration" in text
        assert "Strong commit" in text


class TestExpertRefineSaves:
    """Tests for Expert refinement saving to DB."""

    @patch("social_hook.bot.commands.send_notification_with_buttons")
    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_expert_refine_saves_to_db(self, mock_conn, mock_send, mock_send_buttons, temp_dir):
        """Verify update_draft called after refine_draft action."""
        from social_hook.db import get_draft, insert_decision
        from social_hook.models import Decision

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)
        decision = Decision(
            id=generate_id("decision"), project_id=project.id,
            commit_hash="abc", decision="post_worthy", reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"), project_id=project.id,
            decision_id=decision.id, platform="x",
            content="Original content", status="draft",
        )
        insert_draft(conn, draft)

        # Mock the expert result
        expert_result = MagicMock()
        expert_result.action.value = "refine_draft"
        expert_result.refined_content = "Punchy improved content"
        expert_result.context_note = None
        expert_result.answer = None
        expert_result.reasoning = "Made it punchier"

        route = MagicMock()
        route.escalation_reason = "user request"
        route.escalation_context = "make it punchier"

        config = MagicMock()
        config.models.drafter = "anthropic/claude-sonnet-4-5"

        with patch("social_hook.llm.factory.create_client") as mock_create:
            with patch("social_hook.llm.expert.Expert") as MockExpert:
                MockExpert.return_value.handle.return_value = expert_result

                from social_hook.bot.commands import _handle_expert_escalation

                # Create a mock draft object for context
                draft_obj = get_draft(conn, draft.id)

                _handle_expert_escalation(
                    "token", "123", "make it punchier", route, config,
                    draft=draft_obj, project_id=project.id,
                )

        # Verify buttons were sent
        mock_send_buttons.assert_called_once()
        text = mock_send_buttons.call_args[0][2]
        assert "updated by Expert" in text
        assert "Punchy improved content" in text

        # Verify DB was updated
        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.content == "Punchy improved content"

        # Verify audit trail
        rows = conn2.execute(
            "SELECT changed_by FROM draft_changes WHERE draft_id = ?",
            (draft.id,),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "expert"
        conn2.close()

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_expert_refine_no_draft_context(self, mock_conn, mock_send, temp_dir):
        """Verify preview-only when no draft in context."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        expert_result = MagicMock()
        expert_result.action.value = "refine_draft"
        expert_result.refined_content = "Improved without context"
        expert_result.context_note = None
        expert_result.answer = None
        expert_result.reasoning = "Refined"

        route = MagicMock()
        route.escalation_reason = "user request"
        route.escalation_context = None

        config = MagicMock()
        config.models.drafter = "anthropic/claude-sonnet-4-5"

        with patch("social_hook.llm.factory.create_client"):
            with patch("social_hook.llm.expert.Expert") as MockExpert:
                MockExpert.return_value.handle.return_value = expert_result

                from social_hook.bot.commands import _handle_expert_escalation

                _handle_expert_escalation(
                    "token", "123", "make it better", route, config,
                    draft=None,  # No draft context
                )

        text = mock_send.call_args[0][2]
        assert "no active draft" in text.lower()
        assert "Improved without context" in text

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_expert_receives_draft_context(self, mock_conn, mock_send, temp_dir):
        """Verify expert.handle() called with draft object (not None)."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        expert_result = MagicMock()
        expert_result.action.value = "answer_question"
        expert_result.refined_content = None
        expert_result.context_note = None
        expert_result.answer = "Here is my answer"
        expert_result.reasoning = None

        route = MagicMock()
        route.escalation_reason = "user request"
        route.escalation_context = None

        config = MagicMock()
        config.models.drafter = "anthropic/claude-sonnet-4-5"

        mock_draft = MagicMock()
        mock_draft.content = "Draft content"
        mock_draft.id = "draft_123"

        with patch("social_hook.llm.factory.create_client"):
            with patch("social_hook.llm.expert.Expert") as MockExpert:
                MockExpert.return_value.handle.return_value = expert_result

                from social_hook.bot.commands import _handle_expert_escalation

                _handle_expert_escalation(
                    "token", "123", "what do you think?", route, config,
                    draft=mock_draft, project_id="proj_123",
                )

                # Verify expert was called with draft
                call_kwargs = MockExpert.return_value.handle.call_args
                assert call_kwargs[1]["draft"] == mock_draft
                assert call_kwargs[1]["project_id"] == "proj_123"


class TestHandleMessageContext:
    """Tests for handle_message context threading."""

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_handle_message_passes_draft_to_gatekeeper(self, mock_conn, mock_send, temp_dir):
        """Verify gatekeeper.route() called with draft_context and project_id."""
        from social_hook.db import insert_decision
        from social_hook.models import Decision

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)
        decision = Decision(
            id=generate_id("decision"), project_id=project.id,
            commit_hash="abc", decision="post_worthy", reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"), project_id=project.id,
            decision_id=decision.id, platform="x",
            content="Draft for context test", status="draft",
        )
        insert_draft(conn, draft)

        # Set chat context
        set_chat_draft_context("123", draft.id, project.id)

        config = MagicMock()
        config.models.gatekeeper = "anthropic/claude-haiku-4-5"

        mock_route_result = MagicMock()
        mock_route_result.action.value = "handle_directly"
        mock_route_result.operation = None

        with patch("social_hook.llm.factory.create_client"):
            with patch("social_hook.llm.gatekeeper.Gatekeeper") as MockGK:
                MockGK.return_value.route.return_value = mock_route_result

                message = {"chat": {"id": 123}, "text": "what about this draft?"}
                handle_message(message, "token", config=config)

                # Verify gatekeeper was called with context
                call_kwargs = MockGK.return_value.route.call_args
                assert call_kwargs[1].get("draft_context") is not None
                assert call_kwargs[1].get("project_id") == project.id


class TestAdapterBridge:
    """Tests for the messaging adapter bridge in commands._send()."""

    def test_send_uses_adapter_when_set(self):
        """When adapter is set, _send() uses adapter.send_message."""
        from social_hook.bot.commands import _send, set_adapter

        mock_adapter = MagicMock()
        mock_adapter.send_message.return_value = MagicMock(success=True)
        set_adapter(mock_adapter)

        result = _send("token", "123", "Hello via adapter")
        assert result is True
        mock_adapter.send_message.assert_called_once()
        # Verify the OutboundMessage text
        msg = mock_adapter.send_message.call_args[0][1]
        assert msg.text == "Hello via adapter"

    @patch("social_hook.bot.commands.send_notification")
    def test_send_falls_back_without_adapter(self, mock_send_notif):
        """When no adapter is set, _send() falls back to send_notification."""
        from social_hook.bot.commands import _send

        mock_send_notif.return_value = True

        result = _send("token", "123", "Hello via HTTP")
        assert result is True
        mock_send_notif.assert_called_once_with("token", "123", "Hello via HTTP")
