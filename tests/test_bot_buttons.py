"""Tests for bot inline button handlers (T27)."""

from unittest.mock import MagicMock, patch

import pytest

from social_hook.bot.buttons import (
    btn_approve,
    btn_cancel,
    btn_edit_submenu,
    btn_edit_text,
    btn_quick_approve,
    btn_reject,
    btn_reject_submenu,
    btn_schedule_optimal,
    btn_schedule_submenu,
    handle_callback,
)
from social_hook.db import get_connection, init_database, insert_decision, insert_draft, insert_project
from social_hook.filesystem import generate_id
from social_hook.models import Decision, Draft, Project


class TestHandleCallback:
    """Tests for callback routing."""

    @patch("social_hook.bot.buttons.btn_approve")
    @patch("social_hook.bot.buttons._answer_callback")
    def test_routes_approve(self, mock_answer, mock_btn):
        callback = {
            "id": "cb1",
            "message": {"chat": {"id": 123}},
            "data": "approve:draft_123",
        }
        handle_callback(callback, "token")
        mock_btn.assert_called_once_with("token", "123", "cb1", "draft_123", None)

    @patch("social_hook.bot.buttons.btn_schedule_optimal")
    @patch("social_hook.bot.buttons._answer_callback")
    def test_routes_schedule_optimal(self, mock_answer, mock_btn):
        callback = {
            "id": "cb1",
            "message": {"chat": {"id": 123}},
            "data": "schedule_optimal:draft_456",
        }
        handle_callback(callback, "token")
        mock_btn.assert_called_once()

    @patch("social_hook.bot.buttons.btn_edit_text")
    @patch("social_hook.bot.buttons._answer_callback")
    def test_routes_edit_text(self, mock_answer, mock_btn):
        callback = {
            "id": "cb1",
            "message": {"chat": {"id": 123}},
            "data": "edit_text:draft_789",
        }
        handle_callback(callback, "token")
        mock_btn.assert_called_once()

    @patch("social_hook.bot.buttons.btn_reject_submenu")
    @patch("social_hook.bot.buttons._answer_callback")
    def test_routes_reject(self, mock_answer, mock_btn):
        callback = {
            "id": "cb1",
            "message": {"chat": {"id": 123}},
            "data": "reject:draft_abc",
        }
        handle_callback(callback, "token")
        mock_btn.assert_called_once()

    @patch("social_hook.bot.buttons._answer_callback")
    def test_unknown_action(self, mock_answer):
        callback = {
            "id": "cb1",
            "message": {"chat": {"id": 123}},
            "data": "unknown:draft_123",
        }
        handle_callback(callback, "token")
        mock_answer.assert_called_once()
        assert "Unknown" in mock_answer.call_args[0][2]

    @patch("social_hook.bot.buttons._answer_callback")
    def test_empty_data(self, mock_answer):
        callback = {
            "id": "cb1",
            "message": {"chat": {"id": 123}},
            "data": "",
        }
        handle_callback(callback, "token")
        mock_answer.assert_called_once()
        assert "Invalid" in mock_answer.call_args[0][2]


def _create_test_draft(conn, status="draft"):
    """Helper to create a test project + decision + draft."""
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
        content="Test draft content for social media",
        status=status,
    )
    insert_draft(conn, draft)
    return project, decision, draft


