"""Tests for bot command handlers (T26)."""

import time
from unittest.mock import MagicMock, patch

import pytest

from social_hook.bot.commands import (
    _CONTEXT_TTL_SECONDS,
    _build_chat_history,
    _build_system_snapshot,
    _chat_draft_context,
    _parse_command,
    _save_angle,
    _save_rejection_note,
    cmd_approve,
    cmd_cancel,
    cmd_errors,
    cmd_health,
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
from social_hook.constants import PROJECT_NAME, PROJECT_SLUG
from social_hook.db import get_connection, init_database, insert_draft, insert_project
from social_hook.filesystem import generate_id
from social_hook.messaging.base import InboundMessage, MessagingAdapter, SendResult
from social_hook.models import Draft, Project


@pytest.fixture(autouse=True)
def _clear_chat_context():
    """Clear chat draft context state between tests."""
    _chat_draft_context.clear()
    yield
    _chat_draft_context.clear()


@pytest.fixture
def mock_adapter():
    """Create a mock MessagingAdapter with standard return values."""
    adapter = MagicMock(spec=MessagingAdapter)
    adapter.send_message.return_value = SendResult(success=True, message_id="test_1")
    adapter.answer_callback.return_value = True
    return adapter


def _make_inbound(text: str, chat_id: str = "123") -> InboundMessage:
    """Helper to create an InboundMessage."""
    return InboundMessage(chat_id=chat_id, text=text)


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
    def test_routes_help(self, mock_help, mock_adapter):
        msg = _make_inbound("/help")
        handle_command(msg, mock_adapter)
        mock_help.assert_called_once_with(mock_adapter, "123", "", None)

    @patch("social_hook.bot.commands.cmd_status")
    def test_routes_status(self, mock_status, mock_adapter):
        msg = _make_inbound("/status")
        handle_command(msg, mock_adapter)
        mock_status.assert_called_once()

    @patch("social_hook.bot.commands.cmd_help")
    def test_start_routes_to_help(self, mock_help, mock_adapter):
        msg = _make_inbound("/start")
        handle_command(msg, mock_adapter)
        mock_help.assert_called_once()

    @patch("social_hook.bot.commands._send")
    def test_unknown_command(self, mock_send, mock_adapter):
        msg = _make_inbound("/nonsense")
        handle_command(msg, mock_adapter)
        mock_send.assert_called_once()
        assert "Unknown command" in mock_send.call_args[0][2]


class TestCmdHelp:
    """Tests for /help command."""

    @patch("social_hook.bot.commands._send")
    def test_sends_help_text(self, mock_send, mock_adapter):
        cmd_help(mock_adapter, "123", "", None)
        mock_send.assert_called_once()
        text = mock_send.call_args[0][2]
        assert f"{PROJECT_NAME} Bot" in text
        assert "/status" in text
        assert "/approve" in text
        assert "/help" in text


class TestCmdStatus:
    """Tests for /status command."""

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_shows_status(self, mock_conn, mock_send, mock_adapter, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)

        cmd_status(mock_adapter, "123", "", None)
        text = mock_send.call_args[0][2]
        assert "System Status" in text
        assert "1 active" in text


class TestCmdPending:
    """Tests for /pending command."""

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_no_pending(self, mock_conn, mock_send, mock_adapter, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        cmd_pending(mock_adapter, "123", "", None)
        text = mock_send.call_args[0][2]
        assert "No pending" in text

    @patch("social_hook.bot.commands._get_conn")
    def test_with_pending_drafts(self, mock_conn, mock_adapter, temp_dir):
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
            decision="draft",
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

        cmd_pending(mock_adapter, "123", "", None)
        mock_adapter.send_message.assert_called_once()
        msg = mock_adapter.send_message.call_args[0][1]
        assert "Test post content" in msg.text

    @patch("social_hook.bot.commands._get_conn")
    def test_deferred_icon_in_pending(self, mock_conn, mock_adapter, temp_dir):
        """Deferred drafts should show the pause icon in /pending output."""
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
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)

        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Deferred draft content",
            status="deferred",
        )
        insert_draft(conn, draft)

        cmd_pending(mock_adapter, "123", "", None)
        mock_adapter.send_message.assert_called_once()
        msg = mock_adapter.send_message.call_args[0][1]
        assert "\u23f8" in msg.text  # ⏸ icon

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_deferred_count_in_status(self, mock_conn, mock_send, mock_adapter, temp_dir):
        """cmd_status should include deferred count."""
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
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)

        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Deferred draft",
            status="deferred",
        )
        insert_draft(conn, draft)

        cmd_status(mock_adapter, "123", "", None)
        text = mock_send.call_args[0][2]
        assert "Deferred: 1" in text


