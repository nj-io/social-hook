"""Tests for status guards, media_retry, btn_post_now, and button handlers in bot/buttons.py."""

from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest

from social_hook.adapters.models import MediaResult
from social_hook.bot.buttons import (
    _guard_draft_editable,
    btn_edit_media,
    btn_media_regen,
    btn_media_remove,
    btn_media_retry,
    btn_post_now,
)
from social_hook.messaging.base import PlatformCapabilities, SendResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class FakeDraft:
    """Minimal draft stand-in for tests."""

    id: str = "draft_test123456"
    project_id: str = "proj_abc"
    status: str = "draft"
    media_paths: list = field(default_factory=list)
    media_type: str | None = "mermaid"
    media_spec: dict | None = field(default_factory=lambda: {"type": "flowchart", "code": "A->B"})
    media_spec_used: dict | None = None
    content: str = "test content"


def _make_adapter():
    adapter = MagicMock()
    adapter.send_message.return_value = SendResult(success=True)
    adapter.answer_callback.return_value = True
    adapter.get_capabilities.return_value = PlatformCapabilities(supports_media=True)
    adapter.send_media.return_value = SendResult(success=True)
    return adapter


# ---------------------------------------------------------------------------
# _guard_draft_editable tests
# ---------------------------------------------------------------------------


class TestGuardDraftEditable:
    def test_allows_draft_status(self):
        adapter = _make_adapter()
        draft = FakeDraft(status="draft")
        assert _guard_draft_editable(adapter, "chat1", draft) is True
        adapter.send_message.assert_not_called()

    def test_allows_deferred_status(self):
        adapter = _make_adapter()
        draft = FakeDraft(status="deferred")
        assert _guard_draft_editable(adapter, "chat1", draft) is True

    @pytest.mark.parametrize(
        "status",
        ["posted", "rejected", "approved", "scheduled", "failed", "superseded", "cancelled"],
    )
    def test_blocks_non_editable_statuses(self, status):
        adapter = _make_adapter()
        draft = FakeDraft(status=status)
        assert _guard_draft_editable(adapter, "chat1", draft) is False
        adapter.send_message.assert_called_once()
        msg_text = adapter.send_message.call_args[0][1].text
        assert status in msg_text


# ---------------------------------------------------------------------------
# Status guard integration in handlers
# ---------------------------------------------------------------------------


class TestEditMediaGuard:
    @patch("social_hook.bot.buttons._get_conn")
    @patch("social_hook.bot.buttons._send")
    def test_blocks_posted_draft(self, mock_send, mock_conn):
        draft = FakeDraft(status="posted", media_paths=["/tmp/img.png"])
        conn = MagicMock()
        mock_conn.return_value = conn

        with (
            patch("social_hook.db.get_draft", return_value=draft),
            patch("social_hook.bot.commands.set_chat_draft_context"),
        ):
            adapter = _make_adapter()
            btn_edit_media(adapter, "c1", "cb1", "draft_test123456", None)

        mock_send.assert_any_call(adapter, "c1", "Cannot edit media \u2014 draft is posted.")


class TestMediaRegenGuard:
    @patch("social_hook.bot.buttons._get_conn")
    @patch("social_hook.bot.buttons._send")
    def test_blocks_rejected_draft(self, mock_send, mock_conn):
        draft = FakeDraft(status="rejected")
        conn = MagicMock()
        mock_conn.return_value = conn

        with patch("social_hook.db.get_draft", return_value=draft):
            adapter = _make_adapter()
            btn_media_regen(adapter, "c1", "cb1", "draft_test123456", None)

        mock_send.assert_any_call(adapter, "c1", "Cannot edit media \u2014 draft is rejected.")


class TestMediaRemoveGuard:
    @patch("social_hook.bot.buttons._get_conn")
    @patch("social_hook.bot.buttons._send")
    def test_blocks_scheduled_draft(self, mock_send, mock_conn):
        draft = FakeDraft(status="scheduled")
        conn = MagicMock()
        mock_conn.return_value = conn

        with patch("social_hook.db.get_draft", return_value=draft):
            adapter = _make_adapter()
            btn_media_remove(adapter, "c1", "cb1", "draft_test123456", None)

        mock_send.assert_any_call(adapter, "c1", "Cannot edit media \u2014 draft is scheduled.")

    @patch("social_hook.bot.buttons._get_conn")
    @patch("social_hook.bot.buttons._send")
    def test_blocks_not_found(self, mock_send, mock_conn):
        conn = MagicMock()
        mock_conn.return_value = conn

        with patch("social_hook.db.get_draft", return_value=None):
            adapter = _make_adapter()
            btn_media_remove(adapter, "c1", "cb1", "draft_xyz", None)

        mock_send.assert_any_call(adapter, "c1", "Draft `draft_xyz` not found.")


# ---------------------------------------------------------------------------
# btn_media_retry tests
# ---------------------------------------------------------------------------


