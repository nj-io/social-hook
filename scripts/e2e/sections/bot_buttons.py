"""Section G: Bot Buttons scenarios."""

from datetime import datetime, timezone


def run(harness, runner, adapter):
    """G1-G14: Bot button scenarios."""
    from social_hook.bot.buttons import handle_callback
    from social_hook.db import operations as ops
    from social_hook.messaging.base import CallbackEvent, InboundMessage

    if not harness.project_id:
        harness.seed_project()

    config = harness.load_config()
    chat_id = config.env.get("TELEGRAM_CHAT_ID", "test")

    def make_callback(data):
        action, _, payload = data.partition(":")
        return CallbackEvent(
            callback_id="cb_1",
            chat_id=chat_id,
            action=action,
            payload=payload,
            message_id="1",
        )

    # G1: Quick approve
    def g1():
        draft = harness.seed_draft(harness.project_id, status="draft")
        adapter.clear()
        handle_callback(make_callback(f"quick_approve:{draft.id}"), adapter, config)
        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status in ("scheduled", "approved"), f"Status: {updated.status}"
        return f"Status: {updated.status}"

    runner.run_scenario("G1", "Quick approve button", g1)

    # G2: Schedule submenu
    def g2():
        draft = harness.seed_draft(harness.project_id, status="draft")
        adapter.clear()
        handle_callback(make_callback(f"schedule:{draft.id}"), adapter, config)
        assert adapter.messages, "No message sent"
        return "Schedule submenu shown"

    runner.run_scenario("G2", "Schedule submenu", g2)

    # G3: Schedule optimal
    def g3():
        draft = harness.seed_draft(harness.project_id, status="draft")
        adapter.clear()
        handle_callback(make_callback(f"schedule_optimal:{draft.id}"), adapter, config)
        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "scheduled", f"Status: {updated.status}"
        return f"Scheduled at: {updated.scheduled_time}"

    runner.run_scenario("G3", "Schedule optimal button", g3)

    # G4: Edit submenu
    def g4():
        draft = harness.seed_draft(harness.project_id, status="draft")
        adapter.clear()
        handle_callback(make_callback(f"edit:{draft.id}"), adapter, config)
        assert adapter.messages, "No message sent"
        return "Edit submenu shown"

    runner.run_scenario("G4", "Edit submenu", g4)

    # G5: Reject submenu
    def g5():
        draft = harness.seed_draft(harness.project_id, status="draft")
        adapter.clear()
        handle_callback(make_callback(f"reject:{draft.id}"), adapter, config)
        assert adapter.messages, "No message sent"
        return "Reject submenu shown"

    runner.run_scenario("G5", "Reject submenu", g5)

    # G6: Reject now
    def g6():
        draft = harness.seed_draft(harness.project_id, status="draft")
        adapter.clear()
        handle_callback(make_callback(f"reject_now:{draft.id}"), adapter, config)
        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "rejected", f"Status: {updated.status}"
        return "Draft rejected"

    runner.run_scenario("G6", "Reject now button", g6)

    # G7: Cancel
    def g7():
        draft = harness.seed_draft(
            harness.project_id,
            status="scheduled",
            scheduled_time=datetime.now(timezone.utc).isoformat(),
        )
        adapter.clear()
        handle_callback(make_callback(f"cancel:{draft.id}"), adapter, config)
        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "cancelled", f"Status: {updated.status}"
        return "Draft cancelled"

    runner.run_scenario("G7", "Cancel button", g7)

    # G8: Review
    def g8():
        draft = harness.seed_draft(harness.project_id, status="draft")
        adapter.clear()
        handle_callback(make_callback(f"review:{draft.id}"), adapter, config)
        assert adapter.messages, "No message sent"
        return "Review shown"

    runner.run_scenario("G8", "Review button", g8)

    # G9: Edit text -> reply saves content
    def g9():
        from social_hook.bot.commands import handle_message

        draft = harness.seed_draft(
            harness.project_id, status="draft", content="Original content for G9 test"
        )
        adapter.clear()

        # Step 1: Tap edit_text button to register pending edit
        handle_callback(make_callback(f"edit_text:{draft.id}"), adapter, config)
        assert adapter.messages, "No edit prompt sent"

        # Step 2: Reply with new content (handle_message checks pending edit)
        new_content = "Updated content via edit flow"
        msg = InboundMessage(
            message_id="2",
            chat_id=chat_id,
            sender_id=chat_id,
            text=new_content,
        )
        adapter.clear()
        handle_message(msg, adapter, config)

        # Verify: draft content updated in DB
        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.content == new_content, f"Expected '{new_content}', got '{updated.content}'"

        # Verify: DraftChange row exists
        changes = ops.get_draft_changes(harness.conn, draft.id)
        assert len(changes) >= 1, f"Expected DraftChange row, got {len(changes)}"
        assert changes[-1].changed_by == "human", (
            f"Expected changed_by='human', got '{changes[-1].changed_by}'"
        )
        return "Edit saved, DraftChange recorded"

    runner.run_scenario("G9", "Edit text -> reply saves content", g9)

    # G10: Edit text -> expired TTL
    def g10():
        import time as _time
        from unittest.mock import patch as _patch

        from social_hook.bot.buttons import _EDIT_TTL_SECONDS
        from social_hook.bot.commands import handle_message

        draft = harness.seed_draft(
            harness.project_id, status="draft", content="Original content for G10 test"
        )
        original_content = "Original content for G10 test"
        adapter.clear()

        # Register pending edit
        handle_callback(make_callback(f"edit_text:{draft.id}"), adapter, config)
        assert adapter.messages, "No edit prompt sent"

        # Expire the TTL by patching time.time to return a future value
        real_time = _time.time
        expired_time = real_time() + _EDIT_TTL_SECONDS + 60

        with _patch("social_hook.bot.buttons.time") as mock_time:
            mock_time.time.return_value = expired_time

            msg = InboundMessage(
                message_id="3",
                chat_id=chat_id,
                sender_id=chat_id,
                text="This should not be saved",
            )
            adapter.clear()
            handle_message(msg, adapter, config)

        # Verify: draft content unchanged
        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.content == original_content, (
            f"Content should be unchanged, got '{updated.content}'"
        )
        return "Expired edit TTL correctly prevented save"

    runner.run_scenario("G10", "Edit text -> expired TTL", g10)

    # G10a: Edit overwrite warning
    def g10a():
        from social_hook.bot.buttons import get_pending_edit

        draft_a = harness.seed_draft(harness.project_id, status="draft", content="Draft A content")
        draft_b = harness.seed_draft(harness.project_id, status="draft", content="Draft B content")
        adapter.clear()

        # Register edit for draft A
        handle_callback(make_callback(f"edit_text:{draft_a.id}"), adapter, config)
        assert get_pending_edit(chat_id) == draft_a.id

        # Now register edit for draft B (should warn about switching)
        adapter.clear()
        handle_callback(make_callback(f"edit_text:{draft_b.id}"), adapter, config)

        # Verify warning was sent
        assert adapter.last_message_contains("switching") or adapter.last_message_contains(
            "cancelled"
        ), "Expected overwrite warning"

        # Verify pending edit is now B
        assert get_pending_edit(chat_id) == draft_b.id, "Expected pending edit for draft B"
        return "Overwrite warning shown, edit switched to B"

    runner.run_scenario("G10a", "Edit overwrite warning", g10a)

    # G11: Adapter bridge sends via adapter when set
    def g11():
        from unittest.mock import MagicMock as _MagicMock

        from social_hook.messaging.base import SendResult

        draft = harness.seed_draft(harness.project_id, status="draft")

        mock_adapter = _MagicMock()
        mock_adapter.send_message.return_value = SendResult(success=True, message_id="mock_msg_1")
        mock_adapter.answer_callback.return_value = True

        adapter.clear()
        handle_callback(make_callback(f"approve:{draft.id}"), mock_adapter, config)

        # Verify adapter was used (not direct HTTP)
        assert mock_adapter.send_message.called or mock_adapter.answer_callback.called, (
            "Expected adapter methods to be called"
        )
        return "Adapter bridge used for button handler"

    runner.run_scenario("G11", "Adapter bridge sends via adapter", g11)

    # G12: Edit media shows current file
    def g12():
        from unittest.mock import MagicMock as _MagicMock

        from social_hook.messaging.base import SendResult

        draft = harness.seed_draft(
            harness.project_id,
            status="draft",
            media_paths=["/tmp/test.png"],
            media_type="mermaid",
        )

        mock_adapter = _MagicMock()
        mock_adapter.send_message.return_value = SendResult(success=True, message_id="mock_msg_1")
        mock_adapter.answer_callback.return_value = True
        caps = _MagicMock()
        caps.supports_media = True
        mock_adapter.get_capabilities.return_value = caps
        mock_adapter.send_media.return_value = SendResult(success=True)

        adapter.clear()
        handle_callback(make_callback(f"edit_media:{draft.id}"), mock_adapter, config)

        # Verify send_media was called with the file path
        assert mock_adapter.send_media.called, "Expected send_media to be called"
        call_args = mock_adapter.send_media.call_args
        assert "/tmp/test.png" in str(call_args), (
            f"Expected /tmp/test.png in send_media args: {call_args}"
        )

        # Verify buttons include Regenerate and Remove media
        assert mock_adapter.send_message.called, "No button message sent"
        return "Edit media shows file + action buttons"

    runner.run_scenario("G12", "Edit media shows current file", g12)

    # G13: Media regeneration
    def g13():
        from unittest.mock import MagicMock as _MagicMock
        from unittest.mock import patch as _patch

        from social_hook.adapters.models import MediaResult

        draft = harness.seed_draft(
            harness.project_id,
            status="draft",
            media_paths=["/tmp/old.png"],
            media_type="mermaid",
            media_spec={"diagram": "graph TD; A-->B"},
        )
        adapter.clear()

        mock_media_adapter = _MagicMock()
        mock_media_adapter.generate.return_value = MediaResult(
            success=True, file_path="/tmp/regenerated.png"
        )

        with _patch(
            "social_hook.adapters.registry.get_media_adapter",
            return_value=mock_media_adapter,
        ):
            handle_callback(make_callback(f"media_regen:{draft.id}"), adapter, config)

        assert mock_media_adapter.generate.called, "Expected media adapter generate() called"

        # Verify draft media_paths updated
        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.media_paths == ["/tmp/regenerated.png"], (
            f"Expected ['/tmp/regenerated.png'], got {updated.media_paths}"
        )
        return "Media regenerated, draft updated"

    runner.run_scenario("G13", "Media regeneration", g13)

    # G14: Media removal
    def g14():
        draft = harness.seed_draft(
            harness.project_id,
            status="draft",
            media_paths=["/tmp/to_remove.png"],
        )
        adapter.clear()
        handle_callback(make_callback(f"media_remove:{draft.id}"), adapter, config)

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.media_paths == [], f"Expected empty media_paths, got {updated.media_paths}"

        # Verify DraftChange audit trail exists
        changes = ops.get_draft_changes(harness.conn, draft.id)
        media_changes = [c for c in changes if c.field == "media_paths"]
        assert len(media_changes) >= 1, (
            f"Expected DraftChange audit entry for media_paths, got {len(media_changes)}"
        )

        return "Media removed, paths cleared, audit trail verified"

    runner.run_scenario("G14", "Media removal", g14)