class TestCmdScheduled:
    """Tests for /scheduled command."""

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_no_scheduled(self, mock_conn, mock_send, mock_adapter, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        cmd_scheduled(mock_adapter, "123", "", None)
        text = mock_send.call_args[0][2]
        assert "No scheduled" in text


class TestCmdProjects:
    """Tests for /projects command."""

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_no_projects(self, mock_conn, mock_send, mock_adapter, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        cmd_projects(mock_adapter, "123", "", None)
        text = mock_send.call_args[0][2]
        assert "No registered" in text

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_with_projects(self, mock_conn, mock_send, mock_adapter, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(id=generate_id("project"), name="my-project", repo_path="/tmp/test")
        insert_project(conn, project)

        cmd_projects(mock_adapter, "123", "", None)
        text = mock_send.call_args[0][2]
        assert "Registered Projects" in text
        assert "my-project" in text


class TestCmdUsage:
    """Tests for /usage command."""

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_shows_usage(self, mock_conn, mock_send, mock_adapter, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        cmd_usage(mock_adapter, "123", "", None)
        text = mock_send.call_args[0][2]
        assert "Usage" in text


class TestCmdApprove:
    """Tests for /approve command."""

    @patch("social_hook.bot.commands._send")
    def test_no_draft_id(self, mock_send, mock_adapter):
        cmd_approve(mock_adapter, "123", "", None)
        text = mock_send.call_args[0][2]
        assert "Usage" in text

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_draft_not_found(self, mock_conn, mock_send, mock_adapter, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        cmd_approve(mock_adapter, "123", "nonexistent_id", None)
        text = mock_send.call_args[0][2]
        assert "not found" in text

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_approve_success(self, mock_conn, mock_send, mock_adapter, temp_dir):
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
            decision="draft",
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

        cmd_approve(mock_adapter, "123", draft.id, None)
        text = mock_send.call_args[0][2]
        assert "approved" in text

        # Re-open connection (command handler closes it)
        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.status == "approved"
        conn2.close()

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_approve_wrong_status(self, mock_conn, mock_send, mock_adapter, temp_dir):
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
            decision="draft",
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

        cmd_approve(mock_adapter, "123", draft.id, None)
        text = mock_send.call_args[0][2]
        assert "Cannot approve" in text


class TestCmdReject:
    """Tests for /reject command."""

    @patch("social_hook.bot.commands._send")
    def test_no_draft_id(self, mock_send, mock_adapter):
        cmd_reject(mock_adapter, "123", "", None)
        assert "Usage" in mock_send.call_args[0][2]

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_reject_success(self, mock_conn, mock_send, mock_adapter, temp_dir):
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
            decision="draft",
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

        cmd_reject(mock_adapter, "123", draft.id, None)
        assert "rejected" in mock_send.call_args[0][2]
        conn2 = get_connection(db_path)
        assert get_draft(conn2, draft.id).status == "rejected"
        conn2.close()


class TestCmdSchedule:
    """Tests for /schedule command."""

    @patch("social_hook.bot.commands._send")
    def test_no_args(self, mock_send, mock_adapter):
        cmd_schedule(mock_adapter, "123", "", None)
        assert "Usage" in mock_send.call_args[0][2]

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_schedule_with_time(self, mock_conn, mock_send, mock_adapter, temp_dir):
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
            decision="draft",
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

        cmd_schedule(mock_adapter, "123", f"{draft.id} 2026-02-10T14:00:00", None)
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
    def test_no_draft_id(self, mock_send, mock_adapter):
        cmd_cancel(mock_adapter, "123", "", None)
        assert "Usage" in mock_send.call_args[0][2]

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_cancel_success(self, mock_conn, mock_send, mock_adapter, temp_dir):
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
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Test",
            status="scheduled",
        )
        insert_draft(conn, draft)

        cmd_cancel(mock_adapter, "123", draft.id, None)
        assert "cancelled" in mock_send.call_args[0][2]
        conn2 = get_connection(db_path)
        assert get_draft(conn2, draft.id).status == "cancelled"
        conn2.close()


class TestCmdRetry:
    """Tests for /retry command."""

    @patch("social_hook.bot.commands._send")
    def test_no_draft_id(self, mock_send, mock_adapter):
        cmd_retry(mock_adapter, "123", "", None)
        assert "Usage" in mock_send.call_args[0][2]

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_retry_failed_draft(self, mock_conn, mock_send, mock_adapter, temp_dir):
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
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Test",
            status="failed",
        )
        insert_draft(conn, draft)

        cmd_retry(mock_adapter, "123", draft.id, None)
        assert "retry" in mock_send.call_args[0][2]
        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.status == "scheduled"
        assert updated.retry_count == 0
        conn2.close()

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_retry_non_failed_draft(self, mock_conn, mock_send, mock_adapter, temp_dir):
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
            decision="draft",
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

        cmd_retry(mock_adapter, "123", draft.id, None)
        text = mock_send.call_args[0][2]
        assert "only retry failed" in text.lower() or "Can only retry" in text


class TestCmdPause:
    """Tests for /pause command."""

    @patch("social_hook.bot.commands._send")
    def test_no_project_id(self, mock_send, mock_adapter):
        cmd_pause(mock_adapter, "123", "", None)
        assert "Usage" in mock_send.call_args[0][2]

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_pause_project(self, mock_conn, mock_send, mock_adapter, temp_dir):
        from social_hook.db import get_project

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)

        cmd_pause(mock_adapter, "123", project.id, None)
        assert "paused" in mock_send.call_args[0][2]

        conn2 = get_connection(db_path)
        updated = get_project(conn2, project.id)
        assert updated.paused is True
        conn2.close()

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_pause_already_paused(self, mock_conn, mock_send, mock_adapter, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(
            id=generate_id("project"), name="test", repo_path="/tmp/test", paused=True
        )
        insert_project(conn, project)

        cmd_pause(mock_adapter, "123", project.id, None)
        assert "already paused" in mock_send.call_args[0][2]

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_pause_not_found(self, mock_conn, mock_send, mock_adapter, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        cmd_pause(mock_adapter, "123", "nonexistent", None)
        assert "not found" in mock_send.call_args[0][2]


class TestCmdResume:
    """Tests for /resume command."""

    @patch("social_hook.bot.commands._send")
    def test_no_project_id(self, mock_send, mock_adapter):
        cmd_resume(mock_adapter, "123", "", None)
        assert "Usage" in mock_send.call_args[0][2]

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_resume_paused_project(self, mock_conn, mock_send, mock_adapter, temp_dir):
        from social_hook.db import get_project

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(
            id=generate_id("project"), name="test", repo_path="/tmp/test", paused=True
        )
        insert_project(conn, project)

        cmd_resume(mock_adapter, "123", project.id, None)
        assert "resumed" in mock_send.call_args[0][2]

        conn2 = get_connection(db_path)
        updated = get_project(conn2, project.id)
        assert updated.paused is False
        conn2.close()

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_resume_not_paused(self, mock_conn, mock_send, mock_adapter, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)

        cmd_resume(mock_adapter, "123", project.id, None)
        assert "not paused" in mock_send.call_args[0][2]


class TestCmdReview:
    """Tests for /review command."""

    @patch("social_hook.bot.commands._send")
    def test_review_no_args(self, mock_send, mock_adapter):
        from social_hook.bot.commands import cmd_review

        cmd_review(mock_adapter, "123", "", None)
        assert "Usage" in mock_send.call_args[0][2]

    @patch("social_hook.bot.commands._get_conn")
    def test_review_sends_formatted_with_buttons(self, mock_conn, mock_adapter, temp_dir):
        from social_hook.bot.commands import cmd_review
        from social_hook.db import insert_decision
        from social_hook.models import Decision

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(id=generate_id("project"), name="reviewproj", repo_path="/tmp/test")
        insert_project(conn, project)
        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc12345",
            decision="draft",
            reasoning="Good commit",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Review me",
            status="draft",
        )
        insert_draft(conn, draft)

        cmd_review(mock_adapter, "123", draft.id, None)
        mock_adapter.send_message.assert_called_once()
        msg = mock_adapter.send_message.call_args[0][1]
        assert "reviewproj" in msg.text
        assert "Review me" in msg.text
        # Check buttons passed
        assert len(msg.buttons) == 2  # Two rows of buttons


class TestCmdRegister:
    """Tests for /register command."""

    @patch("social_hook.bot.commands._send")
    def test_sends_terminal_instructions(self, mock_send, mock_adapter):
        from social_hook.bot.commands import cmd_register

        cmd_register(mock_adapter, "123", "", None)
        text = mock_send.call_args[0][2]
        assert "terminal" in text.lower()
        assert f"{PROJECT_SLUG} register" in text


class TestCmdUsageDays:
    """Tests for /usage with days parameter."""

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_usage_7_days(self, mock_conn, mock_send, mock_adapter, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        cmd_usage(mock_adapter, "123", "7", None)
        text = mock_send.call_args[0][2]
        assert "7 days" in text

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_usage_default_30(self, mock_conn, mock_send, mock_adapter, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        cmd_usage(mock_adapter, "123", "", None)
        text = mock_send.call_args[0][2]
        assert "30 days" in text


class TestCmdRejectReason:
    """Tests for /reject with reason."""

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_reject_with_reason(self, mock_conn, mock_send, mock_adapter, temp_dir):
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
            decision="draft",
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

        cmd_reject(mock_adapter, "123", f"{draft.id} too informal", None)
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
    def test_help_approve(self, mock_send, mock_adapter):
        cmd_help(mock_adapter, "123", "approve", None)
        text = mock_send.call_args[0][2]
        assert "/approve" in text
        assert "Approve" in text

    @patch("social_hook.bot.commands._send")
    def test_help_unknown_command(self, mock_send, mock_adapter):
        cmd_help(mock_adapter, "123", "nonexistent", None)
        text = mock_send.call_args[0][2]
        assert "Unknown" in text

    @patch("social_hook.bot.commands._send")
    def test_help_no_args_shows_all(self, mock_send, mock_adapter):
        cmd_help(mock_adapter, "123", "", None)
        text = mock_send.call_args[0][2]
        assert f"{PROJECT_NAME} Bot" in text


class TestHandleMessage:
    """Tests for free-text message handling."""

    @patch("social_hook.bot.commands._send")
    def test_no_config(self, mock_send, mock_adapter):
        msg = _make_inbound("Hello")
        handle_message(msg, mock_adapter, config=None)
        assert (
            "not configured" in mock_send.call_args[0][2].lower()
            or "API key" in mock_send.call_args[0][2]
        )

    @patch("social_hook.bot.commands._send")
    def test_empty_text(self, mock_send, mock_adapter):
        msg = _make_inbound("")
        handle_message(msg, mock_adapter)
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
            "draft_abc",
            "proj_123",
            time.time() - _CONTEXT_TTL_SECONDS - 60,
        )
        result = get_chat_draft_context("chat1")
        assert result is None
        assert "chat1" not in _chat_draft_context

    def test_missing(self):
        """Verify returns None for unknown chat_id."""
        assert get_chat_draft_context("unknown") is None


class TestPendingEditSaves:
    """Tests for pending edit save flow (handle_message -> _save_edit)."""

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_pending_edit_saves_content(self, mock_conn, mock_send, mock_adapter, temp_dir):
        """Mock pending edit, send message, verify update_draft called."""
        from social_hook.bot.buttons import PendingReply, _pending_replies
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
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Old content",
            status="draft",
        )
        insert_draft(conn, draft)

        # Set pending reply
        _pending_replies["123"] = PendingReply(
            type="edit_text", draft_id=draft.id, timestamp=time.time()
        )

        msg = _make_inbound("Brand new content here")
        handle_message(msg, mock_adapter, config=None)

        # Verify content was updated
        text = mock_send.call_args[0][2]
        assert "updated" in text
        assert "Brand new content" in text

        # Verify DB was updated
        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.content == "Brand new content here"
        conn2.close()

        # Verify pending reply was cleared
        assert "123" not in _pending_replies

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_pending_edit_creates_audit_trail(self, mock_conn, mock_send, mock_adapter, temp_dir):
        """Verify insert_draft_change called with changed_by='human'."""
        from social_hook.bot.buttons import PendingReply, _pending_replies
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
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Old content",
            status="draft",
        )
        insert_draft(conn, draft)

        _pending_replies["123"] = PendingReply(
            type="edit_text", draft_id=draft.id, timestamp=time.time()
        )

        msg = _make_inbound("New content")
        handle_message(msg, mock_adapter, config=None)

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
    def test_pending_edit_draft_not_found(self, mock_conn, mock_send, mock_adapter, temp_dir):
        """Verify error message when draft is gone."""
        from social_hook.bot.buttons import PendingReply, _pending_replies

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        _pending_replies["123"] = PendingReply(
            type="edit_text", draft_id="nonexistent_draft", timestamp=time.time()
        )

        msg = _make_inbound("New content")
        handle_message(msg, mock_adapter, config=None)

        text = mock_send.call_args[0][2]
        assert "not found" in text


class TestPendingReplyHandlers:
    """Tests for new pending reply types (schedule_custom, reject_note, edit_angle)."""

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_handle_message_routes_schedule_custom_pending(
        self, mock_conn, mock_send, mock_adapter, temp_dir
    ):
        """Schedule custom pending reply should parse ISO datetime and schedule."""
        from social_hook.bot.buttons import PendingReply, _pending_replies
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
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Test content",
            status="draft",
        )
        insert_draft(conn, draft)

        _pending_replies["123"] = PendingReply(
            type="schedule_custom", draft_id=draft.id, timestamp=time.time()
        )

        msg = _make_inbound("2026-03-15T14:30:00")
        handle_message(msg, mock_adapter, config=None)

        text = mock_send.call_args[0][2]
        assert "scheduled" in text

        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.status == "scheduled"
        assert updated.scheduled_time is not None
        conn2.close()

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_handle_message_routes_reject_note_pending(
        self, mock_conn, mock_send, mock_adapter, temp_dir
    ):
        """Reject note pending reply should reject draft with note."""
        from social_hook.bot.buttons import PendingReply, _pending_replies
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
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Test content",
            status="draft",
        )
        insert_draft(conn, draft)

        _pending_replies["123"] = PendingReply(
            type="reject_note", draft_id=draft.id, timestamp=time.time()
        )

        msg = _make_inbound("Too technical for this audience")
        handle_message(msg, mock_adapter, config=None)

        text = mock_send.call_args[0][2]
        assert "rejected" in text

        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.status == "rejected"
        assert "Too technical" in updated.last_error
        conn2.close()

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_handle_message_schedule_custom_invalid_format(
        self, mock_conn, mock_send, mock_adapter, temp_dir
    ):
        """Invalid datetime should show error and re-set pending reply."""
        from social_hook.bot.buttons import PendingReply, _pending_replies
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
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Test content",
            status="draft",
        )
        insert_draft(conn, draft)

        _pending_replies["123"] = PendingReply(
            type="schedule_custom", draft_id=draft.id, timestamp=time.time()
        )

        msg = _make_inbound("next tuesday at 3pm")
        handle_message(msg, mock_adapter, config=None)

        text = mock_send.call_args[0][2]
        assert "Invalid format" in text

        # Pending reply should be re-set
        assert "123" in _pending_replies
        assert _pending_replies["123"].type == "schedule_custom"

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_save_custom_schedule_emits_data_event(
        self, mock_conn, mock_send, mock_adapter, temp_dir
    ):
        """Schedule custom should call emit_data_event."""
        from social_hook.bot.buttons import PendingReply, _pending_replies
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
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Test content",
            status="draft",
        )
        insert_draft(conn, draft)

        _pending_replies["123"] = PendingReply(
            type="schedule_custom", draft_id=draft.id, timestamp=time.time()
        )

        with patch("social_hook.db.operations.emit_data_event") as mock_emit:
            msg = _make_inbound("2026-03-15T14:30:00")
            handle_message(msg, mock_adapter, config=None)
            mock_emit.assert_called_once_with(conn, "draft", "scheduled", draft.id, project.id)

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_save_rejection_note_emits_data_event(
        self, mock_conn, mock_send, mock_adapter, temp_dir
    ):
        """Reject with note should call emit_data_event."""
        from social_hook.bot.buttons import PendingReply, _pending_replies
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
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Test content",
            status="draft",
        )
        insert_draft(conn, draft)

        _pending_replies["123"] = PendingReply(
            type="reject_note", draft_id=draft.id, timestamp=time.time()
        )

        with patch("social_hook.db.operations.emit_data_event") as mock_emit:
            msg = _make_inbound("Not appropriate")
            handle_message(msg, mock_adapter, config=None)
            mock_emit.assert_called_once_with(conn, "draft", "rejected", draft.id, project.id)


