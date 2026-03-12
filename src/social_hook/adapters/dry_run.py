"""Dry-run mode wrappers for adapters.

When dry_run=True, adapters return simulated success without making API calls.
"""

import tempfile
import uuid
from pathlib import Path

from social_hook.adapters.models import MediaResult, PostResult, ThreadResult


def generate_dry_run_id() -> str:
    """Generate a fake ID for dry-run mode."""
    return f"dry_run_{uuid.uuid4().hex[:12]}"


def dry_run_post_result() -> PostResult:
    """Create a simulated successful PostResult."""
    dry_id = generate_dry_run_id()
    return PostResult(
        success=True,
        external_id=dry_id,
        external_url=f"https://example.com/post/{dry_id}",
        error=None,
    )


def dry_run_thread_result(tweet_count: int) -> ThreadResult:
    """Create a simulated successful ThreadResult.

    Args:
        tweet_count: Number of tweets in the thread

    Returns:
        ThreadResult with simulated PostResults
    """
    return ThreadResult(
        success=True,
        tweet_results=[dry_run_post_result() for _ in range(tweet_count)],
        error=None,
    )


def dry_run_media_result(media_type: str = "image", output_dir: str | None = None) -> MediaResult:
    """Create a simulated successful MediaResult.

    Args:
        media_type: Type of media for filename extension
        output_dir: Directory for placeholder file (uses temp if None)

    Returns:
        MediaResult with placeholder file path
    """
    extension = {
        "mermaid": "png",
        "diagram": "png",
        "code": "png",
        "code_snippet": "png",
        "image": "png",
        "screenshot": "png",
    }.get(media_type, "png")

    dir_path = Path(output_dir) if output_dir else Path(tempfile.gettempdir())

    placeholder_path = dir_path / f"dry_run_{generate_dry_run_id()}.{extension}"

    return MediaResult(
        success=True,
        file_path=str(placeholder_path),
        error=None,
    )
