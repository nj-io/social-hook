"""Tests for bot daemon (T25)."""

import json
from unittest.mock import MagicMock, call, patch

import pytest

from social_hook.bot.daemon import BotDaemon, create_bot


class TestBotDaemonInit:
    """Tests for BotDaemon initialization."""

    def test_default_init(self):
        bot = BotDaemon(token="test_token")
        assert bot.token == "test_token"
        assert bot.allowed_chat_ids == set()
        assert bot._running is False
        assert bot._offset == 0

    def test_init_with_allowed_chats(self):
        bot = BotDaemon(token="test", allowed_chat_ids={"123", "456"})
        assert bot.allowed_chat_ids == {"123", "456"}


class TestAuthorization:
    """Tests for chat ID authorization."""

    def test_empty_allowed_allows_all(self):
        bot = BotDaemon(token="test")
        assert bot._is_authorized("123") is True
        assert bot._is_authorized("any_id") is True

    def test_restricted_allows_listed(self):
        bot = BotDaemon(token="test", allowed_chat_ids={"123", "456"})
        assert bot._is_authorized("123") is True
        assert bot._is_authorized("456") is True
        assert bot._is_authorized("789") is False

    def test_str_comparison(self):
        bot = BotDaemon(token="test", allowed_chat_ids={"123"})
        # _is_authorized compares str(chat_id) against allowed set
        assert bot._is_authorized("123") is True
        assert bot._is_authorized("999") is False


class TestGetUpdates:
    """Tests for _get_updates."""

    @patch("social_hook.bot.daemon.requests.get")
    def test_successful_fetch(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"ok": True, "result": [{"update_id": 1}]},
        )
        bot = BotDaemon(token="test_token")
        updates = bot._get_updates()
        assert len(updates) == 1
        assert updates[0]["update_id"] == 1

    @patch("social_hook.bot.daemon.requests.get")
    def test_api_error(self, mock_get):
        mock_get.return_value = MagicMock(status_code=500)
        bot = BotDaemon(token="test")
        assert bot._get_updates() == []

    @patch("social_hook.bot.daemon.requests.get")
    def test_not_ok_response(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"ok": False, "description": "Unauthorized"},
        )
        bot = BotDaemon(token="test")
        assert bot._get_updates() == []

    @patch("social_hook.bot.daemon.requests.get")
    def test_network_error(self, mock_get):
        import requests
        mock_get.side_effect = requests.RequestException("Connection failed")
        bot = BotDaemon(token="test")
        assert bot._get_updates() == []

    @patch("social_hook.bot.daemon.requests.get")
    def test_empty_result(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"ok": True, "result": []},
        )
        bot = BotDaemon(token="test")
        assert bot._get_updates() == []


