"""Abstract base class for platform adapters."""

from abc import ABC, abstractmethod

from social_hook.adapters.models import (
    PostCapability,
    PostReference,
    PostResult,
    ReferenceType,
)


class PlatformAdapter(ABC):
    """Abstract interface for social media platforms."""

    @abstractmethod
    def post(
        self,
        content: str,
        media_paths: list[str] | None = None,
        dry_run: bool = False,
    ) -> PostResult:
        """Post single content item.

        Args:
            content: Text content to post
            media_paths: Optional list of media file paths to attach
            dry_run: If True, return simulated success without API call

        Returns:
            PostResult with success status and optional external_id/url
        """
        pass

    @abstractmethod
    def post_thread(self, tweets: list[dict], dry_run: bool = False) -> PostResult:
        """Post a thread of connected posts.

        Args:
            tweets: List of dicts with 'content' and optional 'media_paths'
            dry_run: If True, return simulated success without API calls

        Returns:
            PostResult with part_results for per-tweet results
        """
        pass

    @abstractmethod
    def delete(self, external_id: str) -> bool:
        """Delete a post by its platform ID.

        Args:
            external_id: Platform-specific post identifier

        Returns:
            True if deletion succeeded
        """
        pass

    @abstractmethod
    def get_rate_limit_status(self) -> dict:
        """Return current rate limit status.

        Returns:
            Dict with rate limit info (limit, remaining, reset_time)
        """
        pass

    @abstractmethod
    def validate(self) -> tuple[bool, str]:
        """Validate credentials and connection.

        Returns:
            Tuple of (success, info) where info is username on success
            or error message on failure
        """
        pass

    def post_with_reference(
        self,
        content: str,
        reference: PostReference,
        media_paths: list[str] | None = None,
        dry_run: bool = False,
    ) -> PostResult:
        """Post content with a reference to an existing post.

        Default implementation uses LINK fallback: appends the reference URL
        to the content and delegates to post(). Subclasses override for
        platform-native behaviors (quote tweets, reshares, etc.).

        Args:
            content: Text content to post
            reference: Reference to an existing post
            media_paths: Optional list of media file paths to attach
            dry_run: If True, return simulated success without API call

        Returns:
            PostResult with success status and optional external_id/url
        """
        if reference.external_url:
            content = f"{content}\n\n{reference.external_url}"
        return self.post(content, media_paths, dry_run)

    def supports_reference_type(self, ref_type: ReferenceType) -> bool:
        """Check if this platform supports a given reference type.

        Default implementation only supports LINK (URL embedding).
        Subclasses override to advertise native capabilities.

        Args:
            ref_type: The reference type to check

        Returns:
            True if the platform supports this reference type
        """
        return ref_type == ReferenceType.LINK

    def capabilities(self) -> list[PostCapability]:
        """Return the list of posting capabilities this platform supports."""
        from social_hook.adapters.models import SINGLE

        return [SINGLE]

    def supports_threads(self) -> bool:
        """Whether this platform supports threaded posts."""
        return False

    def supports_media(self) -> bool:
        """Whether this platform supports media attachments."""
        return False
