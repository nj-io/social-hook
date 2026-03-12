"""Mermaid diagram adapter using mermaid.ink API."""

import base64
import json
import logging
import shutil
import subprocess
import tempfile
import uuid
import zlib
from pathlib import Path

import requests

from social_hook.adapters.dry_run import dry_run_media_result
from social_hook.adapters.media.base import MediaAdapter
from social_hook.adapters.models import MediaResult

logger = logging.getLogger(__name__)

# mermaid.ink endpoints
MERMAID_INK_BASE = "https://mermaid.ink"


def encode_mermaid(diagram_code: str, theme: str = "default") -> str:
    """Encode mermaid diagram using PAKO compression.

    mermaid.ink requires PAKO compression + base64, not simple base64.

    Args:
        diagram_code: Mermaid diagram code
        theme: Mermaid theme (default, dark, forest, neutral)

    Returns:
        Encoded string prefixed with 'pako:'
    """
    payload = {"code": diagram_code, "mermaid": {"theme": theme}}
    byte_str = bytes(json.dumps(payload), "ascii")

    # PAKO compression settings
    compress = zlib.compressobj(9, zlib.DEFLATED, 15, 8, zlib.Z_DEFAULT_STRATEGY)
    deflated = compress.compress(byte_str) + compress.flush()

    # URL-safe base64
    encoded = base64.b64encode(deflated).decode("ascii")
    encoded = encoded.replace("+", "-").replace("/", "_")

    return "pako:" + encoded


class MermaidAdapter(MediaAdapter):
    """Mermaid diagram generator using mermaid.ink API."""

    def __init__(self, timeout: int = 30):
        """Initialize Mermaid adapter.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout

    def generate(
        self,
        spec: dict,
        output_dir: str | None = None,
        dry_run: bool = False,
    ) -> MediaResult:
        """Generate mermaid diagram image.

        Args:
            spec: Dict with 'diagram' or 'code' (mermaid code),
                  optional 'theme', 'format', 'width', 'height'
            output_dir: Directory to save output file
            dry_run: If True, return placeholder path

        Returns:
            MediaResult with file_path on success
        """
        if dry_run:
            return dry_run_media_result("mermaid", output_dir)

        # Get diagram code
        diagram_code = spec.get("diagram") or spec.get("code")
        if not diagram_code:
            return MediaResult(
                success=False,
                error="Missing 'diagram' or 'code' in spec",
            )

        # Get options
        theme = spec.get("theme", "default")
        output_format = spec.get("format", "png")
        width = spec.get("width")
        height = spec.get("height")

        # Try local mmdc CLI first
        mmdc_result = self._try_mmdc(diagram_code, output_dir, output_format, theme)
        if mmdc_result:
            return mmdc_result

        # Fall back to mermaid.ink API
        encoded = encode_mermaid(diagram_code, theme)

        # Build URL
        url = f"{MERMAID_INK_BASE}/img/{encoded}"

        # Add query parameters
        params = []
        if output_format and output_format != "jpeg":
            params.append(f"type={output_format}")
        if width:
            params.append(f"width={width}")
        if height:
            params.append(f"height={height}")

        if params:
            url += "?" + "&".join(params)

        try:
            response = requests.get(url, timeout=self.timeout)

            if response.status_code == 200:
                # Save to file
                dir_path = Path(output_dir) if output_dir else Path(tempfile.gettempdir())

                dir_path.mkdir(parents=True, exist_ok=True)

                # Generate unique filename
                filename = f"mermaid_{uuid.uuid4().hex[:8]}.{output_format}"
                file_path = dir_path / filename

                file_path.write_bytes(response.content)

                return MediaResult(
                    success=True,
                    file_path=str(file_path),
                )
            else:
                logger.warning(f"mermaid.ink request failed: {response.status_code}")
                return MediaResult(
                    success=False,
                    error=f"mermaid.ink returned {response.status_code}: {response.text[:200]}",
                )

        except requests.RequestException as e:
            logger.error(f"mermaid.ink request error: {e}")
            return MediaResult(
                success=False,
                error=f"Request failed: {e}",
            )

    def _try_mmdc(
        self,
        diagram_code: str,
        output_dir: str | None,
        output_format: str,
        theme: str,
    ) -> MediaResult | None:
        """Try to generate diagram using local mmdc CLI.

        Args:
            diagram_code: Mermaid diagram source
            output_dir: Output directory
            output_format: Output format (png, svg)
            theme: Mermaid theme

        Returns:
            MediaResult on success, None if mmdc unavailable or failed
        """
        mmdc_path = shutil.which("mmdc")
        if not mmdc_path:
            return None

        dir_path = Path(output_dir) if output_dir else Path(tempfile.gettempdir())
        dir_path.mkdir(parents=True, exist_ok=True)

        filename = f"mermaid_{uuid.uuid4().hex[:8]}.{output_format}"
        file_path = dir_path / filename

        # Write diagram to temp file
        input_file = dir_path / f"mermaid_input_{uuid.uuid4().hex[:8]}.mmd"
        try:
            input_file.write_text(diagram_code)

            cmd = [mmdc_path, "-i", str(input_file), "-o", str(file_path)]
            if theme and theme != "default":
                cmd.extend(["-t", theme])

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0 and file_path.exists():
                return MediaResult(success=True, file_path=str(file_path))
            else:
                logger.debug(f"mmdc failed (rc={result.returncode}): {result.stderr}")
                return None

        except (subprocess.TimeoutExpired, OSError) as e:
            logger.debug(f"mmdc error: {e}")
            return None
        finally:
            input_file.unlink(missing_ok=True)

    @classmethod
    def spec_schema(cls) -> dict:
        """Return spec schema for Mermaid diagrams."""
        return {
            "required": {"diagram": "Mermaid markup string"},
            "optional": {
                "theme": "default|dark|forest|neutral",
                "format": "png|svg",
                "width": "int",
                "height": "int",
            },
        }

    def preview_text(self, spec: dict) -> str:
        """Return human-readable preview of the diagram spec."""
        return spec.get("diagram") or spec.get("code") or "No diagram specified"

    def supports(self, media_type: str) -> bool:
        """Check if adapter handles this media type.

        Args:
            media_type: Type identifier

        Returns:
            True for mermaid-related types
        """
        return media_type in ("mermaid", "diagram", "flowchart")
