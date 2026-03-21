"""Tests for the messaging platform abstraction base types and Template Method."""

import pytest

from social_hook.messaging.base import (
    Button,
    ButtonRow,
    CallbackEvent,
    InboundMessage,
    MessagingAdapter,
    OutboundMessage,
    PlatformCapabilities,
    SendResult,
)

# --- Stub adapters for Template Method tests ---


class StubAdapter(MessagingAdapter):
    """Minimal adapter for testing base class behavior."""

    platform = "stub"

    def __init__(self):
        self.send_calls: list[OutboundMessage] = []
        self.edit_calls: list[tuple[str, OutboundMessage]] = []
        self.media_calls: list[tuple[str, str, str]] = []
        self._next_results: list[SendResult] = []

    def queue_result(self, result: SendResult):
        self._next_results.append(result)

    def _do_send_message(self, chat_id, message):
        self.send_calls.append(message)
        return self._next_results.pop(0) if self._next_results else SendResult(success=True)

    def _do_edit_message(self, chat_id, message_id, message):
        self.edit_calls.append((message_id, message))
        return self._next_results.pop(0) if self._next_results else SendResult(success=True)

    def _do_send_media(self, chat_id, file_path, caption="", parse_mode="markdown"):
        self.media_calls.append((file_path, caption, parse_mode))
        return self._next_results.pop(0) if self._next_results else SendResult(success=True)

    def answer_callback(self, callback_id, text=""):
        return True

    def get_capabilities(self):
        return PlatformCapabilities()


class SanitizingAdapter(StubAdapter):
    """Adapter that uppercases text as sanitization (for testing)."""

    platform = "sanitizing"

    def sanitize_text(self, text, parse_mode):
        if parse_mode == "markdown":
            return text.upper()
        return text

    def _is_format_error(self, result):
        return result.error == "format_error"


class TestButton:
    def test_basic_construction(self):
        btn = Button(label="Approve", action="approve")
        assert btn.label == "Approve"
        assert btn.action == "approve"
        assert btn.payload == ""

    def test_with_payload(self):
        btn = Button(label="Approve", action="approve", payload="draft_123")
        assert btn.payload == "draft_123"


class TestButtonRow:
    def test_construction(self):
        row = ButtonRow(
            buttons=[
                Button(label="A", action="a"),
                Button(label="B", action="b"),
            ]
        )
        assert len(row.buttons) == 2
        assert row.buttons[0].label == "A"
        assert row.buttons[1].label == "B"


class TestOutboundMessage:
    def test_defaults(self):
        msg = OutboundMessage(text="Hello")
        assert msg.text == "Hello"
        assert msg.parse_mode == "markdown"
        assert msg.buttons == []

    def test_with_buttons(self):
        btn = Button(label="OK", action="ok")
        row = ButtonRow(buttons=[btn])
        msg = OutboundMessage(text="Choose", buttons=[row])
        assert len(msg.buttons) == 1
        assert msg.buttons[0].buttons[0].label == "OK"

    def test_button_composition(self):
        """Button -> ButtonRow -> OutboundMessage full composition."""
        approve = Button(label="Approve", action="approve", payload="d1")
        reject = Button(label="Reject", action="reject", payload="d1")
        row1 = ButtonRow(buttons=[approve, reject])

        edit = Button(label="Edit", action="edit", payload="d1")
        row2 = ButtonRow(buttons=[edit])

        msg = OutboundMessage(text="Review draft", buttons=[row1, row2])
        assert len(msg.buttons) == 2
        assert len(msg.buttons[0].buttons) == 2
        assert len(msg.buttons[1].buttons) == 1
        assert msg.buttons[0].buttons[0].action == "approve"
        assert msg.buttons[1].buttons[0].action == "edit"

    def test_default_factory_independence(self):
        """Each OutboundMessage gets its own buttons list."""
        msg1 = OutboundMessage(text="A")
        msg2 = OutboundMessage(text="B")
        msg1.buttons.append(ButtonRow(buttons=[Button(label="X", action="x")]))
        assert msg2.buttons == []


class TestSendResult:
    def test_success(self):
        result = SendResult(success=True, message_id="msg_42")
        assert result.success is True
        assert result.message_id == "msg_42"
        assert result.error is None
        assert result.raw is None

    def test_failure(self):
        result = SendResult(success=False, error="Rate limited")
        assert result.success is False
        assert result.message_id is None
        assert result.error == "Rate limited"

    def test_with_raw(self):
        raw_response = {"ok": True, "result": {"message_id": 99}}
        result = SendResult(success=True, message_id="99", raw=raw_response)
        assert result.raw["ok"] is True


