"""Tests for adapter ABCs and dataclasses (T1, T6).

Source: WS3_ADAPTERS.md T1 (lines 118-128), T6 (lines 168-174)
"""

import pytest

from social_hook.adapters.models import MediaResult, PostResult, ThreadResult
from social_hook.adapters.media.base import MediaAdapter
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
                return ThreadResult(success=True)

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
                return ThreadResult(success=True)

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
        """post_thread() accepts tweets list and returns ThreadResult."""

        class FakeAdapter(PlatformAdapter):
            def post(self, content, media_paths=None, dry_run=False):
                return PostResult(success=True)

            def post_thread(self, tweets, dry_run=False):
                return ThreadResult(success=True, tweet_results=[])

            def delete(self, external_id):
                return True

            def get_rate_limit_status(self):
                return {}

            def validate(self):
                return (True, "test")

        adapter = FakeAdapter()
        result = adapter.post_thread([{"content": "test"}])
        assert isinstance(result, ThreadResult)

    def test_get_rate_limit_status_returns_dict(self):
        """get_rate_limit_status() returns dict with rate info."""

        class FakeAdapter(PlatformAdapter):
            def post(self, content, media_paths=None, dry_run=False):
                return PostResult(success=True)

            def post_thread(self, tweets, dry_run=False):
                return ThreadResult(success=True)

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
                return ThreadResult(success=True)

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
    """PostResult, ThreadResult, MediaResult field access."""

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
        """ThreadResult stores list of PostResults."""
        tweets = [PostResult(success=True, external_id=str(i)) for i in range(4)]
        tr = ThreadResult(success=True, tweet_results=tweets)
        assert len(tr.tweet_results) == 4
        assert tr.tweet_results[0].external_id == "0"

    def test_thread_result_default_empty_list(self):
        """ThreadResult tweet_results defaults to empty list."""
        tr = ThreadResult(success=False, error="Failed")
        assert tr.tweet_results == []

    def test_media_result_with_path(self):
        """MediaResult stores file_path."""
        mr = MediaResult(success=True, file_path="/tmp/diagram.png")
        assert mr.file_path == "/tmp/diagram.png"

    def test_media_result_failure(self):
        """MediaResult captures error on failure."""
        mr = MediaResult(success=False, error="API timeout")
        assert mr.success is False
        assert mr.file_path is None
