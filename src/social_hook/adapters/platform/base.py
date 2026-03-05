"""Abstract base class for platform adapters."""

from abc import ABC, abstractmethod

from social_hook.adapters.models import PostResult, ThreadResult


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
    def post_thread(self, tweets: list[dict], dry_run: bool = False) -> ThreadResult:
        """Post a thread of connected posts.

        Args:
            tweets: List of dicts with 'content' and optional 'media_paths'
            dry_run: If True, return simulated success without API calls

        Returns:
            ThreadResult with success status and per-tweet results
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
