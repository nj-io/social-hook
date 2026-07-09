"""Tests for media adapter registry (T13).

Source: WS3_ADAPTERS.md T13 (lines 245-252)
"""

from types import SimpleNamespace

import pytest

from social_hook.adapters.registry import (
    MEDIA_ADAPTER_NAMES,
    clear_adapter_cache,
    get_media_adapter,
    resolve_media_adapter,
)
from social_hook.errors import ConfigError

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


# =============================================================================
# A1#3: resolve_media_adapter centralizes credential lookup + error translation
# =============================================================================


class TestResolveMediaAdapter:
    """Covers the 4-site consolidation helper: bot/web/cli/drafting use this
    instead of reimplementing the nano_banana_pro/GEMINI_API_KEY branch +
    legacy_upload rejection + unknown-tool fallback.
    """

    def setup_method(self):
        clear_adapter_cache()

    def test_nano_banana_pro_with_key_returns_adapter(self):
        from social_hook.adapters.media.nanabananapro import NanaBananaAdapter

        config = SimpleNamespace(env={"GEMINI_API_KEY": "test_key"})
        adapter = resolve_media_adapter("nano_banana_pro", config)
        assert isinstance(adapter, NanaBananaAdapter)

    def test_nano_banana_pro_missing_key_raises_configerror(self):
        config = SimpleNamespace(env={})
        with pytest.raises(ConfigError, match="GEMINI_API_KEY not configured"):
            resolve_media_adapter("nano_banana_pro", config)

    def test_legacy_upload_rejected(self):
        config = SimpleNamespace(env={})
        with pytest.raises(ConfigError, match="legacy_upload items cannot be regenerated"):
            resolve_media_adapter("legacy_upload", config)

    def test_unknown_tool_raises_configerror(self):
        config = SimpleNamespace(env={})
        with pytest.raises(ConfigError, match="Unknown media adapter"):
            resolve_media_adapter("not_a_real_tool", config)

    def test_mermaid_requires_no_credentials(self):
        """Non-credential adapters work with an empty config."""
        from social_hook.adapters.media.mermaid import MermaidAdapter

        config = SimpleNamespace(env={})
        adapter = resolve_media_adapter("mermaid", config)
        assert isinstance(adapter, MermaidAdapter)
