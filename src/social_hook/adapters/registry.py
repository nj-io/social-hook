"""Media adapter registry with lazy initialization."""

from typing import Optional

from social_hook.adapters.media.base import MediaAdapter

# Lazy singleton cache
_adapter_cache: dict[str, MediaAdapter] = {}

# All available media adapter names
MEDIA_ADAPTER_NAMES = ["mermaid", "nano_banana_pro", "playwright", "ray_so"]


def get_media_adapter(
    name: str, api_key: Optional[str] = None
) -> Optional[MediaAdapter]:
    """Get media adapter by name with lazy initialization.

    Args:
        name: One of "mermaid", "nano_banana_pro", "playwright", "ray_so"
        api_key: Required for nano_banana_pro (GEMINI_API_KEY)

    Returns:
        MediaAdapter instance or None if unknown name

    Raises:
        ValueError: If nano_banana_pro requested without api_key
    """
    if name in _adapter_cache:
        return _adapter_cache[name]

    adapter: Optional[MediaAdapter] = None

    if name == "mermaid":
        from social_hook.adapters.media.mermaid import MermaidAdapter

        adapter = MermaidAdapter()

    elif name == "nano_banana_pro":
        if not api_key:
            raise ValueError("nano_banana_pro requires api_key (GEMINI_API_KEY)")
        from social_hook.adapters.media.nanabananapro import NanaBananaAdapter

        adapter = NanaBananaAdapter(api_key=api_key)

    elif name == "playwright":
        from social_hook.adapters.media.playwright import PlaywrightAdapter

        adapter = PlaywrightAdapter()

    elif name == "ray_so":
        from social_hook.adapters.media.rayso import RaySoAdapter

        adapter = RaySoAdapter()

    if adapter:
        _adapter_cache[name] = adapter

    return adapter


def clear_adapter_cache() -> None:
    """Clear the adapter cache. Useful for testing."""
    _adapter_cache.clear()
