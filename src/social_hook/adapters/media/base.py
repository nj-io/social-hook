"""Abstract base class for media adapters."""

from abc import ABC, abstractmethod

from social_hook.adapters.models import MediaResult


class MediaAdapter(ABC):
    """Abstract interface for media generation."""

    @abstractmethod
    def generate(
        self,
        spec: dict,
        output_dir: str | None = None,
        dry_run: bool = False,
    ) -> MediaResult:
        """Generate media from specification.

        Args:
            spec: Media-specific configuration dict
            output_dir: Optional directory to save output file
            dry_run: If True, return placeholder path without generation

        Returns:
            MediaResult with success status and file_path
        """
        pass

    @classmethod
    def spec_schema(cls) -> dict:
        """Return spec schema: {"required": {...}, "optional": {...}}."""
        return {"required": {}, "optional": {}}

    def preview_text(self, spec: dict) -> str:
        """Return human-readable preview of what will be generated."""
        return str(spec)

    @abstractmethod
    def supports(self, media_type: str) -> bool:
        """Check if adapter handles this media type.

        Args:
            media_type: Type identifier (e.g., "mermaid", "code", "image")

        Returns:
            True if this adapter can generate the media type
        """
        pass
