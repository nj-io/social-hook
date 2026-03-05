"""Nano Banana Pro (Gemini) image generation adapter."""

import base64
import logging
import tempfile
import uuid
from pathlib import Path

import requests

from social_hook.adapters.dry_run import dry_run_media_result
from social_hook.adapters.media.base import MediaAdapter
from social_hook.adapters.models import MediaResult

logger = logging.getLogger(__name__)

# Gemini API endpoint for image generation
GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent"
)


class NanaBananaAdapter(MediaAdapter):
    """Image generation adapter using Google's Gemini API."""

    def __init__(self, api_key: str, timeout: int = 60):
        """Initialize Nano Banana adapter.

        Args:
            api_key: Gemini API key (GEMINI_API_KEY)
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.timeout = timeout

    def generate(
        self,
        spec: dict,
        output_dir: str | None = None,
        dry_run: bool = False,
    ) -> MediaResult:
        """Generate image from text prompt.

        Args:
            spec: Dict with 'prompt' (image description)
            output_dir: Directory to save output file
            dry_run: If True, return placeholder path

        Returns:
            MediaResult with file_path on success
        """
        if dry_run:
            return dry_run_media_result("image", output_dir)

        prompt = spec.get("prompt")
        if not prompt:
            return MediaResult(
                success=False,
                error="Missing 'prompt' in spec",
            )

        # Build request
        url = f"{GEMINI_ENDPOINT}?key={self.api_key}"
        body = {
            "contents": [
                {
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "responseModalities": ["image", "text"],
                "responseMimeType": "text/plain",
            },
        }

        try:
            response = requests.post(
                url,
                json=body,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout,
            )

            if response.status_code == 200:
                data = response.json()

                # Extract image from response
                candidates = data.get("candidates", [])
                if not candidates:
                    return MediaResult(
                        success=False,
                        error="No candidates in response",
                    )

                content = candidates[0].get("content", {})
                parts = content.get("parts", [])

                # Find image part
                image_data = None
                for part in parts:
                    if "inlineData" in part:
                        inline = part["inlineData"]
                        if inline.get("mimeType", "").startswith("image/"):
                            image_data = inline.get("data")
                            mime_type = inline.get("mimeType", "image/png")
                            break

                if not image_data:
                    return MediaResult(
                        success=False,
                        error="No image data in response",
                    )

                # Decode and save image
                image_bytes = base64.b64decode(image_data)

                dir_path = Path(output_dir) if output_dir else Path(tempfile.gettempdir())

                dir_path.mkdir(parents=True, exist_ok=True)

                # Determine extension from mime type
                ext = mime_type.split("/")[-1] if "/" in mime_type else "png"
                filename = f"nanabananapro_{uuid.uuid4().hex[:8]}.{ext}"
                file_path = dir_path / filename

                file_path.write_bytes(image_bytes)

                return MediaResult(
                    success=True,
                    file_path=str(file_path),
                )

            else:
                error_msg = response.json().get("error", {}).get("message", response.text)
                logger.warning(f"Gemini API request failed: {response.status_code} - {error_msg}")
                return MediaResult(
                    success=False,
                    error=f"Gemini API error: {error_msg}",
                )

        except requests.RequestException as e:
            logger.error(f"Gemini API request error: {e}")
            return MediaResult(
                success=False,
                error=f"Request failed: {e}",
            )

    def supports(self, media_type: str) -> bool:
        """Check if adapter handles this media type.

        Args:
            media_type: Type identifier

        Returns:
            True for AI image types
        """
        return media_type in ("image", "ai_image", "nano_banana")

    def validate(self) -> tuple[bool, str]:
        """Validate API key by making a simple request.

        Returns:
            (True, "connected") on success, (False, error) on failure
        """
        # Make a minimal request to validate the key
        url = f"{GEMINI_ENDPOINT}?key={self.api_key}"
        body = {
            "contents": [{"parts": [{"text": "test"}]}],
        }

        try:
            response = requests.post(
                url,
                json=body,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )

            if response.status_code == 200:
                return (True, "connected")
            elif response.status_code == 401:
                return (False, "Invalid API key")
            else:
                error_msg = response.json().get("error", {}).get("message", "Unknown error")
                return (False, error_msg)

        except requests.RequestException as e:
            return (False, f"Request failed: {e}")
