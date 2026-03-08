"""Tests for bot inline button handlers (T27)."""

import time
from unittest.mock import MagicMock, patch

import pytest

from social_hook.bot.buttons import (
    _REPLY_TTL_SECONDS,
    PendingReply,
    _pending_replies,
    btn_approve,
    btn_cancel,
    btn_edit_angle,
    btn_edit_media,
    btn_edit_submenu,
    btn_edit_text,
    btn_media_regen,
    btn_media_remove,
    btn_quick_approve,
    btn_reject,
    btn_reject_note,
    btn_reject_submenu,
    btn_schedule_custom,
    btn_schedule_optimal,
    btn_schedule_submenu,
    clear_pending_reply,
    get_pending_reply,
    handle_callback,
)
from social_hook.db import (
    get_connection,
    init_database,
    insert_decision,
    insert_draft,
    insert_project,
)
from social_hook.filesystem import generate_id
from social_hook.messaging.base import CallbackEvent, MessagingAdapter, SendResult
from social_hook.models import Decision, Draft, Project


@pytest.fixture(autouse=True)
def _clear_pending_replies():
    """Clear pending replies state between tests."""
    _pending_replies.clear()
    yield
    _pending_replies.clear()


@pytest.fixture
def mock_adapter():
    """Create a mock MessagingAdapter with standard return values."""
    adapter = MagicMock(spec=MessagingAdapter)
    adapter.send_message.return_value = SendResult(success=True, message_id="test_1")
    adapter.answer_callback.return_value = True
    adapter.get_capabilities.return_value = MagicMock(supports_media=True)
    adapter.send_media.return_value = SendResult(success=True, message_id="test_media_1")
    return adapter


def _make_callback_event(
    action: str, payload: str, chat_id: str = "123", callback_id: str = "cb1"
) -> CallbackEvent:
    """Helper to create a CallbackEvent."""
    return CallbackEvent(
        chat_id=chat_id,
        callback_id=callback_id,
        action=action,
        payload=payload,
    )


