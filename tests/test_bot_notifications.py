"""Tests for bot notification formatting helpers (T28)."""

from social_hook.bot.notifications import (
    format_draft_review,
    get_review_buttons_normalized,
)


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


class TestFormatDraftReviewExtended:
    """Tests for extended format_draft_review params."""

    def test_includes_char_count(self):
        msg = format_draft_review(
            project_name="test",
            commit_hash="abc",
            commit_message="msg",
            platform="x",
            content="hello",
            char_count=42,
        )
        assert "Characters: 42" in msg

    def test_includes_media_info(self):
        msg = format_draft_review(
            project_name="test",
            commit_hash="abc",
            commit_message="msg",
            platform="x",
            content="hello",
            media_info="Screenshot of dashboard",
        )
        assert "Media: Screenshot of dashboard" in msg

    def test_thread_format(self):
        msg = format_draft_review(
            project_name="test",
            commit_hash="abc",
            commit_message="msg",
            platform="x",
            content="Thread content",
            is_thread=True,
            tweet_count=4,
        )
        assert "Thread: 4 tweets" in msg


class TestFormatDraftReviewEvaluatorContext:
    """Tests for format_draft_review with evaluator context params."""

    def test_with_episode_type(self):
        msg = format_draft_review(
            project_name="test",
            commit_hash="abc",
            commit_message="msg",
            platform="x",
            content="hello",
            episode_type="feature_launch",
        )
        assert "Episode: feature_launch" in msg

    def test_with_angle(self):
        msg = format_draft_review(
            project_name="test",
            commit_hash="abc",
            commit_message="msg",
            platform="x",
            content="hello",
            angle="Show the developer workflow",
        )
        assert "Angle:" in msg
        assert "Show the developer workflow" in msg

    def test_with_all_context(self):
        msg = format_draft_review(
            project_name="test",
            commit_hash="abc",
            commit_message="msg",
            platform="x",
            content="hello",
            episode_type="bug_fix",
            post_category="technical",
            angle="Reliability matters",
            evaluator_reasoning="Strong commit that shows commitment to quality",
        )
        assert "Episode: bug_fix" in msg
        assert "Category: technical" in msg
        assert "Angle:" in msg
        assert "Reliability matters" in msg
        assert "Reasoning:" in msg
        assert "commitment to quality" in msg

    def test_without_context_backward_compat(self):
        """Verify backward compat -- no new params still works."""
        msg = format_draft_review(
            project_name="test",
            commit_hash="abc",
            commit_message="msg",
            platform="x",
            content="hello",
        )
        assert "Episode:" not in msg
        assert "Category:" not in msg
        assert "Angle:" not in msg
        assert "Reasoning:" not in msg
        assert "*New draft ready for review*" in msg

    def test_format_draft_review_with_media_info(self):
        """Media info line appears with trigger-style format (type + file count)."""
        msg = format_draft_review(
            project_name="my-project",
            commit_hash="abc1234",
            commit_message="Add diagram",
            platform="x",
            content="Check out the architecture",
            media_info="mermaid (1 file)",
            draft_id="draft_xyz",
        )
        assert "Media: mermaid (1 file)" in msg
        # Media line should appear before draft ID line
        media_pos = msg.index("Media:")
        draft_pos = msg.index("Draft:")
        assert media_pos < draft_pos

    def test_format_draft_review_without_media_info(self):
        """No media line when media_info is None."""
        msg = format_draft_review(
            project_name="test",
            commit_hash="abc",
            commit_message="msg",
            platform="x",
            content="hello",
        )
        assert "Media:" not in msg


class TestGetReviewButtonsNormalized:
    """Tests for get_review_buttons_normalized."""

    def test_returns_button_rows(self):
        from social_hook.messaging.base import ButtonRow

        buttons = get_review_buttons_normalized("draft_123")
        assert len(buttons) == 2
        assert all(isinstance(row, ButtonRow) for row in buttons)

    def test_button_labels(self):
        buttons = get_review_buttons_normalized("draft_abc")
        labels = [btn.label for row in buttons for btn in row.buttons]
        assert labels == ["Quick Approve", "Schedule", "Edit", "Reject"]

    def test_button_actions(self):
        buttons = get_review_buttons_normalized("draft_abc")
        actions = [btn.action for row in buttons for btn in row.buttons]
        assert actions == ["quick_approve", "schedule", "edit", "reject"]

    def test_button_payloads(self):
        buttons = get_review_buttons_normalized("draft_abc")
        payloads = [btn.payload for row in buttons for btn in row.buttons]
        assert all(p == "draft_abc" for p in payloads)

    def test_different_draft_ids(self):
        b1 = get_review_buttons_normalized("draft_1")
        b2 = get_review_buttons_normalized("draft_2")
        assert b1[0].buttons[0].payload != b2[0].buttons[0].payload


class TestPublicAPISurface:
    """Tests for module public API surface."""

    def test_public_api_surface(self):
        """Module only exposes format_draft_review and get_review_buttons_normalized."""
        import social_hook.bot.notifications as mod

        public_names = [n for n in dir(mod) if not n.startswith("_")]
        # Expect: format_draft_review, get_review_buttons_normalized, logger, logging
        assert "format_draft_review" in public_names
        assert "get_review_buttons_normalized" in public_names
        # These should NOT be in the module anymore
        assert "send_notification" not in public_names
        assert "send_notification_with_buttons" not in public_names
        assert "get_review_buttons" not in public_names
        assert "format_post_confirmation" not in public_names
        assert "format_error_notification" not in public_names
        assert "format_engagement_prompt" not in public_names
        assert "send_via_adapter" not in public_names
        assert "send_buttons_via_adapter" not in public_names

    def test_no_requests_import(self):
        """Module no longer imports requests."""
        import social_hook.bot.notifications as mod

        assert not hasattr(mod, "requests")
