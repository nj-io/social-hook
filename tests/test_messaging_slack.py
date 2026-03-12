"""Tests for the Slack messaging adapter stub."""

from unittest.mock import MagicMock, patch

import pytest

from social_hook.errors import ConfigError
from social_hook.messaging.base import OutboundMessage, PlatformCapabilities


class TestSlackAdapterInit:
    def test_missing_slack_bolt_raises_config_error(self):
        """Importing SlackAdapter without slack-bolt raises ConfigError."""
        from social_hook.messaging.slack import SlackAdapter

        with pytest.raises(ConfigError, match="slack-bolt"):
            SlackAdapter(token="xoxb-test")

    def test_init_with_slack_bolt_installed(self):
        """SlackAdapter initializes when slack-bolt is available."""
        mock_module = MagicMock()
        with patch.dict("sys.modules", {"slack_bolt": mock_module}):
            from social_hook.messaging.slack import SlackAdapter

            adapter = SlackAdapter(token="xoxb-test")
            assert adapter.token == "xoxb-test"
            assert adapter.platform == "slack"


class TestSlackAdapterStubMethods:
    @pytest.fixture
    def adapter(self):
        mock_module = MagicMock()
        with patch.dict("sys.modules", {"slack_bolt": mock_module}):
            from social_hook.messaging.slack import SlackAdapter

            return SlackAdapter(token="xoxb-test")

    def test_send_message_raises(self, adapter):
        """send_message raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="stub"):
            adapter.send_message("C123", OutboundMessage(text="hello"))

    def test_edit_message_raises(self, adapter):
        """edit_message raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="stub"):
            adapter.edit_message("C123", "msg_1", OutboundMessage(text="updated"))

    def test_answer_callback_raises(self, adapter):
        """answer_callback raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="stub"):
            adapter.answer_callback("action_id_1")

    def test_get_capabilities(self, adapter):
        """get_capabilities returns real Slack capabilities."""
        caps = adapter.get_capabilities()
        assert isinstance(caps, PlatformCapabilities)
        assert caps.max_message_length == 40000
        assert caps.supports_buttons is True
        assert caps.supports_inline_buttons is True
        assert caps.supports_message_editing is True
        assert caps.supports_markdown is True
        assert caps.supports_html is False
        assert caps.button_text_max_length == 75