class TestSubstituteHandler:
    """Tests for Gatekeeper substitute operation handling."""

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_substitute_saves_content(self, mock_conn, mock_send, mock_adapter, temp_dir):
        """Substitute operation saves content to DB."""
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
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Old content",
            status="draft",
        )
        insert_draft(conn, draft)

        # Simulate gatekeeper route for substitute
        route = MagicMock()
        route.operation.value = "substitute"
        route.params = {"content": "Replaced content", "draft_id": draft.id}

        from social_hook.bot.commands import _handle_gatekeeper_direct

        _handle_gatekeeper_direct(mock_adapter, "123", route, None)

        text = mock_send.call_args[0][2]
        assert "updated" in text

        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.content == "Replaced content"
        conn2.close()

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_substitute_uses_chat_context(self, mock_conn, mock_send, mock_adapter, temp_dir):
        """Verify draft_id resolved from get_chat_draft_context when not in params."""
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
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Old content",
            status="draft",
        )
        insert_draft(conn, draft)

        # Set chat context (no draft_id in params)
        set_chat_draft_context("123", draft.id, project.id)

        route = MagicMock()
        route.operation.value = "substitute"
        route.params = {"content": "New via context"}  # No draft_id

        from social_hook.bot.commands import _handle_gatekeeper_direct

        _handle_gatekeeper_direct(mock_adapter, "123", route, None)

        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.content == "New via context"
        conn2.close()

    @patch("social_hook.bot.commands._send")
    def test_substitute_no_context_shows_error(self, mock_send, mock_adapter):
        """Verify error message when no chat context and no draft_id in params."""
        route = MagicMock()
        route.operation.value = "substitute"
        route.params = {"content": "New content"}  # No draft_id

        from social_hook.bot.commands import _handle_gatekeeper_direct

        _handle_gatekeeper_direct(mock_adapter, "123", route, None)

        text = mock_send.call_args[0][2]
        assert "No active draft" in text


