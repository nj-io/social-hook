"""Tests for vehicle validation and thread parsing."""

from social_hook.vehicle import parse_thread_parts, validate_draft_for_vehicle


class TestValidateDraftForVehicle:
    """Tests for validate_draft_for_vehicle() validation logic."""

    def test_non_x_platform_rejects_thread(self):
        """LinkedIn does not support threads."""
        result = validate_draft_for_vehicle("content", "thread", "linkedin", 3000)
        assert result.valid is False
        assert result.suggested_vehicle == "single"

    def test_free_tier_overflow_suggests_thread(self):
        """Free tier: >280 chars single post suggests thread."""
        result = validate_draft_for_vehicle("x" * 300, "single", "x", 280)
        assert result.valid is False
        assert result.suggested_vehicle == "thread"

    def test_free_tier_under_limit_valid(self):
        """Free tier: <=280 chars single is valid."""
        result = validate_draft_for_vehicle("x" * 100, "single", "x", 280)
        assert result.valid is True

    def test_paid_tier_long_single_valid(self):
        """Paid tier: long content single is valid (higher char limit)."""
        result = validate_draft_for_vehicle("x" * 1000, "single", "x", 25000)
        assert result.valid is True

    def test_thread_on_x_with_enough_parts(self):
        """Thread on X with 4+ parts is valid."""
        content = "1/ First\n\n2/ Second\n\n3/ Third\n\n4/ Fourth"
        result = validate_draft_for_vehicle(content, "thread", "x", 280)
        assert result.valid is True

    def test_thread_too_few_parts(self):
        """Thread with fewer than 4 parts suggests single."""
        content = "1/ First\n\n2/ Second\n\n3/ Third"
        result = validate_draft_for_vehicle(content, "thread", "x", 280, thread_min=4)
        assert result.valid is False
        assert result.suggested_vehicle == "single"

    def test_article_always_valid(self):
        """Article vehicle is always valid."""
        result = validate_draft_for_vehicle("x" * 5000, "article", "x", 280)
        assert result.valid is True

    def test_unknown_vehicle_valid(self):
        """Unknown vehicle is treated as valid."""
        result = validate_draft_for_vehicle("content", "newsletter", "x", 280)
        assert result.valid is True


class TestParseThreadParts:
    """Tests for parse_thread_parts() parsing."""

    def test_numbered_format(self):
        content = "1/ First beat\n\n2/ Second beat\n\n3/ Third beat\n\n4/ Fourth beat"
        parts = parse_thread_parts(content, "x")
        assert len(parts) == 4
        assert parts[0] == "First beat"
        assert parts[3] == "Fourth beat"

    def test_separator_format(self):
        content = "First beat\n---\nSecond beat\n---\nThird beat\n---\nFourth beat"
        parts = parse_thread_parts(content, "x")
        assert len(parts) == 4

    def test_double_newline_format(self):
        content = "First beat\n\nSecond beat\n\nThird beat\n\nFourth beat"
        parts = parse_thread_parts(content, "x")
        assert len(parts) == 4

    def test_empty_content(self):
        parts = parse_thread_parts("", "x")
        assert parts == []

    def test_single_paragraph(self):
        """Single paragraph returns single-element list."""
        parts = parse_thread_parts("Just one tweet.", "x")
        assert len(parts) == 1
        assert parts[0] == "Just one tweet."