class TestInboundMessage:
    def test_required_fields(self):
        msg = InboundMessage(chat_id="123", text="hello")
        assert msg.chat_id == "123"
        assert msg.text == "hello"
        assert msg.sender_id is None
        assert msg.sender_name is None
        assert msg.message_id is None
        assert msg.raw is None

    def test_all_fields(self):
        raw = {"message_id": 1, "text": "hi"}
        msg = InboundMessage(
            chat_id="123",
            text="hi",
            sender_id="456",
            sender_name="Alice",
            message_id="1",
            raw=raw,
        )
        assert msg.sender_id == "456"
        assert msg.sender_name == "Alice"
        assert msg.message_id == "1"
        assert msg.raw is raw


class TestCallbackEvent:
    def test_required_fields(self):
        cb = CallbackEvent(
            chat_id="123",
            callback_id="cb_1",
            action="approve",
            payload="draft_abc",
        )
        assert cb.chat_id == "123"
        assert cb.callback_id == "cb_1"
        assert cb.action == "approve"
        assert cb.payload == "draft_abc"
        assert cb.message_id is None
        assert cb.raw is None

    def test_all_fields(self):
        raw = {"id": "cb_1", "data": "approve:draft_abc"}
        cb = CallbackEvent(
            chat_id="123",
            callback_id="cb_1",
            action="approve",
            payload="draft_abc",
            message_id="msg_5",
            raw=raw,
        )
        assert cb.message_id == "msg_5"
        assert cb.raw is raw


class TestPlatformCapabilities:
    def test_defaults(self):
        caps = PlatformCapabilities()
        assert caps.max_message_length == 4096
        assert caps.supports_buttons is True
        assert caps.supports_inline_buttons is True
        assert caps.supports_message_editing is True
        assert caps.supports_markdown is True
        assert caps.supports_html is True
        assert caps.button_text_max_length == 64
        assert caps.supports_media is True
        assert caps.max_media_per_message == 4
        assert caps.supported_media_types == ["png", "jpg", "jpeg", "gif"]

    def test_custom_values(self):
        caps = PlatformCapabilities(
            max_message_length=40000,
            supports_html=False,
            button_text_max_length=75,
            supports_media=False,
            max_media_per_message=1,
            supported_media_types=["png"],
        )
        assert caps.max_message_length == 40000
        assert caps.supports_html is False
        assert caps.button_text_max_length == 75
        assert caps.supports_media is False
        assert caps.max_media_per_message == 1
        assert caps.supported_media_types == ["png"]

    def test_supported_media_types_default_factory_independence(self):
        """Each PlatformCapabilities gets its own supported_media_types list."""
        caps1 = PlatformCapabilities()
        caps2 = PlatformCapabilities()
        caps1.supported_media_types.append("webp")
        assert "webp" not in caps2.supported_media_types


class TestMessagingAdapterABC:
    def test_cannot_instantiate(self):
        """MessagingAdapter is abstract and cannot be instantiated directly."""
        with pytest.raises(TypeError):
            MessagingAdapter()

    def test_incomplete_subclass_raises(self):
        """A subclass that doesn't implement all abstract methods can't be instantiated."""

        class PartialAdapter(MessagingAdapter):
            platform = "test"

            def _do_send_message(self, chat_id, message):
                pass

        with pytest.raises(TypeError):
            PartialAdapter()

    def test_complete_subclass_works(self):
        """A subclass that implements all abstract methods can be instantiated."""

        class FakeAdapter(MessagingAdapter):
            platform = "fake"

            def _do_send_message(self, chat_id, message):
                return SendResult(success=True, message_id="1")

            def _do_edit_message(self, chat_id, message_id, message):
                return SendResult(success=True)

            def answer_callback(self, callback_id, text=""):
                return True

            def get_capabilities(self):
                return PlatformCapabilities()

        adapter = FakeAdapter()
        assert adapter.platform == "fake"
        result = adapter.send_message("123", OutboundMessage(text="hi"))
        assert result.success is True
        assert adapter.get_capabilities().max_message_length == 4096

    def test_base_send_media_default_returns_failure(self):
        """Default _do_send_media() returns SendResult(success=False)."""

        class MinimalAdapter(MessagingAdapter):
            platform = "minimal"

            def _do_send_message(self, chat_id, message):
                return SendResult(success=True)

            def _do_edit_message(self, chat_id, message_id, message):
                return SendResult(success=True)

            def answer_callback(self, callback_id, text=""):
                return True

            def get_capabilities(self):
                return PlatformCapabilities()

        adapter = MinimalAdapter()
        result = adapter.send_media("123", "/some/file.png")
        assert result.success is False
        assert "minimal" in result.error
        assert "does not support media uploads" in result.error


# --- Template Method tests ---


