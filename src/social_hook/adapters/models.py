"""Result dataclasses for adapter operations."""

from dataclasses import dataclass
from enum import Enum


@dataclass
class PostResult:
    """Result of a single post operation."""

    success: bool
    external_id: str | None = None
    external_url: str | None = None
    error: str | None = None
    part_results: list["PostResult"] | None = None


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
    """Describes a media mode supported by a platform capability.

    ``max_count`` caps how many media items one post in this mode may carry
    (e.g. X SINGLE supports up to 4 images via MULTI_IMAGE_X). The per-
    (vehicle, platform) cap computed in ``vehicle.get_max_media_count`` is
    the ``max`` over all modes attached to the capability, so a capability
    can advertise multiple modes without clobbering the highest one.
    """

    name: str  # "single_image", "multi_image_x", "article_media", "gif", "video"
    formats: tuple[str, ...]  # ("png", "jpg", "gif")
    max_size: int | None  # bytes, platform limit
    max_count: int = 1


@dataclass(frozen=True)
class PostCapability:
    """Describes a posting capability of a platform adapter."""

    name: str  # "single", "thread", "article", "quote", "reply", "reshare"
    media_modes: tuple[MediaMode, ...]  # what media this capability accepts
    description: str = ""
    auto_postable: bool = True


# Common media modes.
# 5 MiB / 15 MiB size limits are the single source of truth — enforced at
# every upload ingress point (Web 413, Bot reply, CLI exit-1) and defensively
# in the drafter.
SINGLE_IMAGE = MediaMode("single_image", ("png", "jpg", "webp"), 5_242_880, max_count=1)
MULTI_IMAGE_X = MediaMode("multi_image_x", ("png", "jpg", "webp"), 5_242_880, max_count=4)
ARTICLE_MEDIA = MediaMode("article_media", ("png", "jpg", "webp"), 5_242_880, max_count=20)
GIF = MediaMode("gif", ("gif",), 15_728_640, max_count=1)  # 15 MiB
VIDEO = MediaMode("video", ("mp4",), 536_870_912, max_count=1)  # 512 MiB

# Common capabilities.
# Effective max_count per capability = max(mode.max_count for mode in
# media_modes) — see vehicle.get_max_media_count. SINGLE is the universal
# baseline (one image, one GIF). Platforms that EXTEND (e.g. X with 4-image
# carousels) declare their own constant; platforms that RESTRICT (e.g. a
# hypothetical text-only platform) declare their own too. Default to SINGLE
# when a platform matches the baseline.
SINGLE = PostCapability("single", (SINGLE_IMAGE, GIF), "Self-contained post")
# X extends SINGLE with MULTI_IMAGE_X (up to 4 images per post).
SINGLE_X = PostCapability("single", (SINGLE_IMAGE, MULTI_IMAGE_X, GIF), "Self-contained post (X)")
THREAD = PostCapability("thread", (SINGLE_IMAGE, GIF), "Multi-part narrative (4+ connected posts)")
ARTICLE = PostCapability(
    "article",
    (ARTICLE_MEDIA,),
    "Long-form structured content (manual post)",
    auto_postable=False,
)
QUOTE = PostCapability("quote", (SINGLE_IMAGE, GIF), "Quote an existing post")
REPLY = PostCapability("reply", (SINGLE_IMAGE, GIF), "Reply to an existing post")
RESHARE = PostCapability("reshare", (), "Share an existing post")
