"""Tests for the messaging platform abstraction base types."""

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
        row = ButtonRow(buttons=[
            Button(label="A", action="a"),
            Button(label="B", action="b"),
        ])
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

    def test_custom_values(self):
        caps = PlatformCapabilities(
            max_message_length=40000,
            supports_html=False,
            button_text_max_length=75,
        )
        assert caps.max_message_length == 40000
        assert caps.supports_html is False
        assert caps.button_text_max_length == 75


class TestMessagingAdapterABC:
    def test_cannot_instantiate(self):
        """MessagingAdapter is abstract and cannot be instantiated directly."""
        with pytest.raises(TypeError):
            MessagingAdapter()

    def test_incomplete_subclass_raises(self):
        """A subclass that doesn't implement all abstract methods can't be instantiated."""

        class PartialAdapter(MessagingAdapter):
            platform = "test"

            def send_message(self, chat_id, message):
                pass

        with pytest.raises(TypeError):
            PartialAdapter()

    def test_complete_subclass_works(self):
        """A subclass that implements all abstract methods can be instantiated."""

        class FakeAdapter(MessagingAdapter):
            platform = "fake"

            def send_message(self, chat_id, message):
                return SendResult(success=True, message_id="1")

            def edit_message(self, chat_id, message_id, message):
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