class TestReviewEvaluatorContext:
    """Tests for enhanced /review with evaluator context."""

    @patch("social_hook.bot.commands._get_conn")
    def test_review_shows_evaluator_context(self, mock_conn, mock_adapter, temp_dir):
        """Verify angle, post_category in formatted review output."""
        from social_hook.bot.commands import cmd_review
        from social_hook.db import insert_decision
        from social_hook.models import Decision

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(id=generate_id("project"), name="reviewproj", repo_path="/tmp/test")
        insert_project(conn, project)
        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc12345",
            decision="draft",
            reasoning="Strong commit with clear narrative",
            post_category="arc",
            angle="Show how the new API simplifies integration",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Check out our new API",
            status="draft",
        )
        insert_draft(conn, draft)

        cmd_review(mock_adapter, "123", draft.id, None)
        mock_adapter.send_message.assert_called_once()
        msg = mock_adapter.send_message.call_args[0][1]
        assert "Category: arc" in msg.text
        assert "Angle:" in msg.text
        assert "simplifies integration" in msg.text
        assert "Strong commit" in msg.text


class TestExpertRefineSaves:
    """Tests for Expert refinement saving to DB."""

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_expert_refine_saves_to_db(self, mock_conn, mock_send, mock_adapter, temp_dir):
        """Verify update_draft called after refine_draft action."""
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
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Original content",
            status="draft",
        )
        insert_draft(conn, draft)

        # Mock the expert result
        expert_result = MagicMock()
        expert_result.action.value = "refine_draft"
        expert_result.refined_content = "Punchy improved content"
        expert_result.refined_media_spec = None
        expert_result.context_note = None
        expert_result.answer = None
        expert_result.reasoning = "Made it punchier"

        route = MagicMock()
        route.escalation_reason = "user request"
        route.escalation_context = "make it punchier"

        config = MagicMock()
        config.models.drafter = "anthropic/claude-sonnet-4-5"

        with (
            patch("social_hook.llm.factory.create_client"),
            patch("social_hook.llm.expert.Expert") as MockExpert,
        ):
            MockExpert.return_value.handle.return_value = expert_result

            from social_hook.bot.commands import _handle_expert_escalation

            # Create a mock draft object for context
            draft_obj = get_draft(conn, draft.id)

            _handle_expert_escalation(
                mock_adapter,
                "123",
                "make it punchier",
                route,
                config,
                draft=draft_obj,
                project_id=project.id,
            )

        # Verify buttons were sent via adapter.send_message
        mock_adapter.send_message.assert_called_once()
        msg = mock_adapter.send_message.call_args[0][1]
        assert "updated by Expert" in msg.text
        assert "Punchy improved content" in msg.text

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
    def test_expert_refine_no_draft_context(self, mock_conn, mock_send, mock_adapter, temp_dir):
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

        with (
            patch("social_hook.llm.factory.create_client"),
            patch("social_hook.llm.expert.Expert") as MockExpert,
        ):
            MockExpert.return_value.handle.return_value = expert_result

            from social_hook.bot.commands import _handle_expert_escalation

            _handle_expert_escalation(
                mock_adapter,
                "123",
                "make it better",
                route,
                config,
                draft=None,  # No draft context
            )

        text = mock_send.call_args[0][2]
        assert "no active draft" in text.lower()
        assert "Improved without context" in text

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_expert_receives_draft_context(self, mock_conn, mock_send, mock_adapter, temp_dir):
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

        with (
            patch("social_hook.llm.factory.create_client"),
            patch("social_hook.llm.expert.Expert") as MockExpert,
        ):
            MockExpert.return_value.handle.return_value = expert_result

            from social_hook.bot.commands import _handle_expert_escalation

            _handle_expert_escalation(
                mock_adapter,
                "123",
                "what do you think?",
                route,
                config,
                draft=mock_draft,
                project_id="proj_123",
            )

            # Verify expert was called with draft
            call_kwargs = MockExpert.return_value.handle.call_args
            assert call_kwargs[1]["draft"] == mock_draft
            assert call_kwargs[1]["project_id"] == "proj_123"


class TestHandleMessageContext:
    """Tests for handle_message context threading."""

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_handle_message_passes_draft_to_gatekeeper(
        self, mock_conn, mock_send, mock_adapter, temp_dir
    ):
        """Verify gatekeeper.route() called with draft_context and project_id."""
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
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Draft for context test",
            status="draft",
        )
        insert_draft(conn, draft)

        # Set chat context
        set_chat_draft_context("123", draft.id, project.id)

        config = MagicMock()
        config.models.gatekeeper = "anthropic/claude-haiku-4-5"

        mock_route_result = MagicMock()
        mock_route_result.action.value = "handle_directly"
        mock_route_result.operation = None

        with (
            patch("social_hook.llm.factory.create_client"),
            patch("social_hook.llm.gatekeeper.Gatekeeper") as MockGK,
        ):
            MockGK.return_value.route.return_value = mock_route_result

            msg = _make_inbound("what about this draft?")
            handle_message(msg, mock_adapter, config=config)

            # Verify gatekeeper was called with context
            call_kwargs = MockGK.return_value.route.call_args
            assert call_kwargs[1].get("draft_context") is not None
            assert call_kwargs[1].get("project_id") == project.id
            # Verify system snapshot was built and passed
            assert call_kwargs[1].get("system_snapshot") is not None
            assert "## System Status" in call_kwargs[1]["system_snapshot"]


# =============================================================================
# _build_system_snapshot Tests
# =============================================================================


class TestBuildSystemSnapshot:
    """Tests for the system snapshot builder."""

    def test_basic_snapshot(self, temp_dir):
        """Snapshot includes project, drafts, and config sections."""
        from social_hook.db import insert_decision
        from social_hook.models import Decision

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)

        project = Project(id=generate_id("project"), name="my-app", repo_path="/tmp/my-app")
        insert_project(conn, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc123",
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Test post",
            status="draft",
        )
        insert_draft(conn, draft)

        config = MagicMock()
        config.platforms = {"x": MagicMock(enabled=True, account_tier="free")}
        config.scheduling = MagicMock(
            timezone="UTC",
            optimal_days=["Tue", "Wed"],
            optimal_hours=[9, 17],
            max_posts_per_day=3,
        )
        config.media_generation = MagicMock(enabled=True, tools={"mermaid": True, "ray_so": False})

        result = _build_system_snapshot(conn, project.id, config)

        assert "## System Status" in result
        assert "my-app" in result
        assert "Pending drafts: 1" in result
        assert "1 draft" in result
        assert "x (enabled, free tier)" in result
        assert "Schedule: UTC" in result
        assert "mermaid" in result
        assert "ray_so" not in result  # disabled tool excluded
        assert "/help" in result
        conn.close()

    def test_empty_db(self, temp_dir):
        """Snapshot works with no projects or drafts."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)

        config = MagicMock()
        config.platforms = {}
        config.scheduling = MagicMock(
            timezone="UTC",
            optimal_days=[],
            optimal_hours=[],
            max_posts_per_day=3,
        )
        config.media_generation = MagicMock(enabled=False)

        result = _build_system_snapshot(conn, None, config)

        assert "## System Status" in result
        assert "Pending drafts: 0" in result
        conn.close()

    def test_no_lifecycle(self, temp_dir):
        """Snapshot shows 'unknown' phase when no lifecycle exists."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)

        project = Project(id=generate_id("project"), name="new-app", repo_path="/tmp/new")
        insert_project(conn, project)

        config = MagicMock()
        config.platforms = {}
        config.scheduling = MagicMock(
            timezone="UTC",
            optimal_days=[],
            optimal_hours=[],
            max_posts_per_day=3,
        )
        config.media_generation = MagicMock(enabled=False)

        result = _build_system_snapshot(conn, project.id, config)

        assert "new-app (active, unknown phase)" in result
        conn.close()

    def test_posted_at_none(self, temp_dir):
        """Snapshot handles posts with posted_at=None gracefully."""
        from social_hook.db import insert_decision
        from social_hook.models import Decision

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc",
            decision="draft",
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

        # Insert a post with posted_at (SQLite default handles this)
        from social_hook.db.operations import insert_post
        from social_hook.models import Post

        post = Post(
            id=generate_id("post"),
            draft_id=draft.id,
            project_id=project.id,
            platform="x",
            content="Posted content",
        )
        insert_post(conn, post)

        config = MagicMock()
        config.platforms = {}
        config.scheduling = MagicMock(
            timezone="UTC",
            optimal_days=[],
            optimal_hours=[],
            max_posts_per_day=3,
        )
        config.media_generation = MagicMock(enabled=False)

        # Should not crash — posted_at comes from DB default
        result = _build_system_snapshot(conn, project.id, config)
        assert "Last post:" in result
        conn.close()


