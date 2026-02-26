"""Tests for bot daemon and TelegramRunner."""

import json
from unittest.mock import MagicMock, patch

import pytest

from social_hook.bot.daemon import BotDaemon, create_bot
from social_hook.bot.runner import ChannelRunner
from social_hook.bot.runners.telegram import TelegramRunner


class TestTelegramRunnerInit:
    def test_default_init(self):
        runner = TelegramRunner(token="test_token")
        assert runner.token == "test_token"
        assert runner.allowed_chat_ids == set()
        assert runner._running is False
        assert runner._offset == 0

    def test_init_with_allowed_chats(self):
        runner = TelegramRunner(token="test", allowed_chat_ids={"123", "456"})
        assert runner.allowed_chat_ids == {"123", "456"}

    def test_platform_property(self):
        runner = TelegramRunner(token="test")
        assert runner.platform == "telegram"

    def test_conforms_to_interface(self):
        assert issubclass(TelegramRunner, ChannelRunner)
        runner = TelegramRunner(token="test")
        assert isinstance(runner, ChannelRunner)


class TestTelegramRunnerAuthorization:
    def test_empty_allowed_allows_all(self):
        runner = TelegramRunner(token="test")
        assert runner._is_authorized("123") is True
        assert runner._is_authorized("any_id") is True

    def test_restricted_allows_listed(self):
        runner = TelegramRunner(token="test", allowed_chat_ids={"123", "456"})
        assert runner._is_authorized("123") is True
        assert runner._is_authorized("456") is True
        assert runner._is_authorized("789") is False

    def test_str_comparison(self):
        runner = TelegramRunner(token="test", allowed_chat_ids={"123"})
        assert runner._is_authorized("123") is True
        assert runner._is_authorized("999") is False


class TestTelegramRunnerGetUpdates:
    @patch("social_hook.bot.runners.telegram.requests.get")
    def test_successful_fetch(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"ok": True, "result": [{"update_id": 1}]},
        )
        runner = TelegramRunner(token="test_token")
        updates = runner._get_updates()
        assert len(updates) == 1
        assert updates[0]["update_id"] == 1

    @patch("social_hook.bot.runners.telegram.requests.get")
    def test_api_error(self, mock_get):
        mock_get.return_value = MagicMock(status_code=500)
        runner = TelegramRunner(token="test")
        assert runner._get_updates() == []

    @patch("social_hook.bot.runners.telegram.requests.get")
    def test_not_ok_response(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"ok": False, "description": "Unauthorized"},
        )
        runner = TelegramRunner(token="test")
        assert runner._get_updates() == []

    @patch("social_hook.bot.runners.telegram.requests.get")
    def test_network_error(self, mock_get):
        import requests
        mock_get.side_effect = requests.RequestException("Connection failed")
        runner = TelegramRunner(token="test")
        assert runner._get_updates() == []

    @patch("social_hook.bot.runners.telegram.requests.get")
    def test_empty_result(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"ok": True, "result": []},
        )
        runner = TelegramRunner(token="test")
        assert runner._get_updates() == []


class TestTelegramRunnerRouteUpdate:
    def test_routes_command(self):
        on_command = MagicMock()
        runner = TelegramRunner(token="test", on_command=on_command)
        update = {"message": {"chat": {"id": 123}, "text": "/status"}}
        runner._route_update(update)
        on_command.assert_called_once()

    def test_routes_message(self):
        on_message = MagicMock()
        runner = TelegramRunner(token="test", on_message=on_message)
        update = {"message": {"chat": {"id": 123}, "text": "Hello bot"}}
        runner._route_update(update)
        on_message.assert_called_once()

    def test_routes_callback(self):
        on_callback = MagicMock()
        runner = TelegramRunner(token="test", on_callback=on_callback)
        update = {
            "callback_query": {
                "id": "cb1",
                "message": {"chat": {"id": 123}},
                "data": "approve:draft_123",
            }
        }
        runner._route_update(update)
        on_callback.assert_called_once()

    def test_unauthorized_command_ignored(self):
        on_command = MagicMock()
        runner = TelegramRunner(token="test", allowed_chat_ids={"999"}, on_command=on_command)
        update = {"message": {"chat": {"id": 123}, "text": "/status"}}
        runner._route_update(update)
        on_command.assert_not_called()

    def test_unauthorized_callback_ignored(self):
        on_callback = MagicMock()
        runner = TelegramRunner(token="test", allowed_chat_ids={"999"}, on_callback=on_callback)
        update = {
            "callback_query": {
                "id": "cb1",
                "message": {"chat": {"id": 123}},
                "data": "approve:draft_123",
            }
        }
        runner._route_update(update)
        on_callback.assert_not_called()

    def test_empty_message_ignored(self):
        on_message = MagicMock()
        runner = TelegramRunner(token="test", on_message=on_message)
        update = {"message": {"chat": {"id": 123}}}
        runner._route_update(update)
        on_message.assert_not_called()

    def test_no_message_or_callback(self):
        on_command = MagicMock()
        runner = TelegramRunner(token="test", on_command=on_command)
        update = {"something_else": {}}
        runner._route_update(update)
        on_command.assert_not_called()

    def test_command_error_logged(self):
        on_command = MagicMock(side_effect=ValueError("test error"))
        runner = TelegramRunner(token="test", on_command=on_command)
        update = {"message": {"chat": {"id": 123}, "text": "/crash"}}
        runner._route_update(update)  # Should not raise

    def test_callback_error_logged(self):
        on_callback = MagicMock(side_effect=ValueError("test error"))
        runner = TelegramRunner(token="test", on_callback=on_callback)
        update = {
            "callback_query": {
                "id": "cb1",
                "message": {"chat": {"id": 123}},
                "data": "approve:draft_123",
            }
        }
        runner._route_update(update)

    def test_message_error_logged(self):
        on_message = MagicMock(side_effect=ValueError("test error"))
        runner = TelegramRunner(token="test", on_message=on_message)
        update = {"message": {"chat": {"id": 123}, "text": "Hello"}}
        runner._route_update(update)


