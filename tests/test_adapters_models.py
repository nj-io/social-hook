"""Tests for adapter ABCs and dataclasses (T1, T6).

Source: WS3_ADAPTERS.md T1 (lines 118-128), T6 (lines 168-174)
"""

import pytest

from social_hook.adapters.media.base import MediaAdapter
from social_hook.adapters.models import (
    ARTICLE,
    ARTICLE_MEDIA,
    GIF,
    MULTI_IMAGE_X,
    QUOTE,
    REPLY,
    RESHARE,
    SINGLE,
    SINGLE_IMAGE,
    SINGLE_X,
    THREAD,
    VIDEO,
    MediaMode,
    MediaResult,
    PostCapability,
    PostReference,
    PostResult,
    ReferenceType,
)
from social_hook.adapters.platform.base import PlatformAdapter

# =============================================================================
# T1: PlatformAdapter Interface
# =============================================================================


class TestPlatformAdapterABC:
    """T1: PlatformAdapter ABC enforcement and signatures."""

    def test_cannot_instantiate(self):
        """ABC enforcement: Instantiate PlatformAdapter directly raises TypeError."""
        with pytest.raises(TypeError):
            PlatformAdapter()

    def test_subclass_with_all_methods(self):
        """Subclass with valid implementations creates without error."""

        class FakeAdapter(PlatformAdapter):
            def post(self, content, media_paths=None, dry_run=False):
                return PostResult(success=True)

            def post_thread(self, tweets, dry_run=False):
                return PostResult(success=True)

            def delete(self, external_id):
                return True

            def get_rate_limit_status(self):
                return {}

            def validate(self):
                return (True, "test")

        adapter = FakeAdapter()
        assert adapter is not None

    def test_subclass_missing_method_raises(self):
        """Subclass missing a method raises TypeError on instantiation."""

        class IncompleteAdapter(PlatformAdapter):
            def post(self, content, media_paths=None, dry_run=False):
                return PostResult(success=True)

            # Missing: post_thread, delete, get_rate_limit_status, validate

        with pytest.raises(TypeError):
            IncompleteAdapter()

    def test_post_signature(self):
        """post() accepts content, media_paths, dry_run and returns PostResult."""

        class FakeAdapter(PlatformAdapter):
            def post(self, content, media_paths=None, dry_run=False):
                return PostResult(success=True, external_id="123")

            def post_thread(self, tweets, dry_run=False):
                return PostResult(success=True)

            def delete(self, external_id):
                return True

            def get_rate_limit_status(self):
                return {}

            def validate(self):
                return (True, "test")

        adapter = FakeAdapter()
        result = adapter.post("test content")
        assert isinstance(result, PostResult)

    def test_post_thread_signature(self):
        """post_thread() accepts tweets list and returns PostResult."""

        class FakeAdapter(PlatformAdapter):
            def post(self, content, media_paths=None, dry_run=False):
                return PostResult(success=True)

            def post_thread(self, tweets, dry_run=False):
                return PostResult(success=True, part_results=[])

            def delete(self, external_id):
                return True

            def get_rate_limit_status(self):
                return {}

            def validate(self):
                return (True, "test")

        adapter = FakeAdapter()
        result = adapter.post_thread([{"content": "test"}])
        assert isinstance(result, PostResult)

    def test_get_rate_limit_status_returns_dict(self):
        """get_rate_limit_status() returns dict with rate info."""

        class FakeAdapter(PlatformAdapter):
            def post(self, content, media_paths=None, dry_run=False):
                return PostResult(success=True)

            def post_thread(self, tweets, dry_run=False):
                return PostResult(success=True)

            def delete(self, external_id):
                return True

            def get_rate_limit_status(self):
                return {"limit": 100, "remaining": 50}

            def validate(self):
                return (True, "test")

        adapter = FakeAdapter()
        status = adapter.get_rate_limit_status()
        assert isinstance(status, dict)

    def test_validate_returns_tuple(self):
        """validate() returns tuple[bool, str]."""

        class FakeAdapter(PlatformAdapter):
            def post(self, content, media_paths=None, dry_run=False):
                return PostResult(success=True)

            def post_thread(self, tweets, dry_run=False):
                return PostResult(success=True)

            def delete(self, external_id):
                return True

            def get_rate_limit_status(self):
                return {}

            def validate(self):
                return (True, "@testuser")

        adapter = FakeAdapter()
        result = adapter.validate()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)


# =============================================================================
# T6: MediaAdapter Interface
# =============================================================================


