"""Tests for PlaywrightAdapter (T9).

Source: WS3_ADAPTERS.md T9 (lines 196-204)
Source: WS3_ASSUMPTIONS.md A9-A10
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

from social_hook.adapters.media.playwright import PlaywrightAdapter
from social_hook.adapters.models import MediaResult


# =============================================================================
# T9: PlaywrightAdapter
# =============================================================================


class TestPlaywrightAdapterSupports:
    """T9: PlaywrightAdapter supports() media types."""

    def test_supports_screenshot(self):
        """supports('screenshot') returns True."""
        adapter = PlaywrightAdapter()
        assert adapter.supports("screenshot") is True

    def test_supports_webpage(self):
        """supports('webpage') returns True."""
        adapter = PlaywrightAdapter()
        assert adapter.supports("webpage") is True

    def test_supports_playwright(self):
        """supports('playwright') returns True."""
        adapter = PlaywrightAdapter()
        assert adapter.supports("playwright") is True

    def test_supports_unknown(self):
        """supports('mermaid') returns False."""
        adapter = PlaywrightAdapter()
        assert adapter.supports("mermaid") is False


class TestPlaywrightAdapterGenerate:
    """T9: PlaywrightAdapter screenshot generation."""

    def test_missing_url(self):
        """Missing 'url' in spec returns error."""
        adapter = PlaywrightAdapter()
        result = adapter.generate({})
        assert result.success is False
        assert "Missing" in result.error

    def test_dry_run(self):
        """dry_run=True returns placeholder path without launching browser."""
        adapter = PlaywrightAdapter()
        result = adapter.generate(
            {"url": "https://example.com"}, dry_run=True
        )
        assert result.success is True
        assert result.file_path is not None

    def test_dry_run_with_dimensions(self):
        """dry_run=True works with width/height params."""
        adapter = PlaywrightAdapter()
        result = adapter.generate(
            {"url": "https://example.com", "width": 800, "height": 600},
            dry_run=True,
        )
        assert result.success is True

    def test_playwright_not_installed(self):
        """Missing playwright package returns clear error message."""
        adapter = PlaywrightAdapter()

        # Temporarily remove playwright from sys.modules to force ImportError
        saved_modules = {}
        for key in list(sys.modules.keys()):
            if key.startswith("playwright"):
                saved_modules[key] = sys.modules.pop(key)

        try:
            with patch.dict(sys.modules, {"playwright.sync_api": None}):
                with patch("builtins.__import__", side_effect=_block_playwright_import):
                    result = adapter.generate({"url": "https://example.com"})
        finally:
            sys.modules.update(saved_modules)

        assert result.success is False
        assert "Playwright" in result.error or "playwright" in result.error

    def test_browser_not_installed(self):
        """Browser not installed returns error with install instructions."""
        adapter = PlaywrightAdapter()

        mock_pw = MagicMock()
        mock_pw.chromium.launch.side_effect = Exception(
            "Executable doesn't exist at /path/to/chromium"
        )

        mock_sync_pw = MagicMock()
        mock_sync_pw.return_value.__enter__ = MagicMock(return_value=mock_pw)
        mock_sync_pw.return_value.__exit__ = MagicMock(return_value=False)

        with patch.dict(
            sys.modules,
            {"playwright.sync_api": MagicMock(sync_playwright=mock_sync_pw)},
        ):
            result = adapter.generate({"url": "https://example.com"})

        assert result.success is False
        assert "chromium" in result.error.lower()
        assert "install" in result.error.lower()

    def test_screenshot_success(self, tmp_path):
        """Successful screenshot saves PNG and returns file_path."""
        # Build mock chain: sync_playwright() -> context manager -> p -> browser -> context -> page
        mock_page = MagicMock()
        mock_context = MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context

        mock_pw = MagicMock()
        mock_pw.chromium.launch.return_value = mock_browser

        mock_sync_pw = MagicMock()
        mock_sync_pw.return_value.__enter__ = MagicMock(return_value=mock_pw)
        mock_sync_pw.return_value.__exit__ = MagicMock(return_value=False)

        # Make page.screenshot create a real file
        def fake_screenshot(path, **kwargs):
            with open(path, "wb") as f:
                f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        mock_page.screenshot.side_effect = fake_screenshot

        with patch.dict(
            sys.modules,
            {"playwright.sync_api": MagicMock(sync_playwright=mock_sync_pw)},
        ):
            adapter = PlaywrightAdapter()
            result = adapter.generate(
                {"url": "https://example.com"},
                output_dir=str(tmp_path),
            )

        assert result.success is True
        assert result.file_path is not None
        mock_page.goto.assert_called_once()

    def test_networkidle_wait(self, tmp_path):
        """Screenshot waits for networkidle before capturing."""
        mock_page = MagicMock()
        mock_context = MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context

        mock_pw = MagicMock()
        mock_pw.chromium.launch.return_value = mock_browser

        mock_sync_pw = MagicMock()
        mock_sync_pw.return_value.__enter__ = MagicMock(return_value=mock_pw)
        mock_sync_pw.return_value.__exit__ = MagicMock(return_value=False)

        def fake_screenshot(path, **kwargs):
            with open(path, "wb") as f:
                f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        mock_page.screenshot.side_effect = fake_screenshot

        with patch.dict(
            sys.modules,
            {"playwright.sync_api": MagicMock(sync_playwright=mock_sync_pw)},
        ):
            adapter = PlaywrightAdapter()
            adapter.generate(
                {"url": "https://example.com"},
                output_dir=str(tmp_path),
            )

        # Verify goto was called with wait_until="networkidle"
        mock_page.goto.assert_called_once()
        call_kwargs = mock_page.goto.call_args
        assert call_kwargs.kwargs.get("wait_until") == "networkidle"

    def test_element_selector_screenshot(self, tmp_path):
        """When selector is provided, screenshots the element not the page."""
        mock_element = MagicMock()
        mock_page = MagicMock()
        mock_page.locator.return_value = mock_element
        mock_context = MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context

        mock_pw = MagicMock()
        mock_pw.chromium.launch.return_value = mock_browser

        mock_sync_pw = MagicMock()
        mock_sync_pw.return_value.__enter__ = MagicMock(return_value=mock_pw)
        mock_sync_pw.return_value.__exit__ = MagicMock(return_value=False)

        def fake_screenshot(path, **kwargs):
            with open(path, "wb") as f:
                f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        mock_element.screenshot.side_effect = fake_screenshot

        with patch.dict(
            sys.modules,
            {"playwright.sync_api": MagicMock(sync_playwright=mock_sync_pw)},
        ):
            adapter = PlaywrightAdapter()
            result = adapter.generate(
                {"url": "https://example.com", "selector": "#frame"},
                output_dir=str(tmp_path),
            )

        assert result.success is True
        mock_page.locator.assert_called_once_with("#frame")
        mock_element.screenshot.assert_called_once()
        # Page-level screenshot should NOT have been called
        mock_page.screenshot.assert_not_called()


def _block_playwright_import(name, *args, **kwargs):
    """Import hook that blocks playwright imports."""
    if "playwright" in name:
        raise ImportError(f"No module named '{name}'")
    return original_import(name, *args, **kwargs)


original_import = __import__
