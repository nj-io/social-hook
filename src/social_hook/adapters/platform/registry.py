"""Process-scoped adapter registry for caching platform adapter instances.

Caches one adapter per platform (pre-targets) or per account (targets).
Benefits: rate limit state persists across scheduler ticks, token refresher
closures are reused without re-reading from DB each tick.

Note on stale config: if config changes between ticks (e.g., hot-reload),
cached adapters use the original config's values (tier, client credentials).
This is acceptable pre-targets. For targets, the registry is keyed by
account name and config changes invalidate affected entries.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from social_hook.adapters.platform.factory import create_adapter

if TYPE_CHECKING:
    from social_hook.adapters.platform.base import PlatformAdapter
    from social_hook.config.targets import AccountConfig, PlatformCredentialConfig


class AdapterRegistry:
    """Process-scoped cache — one adapter instance per platform or account."""

    def __init__(self):
        self._adapters: dict = {}

    def get_for_account(
        self,
        account_name: str,
        account: AccountConfig,
        platform_creds: PlatformCredentialConfig,
        env: dict,
        db_path: str,
        *,
        on_error: Callable[[str], None] | None = None,
    ) -> PlatformAdapter:
        """Get or create a cached adapter for an account.

        Keyed by account_name — two X accounts get separate instances.
        on_error is only used during adapter creation (first call per account).

        Args:
            account_name: Unique account identifier from config.
            account: AccountConfig with platform, tier, etc.
            platform_creds: PlatformCredentialConfig with client_id/secret.
            env: Environment variables dict.
            db_path: Path to SQLite database for token storage.
            on_error: Optional callback for error reporting during creation.

        Returns:
            Cached PlatformAdapter instance.
        """
        if account_name not in self._adapters:
            from social_hook.adapters.platform.factory import create_adapter_from_account

            self._adapters[account_name] = create_adapter_from_account(
                account_name, account, platform_creds, env, db_path, on_error=on_error
            )
        return self._adapters[account_name]

    def get(self, platform: str, config, db_path: str | None = None):
        """Legacy interface — routes to create_adapter() for backward compat.

        Used when no targets config exists (old-style config.platforms).
        Keyed by platform name (single account per platform).
        """
        if platform not in self._adapters:
            self._adapters[platform] = create_adapter(platform, config, db_path=db_path)
        return self._adapters[platform]

    def invalidate(self, key: str) -> None:
        """Remove a cached adapter (e.g., after credential change or token failure)."""
        self._adapters.pop(key, None)

    def clear(self) -> None:
        """Clear all cached adapters."""
        self._adapters.clear()