class TestRouteUpdate:
    """Tests for _route_update."""

    def test_routes_command(self):
        on_command = MagicMock()
        bot = BotDaemon(token="test", on_command=on_command)
        update = {
            "message": {
                "chat": {"id": 123},
                "text": "/status",
            }
        }
        bot._route_update(update)
        on_command.assert_called_once()

    def test_routes_message(self):
        on_message = MagicMock()
        bot = BotDaemon(token="test", on_message=on_message)
        update = {
            "message": {
                "chat": {"id": 123},
                "text": "Hello bot",
            }
        }
        bot._route_update(update)
        on_message.assert_called_once()

    def test_routes_callback(self):
        on_callback = MagicMock()
        bot = BotDaemon(token="test", on_callback=on_callback)
        update = {
            "callback_query": {
                "id": "cb1",
                "message": {"chat": {"id": 123}},
                "data": "approve:draft_123",
            }
        }
        bot._route_update(update)
        on_callback.assert_called_once()

    def test_unauthorized_command_ignored(self):
        on_command = MagicMock()
        bot = BotDaemon(
            token="test",
            allowed_chat_ids={"999"},
            on_command=on_command,
        )
        update = {
            "message": {
                "chat": {"id": 123},
                "text": "/status",
            }
        }
        bot._route_update(update)
        on_command.assert_not_called()

    def test_unauthorized_callback_ignored(self):
        on_callback = MagicMock()
        bot = BotDaemon(
            token="test",
            allowed_chat_ids={"999"},
            on_callback=on_callback,
        )
        update = {
            "callback_query": {
                "id": "cb1",
                "message": {"chat": {"id": 123}},
                "data": "approve:draft_123",
            }
        }
        bot._route_update(update)
        on_callback.assert_not_called()

    def test_empty_message_ignored(self):
        on_message = MagicMock()
        bot = BotDaemon(token="test", on_message=on_message)
        update = {"message": {"chat": {"id": 123}}}
        bot._route_update(update)
        on_message.assert_not_called()

    def test_no_message_or_callback(self):
        on_command = MagicMock()
        bot = BotDaemon(token="test", on_command=on_command)
        update = {"something_else": {}}
        bot._route_update(update)
        on_command.assert_not_called()

    def test_command_error_logged(self):
        on_command = MagicMock(side_effect=ValueError("test error"))
        bot = BotDaemon(token="test", on_command=on_command)
        update = {
            "message": {
                "chat": {"id": 123},
                "text": "/crash",
            }
        }
        # Should not raise - errors are caught and logged
        bot._route_update(update)

    def test_callback_error_logged(self):
        on_callback = MagicMock(side_effect=ValueError("test error"))
        bot = BotDaemon(token="test", on_callback=on_callback)
        update = {
            "callback_query": {
                "id": "cb1",
                "message": {"chat": {"id": 123}},
                "data": "approve:draft_123",
            }
        }
        bot._route_update(update)

    def test_message_error_logged(self):
        on_message = MagicMock(side_effect=ValueError("test error"))
        bot = BotDaemon(token="test", on_message=on_message)
        update = {
            "message": {
                "chat": {"id": 123},
                "text": "Hello",
            }
        }
        bot._route_update(update)


class TestSendMessage:
    """Tests for send_message."""

    @patch("social_hook.bot.daemon.requests.post")
    def test_successful_send(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"result": {"message_id": 42}},
        )
        bot = BotDaemon(token="test_token")
        result = bot.send_message("123", "Hello")
        assert result is not None
        assert result["message_id"] == 42

    @patch("social_hook.bot.daemon.requests.post")
    def test_failed_send(self, mock_post):
        mock_post.return_value = MagicMock(status_code=400)
        bot = BotDaemon(token="test")
        assert bot.send_message("123", "Hello") is None

    @patch("social_hook.bot.daemon.requests.post")
    def test_send_with_reply_markup(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"result": {"message_id": 1}},
        )
        bot = BotDaemon(token="test")
        markup = {"inline_keyboard": [[{"text": "OK", "callback_data": "ok"}]]}
        bot.send_message("123", "Choose", reply_markup=markup)

        call_kwargs = mock_post.call_args[1]["json"]
        assert "reply_markup" in call_kwargs

    @patch("social_hook.bot.daemon.requests.post")
    def test_send_network_error(self, mock_post):
        import requests
        mock_post.side_effect = requests.RequestException("timeout")
        bot = BotDaemon(token="test")
        assert bot.send_message("123", "Hello") is None


