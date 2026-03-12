"""Tests for the Telegram messaging adapter."""

from unittest.mock import MagicMock, patch

import pytest

from social_hook.messaging.base import (
    Button,
    ButtonRow,
    CallbackEvent,
    InboundMessage,
    OutboundMessage,
    PlatformCapabilities,
)
from social_hook.messaging.telegram import TelegramAdapter


@pytest.fixture
def adapter():
    return TelegramAdapter(token="test_token_123")


class TestSendMessage:
    def test_plain_message(self, adapter):
        """Send a plain text message without buttons."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ok": True,
            "result": {"message_id": 42},
        }

        with patch(
            "social_hook.messaging.telegram.requests.post", return_value=mock_response
        ) as mock_post:
            result = adapter.send_message("123", OutboundMessage(text="Hello"))

        assert result.success is True
        assert result.message_id == "42"

        call_args = mock_post.call_args
        assert call_args[0][0] == "https://api.telegram.org/bottest_token_123/sendMessage"
        payload = call_args[1]["json"]
        assert payload["chat_id"] == "123"
        assert payload["text"] == "Hello"
        assert payload["parse_mode"] == "Markdown"
        assert "reply_markup" not in payload

    def test_message_with_buttons(self, adapter):
        """Send a message with inline keyboard buttons."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ok": True,
            "result": {"message_id": 43},
        }

        msg = OutboundMessage(
            text="Review",
            buttons=[
                ButtonRow(
                    buttons=[
                        Button(label="Approve", action="approve", payload="d1"),
                        Button(label="Reject", action="reject", payload="d1"),
                    ]
                ),
            ],
        )

        with patch(
            "social_hook.messaging.telegram.requests.post", return_value=mock_response
        ) as mock_post:
            result = adapter.send_message("123", msg)

        assert result.success is True
        payload = mock_post.call_args[1]["json"]
        keyboard = payload["reply_markup"]["inline_keyboard"]
        assert len(keyboard) == 1
        assert len(keyboard[0]) == 2
        assert keyboard[0][0] == {"text": "Approve", "callback_data": "approve:d1"}
        assert keyboard[0][1] == {"text": "Reject", "callback_data": "reject:d1"}

    def test_html_parse_mode(self, adapter):
        """Verify parse_mode mapping for HTML."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "result": {"message_id": 1}}

        with patch(
            "social_hook.messaging.telegram.requests.post", return_value=mock_response
        ) as mock_post:
            adapter.send_message("123", OutboundMessage(text="<b>Bold</b>", parse_mode="html"))

        payload = mock_post.call_args[1]["json"]
        assert payload["parse_mode"] == "HTML"

    def test_send_failure_http_error(self, adapter):
        """HTTP error returns SendResult with success=False."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.side_effect = ValueError("No JSON")
        mock_response.text = "Bad Request"

        with patch("social_hook.messaging.telegram.requests.post", return_value=mock_response):
            result = adapter.send_message("123", OutboundMessage(text="fail"))

        assert result.success is False
        assert result.error == "HTTP 400"
        assert result.raw == "Bad Request"

    def test_send_failure_telegram_ok_false(self, adapter):
        """HTTP 200 + {"ok": false} returns SendResult with success=False."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ok": False,
            "error_code": 400,
            "description": "Bad Request: can't parse entities",
        }

        with patch("social_hook.messaging.telegram.requests.post", return_value=mock_response):
            result = adapter.send_message("123", OutboundMessage(text="bad *markdown"))

        assert result.success is False
        assert "can't parse entities" in result.error
        assert result.raw["ok"] is False

    def test_send_failure_exception(self, adapter):
        """Network exception returns SendResult with success=False."""
        import requests as req

        with patch(
            "social_hook.messaging.telegram.requests.post",
            side_effect=req.ConnectionError("timeout"),
        ):
            result = adapter.send_message("123", OutboundMessage(text="fail"))

        assert result.success is False
        assert "timeout" in result.error


class TestEditMessage:
    def test_edit_message(self, adapter):
        """Edit an existing message."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ok": True,
            "result": {"message_id": 42},
        }

        with patch(
            "social_hook.messaging.telegram.requests.post", return_value=mock_response
        ) as mock_post:
            result = adapter.edit_message("123", "42", OutboundMessage(text="Updated"))

        assert result.success is True
        call_args = mock_post.call_args
        assert "editMessageText" in call_args[0][0]
        payload = call_args[1]["json"]
        assert payload["chat_id"] == "123"
        assert payload["message_id"] == "42"
        assert payload["text"] == "Updated"

    def test_edit_with_buttons(self, adapter):
        """Edit a message and update its buttons."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "result": {"message_id": 42}}

        msg = OutboundMessage(
            text="Updated",
            buttons=[ButtonRow(buttons=[Button(label="OK", action="ok")])],
        )

        with patch(
            "social_hook.messaging.telegram.requests.post", return_value=mock_response
        ) as mock_post:
            adapter.edit_message("123", "42", msg)

        payload = mock_post.call_args[1]["json"]
        assert "reply_markup" in payload
        keyboard = payload["reply_markup"]["inline_keyboard"]
        assert keyboard[0][0] == {"text": "OK", "callback_data": "ok"}

    def test_edit_message_removes_buttons_when_empty(self, adapter):
        """Edit message with no buttons should send empty inline_keyboard to clear them."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "result": {"message_id": 42}}

        with patch(
            "social_hook.messaging.telegram.requests.post", return_value=mock_response
        ) as mock_post:
            adapter.edit_message("123", "42", OutboundMessage(text="Status update"))

        payload = mock_post.call_args[1]["json"]
        assert payload["reply_markup"] == {"inline_keyboard": []}


