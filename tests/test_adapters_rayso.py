"""Tests for RaySoAdapter (T10).

Source: WS3_ADAPTERS.md T10 (lines 206-213)
Source: WS3_ASSUMPTIONS.md A8 (lines 317-348) - ray.so URL format
"""

import base64
from unittest.mock import MagicMock, patch

import pytest

from social_hook.adapters.media.rayso import RaySoAdapter, build_rayso_url
from social_hook.adapters.models import MediaResult


# =============================================================================
# T10: build_rayso_url
# =============================================================================


class TestBuildRaySoUrl:
    """T10: ray.so URL building with hash fragment."""

    def test_uses_hash_fragment(self):
        """URL uses hash fragment (#), not query params (?)."""
        url = build_rayso_url("print('hello')")
        assert "#" in url
        # Hash fragment should come after the base URL
        base, fragment = url.split("#", 1)
        assert base == "https://ray.so/"
        assert "?" not in base

    def test_code_is_base64_encoded(self):
        """Code parameter is base64 encoded."""
        code = "console.log('hello')"
        url = build_rayso_url(code)
        expected_b64 = base64.b64encode(code.encode()).decode()
        assert expected_b64 in url or expected_b64.replace("=", "%3D") in url

    def test_default_language(self):
        """Default language is 'auto'."""
        url = build_rayso_url("x = 1")
        assert "language=auto" in url

    def test_custom_language(self):
        """Custom language parameter is included."""
        url = build_rayso_url("def foo():", language="python")
        assert "language=python" in url

    def test_default_theme(self):
        """Default theme is 'candy'."""
        url = build_rayso_url("x = 1")
        assert "theme=candy" in url

    def test_custom_theme(self):
        """Custom theme parameter is included."""
        url = build_rayso_url("x = 1", theme="breeze")
        assert "theme=breeze" in url

    def test_padding(self):
        """Padding parameter is included."""
        url = build_rayso_url("x = 1", padding=32)
        assert "padding=32" in url

    def test_dark_mode(self):
        """darkMode parameter is included."""
        url = build_rayso_url("x = 1", dark_mode=True)
        assert "darkMode=true" in url

        url_light = build_rayso_url("x = 1", dark_mode=False)
        assert "darkMode=false" in url_light

    def test_background(self):
        """background parameter is included."""
        url = build_rayso_url("x = 1", background=False)
        assert "background=false" in url

    def test_title(self):
        """title parameter is included when provided."""
        url = build_rayso_url("x = 1", title="main.py")
        assert "title=main.py" in url

    def test_no_title_by_default(self):
        """title parameter is omitted by default."""
        url = build_rayso_url("x = 1")
        assert "title=" not in url

    def test_line_numbers(self):
        """lineNumbers parameter when enabled."""
        url = build_rayso_url("x = 1", line_numbers=True)
        assert "lineNumbers=true" in url

    def test_no_line_numbers_by_default(self):
        """lineNumbers omitted when False (default)."""
        url = build_rayso_url("x = 1")
        assert "lineNumbers" not in url


# =============================================================================
# T10: RaySoAdapter - supports()
# =============================================================================


class TestRaySoAdapterSupports:
    """T10: RaySoAdapter supports() media types."""

    def test_supports_code(self):
        """supports('code') returns True."""
        adapter = RaySoAdapter()
        assert adapter.supports("code") is True

    def test_supports_code_snippet(self):
        """supports('code_snippet') returns True."""
        adapter = RaySoAdapter()
        assert adapter.supports("code_snippet") is True

    def test_supports_ray_so(self):
        """supports('ray_so') returns True."""
        adapter = RaySoAdapter()
        assert adapter.supports("ray_so") is True

    def test_supports_unknown(self):
        """supports('mermaid') returns False."""
        adapter = RaySoAdapter()
        assert adapter.supports("mermaid") is False


# =============================================================================
# T10: RaySoAdapter - Generation
# =============================================================================


