"""Result dataclasses for adapter operations."""

from dataclasses import dataclass, field
from enum import Enum


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


class ReferenceType(Enum):
    """Type of cross-post reference."""

    REPLY = "reply"
    QUOTE = "quote"
    LINK = "link"


@dataclass
class PostReference:
    """Reference to an existing post on a platform."""

    external_id: str
    external_url: str
    reference_type: ReferenceType


@dataclass(frozen=True)
class MediaMode:
    """Describes a media mode supported by a platform capability."""

    name: str  # "single_image", "multi_image", "video", "gif"
    formats: tuple[str, ...]  # ("png", "jpg", "gif")
    max_size: int | None  # bytes, platform limit


@dataclass(frozen=True)
class PostCapability:
    """Describes a posting capability of a platform adapter."""

    name: str  # "single_post", "thread", "quote", "reply", "reshare"
    media_modes: tuple[MediaMode, ...]  # what media this capability accepts


# Common media modes
SINGLE_IMAGE = MediaMode("single_image", ("png", "jpg", "webp"), 5_242_880)  # 5MB
MULTI_IMAGE = MediaMode("multi_image", ("png", "jpg", "webp"), 5_242_880)
GIF = MediaMode("gif", ("gif",), 15_728_640)  # 15MB
VIDEO = MediaMode("video", ("mp4",), 536_870_912)  # 512MB

# Common capabilities
SINGLE_POST = PostCapability("single_post", (SINGLE_IMAGE, MULTI_IMAGE, GIF))
THREAD = PostCapability("thread", (SINGLE_IMAGE, GIF))
QUOTE = PostCapability("quote", (SINGLE_IMAGE, GIF))
REPLY = PostCapability("reply", (SINGLE_IMAGE, GIF))
RESHARE = PostCapability("reshare", ())