class TestBtnApprove:
    """Tests for approve button handler."""

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_approve_success(self, mock_conn, mock_answer, mock_send, temp_dir):
        from social_hook.db import get_draft

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        _, _, draft = _create_test_draft(conn)

        btn_approve("token", "123", "cb1", draft.id, None)
        mock_answer.assert_called_once()
        assert "approved" in mock_send.call_args[0][2]
        conn2 = get_connection(db_path)
        assert get_draft(conn2, draft.id).status == "approved"
        conn2.close()

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_approve_not_found(self, mock_conn, mock_answer, mock_send, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        btn_approve("token", "123", "cb1", "nonexistent", None)
        assert "not found" in mock_send.call_args[0][2]

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_approve_wrong_status(self, mock_conn, mock_answer, mock_send, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        _, _, draft = _create_test_draft(conn, status="posted")

        btn_approve("token", "123", "cb1", draft.id, None)
        assert "Cannot approve" in mock_send.call_args[0][2]


class TestBtnScheduleOptimal:
    """Tests for schedule optimal button handler."""

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_schedule_success(self, mock_conn, mock_answer, mock_send, temp_dir):
        from social_hook.db import get_draft

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        _, _, draft = _create_test_draft(conn)

        btn_schedule_optimal("token", "123", "cb1", draft.id, None)
        mock_answer.assert_called_once()
        assert "scheduled" in mock_send.call_args[0][2]
        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.status == "scheduled"
        assert updated.scheduled_time is not None
        conn2.close()

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_schedule_not_found(self, mock_conn, mock_answer, mock_send, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        btn_schedule_optimal("token", "123", "cb1", "nonexistent", None)
        assert "not found" in mock_send.call_args[0][2]


class TestBtnEditText:
    """Tests for edit text button handler."""

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_edit_shows_content(self, mock_conn, mock_answer, mock_send, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        _, _, draft = _create_test_draft(conn)

        btn_edit_text("token", "123", "cb1", draft.id, None)
        mock_answer.assert_called_once()
        text = mock_send.call_args[0][2]
        assert "Current content" in text
        assert "Test draft content" in text

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_edit_not_found(self, mock_conn, mock_answer, mock_send, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        btn_edit_text("token", "123", "cb1", "nonexistent", None)
        assert "not found" in mock_send.call_args[0][2]


class TestBtnReject:
    """Tests for reject button handler."""

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_reject_success(self, mock_conn, mock_answer, mock_send, temp_dir):
        from social_hook.db import get_draft

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        _, _, draft = _create_test_draft(conn)

        btn_reject("token", "123", "cb1", draft.id, None)
        mock_answer.assert_called_once()
        assert "rejected" in mock_send.call_args[0][2]
        conn2 = get_connection(db_path)
        assert get_draft(conn2, draft.id).status == "rejected"
        conn2.close()

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_reject_not_found(self, mock_conn, mock_answer, mock_send, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        btn_reject("token", "123", "cb1", "nonexistent", None)
        assert "not found" in mock_send.call_args[0][2]


class TestScheduleSubmenu:
    """Tests for schedule submenu flow."""

    @patch("social_hook.bot.buttons.send_notification_with_buttons")
    @patch("social_hook.bot.buttons._answer_callback")
    def test_submenu_shows_options(self, mock_answer, mock_send_buttons):
        btn_schedule_submenu("token", "123", "cb1", "draft_abc", None)
        mock_answer.assert_called_once()
        mock_send_buttons.assert_called_once()
        buttons = mock_send_buttons.call_args[0][3]
        # Should have Optimal time and Custom time
        cb_data = [b["callback_data"] for row in buttons for b in row]
        assert "schedule_optimal:draft_abc" in cb_data
        assert "schedule_custom:draft_abc" in cb_data

    @patch("social_hook.bot.buttons.btn_schedule_submenu")
    @patch("social_hook.bot.buttons._answer_callback")
    def test_schedule_routes_to_submenu(self, mock_answer, mock_submenu):
        callback = {
            "id": "cb1",
            "message": {"chat": {"id": 123}},
            "data": "schedule:draft_abc",
        }
        handle_callback(callback, "token")
        mock_submenu.assert_called_once()


class TestEditSubmenu:
    """Tests for edit submenu flow."""

    @patch("social_hook.bot.buttons.send_notification_with_buttons")
    @patch("social_hook.bot.buttons._answer_callback")
    def test_submenu_shows_options(self, mock_answer, mock_send_buttons):
        btn_edit_submenu("token", "123", "cb1", "draft_abc", None)
        mock_answer.assert_called_once()
        mock_send_buttons.assert_called_once()
        buttons = mock_send_buttons.call_args[0][3]
        cb_data = [b["callback_data"] for row in buttons for b in row]
        assert "edit_text:draft_abc" in cb_data
        assert "edit_media:draft_abc" in cb_data
        assert "edit_angle:draft_abc" in cb_data

    @patch("social_hook.bot.buttons.btn_edit_submenu")
    @patch("social_hook.bot.buttons._answer_callback")
    def test_edit_routes_to_submenu(self, mock_answer, mock_submenu):
        callback = {
            "id": "cb1",
            "message": {"chat": {"id": 123}},
            "data": "edit:draft_abc",
        }
        handle_callback(callback, "token")
        mock_submenu.assert_called_once()


class TestRejectSubmenu:
    """Tests for reject submenu flow."""

    @patch("social_hook.bot.buttons.send_notification_with_buttons")
    @patch("social_hook.bot.buttons._answer_callback")
    def test_submenu_shows_options(self, mock_answer, mock_send_buttons):
        btn_reject_submenu("token", "123", "cb1", "draft_abc", None)
        mock_answer.assert_called_once()
        mock_send_buttons.assert_called_once()
        buttons = mock_send_buttons.call_args[0][3]
        cb_data = [b["callback_data"] for row in buttons for b in row]
        assert "reject_now:draft_abc" in cb_data
        assert "reject_note:draft_abc" in cb_data

    @patch("social_hook.bot.buttons.btn_reject_submenu")
    @patch("social_hook.bot.buttons._answer_callback")
    def test_reject_routes_to_submenu(self, mock_answer, mock_submenu):
        callback = {
            "id": "cb1",
            "message": {"chat": {"id": 123}},
            "data": "reject:draft_abc",
        }
        handle_callback(callback, "token")
        mock_submenu.assert_called_once()


class TestQuickApprove:
    """Tests for quick approve button."""

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_quick_approve_success(self, mock_conn, mock_answer, mock_send, temp_dir):
        from social_hook.db import get_draft

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        _, _, draft = _create_test_draft(conn)

        btn_quick_approve("token", "123", "cb1", draft.id, None)
        mock_answer.assert_called_once()
        text = mock_send.call_args[0][2]
        assert "approved" in text
        assert "scheduled" in text

        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.status == "scheduled"
        assert updated.scheduled_time is not None
        conn2.close()

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_quick_approve_not_found(self, mock_conn, mock_answer, mock_send, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        btn_quick_approve("token", "123", "cb1", "nonexistent", None)
        assert "not found" in mock_send.call_args[0][2]


class TestBtnCancel:
    """Tests for cancel button from scheduled list."""

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_cancel_success(self, mock_conn, mock_answer, mock_send, temp_dir):
        from social_hook.db import get_draft

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        _, _, draft = _create_test_draft(conn, status="scheduled")

        btn_cancel("token", "123", "cb1", draft.id, None)
        mock_answer.assert_called_once()
        assert "cancelled" in mock_send.call_args[0][2]

        conn2 = get_connection(db_path)
        assert get_draft(conn2, draft.id).status == "cancelled"
        conn2.close()
