"""Result dataclasses for adapter operations."""

from dataclasses import dataclass, field


@dataclass
class PostResult:
    """Result of a single post operation."""

    success: bool
    external_id: str | None = None
    external_url: str | None = None
    error: str | None = None


@dataclass
class ThreadResult:
    """Result of a thread post operation."""

    success: bool
    tweet_results: list[PostResult] = field(default_factory=list)
    error: str | None = None


@dataclass
class MediaResult:
    """Result of a media generation operation."""

    success: bool
    file_path: str | None = None
    error: str | None = None