# =============================================================================
# _build_chat_history Tests
# =============================================================================


class TestChatMessageOperations:
    """Tests for chat message DB operations."""

    def test_insert_and_retrieve(self, temp_dir):
        """Insert a message and query it back."""
        from social_hook.db.operations import get_recent_chat_messages, insert_chat_message

        conn = init_database(temp_dir / "test.db")
        try:
            row_id = insert_chat_message(conn, "chat_1", "user", "hello world")
            assert row_id > 0

            msgs = get_recent_chat_messages(conn, "chat_1")
            assert len(msgs) == 1
            assert msgs[0]["role"] == "user"
            assert msgs[0]["content"] == "hello world"
            assert "created_at" in msgs[0]
        finally:
            conn.close()

    def test_time_window_filtering(self, temp_dir):
        """Only recent messages within time window are returned."""
        from social_hook.db.operations import get_recent_chat_messages, insert_chat_message

        conn = init_database(temp_dir / "test.db")
        try:
            # Insert an old message by manipulating created_at
            conn.execute(
                "INSERT INTO chat_messages (chat_id, role, content, created_at) VALUES (?, ?, ?, datetime('now', '-60 minutes'))",
                ("chat_1", "user", "old message"),
            )
            conn.commit()

            # Insert a recent message
            insert_chat_message(conn, "chat_1", "user", "new message")

            msgs = get_recent_chat_messages(conn, "chat_1", time_window_minutes=15)
            assert len(msgs) == 1
            assert msgs[0]["content"] == "new message"
        finally:
            conn.close()

    def test_cleanup_old_messages(self, temp_dir):
        """Cleanup deletes only old messages."""
        from social_hook.db.operations import (
            cleanup_old_chat_messages,
            get_recent_chat_messages,
            insert_chat_message,
        )

        conn = init_database(temp_dir / "test.db")
        try:
            # Insert an old message
            conn.execute(
                "INSERT INTO chat_messages (chat_id, role, content, created_at) VALUES (?, ?, ?, datetime('now', '-10 days'))",
                ("chat_1", "user", "ancient message"),
            )
            conn.commit()

            # Insert a recent message
            insert_chat_message(conn, "chat_1", "user", "fresh message")

            deleted = cleanup_old_chat_messages(conn, days=7)
            assert deleted == 1

            # Recent message should still be there
            msgs = get_recent_chat_messages(conn, "chat_1", time_window_minutes=60)
            assert len(msgs) == 1
            assert msgs[0]["content"] == "fresh message"
        finally:
            conn.close()

    def test_limit_parameter(self, temp_dir):
        """Limit caps the number of returned messages."""
        from social_hook.db.operations import get_recent_chat_messages, insert_chat_message

        conn = init_database(temp_dir / "test.db")
        try:
            for i in range(10):
                insert_chat_message(conn, "chat_1", "user", f"msg {i}")

            msgs = get_recent_chat_messages(conn, "chat_1", limit=3)
            assert len(msgs) == 3
        finally:
            conn.close()


class TestBuildChatHistory:
    """Tests for the token-budgeted chat history builder (platform-agnostic)."""

    def test_returns_none_for_empty_history(self, temp_dir):
        """Empty chat_messages table returns None."""
        conn = init_database(temp_dir / "test.db")
        try:
            result = _build_chat_history(conn, "chat_1")
            assert result is None
        finally:
            conn.close()

    def test_builds_history_from_chat_messages(self, temp_dir):
        """Chat messages are formatted into history block."""
        from social_hook.db.operations import insert_chat_message

        conn = init_database(temp_dir / "test.db")
        try:
            insert_chat_message(conn, "chat_1", "user", "what platforms are enabled?")
            insert_chat_message(conn, "chat_1", "assistant", "X and LinkedIn are enabled.")
            insert_chat_message(conn, "chat_1", "user", "what about now?")

            result = _build_chat_history(conn, "chat_1")

            assert result is not None
            assert "## Recent Chat" in result
            assert "User: what platforms are enabled?" in result
            assert "Assistant: X and LinkedIn are enabled." in result
            assert "User: what about now?" in result
        finally:
            conn.close()

    def test_respects_token_budget(self, temp_dir):
        """History stops when token budget is exhausted."""
        from social_hook.db.operations import insert_chat_message

        conn = init_database(temp_dir / "test.db")
        try:
            for i in range(20):
                insert_chat_message(conn, "chat_1", "user", f"Message {i}: " + "x" * 200)
                insert_chat_message(conn, "chat_1", "assistant", f"Reply {i}: " + "y" * 200)

            result = _build_chat_history(conn, "chat_1", token_budget=100)

            assert result is not None
            # Should not contain all 40 messages — budget limits it
            assert result.count("- User:") + result.count("- Assistant:") < 40
        finally:
            conn.close()

    def test_chronological_order(self, temp_dir):
        """History is in chronological order (oldest first)."""
        from social_hook.db.operations import insert_chat_message

        conn = init_database(temp_dir / "test.db")
        try:
            insert_chat_message(conn, "chat_1", "user", "first")
            insert_chat_message(conn, "chat_1", "assistant", "second")
            insert_chat_message(conn, "chat_1", "user", "third")

            result = _build_chat_history(conn, "chat_1")

            assert result is not None
            first_pos = result.index("first")
            second_pos = result.index("second")
            third_pos = result.index("third")
            assert first_pos < second_pos < third_pos
        finally:
            conn.close()

    def test_chat_id_isolation(self, temp_dir):
        """Messages from chat_a don't appear in chat_b's history."""
        from social_hook.db.operations import insert_chat_message

        conn = init_database(temp_dir / "test.db")
        try:
            insert_chat_message(conn, "chat_a", "user", "message for A")
            insert_chat_message(conn, "chat_b", "user", "message for B")

            result_a = _build_chat_history(conn, "chat_a")
            result_b = _build_chat_history(conn, "chat_b")

            assert result_a is not None
            assert "message for A" in result_a
            assert "message for B" not in result_a

            assert result_b is not None
            assert "message for B" in result_b
            assert "message for A" not in result_b
        finally:
            conn.close()


def _make_test_draft(conn, temp_dir, status="draft", platform="x"):
    """Helper to create a project + decision + draft for tests."""
    from social_hook.db import insert_decision
    from social_hook.models import Decision

    project = Project(id=generate_id("project"), name="test", repo_path=str(temp_dir))
    insert_project(conn, project)
    decision = Decision(
        id=generate_id("decision"),
        project_id=project.id,
        commit_hash="abc123",
        decision="draft",
        reasoning="test",
    )
    insert_decision(conn, decision)
    draft = Draft(
        id=generate_id("draft"),
        project_id=project.id,
        decision_id=decision.id,
        platform=platform,
        content="Original content",
        status=status,
    )
    insert_draft(conn, draft)
    return project, draft