class TestAnswerCallback:
    """Tests for answer_callback."""

    @patch("social_hook.bot.daemon.requests.post")
    def test_answer_success(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        bot = BotDaemon(token="test")
        assert bot.answer_callback("cb1", "Done") is True

    @patch("social_hook.bot.daemon.requests.post")
    def test_answer_failure(self, mock_post):
        mock_post.return_value = MagicMock(status_code=400)
        bot = BotDaemon(token="test")
        assert bot.answer_callback("cb1") is False

    @patch("social_hook.bot.daemon.requests.post")
    def test_answer_network_error(self, mock_post):
        import requests
        mock_post.side_effect = requests.RequestException()
        bot = BotDaemon(token="test")
        assert bot.answer_callback("cb1") is False


class TestEditMessage:
    """Tests for edit_message."""

    @patch("social_hook.bot.daemon.requests.post")
    def test_edit_success(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        bot = BotDaemon(token="test")
        assert bot.edit_message("123", 42, "Updated text") is True

    @patch("social_hook.bot.daemon.requests.post")
    def test_edit_failure(self, mock_post):
        mock_post.return_value = MagicMock(status_code=400)
        bot = BotDaemon(token="test")
        assert bot.edit_message("123", 42, "Updated") is False


class TestBotRunAndStop:
    """Tests for run/stop lifecycle."""

    def test_stop_sets_flag(self):
        bot = BotDaemon(token="test")
        bot._running = True
        bot.stop()
        assert bot._running is False

    @patch("social_hook.bot.daemon.BotDaemon._get_updates")
    def test_run_writes_pid(self, mock_updates, temp_dir):
        """Run writes PID file and removes on exit."""
        pid_file = temp_dir / "bot.pid"
        mock_updates.return_value = []

        bot = BotDaemon(token="test")

        # Stop after first iteration
        call_count = 0
        original = mock_updates.side_effect

        def stop_after_one():
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                bot._running = False
            return []

        mock_updates.side_effect = stop_after_one

        bot.run(pid_file=pid_file)
        # PID file should be cleaned up after run
        assert not pid_file.exists()


class TestCreateBot:
    """Tests for create_bot factory."""

    def test_creates_daemon(self):
        bot = create_bot(
            token="test_token",
            allowed_chat_ids={"123"},
        )
        assert isinstance(bot, BotDaemon)
        assert bot.token == "test_token"
        assert bot.allowed_chat_ids == {"123"}
        assert bot.on_command is not None
        assert bot.on_callback is not None
        assert bot.on_message is not None

    def test_create_bot_no_set_adapter(self):
        """create_bot does not call set_adapter (removed after handler abstraction)."""
        # set_adapter should not exist in buttons or commands modules
        from social_hook.bot import buttons, commands
        assert not hasattr(buttons, "set_adapter")
        assert not hasattr(commands, "set_adapter")
        # create_bot should still work without set_adapter
        bot = create_bot(token="test_token", allowed_chat_ids={"42"})
        assert isinstance(bot, BotDaemon)

    def test_on_command_uses_parse_message(self):
        """on_command converts raw dict to InboundMessage via parse_message."""
        from social_hook.messaging.base import InboundMessage

        mock_config = MagicMock()
        raw_message = {"chat": {"id": 123}, "text": "/status", "from": {"id": 1, "first_name": "Test"}, "message_id": 42}

        # Patch before create_bot so closures capture the mock
        with patch("social_hook.bot.commands.handle_command") as mock_handler:
            bot = create_bot(token="test_token", config=mock_config)
            bot.on_command(raw_message)
            mock_handler.assert_called_once()
            msg_arg = mock_handler.call_args[0][0]
            assert isinstance(msg_arg, InboundMessage)
            assert msg_arg.chat_id == "123"
            assert msg_arg.text == "/status"

    def test_on_callback_uses_parse_callback(self):
        """on_callback converts raw dict to CallbackEvent via parse_callback."""
        from social_hook.messaging.base import CallbackEvent

        mock_config = MagicMock()
        raw_callback = {
            "id": "cb1",
            "message": {"chat": {"id": 123}, "message_id": 99},
            "data": "approve:draft_123",
        }

        with patch("social_hook.bot.buttons.handle_callback") as mock_handler:
            bot = create_bot(token="test_token", config=mock_config)
            bot.on_callback(raw_callback)
            mock_handler.assert_called_once()
            event_arg = mock_handler.call_args[0][0]
            assert isinstance(event_arg, CallbackEvent)
            assert event_arg.chat_id == "123"
            assert event_arg.action == "approve"
            assert event_arg.payload == "draft_123"

    def test_on_message_uses_parse_message(self):
        """on_message converts raw dict to InboundMessage via parse_message."""
        from social_hook.messaging.base import InboundMessage

        mock_config = MagicMock()
        raw_message = {"chat": {"id": 456}, "text": "Hello bot", "from": {"id": 2, "first_name": "User"}, "message_id": 7}

        with patch("social_hook.bot.commands.handle_message") as mock_handler:
            bot = create_bot(token="test_token", config=mock_config)
            bot.on_message(raw_message)
            mock_handler.assert_called_once()
            msg_arg = mock_handler.call_args[0][0]
            assert isinstance(msg_arg, InboundMessage)
            assert msg_arg.chat_id == "456"
            assert msg_arg.text == "Hello bot"
