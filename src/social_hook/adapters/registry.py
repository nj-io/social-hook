"""Media adapter registry with lazy initialization.

Uses AdapterRegistry for dispatch instead of if/elif chains.
Each media tool is registered with its factory, metadata, and
class location for schema introspection.
"""

import importlib
import logging
from typing import Any

from social_hook.adapters.media.base import MediaAdapter
from social_hook.registry import AdapterRegistry

logger = logging.getLogger(__name__)

# Module-level registry for media adapters
_media_registry = AdapterRegistry("media")
_registered = False

# Adapter class locations for lazy import (used by spec_schema introspection)
_ADAPTER_CLASSES = {
    "mermaid": ("social_hook.adapters.media.mermaid", "MermaidAdapter"),
    "nano_banana_pro": ("social_hook.adapters.media.nanabananapro", "NanaBananaAdapter"),
    "ray_so": ("social_hook.adapters.media.rayso", "RaySoAdapter"),
    "playwright": ("social_hook.adapters.media.playwright", "PlaywrightAdapter"),
}


# =============================================================================
# Per-tool factory functions
# =============================================================================


def _create_mermaid(**_kw) -> MediaAdapter:
    from social_hook.adapters.media.mermaid import MermaidAdapter

    return MermaidAdapter()


def _create_nano_banana_pro(*, api_key: str | None = None, **_kw) -> MediaAdapter:
    if not api_key:
        raise ValueError("nano_banana_pro requires api_key (GEMINI_API_KEY)")
    from social_hook.adapters.media.nanabananapro import NanaBananaAdapter

    return NanaBananaAdapter(api_key=api_key)


def _create_playwright(**_kw) -> MediaAdapter:
    from social_hook.adapters.media.playwright import PlaywrightAdapter

    return PlaywrightAdapter()


def _create_ray_so(**_kw) -> MediaAdapter:
    from social_hook.adapters.media.rayso import RaySoAdapter

    return RaySoAdapter()


# =============================================================================
# Registration
# =============================================================================


def _ensure_registered():
    """Lazily register all media adapters."""
    global _registered
    if _registered:
        return
    _registered = True

    _media_registry.register(
        "mermaid",
        _create_mermaid,
        metadata={
            "display_name": "Mermaid",
            "description": "Flowcharts, sequence diagrams, and other Mermaid.js diagrams",
        },
    )
    _media_registry.register(
        "nano_banana_pro",
        _create_nano_banana_pro,
        metadata={
            "display_name": "Nano Banana Pro",
            "description": "AI-generated images from text prompts (Gemini)",
        },
    )
    _media_registry.register(
        "ray_so",
        _create_ray_so,
        metadata={
            "display_name": "Ray.so",
            "description": "Beautiful code snippet screenshots via ray.so",
        },
    )
    _media_registry.register(
        "playwright",
        _create_playwright,
        metadata={
            "display_name": "Playwright",
            "description": "Browser screenshots of any webpage",
        },
    )


# =============================================================================
# Public API (backward-compatible)
# =============================================================================

# Backward-compatible constant
MEDIA_ADAPTER_NAMES = list(_ADAPTER_CLASSES.keys())


def get_media_adapter(name: str, api_key: str | None = None) -> MediaAdapter | None:
    """Get media adapter by name with lazy initialization and caching.

    Args:
        name: One of "mermaid", "nano_banana_pro", "playwright", "ray_so"
        api_key: Required for nano_banana_pro (GEMINI_API_KEY)

    Returns:
        MediaAdapter instance or None if unknown name

    Raises:
        ValueError: If nano_banana_pro requested without api_key
    """
    _ensure_registered()

    if not _media_registry.has(name):
        logger.warning(
            "Unknown media adapter: %s (available: %s)",
            name,
            _media_registry.names(),
        )
        return None

    return _media_registry.get_or_create(name, api_key=api_key)


def clear_adapter_cache() -> None:
    """Clear the adapter cache. Useful for testing."""
    _media_registry.clear_cache()


def get_tool_spec_schema(name: str) -> dict:
    """Get spec schema for a media tool by name (no instantiation needed).

    Args:
        name: Tool name (e.g. "mermaid", "ray_so")

    Returns:
        Schema dict with "required" and "optional" keys
    """
    entry = _ADAPTER_CLASSES.get(name)
    if not entry:
        return {"required": {}, "optional": {}}
    mod = importlib.import_module(entry[0])
    cls = getattr(mod, entry[1])
    result: dict[str, Any] = cls.spec_schema()
    return result


def get_blank_template(name: str) -> dict:
    """Get blank template dict for a media tool (required keys set to empty strings).

    Args:
        name: Tool name

    Returns:
        Dict with required keys mapped to empty strings
    """
    schema = get_tool_spec_schema(name)
    return {k: "" for k in schema.get("required", {})}


def list_available_tools() -> list[dict]:
    """List all available media tools with metadata.

    Returns:
        List of dicts with name, display_name, description, required_fields
    """
    _ensure_registered()
    result = []
    for name in _media_registry.names():
        meta = _media_registry.get_metadata(name)
        schema = get_tool_spec_schema(name)
        result.append(
            {
                "name": name,
                "display_name": meta.get("display_name", name),
                "description": meta.get("description", ""),
                "required_fields": list(schema.get("required", {}).keys()),
            }
        )
    return result