class TestSaveAngle:
    """Tests for _save_angle function."""

    @patch("social_hook.bot.commands._get_conn")
    def test_save_angle_calls_expert_and_updates_draft(self, mock_conn, mock_adapter, temp_dir):
        """Expert.handle() refines content -> draft updated with change record."""
        from social_hook.llm.schemas import ExpertAction, ExpertResponseInput

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn
        _, draft = _make_test_draft(conn, temp_dir)

        mock_result = ExpertResponseInput(
            action=ExpertAction.refine_draft,
            reasoning="Changed angle",
            refined_content="New content from expert",
        )

        with (
            patch("social_hook.config.yaml.load_full_config") as mock_config,
            patch("social_hook.llm.factory.create_client"),
            patch("social_hook.llm.expert.Expert") as MockExpert,
        ):
            mock_config.return_value = MagicMock()
            MockExpert.return_value.handle.return_value = mock_result

            _save_angle(mock_adapter, "123", draft.id, "try a different angle")

            # Verify draft was updated in DB (use new connection since _save_angle closes conn)
            from social_hook.db import get_draft as _get_draft

            conn2 = get_connection(db_path)
            updated = _get_draft(conn2, draft.id)
            assert updated.content == "New content from expert"
            conn2.close()

            # Response should use send_message with buttons (OutboundMessage)
            mock_adapter.send_message.assert_called_once()
            msg = mock_adapter.send_message.call_args[0][1]
            assert msg.buttons is not None
            assert "New content from expert" in msg.text

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_save_angle_expert_no_content(self, mock_conn, mock_send, mock_adapter, temp_dir):
        """Expert returns no refined content -> error message."""
        from social_hook.llm.schemas import ExpertAction, ExpertResponseInput

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn
        _, draft = _make_test_draft(conn, temp_dir)

        mock_result = ExpertResponseInput(
            action=ExpertAction.refine_draft,
            reasoning="Could not refine",
            refined_content=None,
            refined_media_spec=None,
        )

        with (
            patch("social_hook.config.yaml.load_full_config") as mock_config,
            patch("social_hook.llm.factory.create_client"),
            patch("social_hook.llm.expert.Expert") as MockExpert,
        ):
            mock_config.return_value = MagicMock()
            MockExpert.return_value.handle.return_value = mock_result

            _save_angle(mock_adapter, "123", draft.id, "try something")

            text = mock_send.call_args[0][2]
            assert "could not refine" in text.lower()

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_save_angle_config_error(self, mock_conn, mock_send, mock_adapter, temp_dir):
        """Config error -> error message, no crash."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn
        _, draft = _make_test_draft(conn, temp_dir)

        with patch(
            "social_hook.config.yaml.load_full_config",
            side_effect=Exception("No config"),
        ):
            _save_angle(mock_adapter, "123", draft.id, "try something")

            text = mock_send.call_args[0][2]
            assert "Cannot redraft" in text

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_save_angle_draft_not_found(self, mock_conn, mock_send, mock_adapter, temp_dir):
        """Draft not in DB -> not found message."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        _save_angle(mock_adapter, "123", "nonexistent_id", "try something")

        text = mock_send.call_args[0][2]
        assert "not found" in text.lower()

    @patch("social_hook.bot.commands._get_conn")
    def test_save_angle_with_media_spec(self, mock_conn, mock_adapter, temp_dir):
        """Expert returns both content and media spec -> both updated."""
        from social_hook.llm.schemas import ExpertAction, ExpertResponseInput

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn
        _, draft = _make_test_draft(conn, temp_dir)

        mock_result = ExpertResponseInput(
            action=ExpertAction.refine_draft,
            reasoning="Updated both",
            refined_content="New content",
            refined_media_spec={"code": "print('hi')", "language": "python"},
        )

        with (
            patch("social_hook.config.yaml.load_full_config") as mock_config,
            patch("social_hook.llm.factory.create_client"),
            patch("social_hook.llm.expert.Expert") as MockExpert,
        ):
            mock_config.return_value = MagicMock()
            MockExpert.return_value.handle.return_value = mock_result

            _save_angle(mock_adapter, "123", draft.id, "new angle with code")

            # Verify both updates in DB (use new connection since _save_angle closes conn)
            from social_hook.db import get_draft as _get_draft

            conn2 = get_connection(db_path)
            updated = _get_draft(conn2, draft.id)
            assert updated.content == "New content"
            assert updated.media_spec == {"code": "print('hi')", "language": "python"}
            conn2.close()

            # Response message mentions media spec
            msg = mock_adapter.send_message.call_args[0][1]
            assert "media spec" in msg.text.lower()

    @patch("social_hook.bot.commands._get_conn")
    def test_save_angle_media_only(self, mock_conn, mock_adapter, temp_dir):
        """Expert returns only media spec -> media spec updated, message says so."""
        from social_hook.llm.schemas import ExpertAction, ExpertResponseInput

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn
        _, draft = _make_test_draft(conn, temp_dir)

        mock_result = ExpertResponseInput(
            action=ExpertAction.refine_draft,
            reasoning="Updated media only",
            refined_content=None,
            refined_media_spec={"code": "print('hi')"},
        )

        with (
            patch("social_hook.config.yaml.load_full_config") as mock_config,
            patch("social_hook.llm.factory.create_client"),
            patch("social_hook.llm.expert.Expert") as MockExpert,
        ):
            mock_config.return_value = MagicMock()
            MockExpert.return_value.handle.return_value = mock_result

            _save_angle(mock_adapter, "123", draft.id, "change the code")

            # Verify media spec updated, content unchanged (use new connection)
            from social_hook.db import get_draft as _get_draft

            conn2 = get_connection(db_path)
            updated = _get_draft(conn2, draft.id)
            assert updated.content == "Original content"
            assert updated.media_spec == {"code": "print('hi')"}
            conn2.close()

            msg = mock_adapter.send_message.call_args[0][1]
            assert "media spec updated" in msg.text.lower()

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_save_angle_terminal_status(self, mock_conn, mock_send, mock_adapter, temp_dir):
        """Draft with terminal status (rejected) -> cannot redraft."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn
        _, draft = _make_test_draft(conn, temp_dir, status="rejected")

        _save_angle(mock_adapter, "123", draft.id, "try something")

        text = mock_send.call_args[0][2]
        assert "cannot redraft" in text.lower()


class TestSaveRejectionNote:
    """Tests for _save_rejection_note function."""

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_save_rejection_note_saves_memory(self, mock_conn, mock_send, mock_adapter, temp_dir):
        """Rejection saves voice memory with correct args."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn
        project, draft = _make_test_draft(conn, temp_dir, platform="x")

        with (
            patch("social_hook.intro_lifecycle.on_intro_rejected", return_value=""),
            patch("social_hook.config.project.save_memory") as mock_save,
        ):
            _save_rejection_note(mock_adapter, "123", draft.id, "too promotional")

            mock_save.assert_called_once_with(
                project.repo_path,
                context="Rejected x draft",
                feedback="too promotional",
                draft_id=draft.id,
            )
            text = mock_send.call_args[0][2]
            assert "rejected" in text.lower()
            assert "saved" in text.lower()

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_save_rejection_note_memory_failure_doesnt_block(
        self, mock_conn, mock_send, mock_adapter, temp_dir
    ):
        """Memory save failure doesn't block rejection."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn
        _, draft = _make_test_draft(conn, temp_dir)

        with (
            patch("social_hook.intro_lifecycle.on_intro_rejected", return_value=""),
            patch(
                "social_hook.config.project.save_memory",
                side_effect=Exception("disk full"),
            ),
        ):
            _save_rejection_note(mock_adapter, "123", draft.id, "too wordy")

            text = mock_send.call_args[0][2]
            assert "rejected" in text.lower()
            assert "saved" not in text.lower()

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_save_rejection_note_project_not_found(
        self, mock_conn, mock_send, mock_adapter, temp_dir
    ):
        """Project not found -> draft rejected, no memory save."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn
        _, draft = _make_test_draft(conn, temp_dir)

        with (
            patch("social_hook.intro_lifecycle.on_intro_rejected", return_value=""),
            patch("social_hook.db.operations.get_project", return_value=None),
            patch("social_hook.config.project.save_memory") as mock_save,
        ):
            _save_rejection_note(mock_adapter, "123", draft.id, "not good")

            mock_save.assert_not_called()
            text = mock_send.call_args[0][2]
            assert "rejected" in text.lower()
            assert "saved" not in text.lower()