class TestTelegramRunnerLifecycle:
    def test_stop_sets_flag(self):
        runner = TelegramRunner(token="test")
        runner._running = True
        runner.stop()
        assert runner._running is False

    @patch("social_hook.bot.runners.telegram.TelegramRunner._get_updates")
    def test_run_polls_until_stopped(self, mock_updates):
        runner = TelegramRunner(token="test")
        call_count = 0

        def stop_after_one():
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                runner._running = False
            return []

        mock_updates.side_effect = stop_after_one
        runner.run()
        assert call_count >= 1


class TestBotDaemon:
    def test_init_with_runners(self):
        mock_runner = MagicMock(spec=ChannelRunner)
        daemon = BotDaemon(runners=[mock_runner])
        assert len(daemon._runners) == 1
        assert daemon._running is False

    def test_stop_propagates(self):
        r1 = MagicMock(spec=ChannelRunner)
        r2 = MagicMock(spec=ChannelRunner)
        daemon = BotDaemon(runners=[r1, r2])
        daemon._running = True
        daemon.stop()
        assert daemon._running is False
        r1.stop.assert_called_once()
        r2.stop.assert_called_once()

    def test_single_runner_delegates_run(self):
        mock_runner = MagicMock(spec=ChannelRunner)
        daemon = BotDaemon(runners=[mock_runner])
        # run() calls runner.run() directly for single runner
        daemon.run()
        mock_runner.run.assert_called_once()

    @patch("social_hook.bot.daemon.write_pid")
    @patch("social_hook.bot.daemon.remove_pid")
    def test_run_writes_and_removes_pid(self, mock_remove_pid, mock_write_pid, tmp_path):
        pid_file = tmp_path / "bot.pid"
        mock_runner = MagicMock(spec=ChannelRunner)
        daemon = BotDaemon(runners=[mock_runner])
        daemon.run(pid_file=pid_file)
        mock_write_pid.assert_called_once_with(pid_file)
        mock_remove_pid.assert_called_once_with(pid_file)


class TestCreateBot:
    def test_creates_daemon_with_runner(self):
        bot = create_bot(token="test_token", allowed_chat_ids={"123"})
        assert isinstance(bot, BotDaemon)
        assert len(bot._runners) == 1
        assert isinstance(bot._runners[0], TelegramRunner)
        assert bot._runners[0].token == "test_token"
        assert bot._runners[0].allowed_chat_ids == {"123"}

    def test_create_bot_no_set_adapter(self):
        from social_hook.bot import buttons, commands
        assert not hasattr(buttons, "set_adapter")
        assert not hasattr(commands, "set_adapter")
        bot = create_bot(token="test_token", allowed_chat_ids={"42"})
        assert isinstance(bot, BotDaemon)

    def test_on_command_uses_parse_message(self):
        from social_hook.messaging.base import InboundMessage
        mock_config = MagicMock()
        raw_message = {"chat": {"id": 123}, "text": "/status", "from": {"id": 1, "first_name": "Test"}, "message_id": 42}
        with patch("social_hook.bot.commands.handle_command") as mock_handler:
            bot = create_bot(token="test_token", config=mock_config)
            runner = bot._runners[0]
            runner.on_command(raw_message)
            mock_handler.assert_called_once()
            msg_arg = mock_handler.call_args[0][0]
            assert isinstance(msg_arg, InboundMessage)
            assert msg_arg.chat_id == "123"
            assert msg_arg.text == "/status"

    def test_on_callback_uses_parse_callback(self):
        from social_hook.messaging.base import CallbackEvent
        mock_config = MagicMock()
        raw_callback = {
            "id": "cb1",
            "message": {"chat": {"id": 123}, "message_id": 99},
            "data": "approve:draft_123",
        }
        with patch("social_hook.bot.buttons.handle_callback") as mock_handler:
            bot = create_bot(token="test_token", config=mock_config)
            runner = bot._runners[0]
            runner.on_callback(raw_callback)
            mock_handler.assert_called_once()
            event_arg = mock_handler.call_args[0][0]
            assert isinstance(event_arg, CallbackEvent)
            assert event_arg.chat_id == "123"
            assert event_arg.action == "approve"
            assert event_arg.payload == "draft_123"

    def test_on_message_uses_parse_message(self):
        from social_hook.messaging.base import InboundMessage
        mock_config = MagicMock()
        raw_message = {"chat": {"id": 456}, "text": "Hello bot", "from": {"id": 2, "first_name": "User"}, "message_id": 7}
        with patch("social_hook.bot.commands.handle_message") as mock_handler:
            bot = create_bot(token="test_token", config=mock_config)
            runner = bot._runners[0]
            runner.on_message(raw_message)
            mock_handler.assert_called_once()
            msg_arg = mock_handler.call_args[0][0]
            assert isinstance(msg_arg, InboundMessage)
            assert msg_arg.chat_id == "456"
            assert msg_arg.text == "Hello bot"
