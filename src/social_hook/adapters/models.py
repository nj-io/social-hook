"""Result dataclasses for adapter operations."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PostResult:
    """Result of a single post operation."""

    success: bool
    external_id: Optional[str] = None
    external_url: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ThreadResult:
    """Result of a thread post operation."""

    success: bool
    tweet_results: list[PostResult] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class MediaResult:
    """Result of a media generation operation."""

    success: bool
    file_path: Optional[str] = None
    error: Optional[str] = None