# =============================================================================
# Button Handler Tests (buttons.py)
# =============================================================================


class TestBtnUnapprove:
    """Tests for btn_unapprove button handler."""

    @patch("social_hook.bot.buttons._get_conn")
    def test_unapprove_success(self, mock_conn, mock_adapter, temp_dir):
        """Unapprove an approved draft -> status becomes draft."""
        from social_hook.bot.buttons import btn_unapprove
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
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Test",
            status="approved",
        )
        insert_draft(conn, draft)

        with patch("social_hook.db.operations.emit_data_event") as mock_emit:
            btn_unapprove(mock_adapter, "123", "cb_1", draft.id, None)
            mock_emit.assert_called_once_with(conn, "draft", "unapproved", draft.id, project.id)

        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.status == "draft"
        conn2.close()

    @patch("social_hook.bot.buttons._get_conn")
    def test_unapprove_wrong_status(self, mock_conn, mock_adapter, temp_dir):
        """Cannot unapprove a draft that is not approved."""
        from social_hook.bot.buttons import btn_unapprove
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
            decision="draft",
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

        with patch("social_hook.db.operations.emit_data_event") as mock_emit:
            btn_unapprove(mock_adapter, "123", "cb_1", draft.id, None)
            mock_emit.assert_not_called()

        # Verify error message was sent
        mock_adapter.send_message.assert_called()
        msg = mock_adapter.send_message.call_args[0][1]
        assert "Cannot unapprove" in msg.text


class TestBtnUnschedule:
    """Tests for btn_unschedule button handler."""

    @patch("social_hook.bot.buttons._get_conn")
    def test_unschedule_success(self, mock_conn, mock_adapter, temp_dir):
        """Unschedule a scheduled draft -> status becomes draft."""
        from social_hook.bot.buttons import btn_unschedule
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
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Test",
            status="scheduled",
        )
        insert_draft(conn, draft)

        with patch("social_hook.db.operations.emit_data_event") as mock_emit:
            btn_unschedule(mock_adapter, "123", "cb_1", draft.id, None)
            mock_emit.assert_called_once_with(conn, "draft", "unscheduled", draft.id, project.id)

        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.status == "draft"
        conn2.close()

    @patch("social_hook.bot.buttons._get_conn")
    def test_unschedule_wrong_status(self, mock_conn, mock_adapter, temp_dir):
        """Cannot unschedule a draft that is not scheduled."""
        from social_hook.bot.buttons import btn_unschedule
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
            decision="draft",
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

        with patch("social_hook.db.operations.emit_data_event") as mock_emit:
            btn_unschedule(mock_adapter, "123", "cb_1", draft.id, None)
            mock_emit.assert_not_called()

        mock_adapter.send_message.assert_called()
        msg = mock_adapter.send_message.call_args[0][1]
        assert "Cannot unschedule" in msg.text


class TestBtnReopen:
    """Tests for btn_reopen button handler."""

    @patch("social_hook.bot.buttons._get_conn")
    def test_reopen_cancelled(self, mock_conn, mock_adapter, temp_dir):
        """Reopen a cancelled draft -> status becomes draft."""
        from social_hook.bot.buttons import btn_reopen
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
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Test",
            status="cancelled",
        )
        insert_draft(conn, draft)

        with patch("social_hook.db.operations.emit_data_event") as mock_emit:
            btn_reopen(mock_adapter, "123", "cb_1", draft.id, None)
            mock_emit.assert_called_once_with(conn, "draft", "reopened", draft.id, project.id)

        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.status == "draft"
        conn2.close()

    @patch("social_hook.bot.buttons._get_conn")
    def test_reopen_rejected(self, mock_conn, mock_adapter, temp_dir):
        """Reopen a rejected draft -> status becomes draft, last_error cleared."""
        from social_hook.bot.buttons import btn_reopen
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
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Test",
            status="rejected",
            last_error="old rejection reason",
        )
        insert_draft(conn, draft)

        with patch("social_hook.db.operations.emit_data_event") as mock_emit:
            btn_reopen(mock_adapter, "123", "cb_1", draft.id, None)
            mock_emit.assert_called_once_with(conn, "draft", "reopened", draft.id, project.id)

        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.status == "draft"
        assert updated.last_error == ""
        conn2.close()

    @patch("social_hook.bot.buttons._get_conn")
    def test_reopen_wrong_status(self, mock_conn, mock_adapter, temp_dir):
        """Cannot reopen a draft that is not cancelled or rejected."""
        from social_hook.bot.buttons import btn_reopen
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
            decision="draft",
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

        with patch("social_hook.db.operations.emit_data_event") as mock_emit:
            btn_reopen(mock_adapter, "123", "cb_1", draft.id, None)
            mock_emit.assert_not_called()

        mock_adapter.send_message.assert_called()
        msg = mock_adapter.send_message.call_args[0][1]
        assert "Cannot reopen" in msg.text

    @patch("social_hook.bot.buttons._get_conn")
    def test_reopen_intro_blocked(self, mock_conn, mock_adapter, temp_dir):
        """Intro drafts cannot be reopened."""
        from social_hook.bot.buttons import btn_reopen
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
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Test",
            status="cancelled",
            is_intro=True,
        )
        insert_draft(conn, draft)

        with patch("social_hook.db.operations.emit_data_event") as mock_emit:
            btn_reopen(mock_adapter, "123", "cb_1", draft.id, None)
            mock_emit.assert_not_called()

        mock_adapter.send_message.assert_called()
        msg = mock_adapter.send_message.call_args[0][1]
        assert "Intro drafts cannot be reopened" in msg.text


class TestApplyExpertResultUnpack:
    """Test that _apply_expert_result handles 4-tuple from _generate_media."""

    @patch("social_hook.bot.commands._get_conn")
    def test_no_value_error_on_4_tuple(self, mock_conn, mock_adapter, temp_dir):
        """_generate_media returns 4 values; _apply_expert_result should not crash."""
        from social_hook.bot.commands import _apply_expert_result
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
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Original",
            status="draft",
            media_type="test",
        )
        insert_draft(conn, draft)

        draft_obj = get_draft(conn, draft.id)

        result = MagicMock()
        result.refined_content = None
        result.refined_media_spec = {"some": "spec"}

        config = MagicMock()

        with patch(
            "social_hook.drafting._generate_media",
            return_value=(["path.png"], "image", {"key": "val"}, None),
        ):
            # Should not raise ValueError: not enough values to unpack
            applied = _apply_expert_result(conn, draft_obj, result, config=config)
            assert applied is True

        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.media_spec == {"some": "spec"}
        conn2.close()


class TestButtonRestoration:
    """Tests that buttons are restored on failure/completion paths."""

    @patch("social_hook.bot.commands._get_conn")
    def test_save_edit_includes_buttons(self, mock_conn, mock_adapter, temp_dir):
        """_save_edit sends response with buttons attached."""
        from social_hook.bot.commands import _save_edit
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
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Old content",
            status="draft",
        )
        insert_draft(conn, draft)

        _save_edit(mock_adapter, "123", draft.id, "New content")

        mock_adapter.send_message.assert_called()
        msg = mock_adapter.send_message.call_args[0][1]
        assert len(msg.buttons) > 0

    @patch("social_hook.bot.commands._get_conn")
    def test_save_angle_failure_includes_buttons(self, mock_conn, mock_adapter, temp_dir):
        """_save_angle failure path sends response with buttons attached."""
        from social_hook.llm.schemas import ExpertAction, ExpertResponseInput

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn
        _, draft = _make_test_draft(conn, temp_dir)

        mock_result = ExpertResponseInput(
            action=ExpertAction.refine_draft,
            reasoning="Could not refine",
            refined_content=None,
            refined_media_spec=None,
        )

        with (
            patch("social_hook.config.yaml.load_full_config") as mock_config,
            patch("social_hook.llm.factory.create_client"),
            patch("social_hook.llm.expert.Expert") as MockExpert,
        ):
            mock_config.return_value = MagicMock()
            MockExpert.return_value.handle.return_value = mock_result

            _save_angle(mock_adapter, "123", draft.id, "try something")

        mock_adapter.send_message.assert_called()
        msg = mock_adapter.send_message.call_args[0][1]
        assert len(msg.buttons) > 0


