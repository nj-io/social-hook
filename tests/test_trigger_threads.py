"""Tests for trigger thread pipeline and format decisions (Phase A)."""

from types import SimpleNamespace

from social_hook.trigger import _needs_thread, _parse_thread_tweets


class TestNeedsThread:
    """Tests for _needs_thread format decision logic."""

    def _make_draft(self, content="short", format_hint=None, beat_count=None):
        return SimpleNamespace(
            content=content,
            format_hint=format_hint,
            beat_count=beat_count,
        )

    def test_non_x_platform_never_threads(self):
        """LinkedIn never uses threads."""
        draft = self._make_draft(format_hint="thread", beat_count=6)
        assert _needs_thread(draft, "linkedin", "free") is False

    def test_free_tier_overflow_forces_thread(self):
        """Free tier: >280 chars must thread."""
        draft = self._make_draft(content="x" * 300, format_hint="single")
        assert _needs_thread(draft, "x", "free") is True

    def test_free_tier_under_limit_single(self):
        """Free tier: <=280 chars stays single."""
        draft = self._make_draft(content="x" * 100)
        assert _needs_thread(draft, "x", "free") is False

    def test_paid_tier_no_overflow_forced(self):
        """Paid tier: long content doesn't force thread."""
        draft = self._make_draft(content="x" * 1000, format_hint="single")
        assert _needs_thread(draft, "x", "premium") is False

    def test_explicit_single_hint_respected(self):
        """Drafter says single → respect it."""
        draft = self._make_draft(content="x" * 200, format_hint="single")
        assert _needs_thread(draft, "x", "premium") is False

    def test_explicit_thread_hint_respected(self):
        """Drafter says thread → thread."""
        draft = self._make_draft(format_hint="thread")
        assert _needs_thread(draft, "x", "free") is True

    def test_explicit_thread_hint_paid(self):
        """Drafter says thread on paid tier → thread."""
        draft = self._make_draft(format_hint="thread")
        assert _needs_thread(draft, "x", "premium") is True

    def test_four_beats_triggers_thread(self):
        """4+ beats → thread candidate."""
        draft = self._make_draft(beat_count=4)
        assert _needs_thread(draft, "x", "free") is True

    def test_three_beats_no_thread(self):
        """3 beats is not enough for thread."""
        draft = self._make_draft(beat_count=3)
        assert _needs_thread(draft, "x", "free") is False

    def test_no_hints_short_content_single(self):
        """No hints, short content → single."""
        draft = self._make_draft(content="Quick update")
        assert _needs_thread(draft, "x", "free") is False

    def test_free_tier_overflow_overrides_single_hint(self):
        """Free tier overflow overrides even explicit 'single' hint."""
        draft = self._make_draft(content="x" * 500, format_hint="single")
        assert _needs_thread(draft, "x", "free") is True

    def test_paid_tier_postmortem_thread(self):
        """Paid tier: drafter recommends thread for postmortem."""
        draft = self._make_draft(format_hint="thread", beat_count=5)
        assert _needs_thread(draft, "x", "premium_plus") is True

    def test_paid_tier_milestone_single(self):
        """Paid tier: punchy milestone stays single."""
        draft = self._make_draft(content="Shipped v2!", format_hint="single")
        assert _needs_thread(draft, "x", "basic") is False


class TestParseThreadTweets:
    """Tests for _parse_thread_tweets parsing."""

    def test_numbered_format(self):
        content = "1/ First beat\n\n2/ Second beat\n\n3/ Third beat\n\n4/ Fourth beat"
        tweets = _parse_thread_tweets(content)
        assert len(tweets) == 4
        assert tweets[0] == "First beat"
        assert tweets[3] == "Fourth beat"

    def test_separator_format(self):
        content = "First beat\n---\nSecond beat\n---\nThird beat\n---\nFourth beat"
        tweets = _parse_thread_tweets(content)
        assert len(tweets) == 4

    def test_double_newline_format(self):
        content = "First beat\n\nSecond beat\n\nThird beat\n\nFourth beat"
        tweets = _parse_thread_tweets(content)
        assert len(tweets) == 4

    def test_empty_content(self):
        tweets = _parse_thread_tweets("")
        assert tweets == []

    def test_single_paragraph(self):
        """Single paragraph returns single-element list."""
        tweets = _parse_thread_tweets("Just one tweet.")
        assert len(tweets) == 1
        assert tweets[0] == "Just one tweet."