class TestTemplateMethodPassthrough:
    def test_send_passes_through(self):
        adapter = StubAdapter()
        result = adapter.send_message("chat1", OutboundMessage(text="hello"))
        assert result.success
        assert adapter.send_calls[0].text == "hello"

    def test_edit_passes_through(self):
        adapter = StubAdapter()
        result = adapter.edit_message("chat1", "msg1", OutboundMessage(text="updated"))
        assert result.success
        assert adapter.edit_calls[0][1].text == "updated"

    def test_media_passes_through(self):
        adapter = StubAdapter()
        result = adapter.send_media("chat1", "/img.png", caption="cap")
        assert result.success
        assert adapter.media_calls[0] == ("/img.png", "cap", "markdown")

    def test_no_retry_on_failure_without_format_error(self):
        adapter = StubAdapter()
        adapter.queue_result(SendResult(success=False, error="network"))
        result = adapter.send_message("chat1", OutboundMessage(text="hi"))
        assert not result.success
        assert len(adapter.send_calls) == 1


class TestTemplateMethodSanitization:
    def test_send_sanitizes_text(self):
        adapter = SanitizingAdapter()
        adapter.send_message("chat1", OutboundMessage(text="hello"))
        assert adapter.send_calls[0].text == "HELLO"

    def test_edit_sanitizes_text(self):
        adapter = SanitizingAdapter()
        adapter.edit_message("chat1", "msg1", OutboundMessage(text="hello"))
        assert adapter.edit_calls[0][1].text == "HELLO"

    def test_media_sanitizes_caption(self):
        adapter = SanitizingAdapter()
        adapter.send_media("chat1", "/img.png", caption="hello")
        assert adapter.media_calls[0][1] == "HELLO"

    def test_no_sanitize_for_plain(self):
        adapter = SanitizingAdapter()
        adapter.send_message("chat1", OutboundMessage(text="hello", parse_mode="plain"))
        assert adapter.send_calls[0].text == "hello"

    def test_empty_caption_not_sanitized(self):
        adapter = SanitizingAdapter()
        adapter.send_media("chat1", "/img.png", caption="")
        assert adapter.media_calls[0][1] == ""


class TestTemplateMethodFormatRetry:
    def test_retries_as_plain_on_format_error(self):
        adapter = SanitizingAdapter()
        adapter.queue_result(SendResult(success=False, error="format_error"))
        adapter.queue_result(SendResult(success=True, message_id="2"))
        result = adapter.send_message("chat1", OutboundMessage(text="hello"))
        assert result.success
        assert len(adapter.send_calls) == 2
        assert adapter.send_calls[0].text == "HELLO"  # Sanitized
        assert adapter.send_calls[0].parse_mode == "markdown"
        assert adapter.send_calls[1].text == "hello"  # Original, unsanitized
        assert adapter.send_calls[1].parse_mode == "plain"

    def test_no_retry_for_non_format_error(self):
        adapter = SanitizingAdapter()
        adapter.queue_result(SendResult(success=False, error="network_timeout"))
        result = adapter.send_message("chat1", OutboundMessage(text="hello"))
        assert not result.success
        assert len(adapter.send_calls) == 1

    def test_no_retry_when_already_plain(self):
        adapter = SanitizingAdapter()
        adapter.queue_result(SendResult(success=False, error="format_error"))
        result = adapter.send_message("chat1", OutboundMessage(text="hello", parse_mode="plain"))
        assert not result.success
        assert len(adapter.send_calls) == 1

    def test_edit_retries_on_format_error(self):
        adapter = SanitizingAdapter()
        adapter.queue_result(SendResult(success=False, error="format_error"))
        adapter.queue_result(SendResult(success=True))
        result = adapter.edit_message("chat1", "msg1", OutboundMessage(text="hello"))
        assert result.success
        assert len(adapter.edit_calls) == 2
        assert adapter.edit_calls[1][1].parse_mode == "plain"

    def test_media_retries_on_format_error(self):
        adapter = SanitizingAdapter()
        adapter.queue_result(SendResult(success=False, error="format_error"))
        adapter.queue_result(SendResult(success=True))
        result = adapter.send_media("chat1", "/img.png", caption="hello")
        assert result.success
        assert len(adapter.media_calls) == 2
        assert adapter.media_calls[0][1] == "HELLO"  # Sanitized caption
        assert adapter.media_calls[1][1] == "hello"  # Original caption
        assert adapter.media_calls[1][2] == "plain"  # Plain parse_mode

    def test_retry_preserves_buttons(self):
        adapter = SanitizingAdapter()
        adapter.queue_result(SendResult(success=False, error="format_error"))
        adapter.queue_result(SendResult(success=True))
        buttons = [ButtonRow(buttons=[Button(label="OK", action="ok")])]
        adapter.send_message("chat1", OutboundMessage(text="hi", buttons=buttons))
        assert adapter.send_calls[1].buttons == buttons