class TestMediaAdapterABC:
    """T6: MediaAdapter ABC enforcement and signatures."""

    def test_cannot_instantiate(self):
        """ABC enforcement: Instantiate MediaAdapter directly raises TypeError."""
        with pytest.raises(TypeError):
            MediaAdapter()

    def test_subclass_with_all_methods(self):
        """Subclass with valid generate() and supports() creates without error."""

        class FakeMediaAdapter(MediaAdapter):
            def generate(self, spec, output_dir=None, dry_run=False):
                return MediaResult(success=True, file_path="/tmp/test.png")

            def supports(self, media_type):
                return media_type == "test"

        adapter = FakeMediaAdapter()
        assert adapter is not None

    def test_supports_returns_bool(self):
        """supports() returns bool for given media type."""

        class FakeMediaAdapter(MediaAdapter):
            def generate(self, spec, output_dir=None, dry_run=False):
                return MediaResult(success=True)

            def supports(self, media_type):
                return media_type in ("test", "fake")

        adapter = FakeMediaAdapter()
        assert adapter.supports("test") is True
        assert adapter.supports("unknown") is False


# =============================================================================
# Dataclass Tests
# =============================================================================


class TestDataclasses:
    """PostResult and MediaResult field access."""

    def test_post_result_defaults(self):
        """PostResult optional fields default to None."""
        pr = PostResult(success=True)
        assert pr.success is True
        assert pr.external_id is None
        assert pr.external_url is None
        assert pr.error is None

    def test_post_result_with_fields(self):
        """PostResult stores all fields."""
        pr = PostResult(
            success=True,
            external_id="123",
            external_url="https://x.com/user/status/123",
        )
        assert pr.external_id == "123"
        assert pr.external_url == "https://x.com/user/status/123"

    def test_post_result_failure(self):
        """PostResult captures error on failure."""
        pr = PostResult(success=False, error="Content too long")
        assert pr.success is False
        assert pr.error == "Content too long"

    def test_thread_result_with_tweets(self):
        """PostResult stores list of PostResults."""
        tweets = [PostResult(success=True, external_id=str(i)) for i in range(4)]
        tr = PostResult(success=True, part_results=tweets)
        assert len(tr.part_results) == 4
        assert tr.part_results[0].external_id == "0"

    def test_thread_result_default_none(self):
        """PostResult part_results defaults to None."""
        tr = PostResult(success=False, error="Failed")
        assert tr.part_results is None

    def test_media_result_with_path(self):
        """MediaResult stores file_path."""
        mr = MediaResult(success=True, file_path="/tmp/diagram.png")
        assert mr.file_path == "/tmp/diagram.png"

    def test_media_result_failure(self):
        """MediaResult captures error on failure."""
        mr = MediaResult(success=False, error="API timeout")
        assert mr.success is False
        assert mr.file_path is None


# =============================================================================
# ReferenceType and PostReference
# =============================================================================


class TestReferenceType:
    """ReferenceType enum values."""

    def test_reply_value(self):
        assert ReferenceType.REPLY.value == "reply"

    def test_quote_value(self):
        assert ReferenceType.QUOTE.value == "quote"

    def test_link_value(self):
        assert ReferenceType.LINK.value == "link"

    def test_all_members(self):
        assert set(ReferenceType) == {ReferenceType.REPLY, ReferenceType.QUOTE, ReferenceType.LINK}


class TestPostReference:
    """PostReference dataclass fields."""

    def test_fields(self):
        ref = PostReference(
            external_id="123",
            external_url="https://x.com/user/status/123",
            reference_type=ReferenceType.QUOTE,
        )
        assert ref.external_id == "123"
        assert ref.external_url == "https://x.com/user/status/123"
        assert ref.reference_type == ReferenceType.QUOTE


# =============================================================================
# PlatformAdapter base class - LINK fallback
# =============================================================================


class TestPlatformAdapterLinkFallback:
    """PlatformAdapter.post_with_reference() default LINK fallback."""

    def _make_adapter(self):
        """Create a minimal concrete adapter for testing base class behavior."""

        class MinimalAdapter(PlatformAdapter):
            def __init__(self):
                self.last_post_content = None

            def post(self, content, media_paths=None, dry_run=False):
                self.last_post_content = content
                return PostResult(success=True, external_id="base_post")

            def post_thread(self, tweets, dry_run=False):
                return PostResult(success=True)

            def delete(self, external_id):
                return True

            def get_rate_limit_status(self):
                return {}

            def validate(self):
                return (True, "test")

        return MinimalAdapter()

    def test_link_fallback_appends_url(self):
        """Base class appends external_url to content for any reference type."""
        adapter = self._make_adapter()
        ref = PostReference(
            external_id="abc",
            external_url="https://example.com/post/abc",
            reference_type=ReferenceType.LINK,
        )
        result = adapter.post_with_reference("Check this", ref)

        assert result.success is True
        assert "https://example.com/post/abc" in adapter.last_post_content
        assert "Check this" in adapter.last_post_content

    def test_link_fallback_handles_empty_url(self):
        """Base class handles empty external_url gracefully."""
        adapter = self._make_adapter()
        ref = PostReference(
            external_id="abc",
            external_url="",
            reference_type=ReferenceType.LINK,
        )
        result = adapter.post_with_reference("No URL", ref)

        assert result.success is True
        assert adapter.last_post_content == "No URL"

    def test_base_supports_only_link(self):
        """Base class only supports LINK reference type."""
        adapter = self._make_adapter()
        assert adapter.supports_reference_type(ReferenceType.LINK) is True
        assert adapter.supports_reference_type(ReferenceType.REPLY) is False
        assert adapter.supports_reference_type(ReferenceType.QUOTE) is False