class TestAnswerCallback:
    def test_answer_callback(self, adapter):
        """Acknowledge a callback query."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "result": True}

        with patch(
            "social_hook.messaging.telegram.requests.post", return_value=mock_response
        ) as mock_post:
            ok = adapter.answer_callback("cb_123", text="Done")

        assert ok is True
        call_args = mock_post.call_args
        assert "answerCallbackQuery" in call_args[0][0]
        payload = call_args[1]["json"]
        assert payload["callback_query_id"] == "cb_123"
        assert payload["text"] == "Done"

    def test_answer_callback_no_text(self, adapter):
        """Acknowledge without text doesn't include text field."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "result": True}

        with patch(
            "social_hook.messaging.telegram.requests.post", return_value=mock_response
        ) as mock_post:
            adapter.answer_callback("cb_123")

        payload = mock_post.call_args[1]["json"]
        assert "text" not in payload

    def test_answer_callback_failure(self, adapter):
        """Failed callback returns False."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"

        with patch("social_hook.messaging.telegram.requests.post", return_value=mock_response):
            ok = adapter.answer_callback("cb_123")

        assert ok is False


class TestButtonsToTelegram:
    def test_single_row(self, adapter):
        """Convert a single button row."""
        rows = [
            ButtonRow(
                buttons=[
                    Button(label="A", action="act_a", payload="p1"),
                    Button(label="B", action="act_b", payload="p2"),
                ]
            )
        ]
        result = adapter._buttons_to_telegram(rows)
        assert result == [
            [
                {"text": "A", "callback_data": "act_a:p1"},
                {"text": "B", "callback_data": "act_b:p2"},
            ]
        ]

    def test_multiple_rows(self, adapter):
        """Convert multiple button rows."""
        rows = [
            ButtonRow(buttons=[Button(label="X", action="x", payload="1")]),
            ButtonRow(buttons=[Button(label="Y", action="y", payload="2")]),
        ]
        result = adapter._buttons_to_telegram(rows)
        assert len(result) == 2
        assert result[0][0]["callback_data"] == "x:1"
        assert result[1][0]["callback_data"] == "y:2"

    def test_button_without_payload(self, adapter):
        """Button with no payload uses action only as callback_data."""
        rows = [ButtonRow(buttons=[Button(label="Cancel", action="cancel")])]
        result = adapter._buttons_to_telegram(rows)
        assert result[0][0]["callback_data"] == "cancel"

    def test_empty_rows(self, adapter):
        """Empty row list returns empty list."""
        assert adapter._buttons_to_telegram([]) == []


class TestParseCallback:
    def test_parse_callback(self):
        """Parse a Telegram callback_query dict into CallbackEvent."""
        callback = {
            "id": "cb_999",
            "data": "approve:draft_abc123",
            "message": {
                "message_id": 42,
                "chat": {"id": 12345},
            },
        }
        event = TelegramAdapter.parse_callback(callback)
        assert isinstance(event, CallbackEvent)
        assert event.chat_id == "12345"
        assert event.callback_id == "cb_999"
        assert event.action == "approve"
        assert event.payload == "draft_abc123"
        assert event.message_id == "42"
        assert event.raw is callback

    def test_parse_callback_no_payload(self):
        """Parse callback with action only (no colon separator)."""
        callback = {
            "id": "cb_1",
            "data": "cancel",
            "message": {"message_id": 1, "chat": {"id": 100}},
        }
        event = TelegramAdapter.parse_callback(callback)
        assert event.action == "cancel"
        assert event.payload == ""

    def test_parse_callback_empty(self):
        """Parse callback with missing fields gracefully."""
        event = TelegramAdapter.parse_callback({})
        assert event.chat_id == ""
        assert event.callback_id == ""
        assert event.action == ""
        assert event.payload == ""


class TestParseMessage:
    def test_parse_message(self):
        """Parse a Telegram message dict into InboundMessage."""
        message = {
            "message_id": 42,
            "chat": {"id": 12345},
            "from": {"id": 67890, "first_name": "Alice"},
            "text": "Hello bot",
        }
        msg = TelegramAdapter.parse_message(message)
        assert isinstance(msg, InboundMessage)
        assert msg.chat_id == "12345"
        assert msg.text == "Hello bot"
        assert msg.sender_id == "67890"
        assert msg.sender_name == "Alice"
        assert msg.message_id == "42"
        assert msg.raw is message

    def test_parse_message_minimal(self):
        """Parse message with minimal fields."""
        msg = TelegramAdapter.parse_message({"chat": {"id": 1}})
        assert msg.chat_id == "1"
        assert msg.text == ""
        assert msg.sender_id == ""
        assert msg.sender_name == ""


class TestCapabilities:
    def test_capabilities(self, adapter):
        """Verify returned PlatformCapabilities values."""
        caps = adapter.get_capabilities()
        assert isinstance(caps, PlatformCapabilities)
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


class TestSendMedia:
    def test_send_photo_success(self, adapter, tmp_path):
        """Send a photo file uses sendPhoto with multipart payload."""
        photo = tmp_path / "test.png"
        photo.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ok": True,
            "result": {"message_id": 99},
        }

        with patch(
            "social_hook.messaging.telegram.requests.post", return_value=mock_response
        ) as mock_post:
            result = adapter.send_media("123", str(photo), caption="A photo")

        assert result.success is True
        assert result.message_id == "99"

        call_args = mock_post.call_args
        assert "sendPhoto" in call_args[0][0]
        assert call_args[1]["data"]["chat_id"] == "123"
        assert call_args[1]["data"]["caption"] == "A photo"
        assert "photo" in call_args[1]["files"]
        assert call_args[1]["timeout"] == 30

    def test_send_document_for_non_image(self, adapter, tmp_path):
        """Non-image file (.svg) uses sendDocument."""
        svg = tmp_path / "icon.svg"
        svg.write_text("<svg></svg>")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ok": True,
            "result": {"message_id": 100},
        }

        with patch(
            "social_hook.messaging.telegram.requests.post", return_value=mock_response
        ) as mock_post:
            result = adapter.send_media("123", str(svg))

        assert result.success is True
        call_args = mock_post.call_args
        assert "sendDocument" in call_args[0][0]
        assert "document" in call_args[1]["files"]

    def test_send_photo_over_10mb_falls_back_to_document(self, adapter, tmp_path):
        """Large .png (>10MB) falls back to sendDocument."""
        large_png = tmp_path / "big.png"
        large_png.write_bytes(b"\x00" * (11 * 1024 * 1024))  # 11 MB

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ok": True,
            "result": {"message_id": 101},
        }

        with patch(
            "social_hook.messaging.telegram.requests.post", return_value=mock_response
        ) as mock_post:
            result = adapter.send_media("123", str(large_png))

        assert result.success is True
        call_args = mock_post.call_args
        assert "sendDocument" in call_args[0][0]
        assert "document" in call_args[1]["files"]

    def test_send_media_file_not_found(self, adapter):
        """Missing file returns SendResult(success=False)."""
        result = adapter.send_media("123", "/nonexistent/photo.png")

        assert result.success is False
        assert "File not found" in result.error

    def test_send_media_network_error(self, adapter, tmp_path):
        """Network error returns SendResult(success=False)."""
        import requests as req

        photo = tmp_path / "test.jpg"
        photo.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)

        with patch(
            "social_hook.messaging.telegram.requests.post",
            side_effect=req.ConnectionError("network down"),
        ):
            result = adapter.send_media("123", str(photo))

        assert result.success is False
        assert "network down" in result.error


class TestSanitizeText:
    def test_escapes_underscores_outside_code(self, adapter):
        """Underscores in plain text are escaped."""
        result = adapter.sanitize_text("nano_banana_pro", "markdown")
        assert result == "nano\\_banana\\_pro"

    def test_preserves_code_spans(self, adapter):
        """Text inside backticks is not escaped."""
        result = adapter.sanitize_text("Media for `draft_abc` (nano_banana):", "markdown")
        assert result == "Media for `draft_abc` (nano\\_banana):"

    def test_already_escaped_underscores(self, adapter):
        """Already-escaped underscores are not double-escaped."""
        result = adapter.sanitize_text("already\\_escaped", "markdown")
        assert result == "already\\_escaped"

    def test_html_mode_unchanged(self, adapter):
        """HTML mode text is returned as-is."""
        result = adapter.sanitize_text("nano_banana_pro", "html")
        assert result == "nano_banana_pro"

    def test_no_underscores(self, adapter):
        """Text without underscores is unchanged."""
        result = adapter.sanitize_text("Hello world", "markdown")
        assert result == "Hello world"

    def test_multiple_code_spans(self, adapter):
        """Multiple code spans are all preserved."""
        result = adapter.sanitize_text("`a_b` then c_d then `e_f`", "markdown")
        assert result == "`a_b` then c\\_d then `e_f`"


class TestMarkdownRetryFallback:
    def test_retries_without_parse_mode_on_entity_error(self, adapter):
        """If Telegram rejects with parse entities error, retries without parse_mode."""
        error_response = MagicMock()
        error_response.status_code = 400
        error_response.json.return_value = {
            "ok": False,
            "description": "Bad Request: can't parse entities",
        }
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"ok": True, "result": {"message_id": 1}}

        with patch(
            "social_hook.messaging.telegram.requests.post",
            side_effect=[error_response, success_response],
        ) as mock_post:
            result = adapter.send_message("123", OutboundMessage(text="bad_text"))

        assert result.success is True
        # Second call should not have parse_mode
        second_call_payload = mock_post.call_args_list[1][1]["json"]
        assert "parse_mode" not in second_call_payload

    def test_no_retry_for_non_parse_errors(self, adapter):
        """Non-parse errors are not retried."""
        error_response = MagicMock()
        error_response.status_code = 403
        error_response.json.return_value = {
            "ok": False,
            "description": "Forbidden: bot was blocked by the user",
        }

        with patch(
            "social_hook.messaging.telegram.requests.post",
            return_value=error_response,
        ) as mock_post:
            result = adapter.send_message("123", OutboundMessage(text="hello"))

        assert result.success is False
        assert mock_post.call_count == 1


class TestMapParseMode:
    def test_markdown(self):
        assert TelegramAdapter._map_parse_mode("markdown") == "Markdown"

    def test_html(self):
        assert TelegramAdapter._map_parse_mode("html") == "HTML"

    def test_plain_returns_none(self):
        assert TelegramAdapter._map_parse_mode("plain") is None

    def test_unknown_returns_none(self):
        assert TelegramAdapter._map_parse_mode("other") is None
