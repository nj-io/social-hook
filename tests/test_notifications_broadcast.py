"""Tests for broadcast_notification in notifications.py."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from social_hook.messaging.base import Button, ButtonRow, OutboundMessage, SendResult
from social_hook.notifications import broadcast_notification, send_notification


class TestBroadcastIteratesChannels:
    """broadcast_notification iterates enabled channels."""

    def test_broadcast_iterates_enabled_channels(self):
        """Sends to both web and telegram when both enabled."""
        cfg = MagicMock()
        cfg.channels = {}  # defaults = both enabled
        cfg.env.get = lambda key, default="": {
            "TELEGRAM_BOT_TOKEN": "fake-token",
            "TELEGRAM_ALLOWED_CHAT_IDS": "123,456",
        }.get(key, default)

        msg = OutboundMessage(text="Hello")

        with (
            patch(
                "social_hook.filesystem.get_db_path",
                return_value=Path("/tmp/test.db"),
            ),
            patch("social_hook.messaging.web.WebAdapter") as mock_web_cls,
            patch("social_hook.messaging.telegram.TelegramAdapter") as mock_tg_cls,
        ):
            mock_web = MagicMock()
            mock_web_cls.return_value = mock_web
            mock_tg = MagicMock()
            mock_tg.send_message.return_value = SendResult(success=True)
            mock_tg_cls.return_value = mock_tg

            broadcast_notification(cfg, msg)

            mock_web.send_message.assert_called_once()
            assert mock_tg.send_message.call_count == 2  # two chat_ids


class TestBroadcastButtonBehavior:
    """Tests for button behavior in notifications."""

    def _make_msg_with_buttons(self):
        return OutboundMessage(
            text="Draft review",
            buttons=[
                ButtonRow(
                    buttons=[
                        Button(label="Approve", action="approve", payload="d1"),
                        Button(label="Reject", action="reject", payload="d1"),
                    ]
                )
            ],
        )

    def test_broadcast_always_sends_buttons_to_telegram(self):
        """Telegram message always includes buttons regardless of daemon state."""
        cfg = MagicMock()
        cfg.channels = {}
        cfg.env.get = lambda key, default="": {
            "TELEGRAM_BOT_TOKEN": "fake-token",
            "TELEGRAM_ALLOWED_CHAT_IDS": "123",
        }.get(key, default)

        msg = self._make_msg_with_buttons()

        with (
            patch(
                "social_hook.filesystem.get_db_path",
                return_value=Path("/tmp/test.db"),
            ),
            patch("social_hook.messaging.web.WebAdapter") as mock_web_cls,
            patch("social_hook.messaging.telegram.TelegramAdapter") as mock_tg_cls,
        ):
            mock_web_cls.return_value = MagicMock()
            mock_tg = MagicMock()
            mock_tg.send_message.return_value = SendResult(success=True)
            mock_tg_cls.return_value = mock_tg

            broadcast_notification(cfg, msg)

            tg_msg = mock_tg.send_message.call_args[0][1]
            assert len(tg_msg.buttons) == 1

    def test_broadcast_web_always_has_buttons(self):
        """Web adapter always receives buttons regardless of daemon status."""
        cfg = MagicMock()
        cfg.channels = {}
        cfg.env.get = lambda key, default="": {}.get(key, default)  # no telegram

        msg = self._make_msg_with_buttons()

        with (
            patch(
                "social_hook.filesystem.get_db_path",
                return_value=Path("/tmp/test.db"),
            ),
            patch("social_hook.messaging.web.WebAdapter") as mock_web_cls,
        ):
            mock_web = MagicMock()
            mock_web_cls.return_value = mock_web

            broadcast_notification(cfg, msg)

            web_msg = mock_web.send_message.call_args[0][1]
            assert len(web_msg.buttons) == 1


class TestBroadcastMedia:
    """Tests for media sending."""

    def test_broadcast_sends_media(self):
        """send_media called for channels with supports_media."""
        cfg = MagicMock()
        cfg.channels = {}
        cfg.env.get = lambda key, default="": {
            "TELEGRAM_BOT_TOKEN": "fake-token",
            "TELEGRAM_ALLOWED_CHAT_IDS": "123",
        }.get(key, default)

        msg = OutboundMessage(text="Draft")
        media = ["/tmp/image.png"]

        with (
            patch(
                "social_hook.filesystem.get_db_path",
                return_value=Path("/tmp/test.db"),
            ),
            patch("social_hook.messaging.web.WebAdapter") as mock_web_cls,
            patch("social_hook.messaging.telegram.TelegramAdapter") as mock_tg_cls,
        ):
            mock_web = MagicMock()
            mock_web_cls.return_value = mock_web
            mock_tg = MagicMock()
            mock_tg.send_message.return_value = SendResult(success=True)
            caps = MagicMock()
            caps.supports_media = True
            mock_tg.get_capabilities.return_value = caps
            mock_tg_cls.return_value = mock_tg

            broadcast_notification(cfg, msg, media=media)

            mock_web.send_media.assert_called_once()
            mock_tg.send_media.assert_called_once()


class TestBroadcastDryRun:
    """Tests for dry_run behavior."""

    def test_broadcast_dry_run_skips(self):
        """dry_run=True skips all sends."""
        cfg = MagicMock()
        msg = OutboundMessage(text="Hello")

        with patch("social_hook.messaging.web.WebAdapter") as mock_web_cls:
            broadcast_notification(cfg, msg, dry_run=True)
            mock_web_cls.assert_not_called()


class TestBroadcastChatContext:
    """Tests for chat_context setting."""

    def test_broadcast_sets_chat_context(self):
        """set_chat_draft_context called when chat_context provided."""
        cfg = MagicMock()
        cfg.channels = {}
        cfg.env.get = lambda key, default="": {
            "TELEGRAM_BOT_TOKEN": "fake-token",
            "TELEGRAM_ALLOWED_CHAT_IDS": "123,456",
        }.get(key, default)

        msg = OutboundMessage(text="Draft")

        with (
            patch(
                "social_hook.filesystem.get_db_path",
                return_value=Path("/tmp/test.db"),
            ),
            patch("social_hook.messaging.web.WebAdapter") as mock_web_cls,
            patch("social_hook.messaging.telegram.TelegramAdapter") as mock_tg_cls,
            patch("social_hook.bot.commands.set_chat_draft_context") as mock_ctx,
        ):
            mock_web_cls.return_value = MagicMock()
            mock_tg = MagicMock()
            mock_tg.send_message.return_value = SendResult(success=True)
            mock_tg_cls.return_value = mock_tg

            broadcast_notification(cfg, msg, chat_context=("draft-1", "proj-1"))

            assert mock_ctx.call_count == 2
            mock_ctx.assert_any_call("123", "draft-1", "proj-1")
            mock_ctx.assert_any_call("456", "draft-1", "proj-1")


class TestSendNotificationBackwardCompat:
    """Tests for the backward-compatible send_notification wrapper."""

    def test_send_notification_backward_compat(self):
        """Old send_notification(config, message_str) still works."""
        cfg = MagicMock()

        with patch("social_hook.notifications.broadcast_notification") as mock_broadcast:
            send_notification(cfg, "Hello world", dry_run=False)

            mock_broadcast.assert_called_once()
            args = mock_broadcast.call_args
            assert args[0][0] is cfg
            assert args[0][1].text == "Hello world"
            assert args[1]["dry_run"] is False