class TestHandleCallback:
    """Tests for callback routing."""

    @patch("social_hook.bot.buttons.btn_approve")
    @patch("social_hook.bot.buttons._answer_callback")
    def test_routes_approve(self, mock_answer, mock_btn, mock_adapter):
        event = _make_callback_event("approve", "draft_123")
        handle_callback(event, mock_adapter)
        mock_btn.assert_called_once_with(
            mock_adapter, "123", "cb1", "draft_123", None, message_id=None
        )

    @patch("social_hook.bot.buttons.btn_schedule_optimal")
    @patch("social_hook.bot.buttons._answer_callback")
    def test_routes_schedule_optimal(self, mock_answer, mock_btn, mock_adapter):
        event = _make_callback_event("schedule_optimal", "draft_456")
        handle_callback(event, mock_adapter)
        mock_btn.assert_called_once()

    @patch("social_hook.bot.buttons.btn_edit_text")
    @patch("social_hook.bot.buttons._answer_callback")
    def test_routes_edit_text(self, mock_answer, mock_btn, mock_adapter):
        event = _make_callback_event("edit_text", "draft_789")
        handle_callback(event, mock_adapter)
        mock_btn.assert_called_once()

    @patch("social_hook.bot.buttons.btn_reject_submenu")
    @patch("social_hook.bot.buttons._answer_callback")
    def test_routes_reject(self, mock_answer, mock_btn, mock_adapter):
        event = _make_callback_event("reject", "draft_abc")
        handle_callback(event, mock_adapter)
        mock_btn.assert_called_once()

    @patch("social_hook.bot.buttons._answer_callback")
    def test_unknown_action(self, mock_answer, mock_adapter):
        event = _make_callback_event("unknown", "draft_123")
        handle_callback(event, mock_adapter)
        mock_answer.assert_called_once()
        assert "Unknown" in mock_answer.call_args[0][2]

    @patch("social_hook.bot.buttons._answer_callback")
    def test_empty_action(self, mock_answer, mock_adapter):
        event = CallbackEvent(chat_id="123", callback_id="cb1", action="", payload="")
        handle_callback(event, mock_adapter)
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
        decision="draft",
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
    def test_approve_success(self, mock_conn, mock_answer, mock_send, mock_adapter, temp_dir):
        from social_hook.db import get_draft

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        _, _, draft = _create_test_draft(conn)

        btn_approve(mock_adapter, "123", "cb1", draft.id, None)
        mock_answer.assert_called_once()
        assert "approved" in mock_send.call_args[0][2]
        conn2 = get_connection(db_path)
        assert get_draft(conn2, draft.id).status == "approved"
        conn2.close()

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_approve_not_found(self, mock_conn, mock_answer, mock_send, mock_adapter, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        btn_approve(mock_adapter, "123", "cb1", "nonexistent", None)
        assert "not found" in mock_send.call_args[0][2]

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_approve_wrong_status(self, mock_conn, mock_answer, mock_send, mock_adapter, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        _, _, draft = _create_test_draft(conn, status="posted")

        btn_approve(mock_adapter, "123", "cb1", draft.id, None)
        assert "Cannot approve" in mock_send.call_args[0][2]


class TestBtnScheduleOptimal:
    """Tests for schedule optimal button handler."""

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_schedule_success(self, mock_conn, mock_answer, mock_send, mock_adapter, temp_dir):
        from social_hook.db import get_draft

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        _, _, draft = _create_test_draft(conn)

        btn_schedule_optimal(mock_adapter, "123", "cb1", draft.id, None)
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
    def test_schedule_not_found(self, mock_conn, mock_answer, mock_send, mock_adapter, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        btn_schedule_optimal(mock_adapter, "123", "cb1", "nonexistent", None)
        assert "not found" in mock_send.call_args[0][2]


class TestBtnEditText:
    """Tests for edit text button handler."""

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_edit_shows_content(self, mock_conn, mock_answer, mock_send, mock_adapter, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        _, _, draft = _create_test_draft(conn)

        btn_edit_text(mock_adapter, "123", "cb1", draft.id, None)
        mock_answer.assert_called_once()
        text = mock_send.call_args[0][2]
        assert "Current content" in text
        assert "Test draft content" in text

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_edit_not_found(self, mock_conn, mock_answer, mock_send, mock_adapter, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        btn_edit_text(mock_adapter, "123", "cb1", "nonexistent", None)
        assert "not found" in mock_send.call_args[0][2]


class TestBtnReject:
    """Tests for reject button handler."""

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_reject_success(self, mock_conn, mock_answer, mock_send, mock_adapter, temp_dir):
        from social_hook.db import get_draft

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        _, _, draft = _create_test_draft(conn)

        btn_reject(mock_adapter, "123", "cb1", draft.id, None)
        mock_answer.assert_called_once()
        assert "rejected" in mock_send.call_args[0][2]
        conn2 = get_connection(db_path)
        assert get_draft(conn2, draft.id).status == "rejected"
        conn2.close()

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_reject_not_found(self, mock_conn, mock_answer, mock_send, mock_adapter, temp_dir):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        btn_reject(mock_adapter, "123", "cb1", "nonexistent", None)
        assert "not found" in mock_send.call_args[0][2]


class TestScheduleSubmenu:
    """Tests for schedule submenu flow."""

    def test_submenu_shows_options(self, mock_adapter):
        btn_schedule_submenu(mock_adapter, "123", "cb1", "draft_abc", None)
        mock_adapter.answer_callback.assert_called_once()
        mock_adapter.send_message.assert_called_once()
        msg = mock_adapter.send_message.call_args[0][1]
        # Verify buttons contain correct actions
        actions = [b.action for row in msg.buttons for b in row.buttons]
        assert "schedule_optimal" in actions
        assert "schedule_custom" in actions

    @patch("social_hook.bot.buttons.btn_schedule_submenu")
    @patch("social_hook.bot.buttons._answer_callback")
    def test_schedule_routes_to_submenu(self, mock_answer, mock_submenu, mock_adapter):
        event = _make_callback_event("schedule", "draft_abc")
        handle_callback(event, mock_adapter)
        mock_submenu.assert_called_once()


class TestEditSubmenu:
    """Tests for edit submenu flow."""

    def test_submenu_shows_options(self, mock_adapter):
        btn_edit_submenu(mock_adapter, "123", "cb1", "draft_abc", None)
        mock_adapter.answer_callback.assert_called_once()
        mock_adapter.send_message.assert_called_once()
        msg = mock_adapter.send_message.call_args[0][1]
        actions = [b.action for row in msg.buttons for b in row.buttons]
        assert "edit_text" in actions
        assert "edit_media" in actions
        assert "edit_angle" in actions

    @patch("social_hook.bot.buttons.btn_edit_submenu")
    @patch("social_hook.bot.buttons._answer_callback")
    def test_edit_routes_to_submenu(self, mock_answer, mock_submenu, mock_adapter):
        event = _make_callback_event("edit", "draft_abc")
        handle_callback(event, mock_adapter)
        mock_submenu.assert_called_once()


class TestRejectSubmenu:
    """Tests for reject submenu flow."""

    def test_submenu_shows_options(self, mock_adapter):
        btn_reject_submenu(mock_adapter, "123", "cb1", "draft_abc", None)
        mock_adapter.answer_callback.assert_called_once()
        mock_adapter.send_message.assert_called_once()
        msg = mock_adapter.send_message.call_args[0][1]
        actions = [b.action for row in msg.buttons for b in row.buttons]
        assert "reject_now" in actions
        assert "reject_note" in actions

    @patch("social_hook.bot.buttons.btn_reject_submenu")
    @patch("social_hook.bot.buttons._answer_callback")
    def test_reject_routes_to_submenu(self, mock_answer, mock_submenu, mock_adapter):
        event = _make_callback_event("reject", "draft_abc")
        handle_callback(event, mock_adapter)
        mock_submenu.assert_called_once()


class TestQuickApprove:
    """Tests for quick approve button."""

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_quick_approve_success(self, mock_conn, mock_answer, mock_send, mock_adapter, temp_dir):
        from social_hook.db import get_draft

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        _, _, draft = _create_test_draft(conn)

        btn_quick_approve(mock_adapter, "123", "cb1", draft.id, None)
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
    def test_quick_approve_not_found(
        self, mock_conn, mock_answer, mock_send, mock_adapter, temp_dir
    ):
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        btn_quick_approve(mock_adapter, "123", "cb1", "nonexistent", None)
        assert "not found" in mock_send.call_args[0][2]


class TestBtnCancel:
    """Tests for cancel button from scheduled list."""

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_cancel_success(self, mock_conn, mock_answer, mock_send, mock_adapter, temp_dir):
        from social_hook.db import get_draft

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        _, _, draft = _create_test_draft(conn, status="scheduled")

        btn_cancel(mock_adapter, "123", "cb1", draft.id, None)
        mock_answer.assert_called_once()
        assert "cancelled" in mock_send.call_args[0][2]

        conn2 = get_connection(db_path)
        assert get_draft(conn2, draft.id).status == "cancelled"
        conn2.close()


class TestPendingReplies:
    """Tests for pending reply state tracking."""

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_edit_text_sets_pending(
        self, mock_conn, mock_answer, mock_send, mock_adapter, temp_dir
    ):
        """Verify _pending_replies[chat_id] is PendingReply after btn_edit_text."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        _, _, draft = _create_test_draft(conn)

        btn_edit_text(mock_adapter, "123", "cb1", draft.id, None)

        assert "123" in _pending_replies
        pending = _pending_replies["123"]
        assert pending.type == "edit_text"
        assert pending.draft_id == draft.id
        assert time.time() - pending.timestamp < 5

    def test_get_pending_reply_returns_without_consuming(self):
        """Verify get_pending_reply returns PendingReply but entry persists."""
        _pending_replies["chat1"] = PendingReply(
            type="edit_text", draft_id="draft_abc", timestamp=time.time()
        )

        result = get_pending_reply("chat1")
        assert result.draft_id == "draft_abc"

        result2 = get_pending_reply("chat1")
        assert result2.draft_id == "draft_abc"

    def test_clear_pending_reply_removes_entry(self):
        """Verify clear_pending_reply removes the entry."""
        _pending_replies["chat1"] = PendingReply(
            type="edit_text", draft_id="draft_abc", timestamp=time.time()
        )

        clear_pending_reply("chat1")
        assert "chat1" not in _pending_replies

    def test_get_pending_reply_missing(self):
        """Verify returns None for unknown chat_id."""
        assert get_pending_reply("unknown_chat") is None

    def test_get_pending_reply_expired(self):
        """Verify returns None when reply TTL has expired."""
        _pending_replies["chat1"] = PendingReply(
            type="edit_text", draft_id="draft_abc", timestamp=time.time() - _REPLY_TTL_SECONDS - 60
        )

        result = get_pending_reply("chat1")
        assert result is None
        assert "chat1" not in _pending_replies

    def test_concurrent_pending_replies(self):
        """Two different chat_ids should have independent pending replies."""
        _pending_replies["chat1"] = PendingReply(
            type="edit_text", draft_id="draft_a", timestamp=time.time()
        )
        _pending_replies["chat2"] = PendingReply(
            type="edit_text", draft_id="draft_b", timestamp=time.time()
        )

        assert get_pending_reply("chat1").draft_id == "draft_a"
        assert get_pending_reply("chat2").draft_id == "draft_b"

        clear_pending_reply("chat1")
        assert get_pending_reply("chat1") is None
        assert get_pending_reply("chat2").draft_id == "draft_b"

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_edit_overwrite_warns(self, mock_conn, mock_answer, mock_send, mock_adapter, temp_dir):
        """Clicking Edit on draft B while draft A is pending warns about switch."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        _, _, draft_a = _create_test_draft(conn)

        # Create second draft
        draft_b = Draft(
            id=generate_id("draft"),
            project_id=draft_a.project_id,
            decision_id=draft_a.decision_id,
            platform="x",
            content="Second draft content",
            status="draft",
        )
        insert_draft(conn, draft_b)

        # Edit draft A
        btn_edit_text(mock_adapter, "123", "cb1", draft_a.id, None)
        assert _pending_replies["123"].draft_id == draft_a.id

        # Now edit draft B — should warn about switch
        mock_send.reset_mock()
        mock_conn.return_value = get_connection(db_path)
        btn_edit_text(mock_adapter, "123", "cb2", draft_b.id, None)

        # Should have warned about switching
        calls = [c[0][2] for c in mock_send.call_args_list]
        assert any("Switching edit" in c or "cancelled" in c for c in calls)
        # Pending reply should now be draft B
        assert _pending_replies["123"].draft_id == draft_b.id

    def test_schedule_custom_sets_pending_reply(self, mock_adapter):
        """btn_schedule_custom should set a pending reply of type schedule_custom."""
        btn_schedule_custom(mock_adapter, "123", "cb1", "draft_abc", None)
        assert "123" in _pending_replies
        pending = _pending_replies["123"]
        assert pending.type == "schedule_custom"
        assert pending.draft_id == "draft_abc"

    def test_edit_angle_sets_pending_reply(self, mock_adapter):
        """btn_edit_angle should set a pending reply of type edit_angle."""
        btn_edit_angle(mock_adapter, "123", "cb1", "draft_abc", None)
        assert "123" in _pending_replies
        pending = _pending_replies["123"]
        assert pending.type == "edit_angle"
        assert pending.draft_id == "draft_abc"

    def test_reject_note_sets_pending_reply(self, mock_adapter):
        """btn_reject_note should set a pending reply of type reject_note."""
        btn_reject_note(mock_adapter, "123", "cb1", "draft_abc", None)
        assert "123" in _pending_replies
        pending = _pending_replies["123"]
        assert pending.type == "reject_note"
        assert pending.draft_id == "draft_abc"


class TestButtonClearing:
    """Tests for clearing buttons from original notification messages."""

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_approve_clears_original_buttons(
        self, mock_conn, mock_answer, mock_send, mock_adapter, temp_dir
    ):
        """Approve should call adapter.edit_message to clear buttons."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn
        _, _, draft = _create_test_draft(conn)
        mock_adapter.edit_message.return_value = SendResult(success=True)

        btn_approve(mock_adapter, "123", "cb1", draft.id, None, message_id="42")

        mock_adapter.edit_message.assert_called_once()
        call_args = mock_adapter.edit_message.call_args
        assert call_args[0][0] == "123"
        assert call_args[0][1] == "42"
        assert "approved" in call_args[0][2].text

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_reject_clears_original_buttons(
        self, mock_conn, mock_answer, mock_send, mock_adapter, temp_dir
    ):
        """Reject should call adapter.edit_message to clear buttons."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn
        _, _, draft = _create_test_draft(conn)
        mock_adapter.edit_message.return_value = SendResult(success=True)

        btn_reject(mock_adapter, "123", "cb1", draft.id, None, message_id="42")

        mock_adapter.edit_message.assert_called_once()
        assert "rejected" in mock_adapter.edit_message.call_args[0][2].text

    def test_submenu_does_not_clear_buttons(self, mock_adapter):
        """Submenus should NOT call edit_message."""
        btn_schedule_submenu(mock_adapter, "123", "cb1", "draft_abc", None, message_id="42")
        mock_adapter.edit_message.assert_not_called()

        btn_edit_submenu(mock_adapter, "123", "cb1", "draft_abc", None, message_id="42")
        mock_adapter.edit_message.assert_not_called()

        btn_reject_submenu(mock_adapter, "123", "cb1", "draft_abc", None, message_id="42")
        mock_adapter.edit_message.assert_not_called()

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_clear_buttons_skipped_when_no_message_id(
        self, mock_conn, mock_answer, mock_send, mock_adapter, temp_dir
    ):
        """When message_id is None, edit_message should NOT be called."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn
        _, _, draft = _create_test_draft(conn)

        btn_approve(mock_adapter, "123", "cb1", draft.id, None, message_id=None)

        mock_adapter.edit_message.assert_not_called()


class TestEmitDataEvent:
    """Tests for emit_data_event calls in button handlers."""

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_approve_emits_data_event(
        self, mock_conn, mock_answer, mock_send, mock_adapter, temp_dir
    ):
        """Approve should call ops.emit_data_event."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn
        _, _, draft = _create_test_draft(conn)

        with patch("social_hook.db.operations.emit_data_event") as mock_emit:
            btn_approve(mock_adapter, "123", "cb1", draft.id, None)
            mock_emit.assert_called_once_with(conn, "draft", "approved", draft.id, draft.project_id)

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_reject_emits_data_event(
        self, mock_conn, mock_answer, mock_send, mock_adapter, temp_dir
    ):
        """Reject should call ops.emit_data_event."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn
        _, _, draft = _create_test_draft(conn)

        with patch("social_hook.db.operations.emit_data_event") as mock_emit:
            btn_reject(mock_adapter, "123", "cb1", draft.id, None)
            mock_emit.assert_called_once_with(conn, "draft", "rejected", draft.id, draft.project_id)


class TestBtnEditMedia:
    """Tests for edit media button handler."""

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_edit_media_shows_current_file(
        self, mock_conn, mock_answer, mock_send, mock_adapter, temp_dir
    ):
        """Draft with media_paths sends media via adapter and shows action buttons."""
        from social_hook.db import update_draft

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        _, _, draft = _create_test_draft(conn)
        # Add media to the draft
        update_draft(conn, draft.id, media_paths=["/tmp/test.png"], media_type="mermaid")

        btn_edit_media(mock_adapter, "123", "cb1", draft.id, None)

        mock_answer.assert_called_once()
        mock_adapter.send_media.assert_called_once_with(
            "123", "/tmp/test.png", caption=f"Current media for `{draft.id[:12]}`"
        )
        mock_adapter.send_message.assert_called_once()
        msg = mock_adapter.send_message.call_args[0][1]
        actions = [b.action for row in msg.buttons for b in row.buttons]
        assert "media_regen" in actions
        assert "media_remove" in actions

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_edit_media_no_media(self, mock_conn, mock_answer, mock_send, mock_adapter, temp_dir):
        """Draft with empty media_paths shows text-only response."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        _, _, draft = _create_test_draft(conn)

        btn_edit_media(mock_adapter, "123", "cb1", draft.id, None)

        mock_answer.assert_called_once()
        text = mock_send.call_args[0][2]
        assert "No media" in text


class TestBtnMediaRegen:
    """Tests for media regeneration button handler."""

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_media_regen_calls_adapter(
        self, mock_conn, mock_answer, mock_send, mock_adapter, temp_dir
    ):
        """Regeneration calls get_media_adapter and updates draft."""
        from social_hook.adapters.models import MediaResult
        from social_hook.db import get_draft, update_draft

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        _, _, draft = _create_test_draft(conn)
        update_draft(
            conn,
            draft.id,
            media_paths=["/old/path.png"],
            media_type="mermaid",
            media_spec={"diagram": "graph TD; A-->B"},
        )

        mock_media_adapter = MagicMock()
        mock_media_adapter.generate.return_value = MediaResult(
            success=True, file_path="/new/regenerated.png"
        )

        with patch(
            "social_hook.adapters.registry.get_media_adapter",
            return_value=mock_media_adapter,
        ):
            btn_media_regen(mock_adapter, "123", "cb1", draft.id, None)

        mock_media_adapter.generate.assert_called_once()
        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.media_paths == ["/new/regenerated.png"]
        conn2.close()
        assert "regenerated" in mock_send.call_args[0][2].lower()

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_media_regen_no_spec(self, mock_conn, mock_answer, mock_send, mock_adapter, temp_dir):
        """Draft without media_type/media_spec returns error message."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        _, _, draft = _create_test_draft(conn)

        btn_media_regen(mock_adapter, "123", "cb1", draft.id, None)

        text = mock_send.call_args[0][2]
        assert "No media spec" in text


class TestBtnMediaRemove:
    """Tests for media removal button handler."""

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_media_remove_clears_paths(
        self, mock_conn, mock_answer, mock_send, mock_adapter, temp_dir
    ):
        """Removing media sets media_paths to [] and creates audit trail."""
        from social_hook.db import get_draft, update_draft
        from social_hook.db.operations import get_draft_changes

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        _, _, draft = _create_test_draft(conn)
        update_draft(conn, draft.id, media_paths=["/tmp/old.png"])

        btn_media_remove(mock_adapter, "123", "cb1", draft.id, None)

        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.media_paths == []
        text = mock_send.call_args[0][2]
        assert "removed" in text.lower()

        # Verify DraftChange audit trail
        changes = get_draft_changes(conn2, draft.id)
        media_changes = [c for c in changes if c.field == "media_paths"]
        assert len(media_changes) >= 1
        assert media_changes[0].changed_by == "human"
        conn2.close()


class TestMediaRouting:
    """Tests for media_regen and media_remove dispatch routing."""

    @patch("social_hook.bot.buttons.btn_media_regen")
    @patch("social_hook.bot.buttons._answer_callback")
    def test_routes_media_regen(self, mock_answer, mock_btn, mock_adapter):
        event = _make_callback_event("media_regen", "draft_123")
        handle_callback(event, mock_adapter)
        mock_btn.assert_called_once_with(
            mock_adapter, "123", "cb1", "draft_123", None, message_id=None
        )

    @patch("social_hook.bot.buttons.btn_media_remove")
    @patch("social_hook.bot.buttons._answer_callback")
    def test_routes_media_remove(self, mock_answer, mock_btn, mock_adapter):
        event = _make_callback_event("media_remove", "draft_456")
        handle_callback(event, mock_adapter)
        mock_btn.assert_called_once_with(
            mock_adapter, "123", "cb1", "draft_456", None, message_id=None
        )


class TestDeferredStatusAccepted:
    """Verify btn_approve and btn_quick_approve accept deferred status."""

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_btn_approve_accepts_deferred(
        self, mock_conn, mock_answer, mock_send, mock_adapter, temp_dir
    ):
        from social_hook.db import get_draft

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        _, _, draft = _create_test_draft(conn, status="deferred")

        btn_approve(mock_adapter, "123", "cb1", draft.id, None)
        mock_answer.assert_called_once()
        assert "approved" in mock_send.call_args[0][2]
        conn2 = get_connection(db_path)
        assert get_draft(conn2, draft.id).status == "approved"
        conn2.close()

    @patch("social_hook.bot.buttons._send")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._get_conn")
    def test_btn_quick_approve_accepts_deferred(
        self, mock_conn, mock_answer, mock_send, mock_adapter, temp_dir
    ):
        from social_hook.db import get_draft

        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        mock_conn.return_value = conn

        _, _, draft = _create_test_draft(conn, status="deferred")

        btn_quick_approve(mock_adapter, "123", "cb1", draft.id, None)
        mock_answer.assert_called_once()
        text = mock_send.call_args[0][2]
        assert "approved" in text
        assert "scheduled" in text

        conn2 = get_connection(db_path)
        updated = get_draft(conn2, draft.id)
        assert updated.status == "scheduled"
        conn2.close()
