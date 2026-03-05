"""Ray.so code snippet screenshot adapter."""

import base64
import logging
from urllib.parse import quote

from social_hook.adapters.dry_run import dry_run_media_result
from social_hook.adapters.media.base import MediaAdapter
from social_hook.adapters.media.playwright import PlaywrightAdapter
from social_hook.adapters.models import MediaResult

logger = logging.getLogger(__name__)

# ray.so base URL
RAYSO_BASE = "https://ray.so"

# Default settings
DEFAULT_THEME = "candy"
DEFAULT_PADDING = 64
DEFAULT_LANGUAGE = "auto"


def build_rayso_url(
    code: str,
    language: str = DEFAULT_LANGUAGE,
    theme: str = DEFAULT_THEME,
    padding: int = DEFAULT_PADDING,
    background: bool = True,
    dark_mode: bool = True,
    title: str | None = None,
    line_numbers: bool = False,
) -> str:
    """Build ray.so URL with hash fragment parameters.

    ray.so uses hash fragment (#) for parameters, not query string (?).

    Args:
        code: Code snippet to render
        language: Language for syntax highlighting
        theme: Color theme (candy, breeze, midnight, etc.)
        padding: Padding in pixels (16, 32, 64, 128)
        background: Show gradient background
        dark_mode: Use dark color scheme
        title: Filename in title bar
        line_numbers: Show line numbers

    Returns:
        Complete ray.so URL with hash fragment
    """
    # Base64 encode the code
    encoded_code = base64.b64encode(code.encode()).decode()

    # Build hash fragment parameters
    params = [
        f"code={quote(encoded_code, safe='')}",
        f"language={quote(language, safe='')}",
        f"theme={quote(theme, safe='')}",
        f"padding={padding}",
        f"background={'true' if background else 'false'}",
        f"darkMode={'true' if dark_mode else 'false'}",
    ]

    if title:
        params.append(f"title={quote(title, safe='')}")

    if line_numbers:
        params.append("lineNumbers=true")

    return f"{RAYSO_BASE}/#{('&').join(params)}"


class RaySoAdapter(MediaAdapter):
    """Code snippet screenshot adapter using ray.so and Playwright."""

    def __init__(self, playwright_adapter: PlaywrightAdapter | None = None):
        """Initialize RaySo adapter.

        Args:
            playwright_adapter: Optional PlaywrightAdapter instance to reuse
        """
        self.playwright = playwright_adapter or PlaywrightAdapter()

    def generate(
        self,
        spec: dict,
        output_dir: str | None = None,
        dry_run: bool = False,
    ) -> MediaResult:
        """Generate code snippet image using ray.so.

        Args:
            spec: Dict with 'code' (required),
                  optional 'language', 'theme', 'padding', 'background',
                  'dark_mode', 'title', 'line_numbers'
            output_dir: Directory to save output file
            dry_run: If True, return placeholder path

        Returns:
            MediaResult with file_path on success
        """
        if dry_run:
            return dry_run_media_result("code", output_dir)

        code = spec.get("code")
        if not code:
            return MediaResult(
                success=False,
                error="Missing 'code' in spec",
            )

        # Build ray.so URL
        url = build_rayso_url(
            code=code,
            language=spec.get("language", DEFAULT_LANGUAGE),
            theme=spec.get("theme", DEFAULT_THEME),
            padding=spec.get("padding", DEFAULT_PADDING),
            background=spec.get("background", True),
            dark_mode=spec.get("dark_mode", True),
            title=spec.get("title"),
            line_numbers=spec.get("line_numbers", False),
        )

        # Use Playwright to screenshot
        # ray.so renders to a specific frame element
        playwright_spec = {
            "url": url,
            "selector": "#frame",
            "width": 1280,
            "height": 800,
        }

        result = self.playwright.generate(playwright_spec, output_dir=output_dir)

        # If selector-based screenshot fails, try full viewport
        if not result.success and result.error and "locator" in result.error.lower():
            logger.info("Retrying ray.so screenshot with full viewport")
            fallback_spec = {**playwright_spec, "selector": None}
            result = self.playwright.generate(fallback_spec, output_dir=output_dir)

        return result

    def supports(self, media_type: str) -> bool:
        """Check if adapter handles this media type.

        Args:
            media_type: Type identifier

        Returns:
            True for code-related types
        """
        return media_type in ("code", "code_snippet", "ray_so")