class TestResyncThreadTweets:
    """Tests that draft_tweets are re-split when content is edited on a threaded draft."""

    @patch("social_hook.bot.commands._get_conn")
    def test_save_edit_resyncs_tweets(self, mock_conn, mock_adapter, temp_dir):
        """_save_edit re-splits draft_tweets when editing a threaded draft."""
        from social_hook.bot.commands import _save_edit
        from social_hook.db import insert_decision
        from social_hook.db.operations import get_draft_tweets, insert_draft_tweet
        from social_hook.models import Decision, DraftTweet

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)
        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc",
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="1/ Old tweet one\n\n2/ Old tweet two\n\n3/ Old tweet three\n\n4/ Old tweet four",
            status="draft",
        )
        insert_draft(conn, draft)

        # Insert original thread tweets
        for i, text in enumerate(
            ["Old tweet one", "Old tweet two", "Old tweet three", "Old tweet four"]
        ):
            insert_draft_tweet(
                conn,
                DraftTweet(
                    id=generate_id("tweet"),
                    draft_id=draft.id,
                    position=i,
                    content=text,
                ),
            )

        assert len(get_draft_tweets(conn, draft.id)) == 4

        new_content = "1/ New first tweet\n\n2/ New second tweet\n\n3/ New third tweet\n\n4/ New fourth tweet\n\n5/ Bonus fifth tweet"
        _save_edit(mock_adapter, "123", draft.id, new_content)

        conn2 = get_connection(db_path)
        tweets = get_draft_tweets(conn2, draft.id)
        assert len(tweets) == 5
        assert tweets[0].content == "New first tweet"
        assert tweets[4].content == "Bonus fifth tweet"
        conn2.close()

    @patch("social_hook.bot.commands._get_conn")
    def test_save_edit_no_tweets_is_noop(self, mock_conn, mock_adapter, temp_dir):
        """_save_edit on a non-threaded draft does not create draft_tweets."""
        from social_hook.bot.commands import _save_edit
        from social_hook.db import insert_decision
        from social_hook.db.operations import get_draft_tweets
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
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Single post content",
            status="draft",
        )
        insert_draft(conn, draft)

        _save_edit(mock_adapter, "123", draft.id, "Updated single post")

        conn2 = get_connection(db_path)
        tweets = get_draft_tweets(conn2, draft.id)
        assert len(tweets) == 0
        conn2.close()

    def test_replace_draft_tweets(self, temp_dir):
        """replace_draft_tweets deletes old tweets and inserts new ones."""
        from social_hook.db import insert_decision
        from social_hook.db.operations import (
            get_draft_tweets,
            insert_draft_tweet,
            replace_draft_tweets,
        )
        from social_hook.models import Decision, DraftTweet

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)

        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
        insert_project(conn, project)
        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc",
            decision="draft",
            reasoning="test",
        )
        insert_decision(conn, decision)
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="old",
            status="draft",
        )
        insert_draft(conn, draft)

        # Insert 3 original tweets
        for i in range(3):
            insert_draft_tweet(
                conn,
                DraftTweet(
                    id=generate_id("tweet"),
                    draft_id=draft.id,
                    position=i,
                    content=f"old {i}",
                ),
            )
        assert len(get_draft_tweets(conn, draft.id)) == 3

        # Replace with 2 new tweets
        new_tweets = [
            DraftTweet(id=generate_id("tweet"), draft_id=draft.id, position=0, content="new A"),
            DraftTweet(id=generate_id("tweet"), draft_id=draft.id, position=1, content="new B"),
        ]
        replace_draft_tweets(conn, draft.id, new_tweets)

        tweets = get_draft_tweets(conn, draft.id)
        assert len(tweets) == 2
        assert tweets[0].content == "new A"
        assert tweets[1].content == "new B"


class TestCmdErrors:
    """Tests for /errors command."""

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_no_errors(self, mock_conn, mock_send, mock_adapter, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        cmd_errors(mock_adapter, "123", "", None)
        text = mock_send.call_args[0][2]
        assert "No recent errors" in text

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_shows_errors(self, mock_conn, mock_send, mock_adapter, temp_dir):
        from social_hook.db import operations as ops
        from social_hook.models import SystemErrorRecord

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        ops.insert_system_error(
            conn,
            SystemErrorRecord(
                id=generate_id("err"),
                severity="error",
                message="Token refresh failed",
                source="trigger",
            ),
        )

        cmd_errors(mock_adapter, "123", "", None)
        text = mock_send.call_args[0][2]
        assert "Recent Errors" in text
        assert "Token refresh failed" in text

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_severity_filter(self, mock_conn, mock_send, mock_adapter, temp_dir):
        from social_hook.db import operations as ops
        from social_hook.models import SystemErrorRecord

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        ops.insert_system_error(
            conn,
            SystemErrorRecord(
                id=generate_id("err"),
                severity="warning",
                message="Slow query",
                source="web",
            ),
        )

        cmd_errors(mock_adapter, "123", "warning", None)
        text = mock_send.call_args[0][2]
        assert "Slow query" in text

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_limit_arg(self, mock_conn, mock_send, mock_adapter, temp_dir):
        from social_hook.db import operations as ops
        from social_hook.models import SystemErrorRecord

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        for i in range(5):
            ops.insert_system_error(
                conn,
                SystemErrorRecord(
                    id=generate_id("err"),
                    severity="error",
                    message=f"Error {i}",
                ),
            )

        cmd_errors(mock_adapter, "123", "3", None)
        text = mock_send.call_args[0][2]
        assert "Recent Errors" in text
        assert "(3)" in text

    @patch("social_hook.bot.commands._send")
    def test_invalid_arg(self, mock_send, mock_adapter):
        cmd_errors(mock_adapter, "123", "bogus", None)
        text = mock_send.call_args[0][2]
        assert "Usage" in text

    @patch("social_hook.bot.commands.cmd_errors")
    def test_route_errors(self, mock_errors, mock_adapter):
        msg = _make_inbound("/errors")
        handle_command(msg, mock_adapter)
        mock_errors.assert_called_once()

    @patch("social_hook.bot.commands.cmd_health")
    def test_route_health(self, mock_health, mock_adapter):
        msg = _make_inbound("/health")
        handle_command(msg, mock_adapter)
        mock_health.assert_called_once()


class TestCmdHealth:
    """Tests for /health command."""

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_healthy(self, mock_conn, mock_send, mock_adapter, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        cmd_health(mock_adapter, "123", "", None)
        text = mock_send.call_args[0][2]
        assert "HEALTHY" in text
        assert "Errors in last 24h: 0" in text

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_degraded(self, mock_conn, mock_send, mock_adapter, temp_dir):
        from social_hook.db import operations as ops
        from social_hook.models import SystemErrorRecord

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        ops.insert_system_error(
            conn,
            SystemErrorRecord(
                id=generate_id("err"),
                severity="error",
                message="Something broke",
            ),
        )

        cmd_health(mock_adapter, "123", "", None)
        text = mock_send.call_args[0][2]
        assert "DEGRADED" in text
        assert "error: 1" in text

    @patch("social_hook.bot.commands._send")
    @patch("social_hook.bot.commands._get_conn")
    def test_critical(self, mock_conn, mock_send, mock_adapter, temp_dir):
        from social_hook.db import operations as ops
        from social_hook.models import SystemErrorRecord

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        ops.insert_system_error(
            conn,
            SystemErrorRecord(
                id=generate_id("err"),
                severity="critical",
                message="DB corrupted",
            ),
        )

        cmd_health(mock_adapter, "123", "", None)
        text = mock_send.call_args[0][2]
        assert "CRITICAL" in text
