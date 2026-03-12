"""Media adapter registry with lazy initialization."""

import importlib

from social_hook.adapters.media.base import MediaAdapter

# Lazy singleton cache
_adapter_cache: dict[str, MediaAdapter] = {}

# All available media adapter names
MEDIA_ADAPTER_NAMES = ["mermaid", "nano_banana_pro", "playwright", "ray_so"]

# Adapter class locations for lazy import
_ADAPTER_CLASSES = {
    "mermaid": ("social_hook.adapters.media.mermaid", "MermaidAdapter"),
    "nano_banana_pro": ("social_hook.adapters.media.nanabananapro", "NanaBananaAdapter"),
    "ray_so": ("social_hook.adapters.media.rayso", "RaySoAdapter"),
    "playwright": ("social_hook.adapters.media.playwright", "PlaywrightAdapter"),
}

# Display metadata for each tool
_TOOL_METADATA = {
    "mermaid": {
        "display_name": "Mermaid",
        "description": "Flowcharts, sequence diagrams, and other Mermaid.js diagrams",
    },
    "nano_banana_pro": {
        "display_name": "Nano Banana Pro",
        "description": "AI-generated images from text prompts (Gemini)",
    },
    "ray_so": {
        "display_name": "Ray.so",
        "description": "Beautiful code snippet screenshots via ray.so",
    },
    "playwright": {
        "display_name": "Playwright",
        "description": "Browser screenshots of any webpage",
    },
}


def get_media_adapter(name: str, api_key: str | None = None) -> MediaAdapter | None:
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

    adapter: MediaAdapter | None = None

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
    return cls.spec_schema()


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
    result = []
    for name in MEDIA_ADAPTER_NAMES:
        meta = _TOOL_METADATA.get(name, {})
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
