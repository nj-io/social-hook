"""Playwright browser screenshot adapter."""

import logging
import tempfile
import uuid
from pathlib import Path

from social_hook.adapters.dry_run import dry_run_media_result
from social_hook.adapters.media.base import MediaAdapter
from social_hook.adapters.models import MediaResult

logger = logging.getLogger(__name__)


class PlaywrightAdapter(MediaAdapter):
    """Browser screenshot adapter using Playwright."""

    def __init__(self, headless: bool = True, timeout: int = 30000):
        """Initialize Playwright adapter.

        Args:
            headless: Run browser in headless mode
            timeout: Page load timeout in milliseconds
        """
        self.headless = headless
        self.timeout = timeout
        self._browser = None
        self._playwright = None

    def generate(
        self,
        spec: dict,
        output_dir: str | None = None,
        dry_run: bool = False,
    ) -> MediaResult:
        """Take screenshot of webpage or element.

        Args:
            spec: Dict with 'url' (required),
                  optional 'selector', 'width', 'height', 'full_page'
            output_dir: Directory to save output file
            dry_run: If True, return placeholder path without browser

        Returns:
            MediaResult with file_path on success
        """
        if dry_run:
            return dry_run_media_result("screenshot", output_dir)

        url = spec.get("url")
        if not url:
            return MediaResult(
                success=False,
                error="Missing 'url' in spec",
            )

        selector = spec.get("selector")
        width = spec.get("width", 1280)
        height = spec.get("height", 720)
        full_page = spec.get("full_page", False)

        try:
            # Import playwright (may fail if not installed)
            from playwright.sync_api import sync_playwright
        except ImportError:
            return MediaResult(
                success=False,
                error=(
                    "Playwright not installed. Install with:\n"
                    "  pip install playwright\n"
                    "  playwright install chromium"
                ),
            )

        try:
            with sync_playwright() as p:
                try:
                    browser = p.chromium.launch(headless=self.headless)
                except Exception as e:
                    error_msg = str(e)
                    if "Executable doesn't exist" in error_msg:
                        return MediaResult(
                            success=False,
                            error=(
                                "Chromium browser not installed. Run:\n"
                                "  playwright install chromium"
                            ),
                        )
                    raise

                context = browser.new_context(viewport={"width": width, "height": height})
                page = context.new_page()

                # Navigate and wait for load
                page.goto(url, timeout=self.timeout, wait_until="networkidle")

                # Prepare output path
                dir_path = Path(output_dir) if output_dir else Path(tempfile.gettempdir())

                dir_path.mkdir(parents=True, exist_ok=True)

                filename = f"screenshot_{uuid.uuid4().hex[:8]}.png"
                file_path = dir_path / filename

                # Take screenshot
                if selector:
                    element = page.locator(selector)
                    element.screenshot(path=str(file_path))
                else:
                    page.screenshot(path=str(file_path), full_page=full_page)

                browser.close()

                return MediaResult(
                    success=True,
                    file_path=str(file_path),
                )

        except Exception as e:
            logger.error(f"Playwright screenshot failed: {e}")
            return MediaResult(
                success=False,
                error=f"Screenshot failed: {e}",
            )

    def supports(self, media_type: str) -> bool:
        """Check if adapter handles this media type.

        Args:
            media_type: Type identifier

        Returns:
            True for screenshot-related types
        """
        return media_type in ("screenshot", "webpage", "playwright")