class TestMediaRetry:
    @patch("social_hook.bot.buttons._get_conn")
    @patch("social_hook.bot.buttons._send")
    def test_retry_bypasses_spec_guard_and_generates(self, mock_send, mock_conn):
        """media_retry should NOT check spec==spec_used, and should call generate()."""
        draft = FakeDraft(
            status="draft",
            media_spec={"type": "flowchart", "code": "A->B"},
            media_spec_used={"type": "flowchart", "code": "A->B"},  # same as spec
            media_paths=["/old/img.png"],
        )
        conn = MagicMock()
        mock_conn.return_value = conn

        mock_media_adapter = MagicMock()
        mock_media_adapter.generate.return_value = MediaResult(
            success=True, file_path="/new/img.png"
        )

        with (
            patch("social_hook.db.get_draft", return_value=draft),
            patch("social_hook.db.update_draft"),
            patch("social_hook.db.operations.insert_draft_change"),
            patch(
                "social_hook.adapters.registry.get_media_adapter",
                return_value=mock_media_adapter,
            ),
            patch("social_hook.filesystem.generate_id", return_value="change_abc"),
            patch(
                "social_hook.filesystem.get_base_path",
                return_value=MagicMock(
                    __truediv__=MagicMock(
                        return_value=MagicMock(
                            __truediv__=MagicMock(return_value="/tmp/cache/draft_test")
                        )
                    )
                ),
            ),
        ):
            adapter = _make_adapter()
            btn_media_retry(adapter, "c1", "cb1", "draft_test123456", None)

        mock_media_adapter.generate.assert_called_once()
        mock_send.assert_any_call(adapter, "c1", "Media retry succeeded.")

    @patch("social_hook.bot.buttons._get_conn")
    @patch("social_hook.bot.buttons._send")
    def test_retry_guard_blocks_posted(self, mock_send, mock_conn):
        draft = FakeDraft(status="posted")
        conn = MagicMock()
        mock_conn.return_value = conn

        with patch("social_hook.db.get_draft", return_value=draft):
            adapter = _make_adapter()
            btn_media_retry(adapter, "c1", "cb1", "draft_test123456", None)

        mock_send.assert_any_call(adapter, "c1", "Cannot edit media \u2014 draft is posted.")

    @patch("social_hook.bot.buttons._get_conn")
    @patch("social_hook.bot.buttons._send")
    def test_retry_no_spec(self, mock_send, mock_conn):
        draft = FakeDraft(status="draft", media_spec=None)
        conn = MagicMock()
        mock_conn.return_value = conn

        with patch("social_hook.db.get_draft", return_value=draft):
            adapter = _make_adapter()
            btn_media_retry(adapter, "c1", "cb1", "draft_test123456", None)

        mock_send.assert_any_call(adapter, "c1", "No media spec available for retry.")


# ---------------------------------------------------------------------------
# Guard allows draft/deferred through handlers
# ---------------------------------------------------------------------------


class TestGuardAllowsDraftDeferred:
    @patch("social_hook.bot.buttons._get_conn")
    @patch("social_hook.bot.buttons._send")
    def test_edit_media_allows_draft(self, mock_send, mock_conn):
        draft = FakeDraft(status="draft", media_paths=["/tmp/img.png"])
        conn = MagicMock()
        mock_conn.return_value = conn

        with (
            patch("social_hook.db.get_draft", return_value=draft),
            patch("social_hook.bot.commands.set_chat_draft_context"),
        ):
            adapter = _make_adapter()
            btn_edit_media(adapter, "c1", "cb1", "draft_test123456", None)

        for call in mock_send.call_args_list:
            assert "Cannot edit media" not in str(call)

    @patch("social_hook.bot.buttons._get_conn")
    @patch("social_hook.bot.buttons._send")
    def test_edit_media_allows_deferred(self, mock_send, mock_conn):
        draft = FakeDraft(status="deferred", media_paths=["/tmp/img.png"])
        conn = MagicMock()
        mock_conn.return_value = conn

        with (
            patch("social_hook.db.get_draft", return_value=draft),
            patch("social_hook.bot.commands.set_chat_draft_context"),
        ):
            adapter = _make_adapter()
            btn_edit_media(adapter, "c1", "cb1", "draft_test123456", None)

        for call in mock_send.call_args_list:
            assert "Cannot edit media" not in str(call)


# ---------------------------------------------------------------------------
# btn_post_now tests
# ---------------------------------------------------------------------------


class TestBtnPostNow:
    @patch("social_hook.bot.buttons._get_conn")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._send")
    def test_post_now_preview_blocked(self, mock_send, mock_answer, mock_conn):
        """Post Now should reject preview drafts."""
        draft = MagicMock()
        draft.id = "draft_123"
        draft.status = "draft"
        draft.platform = "preview"
        draft.project_id = "proj_1"

        conn = MagicMock()
        mock_conn.return_value = conn

        with (
            patch("social_hook.db.get_draft", return_value=draft),
            patch("social_hook.bot.commands.set_chat_draft_context"),
        ):
            btn_post_now(MagicMock(), "chat1", "cb1", "draft_123", None)

        mock_send.assert_called_once()
        assert "preview" in mock_send.call_args[0][2].lower()

    @patch("social_hook.bot.buttons._get_conn")
    @patch("social_hook.bot.buttons._answer_callback")
    @patch("social_hook.bot.buttons._send")
    def test_post_now_wrong_status(self, mock_send, mock_answer, mock_conn):
        """Post Now should reject terminal status drafts."""
        draft = MagicMock()
        draft.id = "draft_123"
        draft.status = "posted"
        draft.platform = "x"
        draft.project_id = "proj_1"

        conn = MagicMock()
        mock_conn.return_value = conn

        with (
            patch("social_hook.db.get_draft", return_value=draft),
            patch("social_hook.bot.commands.set_chat_draft_context"),
        ):
            btn_post_now(MagicMock(), "chat1", "cb1", "draft_123", None)

        mock_send.assert_called_once()
        assert (
            "cannot" in mock_send.call_args[0][2].lower()
            or "status" in mock_send.call_args[0][2].lower()
        )

    def test_post_now_in_dispatch_map(self):
        """post_now should be in the button dispatch map."""
        import inspect

        from social_hook.bot.buttons import handle_callback

        source = inspect.getsource(handle_callback)
        assert '"post_now"' in source or "'post_now'" in source
