"""Tests for social_hook.parsing safe parsing utilities."""

import logging

from social_hook.parsing import check_unknown_keys, safe_int, safe_json_loads


class TestSafeJsonLoads:
    """Tests for safe_json_loads."""

    def test_safe_json_loads_valid(self):
        """Valid JSON string is parsed correctly."""
        result = safe_json_loads('{"a": 1}', "test")
        assert result == {"a": 1}

    def test_safe_json_loads_invalid_returns_default(self, caplog):
        """Invalid JSON returns default and logs warning."""
        with caplog.at_level(logging.WARNING):
            result = safe_json_loads("not json", "test", default=[])

        assert result == []
        assert "JSON parse failed" in caplog.text
        assert "test" in caplog.text

    def test_safe_json_loads_none_input(self):
        """None input returns default (None) without crashing."""
        result = safe_json_loads(None, "test")
        assert result is None

    def test_safe_json_loads_none_input_custom_default(self):
        """None input returns the specified default."""
        result = safe_json_loads(None, "test", default={})
        assert result == {}


class TestSafeInt:
    """Tests for safe_int."""

    def test_safe_int_valid(self):
        """Valid integer string is parsed correctly."""
        result = safe_int("42", 0, "test")
        assert result == 42

    def test_safe_int_invalid_returns_default(self, caplog):
        """Non-numeric string returns default and logs warning."""
        with caplog.at_level(logging.WARNING):
            result = safe_int("abc", 0, "test")

        assert result == 0
        assert "int() parse failed" in caplog.text
        assert "test" in caplog.text

    def test_safe_int_float_string(self):
        """Float string returns default (not truncated via int(float()))."""
        result = safe_int("3.5", 0, "test")
        assert result == 0


class TestCheckUnknownKeys:
    """Tests for check_unknown_keys."""

    def test_check_unknown_keys_warns(self, caplog):
        """Unknown keys trigger a warning mentioning the unknown key."""
        with caplog.at_level(logging.WARNING):
            check_unknown_keys({"a": 1, "b": 2, "c": 3}, {"a", "b"}, "test")

        assert "Unknown keys" in caplog.text
        assert "c" in caplog.text

    def test_check_unknown_keys_no_warning_when_clean(self, caplog):
        """No warning when all keys are known."""
        with caplog.at_level(logging.WARNING):
            check_unknown_keys({"a": 1}, {"a", "b"}, "test")

        assert "Unknown keys" not in caplog.text