class TestRaySoAdapterGenerate:
    """T10: RaySoAdapter generation."""

    def test_missing_code(self):
        """Missing 'code' in spec returns error."""
        adapter = RaySoAdapter()
        result = adapter.generate({})
        assert result.success is False
        assert "Missing" in result.error

    def test_dry_run(self):
        """dry_run=True returns placeholder path without browser."""
        adapter = RaySoAdapter()
        result = adapter.generate(
            {"code": "def foo():", "language": "python"},
            dry_run=True,
        )
        assert result.success is True
        assert result.file_path is not None

    def test_delegates_to_playwright(self):
        """generate() calls PlaywrightAdapter with ray.so URL."""
        mock_pw = MagicMock()
        mock_pw.generate.return_value = MediaResult(
            success=True, file_path="/tmp/screenshot.png"
        )

        adapter = RaySoAdapter(playwright_adapter=mock_pw)
        result = adapter.generate(
            {"code": "print('hello')", "language": "python", "theme": "candy"}
        )

        # Should have called playwright.generate with a spec containing ray.so URL
        mock_pw.generate.assert_called()
        call_spec = mock_pw.generate.call_args.args[0]
        assert "ray.so" in call_spec["url"]
        assert "#" in call_spec["url"]

    def test_passes_theme_to_url(self):
        """Theme from spec is passed to ray.so URL."""
        mock_pw = MagicMock()
        mock_pw.generate.return_value = MediaResult(success=True, file_path="/tmp/test.png")

        adapter = RaySoAdapter(playwright_adapter=mock_pw)
        adapter.generate(
            {"code": "x = 1", "language": "python", "theme": "midnight"}
        )

        call_spec = mock_pw.generate.call_args.args[0]
        assert "theme=midnight" in call_spec["url"]

    def test_passes_language_to_url(self):
        """Language from spec is passed to ray.so URL."""
        mock_pw = MagicMock()
        mock_pw.generate.return_value = MediaResult(success=True, file_path="/tmp/test.png")

        adapter = RaySoAdapter(playwright_adapter=mock_pw)
        adapter.generate(
            {"code": "const x = 1;", "language": "typescript"}
        )

        call_spec = mock_pw.generate.call_args.args[0]
        assert "language=typescript" in call_spec["url"]


# =============================================================================
# T10: RaySoAdapter - Selector & Viewport
# =============================================================================


class TestRaySoAdapterRendering:
    """T10: RaySoAdapter #frame selector and viewport behavior."""

    def test_passes_frame_selector(self):
        """generate() passes selector='#frame' to PlaywrightAdapter."""
        mock_pw = MagicMock()
        mock_pw.generate.return_value = MediaResult(
            success=True, file_path="/tmp/test.png"
        )

        adapter = RaySoAdapter(playwright_adapter=mock_pw)
        adapter.generate({"code": "x = 1"})

        call_spec = mock_pw.generate.call_args.args[0]
        assert call_spec["selector"] == "#frame"

    def test_viewport_dimensions(self):
        """ray.so screenshots use 1280x800 viewport for proper rendering."""
        mock_pw = MagicMock()
        mock_pw.generate.return_value = MediaResult(
            success=True, file_path="/tmp/test.png"
        )

        adapter = RaySoAdapter(playwright_adapter=mock_pw)
        adapter.generate({"code": "x = 1"})

        call_spec = mock_pw.generate.call_args.args[0]
        assert call_spec["width"] == 1280
        assert call_spec["height"] == 800

    def test_selector_fallback_on_locator_error(self):
        """When #frame selector fails, retries with full viewport."""
        mock_pw = MagicMock()
        # First call fails with locator error, second succeeds
        mock_pw.generate.side_effect = [
            MediaResult(success=False, error="Locator '#frame' not found"),
            MediaResult(success=True, file_path="/tmp/screenshot.png"),
        ]

        adapter = RaySoAdapter(playwright_adapter=mock_pw)
        result = adapter.generate({"code": "x = 1", "language": "python"})

        assert result.success is True
        assert mock_pw.generate.call_count == 2

        # First call has selector
        first_spec = mock_pw.generate.call_args_list[0].args[0]
        assert first_spec["selector"] == "#frame"

        # Second call has no selector (full viewport)
        second_spec = mock_pw.generate.call_args_list[1].args[0]
        assert second_spec["selector"] is None

    def test_non_locator_error_not_retried(self):
        """Non-locator errors are not retried with fallback."""
        mock_pw = MagicMock()
        mock_pw.generate.return_value = MediaResult(
            success=False, error="Screenshot failed: timeout"
        )

        adapter = RaySoAdapter(playwright_adapter=mock_pw)
        result = adapter.generate({"code": "x = 1"})

        assert result.success is False
        assert mock_pw.generate.call_count == 1  # No retry
