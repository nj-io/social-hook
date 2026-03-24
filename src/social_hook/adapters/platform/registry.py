"""Process-scoped adapter registry for caching platform adapter instances.

Caches one adapter per platform (pre-targets) or per account (targets).
Benefits: rate limit state persists across scheduler ticks, token refresher
closures are reused without re-reading from DB each tick.

Note on stale config: if config changes between ticks (e.g., hot-reload),
cached adapters use the original config's values (tier, client credentials).
This is acceptable pre-targets. When targets lands, the registry will be
keyed by account name and config changes will invalidate affected entries.
"""

from social_hook.adapters.platform.factory import create_adapter


class AdapterRegistry:
    """Process-scoped cache — one adapter instance per platform or account."""

    def __init__(self):
        self._adapters: dict = {}

    def get(self, platform: str, config, db_path: str | None = None):
        """Get or create adapter, keyed by platform name.

        When targets lands, the key changes from platform name to account name.
        """
        if platform not in self._adapters:
            self._adapters[platform] = create_adapter(platform, config, db_path=db_path)
        return self._adapters[platform]

    def invalidate(self, platform: str) -> None:
        """Remove cached adapter (e.g., after credential change)."""
        self._adapters.pop(platform, None)

    def clear(self) -> None:
        """Clear all cached adapters."""
        self._adapters.clear()
