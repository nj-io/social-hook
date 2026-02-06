"""Tests for media adapter registry (T13).

Source: WS3_ADAPTERS.md T13 (lines 245-252)
"""

import pytest

from social_hook.adapters.registry import (
    MEDIA_ADAPTER_NAMES,
    clear_adapter_cache,
    get_media_adapter,
)


# =============================================================================
# T13: Media Adapter Registry
# =============================================================================


class TestMediaAdapterRegistry:
    """T13: Registry contains all media adapters and returns correct types."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_adapter_cache()

    def test_media_adapter_names_contains_all(self):
        """MEDIA_ADAPTER_NAMES contains all 4 adapter names."""
        expected = {"mermaid", "nano_banana_pro", "playwright", "ray_so"}
        assert set(MEDIA_ADAPTER_NAMES) == expected

    def test_get_mermaid_adapter(self):
        """get_media_adapter('mermaid') returns MermaidAdapter instance."""
        from social_hook.adapters.media.mermaid import MermaidAdapter

        adapter = get_media_adapter("mermaid")
        assert adapter is not None
        assert isinstance(adapter, MermaidAdapter)

    def test_get_playwright_adapter(self):
        """get_media_adapter('playwright') returns PlaywrightAdapter instance."""
        from social_hook.adapters.media.playwright import PlaywrightAdapter

        adapter = get_media_adapter("playwright")
        assert adapter is not None
        assert isinstance(adapter, PlaywrightAdapter)

    def test_get_rayso_adapter(self):
        """get_media_adapter('ray_so') returns RaySoAdapter instance."""
        from social_hook.adapters.media.rayso import RaySoAdapter

        adapter = get_media_adapter("ray_so")
        assert adapter is not None
        assert isinstance(adapter, RaySoAdapter)

    def test_get_nano_banana_pro_with_key(self):
        """get_media_adapter('nano_banana_pro') with api_key returns NanaBananaAdapter."""
        from social_hook.adapters.media.nanabananapro import NanaBananaAdapter

        adapter = get_media_adapter("nano_banana_pro", api_key="test_key")
        assert adapter is not None
        assert isinstance(adapter, NanaBananaAdapter)

    def test_get_nano_banana_pro_without_key_raises(self):
        """get_media_adapter('nano_banana_pro') without api_key raises ValueError."""
        with pytest.raises(ValueError, match="requires api_key"):
            get_media_adapter("nano_banana_pro")

    def test_invalid_name_returns_none(self):
        """get_media_adapter('invalid') returns None."""
        adapter = get_media_adapter("invalid")
        assert adapter is None

    def test_caching(self):
        """Same adapter returned on subsequent calls (singleton cache)."""
        adapter1 = get_media_adapter("mermaid")
        adapter2 = get_media_adapter("mermaid")
        assert adapter1 is adapter2

    def test_clear_cache(self):
        """clear_adapter_cache() resets the cache."""
        adapter1 = get_media_adapter("mermaid")
        clear_adapter_cache()
        adapter2 = get_media_adapter("mermaid")
        assert adapter1 is not adapter2