# =============================================================================
# MediaMode and PostCapability frozen dataclasses
# =============================================================================


class TestMediaMode:
    """MediaMode frozen dataclass tests."""

    def test_media_mode_is_frozen(self):
        """MediaMode instances cannot be mutated."""
        mode = MediaMode("test", ("png",), 1024)
        with pytest.raises(AttributeError):
            mode.name = "changed"

    def test_media_mode_equality(self):
        """Two MediaMode instances with same values are equal."""
        a = MediaMode("single_image", ("png", "jpg"), 100)
        b = MediaMode("single_image", ("png", "jpg"), 100)
        assert a == b

    def test_single_image_constant(self):
        """SINGLE_IMAGE constant is defined with expected values."""
        assert SINGLE_IMAGE.name == "single_image"
        assert SINGLE_IMAGE.formats == ("png", "jpg", "webp")
        assert SINGLE_IMAGE.max_size == 5_242_880
        assert SINGLE_IMAGE.max_count == 1

    def test_max_count_defaults_to_one(self):
        """MediaMode.max_count defaults to 1 when not specified."""
        m = MediaMode("t", ("png",), 1000)
        assert m.max_count == 1

    def test_max_count_is_configurable(self):
        m = MediaMode("t", ("png",), 1000, max_count=10)
        assert m.max_count == 10

    def test_multi_image_x_cap(self):
        assert MULTI_IMAGE_X.name == "multi_image_x"
        assert MULTI_IMAGE_X.max_count == 4
        assert MULTI_IMAGE_X.max_size == 5_242_880

    def test_article_media_cap(self):
        assert ARTICLE_MEDIA.name == "article_media"
        assert ARTICLE_MEDIA.max_count == 20

    def test_gif_cap(self):
        assert GIF.name == "gif"
        assert GIF.max_count == 1
        assert GIF.max_size == 15_728_640

    def test_video_cap(self):
        assert VIDEO.name == "video"
        assert VIDEO.max_count == 1


class TestPostCapability:
    """PostCapability frozen dataclass tests."""

    def test_post_capability_is_frozen(self):
        """PostCapability instances cannot be mutated."""
        cap = PostCapability("test", ())
        with pytest.raises(AttributeError):
            cap.name = "changed"

    def test_post_capability_equality(self):
        """Two PostCapability instances with same values are equal."""
        a = PostCapability("single", (SINGLE_IMAGE,))
        b = PostCapability("single", (SINGLE_IMAGE,))
        assert a == b

    def test_single_image_identity(self):
        """SINGLE_IMAGE module constant is the same object."""
        assert SINGLE_IMAGE is SINGLE_IMAGE

    def test_module_constants_defined(self):
        """All module-level media mode and capability constants are defined."""
        # Media modes
        assert SINGLE_IMAGE is not None
        assert MULTI_IMAGE_X is not None
        assert ARTICLE_MEDIA is not None
        assert GIF is not None
        assert VIDEO is not None
        # Capabilities
        assert SINGLE is not None
        assert SINGLE_X is not None
        assert THREAD is not None
        assert ARTICLE is not None
        assert QUOTE is not None
        assert REPLY is not None
        assert RESHARE is not None

    def test_single_is_universal_baseline(self):
        """SINGLE is the universal baseline: one image, one GIF, no carousel.

        Platforms that match the baseline (LinkedIn) reuse SINGLE; platforms
        that extend it declare their own constant (e.g. SINGLE_X).
        """
        assert SINGLE.media_modes == (SINGLE_IMAGE, GIF)
        assert max(m.max_count for m in SINGLE.media_modes) == 1

    def test_single_x_extends_baseline_with_multi_image(self):
        """SINGLE_X adds MULTI_IMAGE_X (4-image carousels) on top of SINGLE."""
        assert SINGLE_X.media_modes == (SINGLE_IMAGE, MULTI_IMAGE_X, GIF)
        assert max(m.max_count for m in SINGLE_X.media_modes) == 4

    def test_article_uses_article_media(self):
        assert ARTICLE.media_modes == (ARTICLE_MEDIA,)
        assert ARTICLE.auto_postable is False
        assert max(m.max_count for m in ARTICLE.media_modes) == 20

    def test_thread_media_modes(self):
        """THREAD includes SINGLE_IMAGE, GIF."""
        assert THREAD.media_modes == (SINGLE_IMAGE, GIF)

    def test_reshare_no_media(self):
        """RESHARE has no media modes."""
        assert RESHARE.media_modes == ()
