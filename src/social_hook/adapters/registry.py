"""Media adapter registry with lazy initialization.

Uses AdapterRegistry for dispatch instead of if/elif chains.
Each media tool is registered with its factory, metadata, and
class location for schema introspection.
"""

import contextlib
import importlib
import logging
import threading
from typing import Any

from social_hook.adapters.media.base import MediaAdapter
from social_hook.errors import ConfigError
from social_hook.registry import AdapterRegistry

logger = logging.getLogger(__name__)

# Typo-proof metadata key for adapter thread-safety. Parallel media
# generators (drafting._generate_all_media, media_regen.regen_all_media_items)
# read this to decide whether an adapter can run under a ThreadPoolExecutor
# without serialization.
THREAD_SAFE_KEY = "thread_safe"

# Pre-populated at module import to eliminate a defaultdict-race on first
# access. Keys mirror the registrations below marked ``THREAD_SAFE_KEY:
# False`` (playwright + ray_so — sync_playwright()'s asyncio loop cannot be
# reentered across threads). Adding a new non-thread-safe adapter requires a
# matching entry here.
_ADAPTER_LOCKS: dict[str, threading.Lock] = {
    "playwright": threading.Lock(),
    "ray_so": threading.Lock(),
}


@contextlib.contextmanager
def with_adapter_lock(tool: str):
    """Serialize non-thread-safe adapters; no-op for thread-safe ones.

    Reads ``THREAD_SAFE_KEY`` from registry metadata. Used by every parallel
    media caller (drafting batch, regen-all helper) so a single source of
    truth governs which adapters may run concurrently.
    """
    meta = media_registry.get_metadata(tool) if media_registry.has(tool) else {}
    if meta.get(THREAD_SAFE_KEY, True):
        yield
        return
    lock = _ADAPTER_LOCKS.get(tool)
    if lock is None:
        logger.warning(
            "No pre-populated lock for non-thread-safe adapter %s; creating on demand",
            tool,
        )
        lock = threading.Lock()
        _ADAPTER_LOCKS[tool] = lock
    with lock:
        yield


# Module-level registry for media adapters
media_registry = AdapterRegistry("media")


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


# Register at module load (lazy imports inside each factory function)
media_registry.register(
    "mermaid",
    _create_mermaid,
    metadata={
        "display_name": "Mermaid",
        "description": "Flowcharts, sequence diagrams, and other Mermaid.js diagrams",
        "class_module": "social_hook.adapters.media.mermaid",
        "class_name": "MermaidAdapter",
        THREAD_SAFE_KEY: True,
    },
)
media_registry.register(
    "nano_banana_pro",
    _create_nano_banana_pro,
    metadata={
        "display_name": "Nano Banana Pro",
        "description": "AI-generated images from text prompts (Gemini)",
        "class_module": "social_hook.adapters.media.nanabananapro",
        "class_name": "NanaBananaAdapter",
        THREAD_SAFE_KEY: True,
    },
)
media_registry.register(
    "ray_so",
    _create_ray_so,
    metadata={
        "display_name": "Ray.so",
        "description": "Beautiful code snippet screenshots via ray.so",
        "class_module": "social_hook.adapters.media.rayso",
        "class_name": "RaySoAdapter",
        # ray.so wraps Playwright internally, so inherits playwright's
        # single-threaded constraint.
        THREAD_SAFE_KEY: False,
    },
)
media_registry.register(
    "playwright",
    _create_playwright,
    metadata={
        "display_name": "Playwright",
        "description": "Browser screenshots of any webpage",
        "class_module": "social_hook.adapters.media.playwright",
        "class_name": "PlaywrightAdapter",
        # sync_playwright() is not thread-safe — parallel calls crash.
        THREAD_SAFE_KEY: False,
    },
)

# Backward-compatible constant — derived from registry, not a separate data structure
MEDIA_ADAPTER_NAMES = media_registry.names()


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
    if not media_registry.has(name):
        logger.warning(
            "Unknown media adapter: %s (available: %s)",
            name,
            media_registry.names(),
        )
        return None

    result: MediaAdapter = media_registry.get_or_create(name, api_key=api_key)
    return result


def resolve_media_adapter(tool: str, config: Any) -> MediaAdapter:
    """Resolve a media adapter by tool name with credential injection.

    Centralizes the ``nano_banana_pro``/``GEMINI_API_KEY`` lookup pattern
    duplicated across bot, web, cli, and drafting surfaces. Raises
    ``ConfigError`` on missing credentials, uploads that cannot be
    regenerated, and unknown tool names — callers translate to a
    surface-appropriate response (HTTP 400, Telegram reply, CLI exit 1).

    Args:
        tool: Adapter name (e.g. ``"nano_banana_pro"``, ``"mermaid"``).
        config: Full config object exposing ``config.env`` dict.

    Returns:
        A ready-to-use ``MediaAdapter`` instance.

    Raises:
        ConfigError: ``GEMINI_API_KEY`` not configured, ``legacy_upload``
            requested (uploads have no generator), or unknown tool name.
    """
    if tool == "legacy_upload":
        raise ConfigError("legacy_upload items cannot be regenerated")

    api_key: str | None = None
    if tool == "nano_banana_pro":
        api_key = config.env.get("GEMINI_API_KEY") if config else None
        if not api_key:
            raise ConfigError("GEMINI_API_KEY not configured")

    try:
        adapter = get_media_adapter(tool, api_key=api_key)
    except ValueError as exc:
        # nano_banana_pro raises ValueError if api_key is missing — we
        # guarded above, but keep the translation for defense in depth.
        raise ConfigError(str(exc)) from exc
    if adapter is None:
        raise ConfigError(f"Unknown media adapter: {tool!r}")
    return adapter


def clear_adapter_cache() -> None:
    """Clear the adapter cache. Useful for testing."""
    media_registry.clear_cache()


def get_tool_spec_schema(name: str) -> dict:
    """Get spec schema for a media tool by name (no instantiation needed).

    Uses class location stored in registry metadata for lazy import.

    Args:
        name: Tool name (e.g. "mermaid", "ray_so")

    Returns:
        Schema dict with "required" and "optional" keys
    """
    meta = media_registry.get_metadata(name)
    class_module = meta.get("class_module")
    class_name = meta.get("class_name")
    if not class_module or not class_name:
        return {"required": {}, "optional": {}}
    mod = importlib.import_module(class_module)
    cls = getattr(mod, class_name)
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
    result = []
    for name in media_registry.names():
        meta = media_registry.get_metadata(name)
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
