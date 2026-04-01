"""Generic adapter registry with lazy initialization and metadata.

A domain-agnostic registry that maps string names to factory callables.
Supports lazy instantiation, optional caching, and metadata for
introspection (display names, descriptions, capabilities).

Used by platform adapters, media adapters, and messaging adapters to
replace hardcoded if/elif dispatch chains with extensible registration.

REUSABILITY: This file has zero project-specific imports.
Only stdlib (logging, typing). Copy-paste safe.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class AdapterRegistry:
    """Generic registry mapping string names to adapter factory callables.

    Supports:
    - Registration of factory functions with optional metadata
    - Lazy creation via factory call
    - Optional instance caching (get_or_create)
    - Metadata introspection (list_all, get_metadata)
    - Cache invalidation

    Example::

        registry = AdapterRegistry("platform")

        def create_x(**kwargs):
            return XAdapter(kwargs["token"])

        registry.register("x", create_x, metadata={"display_name": "X/Twitter"})

        adapter = registry.create("x", token="abc123")
    """

    def __init__(self, kind: str = "adapter") -> None:
        """Initialize registry.

        Args:
            kind: Human-readable label for error messages (e.g., "platform",
                "media", "messaging"). Used in log messages and exceptions.
        """
        self._kind = kind
        self._factories: dict[str, Callable[..., Any]] = {}
        self._metadata: dict[str, dict[str, Any]] = {}
        self._cache: dict[str, Any] = {}

    def register(
        self,
        name: str,
        factory: Callable[..., Any],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register a factory callable under a name.

        Args:
            name: Unique adapter name (e.g., "x", "telegram", "mermaid").
            factory: Callable that creates an adapter instance.
                Called with whatever args/kwargs are passed to create().
            metadata: Optional dict of display metadata (display_name,
                description, etc.) for introspection.
        """
        self._factories[name] = factory
        if metadata is not None:
            self._metadata[name] = metadata

    def create(self, name: str, *args: Any, **kwargs: Any) -> Any:
        """Create a new adapter instance by name.

        Args:
            name: Registered adapter name.
            *args, **kwargs: Forwarded to the factory callable.

        Returns:
            New adapter instance.

        Raises:
            KeyError: If name is not registered.
        """
        factory = self._factories.get(name)
        if factory is None:
            available = ", ".join(sorted(self._factories)) or "(none)"
            raise KeyError(f"Unknown {self._kind} adapter: '{name}' (available: {available})")
        return factory(*args, **kwargs)

    def get_or_create(self, name: str, *args: Any, **kwargs: Any) -> Any:
        """Return cached instance or create and cache a new one.

        Useful for adapters that should be singletons within a process
        (e.g., media adapters with expensive initialization).

        Note: cache key is ``name`` only — args/kwargs are used only on
        first creation. Subsequent calls with different args still return
        the originally cached instance. Use ``invalidate(name)`` first
        if you need to re-create with different parameters.

        Args:
            name: Registered adapter name.
            *args, **kwargs: Forwarded to factory on first creation.

        Returns:
            Cached or newly created adapter instance.
        """
        if name not in self._cache:
            self._cache[name] = self.create(name, *args, **kwargs)
        return self._cache[name]

    def has(self, name: str) -> bool:
        """Check if a name is registered."""
        return name in self._factories

    def names(self) -> list[str]:
        """Return list of all registered names."""
        return list(self._factories.keys())

    def get_metadata(self, name: str) -> dict[str, Any]:
        """Return metadata dict for a registered name, or empty dict."""
        return dict(self._metadata.get(name, {}))

    def all_metadata(self) -> dict[str, dict[str, Any]]:
        """Return metadata for all registered names."""
        return {name: dict(self._metadata.get(name, {})) for name in self._factories}

    def invalidate(self, name: str) -> None:
        """Remove a cached instance (next get_or_create will re-create)."""
        self._cache.pop(name, None)

    def clear_cache(self) -> None:
        """Remove all cached instances."""
        self._cache.clear()

    def __contains__(self, name: str) -> bool:
        return self.has(name)

    def __len__(self) -> int:
        return len(self._factories)

    def __repr__(self) -> str:
        names = ", ".join(sorted(self._factories))
        return f"AdapterRegistry({self._kind!r}, [{names}])"
