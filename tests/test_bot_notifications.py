"""Tests for bot notification formatting and sending (T28)."""

from unittest.mock import MagicMock, patch

import pytest

from social_hook.bot.notifications import (
    format_draft_review,
    format_engagement_prompt,
    format_error_notification,
    format_post_confirmation,
    get_review_buttons,
    send_notification,
    send_notification_with_buttons,
)


class TestSendNotification:
    """Tests for send_notification."""

    @patch("social_hook.bot.notifications.requests.post")
    def test_successful_send(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        assert send_notification("token", "123", "Hello") is True
        mock_post.assert_called_once()

        call_kwargs = mock_post.call_args[1]["json"]
        assert call_kwargs["chat_id"] == "123"
        assert call_kwargs["text"] == "Hello"
        assert call_kwargs["parse_mode"] == "Markdown"

    @patch("social_hook.bot.notifications.requests.post")
    def test_failed_send(self, mock_post):
        mock_post.return_value = MagicMock(status_code=400)
        assert send_notification("token", "123", "Hello") is False

    @patch("social_hook.bot.notifications.requests.post")
    def test_network_error(self, mock_post):
        import requests
        mock_post.side_effect = requests.RequestException("Connection refused")
        assert send_notification("token", "123", "Hello") is False

    @patch("social_hook.bot.notifications.requests.post")
    def test_custom_parse_mode(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        send_notification("token", "123", "Hello", parse_mode="HTML")
        call_kwargs = mock_post.call_args[1]["json"]
        assert call_kwargs["parse_mode"] == "HTML"


class TestSendNotificationWithButtons:
    """Tests for send_notification_with_buttons."""

    @patch("social_hook.bot.notifications.requests.post")
    def test_successful_send(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"result": {"message_id": 42}},
        )
        buttons = [[{"text": "OK", "callback_data": "ok"}]]
        result = send_notification_with_buttons("token", "123", "Choose", buttons)
        assert result == 42

        call_kwargs = mock_post.call_args[1]["json"]
        assert "reply_markup" in call_kwargs
        assert call_kwargs["reply_markup"]["inline_keyboard"] == buttons

    @patch("social_hook.bot.notifications.requests.post")
    def test_failed_send(self, mock_post):
        mock_post.return_value = MagicMock(status_code=400)
        buttons = [[{"text": "OK", "callback_data": "ok"}]]
        assert send_notification_with_buttons("token", "123", "Choose", buttons) is None

    @patch("social_hook.bot.notifications.requests.post")
    def test_network_error(self, mock_post):
        import requests
        mock_post.side_effect = requests.RequestException("timeout")
        buttons = [[{"text": "OK", "callback_data": "ok"}]]
        assert send_notification_with_buttons("token", "123", "Choose", buttons) is None


class TestFormatDraftReview:
    """Tests for format_draft_review."""

    def test_basic_format(self):
        msg = format_draft_review(
            project_name="my-project",
            commit_hash="abc1234",
            commit_message="Add feature X",
            platform="x",
            content="This is a test post about feature X",
        )
        assert "*New draft ready for review*" in msg
        assert "my-project" in msg
        assert "`abc1234`" in msg
        assert "Add feature X" in msg
        assert "Platform: x" in msg
        assert "test post about feature X" in msg

    def test_with_draft_id(self):
        msg = format_draft_review(
            project_name="test",
            commit_hash="abc",
            commit_message="msg",
            platform="x",
            content="content",
            draft_id="draft_123",
        )
        assert "`draft_123`" in msg

    def test_with_suggested_time(self):
        msg = format_draft_review(
            project_name="test",
            commit_hash="abc",
            commit_message="msg",
            platform="x",
            content="content",
            suggested_time="2026-02-10 14:00 UTC",
        )
        assert "Suggested time:" in msg
        assert "2026-02-10 14:00 UTC" in msg

    def test_content_truncated(self):
        long_content = "x" * 1000
        msg = format_draft_review(
            project_name="test",
            commit_hash="abc",
            commit_message="msg",
            platform="x",
            content=long_content,
        )
        # Content should be truncated to 500 chars
        assert len(long_content) > 500
        assert "x" * 500 in msg
        assert "x" * 501 not in msg

    def test_includes_code_block(self):
        msg = format_draft_review(
            project_name="test",
            commit_hash="abc",
            commit_message="msg",
            platform="x",
            content="Hello world",
        )
        assert "```" in msg


class TestFormatPostConfirmation:
    """Tests for format_post_confirmation."""

    def test_basic_format(self):
        msg = format_post_confirmation(
            project_name="my-project",
            platform="x",
            content="Posted content here",
        )
        assert "*Posted successfully*" in msg
        assert "my-project" in msg
        assert "Platform: x" in msg
        assert "Posted content" in msg

    def test_with_url(self):
        msg = format_post_confirmation(
            project_name="test",
            platform="x",
            content="content",
            external_url="https://x.com/user/status/123",
        )
        assert "URL:" in msg
        assert "https://x.com/user/status/123" in msg

    def test_content_truncated(self):
        long_content = "y" * 500
        msg = format_post_confirmation(
            project_name="test",
            platform="x",
            content=long_content,
        )
        # Truncated to 300
        assert "y" * 300 in msg
        assert "y" * 301 not in msg


class TestFormatErrorNotification:
    """Tests for format_error_notification."""

    def test_basic_format(self):
        msg = format_error_notification(
            project_name="test",
            platform="x",
            error="Rate limited",
            retry_count=1,
            max_retries=3,
        )
        assert "*Post failed*" in msg
        assert "Rate limited" in msg
        assert "1/3" in msg

    def test_with_draft_id(self):
        msg = format_error_notification(
            project_name="test",
            platform="x",
            error="Error",
            draft_id="draft_abc",
        )
        assert "`draft_abc`" in msg

    def test_max_retries_reached(self):
        msg = format_error_notification(
            project_name="test",
            platform="x",
            error="Persistent error",
            retry_count=3,
            max_retries=3,
        )
        assert "failed" in msg.lower()
        assert "/retry" in msg

    def test_not_max_retries(self):
        msg = format_error_notification(
            project_name="test",
            platform="x",
            error="Temp error",
            retry_count=1,
            max_retries=3,
        )
        assert "/retry" not in msg


class TestGetReviewButtons:
    """Tests for get_review_buttons."""

    def test_button_layout(self):
        buttons = get_review_buttons("draft_123")
        assert len(buttons) == 2  # Two rows
        assert len(buttons[0]) == 2  # First row: Approve + Schedule
        assert len(buttons[1]) == 2  # Second row: Edit + Reject

    def test_button_data(self):
        buttons = get_review_buttons("draft_abc")
        # First row
        assert buttons[0][0]["text"] == "Approve"
        assert buttons[0][0]["callback_data"] == "approve:draft_abc"
        assert buttons[0][1]["text"] == "Schedule"
        assert buttons[0][1]["callback_data"] == "schedule:draft_abc"
        # Second row
        assert buttons[1][0]["text"] == "Edit"
        assert buttons[1][0]["callback_data"] == "edit:draft_abc"
        assert buttons[1][1]["text"] == "Reject"
        assert buttons[1][1]["callback_data"] == "reject:draft_abc"

    def test_different_draft_ids(self):
        b1 = get_review_buttons("draft_1")
        b2 = get_review_buttons("draft_2")
        assert b1[0][0]["callback_data"] != b2[0][0]["callback_data"]

    def test_submenu_callback_ids(self):
        """Review buttons use submenu callback IDs for schedule/edit/reject."""
        buttons = get_review_buttons("draft_x")
        all_data = [b["callback_data"] for row in buttons for b in row]
        assert "schedule:draft_x" in all_data
        assert "edit:draft_x" in all_data
        assert "reject:draft_x" in all_data
        # Should NOT have direct action IDs
        assert "schedule_optimal:draft_x" not in all_data
        assert "edit_text:draft_x" not in all_data


class TestFormatDraftReviewExtended:
    """Tests for extended format_draft_review params."""

    def test_includes_char_count(self):
        msg = format_draft_review(
            project_name="test", commit_hash="abc", commit_message="msg",
            platform="x", content="hello", char_count=42,
        )
        assert "Characters: 42" in msg

    def test_includes_media_info(self):
        msg = format_draft_review(
            project_name="test", commit_hash="abc", commit_message="msg",
            platform="x", content="hello", media_info="Screenshot of dashboard",
        )
        assert "Media: Screenshot of dashboard" in msg

    def test_thread_format(self):
        msg = format_draft_review(
            project_name="test", commit_hash="abc", commit_message="msg",
            platform="x", content="Thread content",
            is_thread=True, tweet_count=4,
        )
        assert "Thread: 4 tweets" in msg


class TestFormatPostConfirmationExtended:
    """Tests for extended format_post_confirmation params."""

    def test_includes_link_hint(self):
        msg = format_post_confirmation(
            project_name="test", platform="x", content="Check it out",
            link_hint="https://example.com/blog",
        )
        assert "Consider posting this link as a reply" in msg
        assert "https://example.com/blog" in msg

    def test_no_link_hint(self):
        msg = format_post_confirmation(
            project_name="test", platform="x", content="No link",
        )
        assert "Consider posting" not in msg


class TestFormatEngagementPrompt:
    """Tests for format_engagement_prompt."""

    def test_format(self):
        msg = format_engagement_prompt()
        assert "150x" in msg
        assert "first hour" in msg
