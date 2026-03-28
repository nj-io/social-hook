"""Platform adapter factory -- routes platform name to adapter class.

Uses AdapterRegistry to dispatch by platform name instead of if/elif chains.
Each platform has a private factory function registered on the module-level
registry. Adding a new platform = one function + one register() call.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from social_hook.adapters import auth
from social_hook.errors import ConfigError
from social_hook.registry import AdapterRegistry

if TYPE_CHECKING:
    from social_hook.adapters.platform.base import PlatformAdapter
    from social_hook.config.targets import AccountConfig, PlatformCredentialConfig

logger = logging.getLogger(__name__)

# Module-level registry for platform adapters
_platform_registry = AdapterRegistry("platform")
_registered = False


# =============================================================================
# Per-platform factory functions
# =============================================================================


def _create_x(
    *,
    config=None,
    account_name: str | None = None,
    account=None,
    platform_creds=None,
    db_path: str | None = None,
    **_kw,
) -> PlatformAdapter:
    """Create an X (Twitter) adapter from either legacy or targets config."""
    from social_hook.adapters.platform.x import XAdapter

    refresh_url = "https://api.x.com/2/oauth2/token"

    if account is not None:
        # Targets path
        if not platform_creds.client_id:
            raise ConfigError(f"X client_id not configured for account '{account_name}'")

        tier = account.tier or "free"
        token_kwargs = dict(
            client_id=platform_creds.client_id,
            client_secret=platform_creds.client_secret,
            token_url=refresh_url,
        )
        access_token = auth.refresh_and_get_token(db_path, account_name, "x", **token_kwargs)

        def x_refresher():
            return auth.refresh_and_get_token(db_path, account_name, "x", **token_kwargs)

        logger.info("Created X adapter for account '%s' (tier=%s)", account_name, tier)
        return XAdapter(access_token, tier=tier, token_refresher=x_refresher)

    # Legacy path
    from social_hook.filesystem import get_db_path

    client_id = config.env.get("X_CLIENT_ID", "")
    client_secret = config.env.get("X_CLIENT_SECRET", "")

    if not client_id:
        raise ConfigError("X_CLIENT_ID not configured in .env")

    token_db = str(get_db_path())
    x_config = config.platforms.get("x")
    tier = (x_config.account_tier if x_config else None) or "free"

    account_name_legacy = "x"  # pre-targets: one account per platform
    token_kwargs = dict(client_id=client_id, client_secret=client_secret, token_url=refresh_url)
    access_token = auth.refresh_and_get_token(token_db, account_name_legacy, "x", **token_kwargs)

    def refresher():
        return auth.refresh_and_get_token(token_db, account_name_legacy, "x", **token_kwargs)

    return XAdapter(access_token, tier=tier, token_refresher=refresher)


def _create_linkedin(
    *,
    config=None,
    account_name: str | None = None,
    account=None,
    platform_creds=None,
    db_path: str | None = None,
    **_kw,
) -> PlatformAdapter:
    """Create a LinkedIn adapter from either legacy or targets config."""
    from social_hook.adapters.platform.linkedin import LinkedInAdapter

    refresh_url = "https://www.linkedin.com/oauth/v2/accessToken"

    if account is not None:
        # Targets path
        if not platform_creds.client_id:
            raise ConfigError(f"LinkedIn client_id not configured for account '{account_name}'")

        token_kwargs = dict(
            client_id=platform_creds.client_id,
            client_secret=platform_creds.client_secret,
            token_url=refresh_url,
        )
        access_token = auth.refresh_and_get_token(db_path, account_name, "linkedin", **token_kwargs)

        def linkedin_refresher():
            return auth.refresh_and_get_token(db_path, account_name, "linkedin", **token_kwargs)

        entity = account.entity
        logger.info(
            "Created LinkedIn adapter for account '%s' (entity=%s)",
            account_name,
            entity or "personal",
        )
        return LinkedInAdapter(access_token, entity=entity, token_refresher=linkedin_refresher)

    # Legacy path
    access_token = config.env.get("LINKEDIN_ACCESS_TOKEN", "")
    if not access_token:
        raise ConfigError("Missing LinkedIn access token")
    return LinkedInAdapter(access_token)


# =============================================================================
# Registration
# =============================================================================


def _ensure_registered():
    """Lazily register all platform adapters."""
    global _registered
    if _registered:
        return
    _registered = True

    _platform_registry.register(
        "x",
        _create_x,
        metadata={"display_name": "X/Twitter"},
    )
    _platform_registry.register(
        "linkedin",
        _create_linkedin,
        metadata={"display_name": "LinkedIn"},
    )


# =============================================================================
# Public API (backward-compatible)
# =============================================================================


def create_adapter(platform: str, config, db_path: str | None = None) -> PlatformAdapter:
    """Create a platform adapter by name (legacy interface).

    Args:
        platform: Platform name (e.g., "x", "linkedin").
        config: Global Config object (for credentials via config.env).
        db_path: Ignored for token operations (tokens always use the main DB).
            Kept for backward compatibility with callers that pass it.

    Returns:
        Configured PlatformAdapter instance.

    Raises:
        ConfigError: If platform is unknown or credentials missing.
    """
    _ensure_registered()
    if not _platform_registry.has(platform):
        raise ConfigError(f"Unknown platform: {platform}")
    return _platform_registry.create(platform, config=config, db_path=db_path)


def resolve_platform_creds(
    account: AccountConfig,
    platform_credentials: dict[str, PlatformCredentialConfig],
) -> PlatformCredentialConfig:
    """Resolve the platform credential entry for an account.

    If account.app is set, looks up that specific entry.
    Otherwise, returns the first platform_credentials entry matching account.platform.

    Args:
        account: AccountConfig with platform and optional app reference.
        platform_credentials: Dict of credential name -> PlatformCredentialConfig.

    Returns:
        Matching PlatformCredentialConfig.

    Raises:
        ConfigError: If no matching credentials found.
    """
    if account.app:
        if account.app not in platform_credentials:
            raise ConfigError(f"Account references unknown app: '{account.app}'")
        return platform_credentials[account.app]

    # Default: first platform_credentials entry matching account.platform
    for cred in platform_credentials.values():
        if cred.platform == account.platform:
            return cred

    raise ConfigError(f"No platform_credentials entry for platform: '{account.platform}'")


def create_adapter_from_account(
    account_name: str,
    account: AccountConfig,
    platform_creds: PlatformCredentialConfig,
    env: dict,
    db_path: str,
    *,
    on_error: Callable[[str], None] | None = None,
) -> PlatformAdapter:
    """Create a platform adapter from targets-style account config.

    Routes by account.platform to the appropriate adapter class via
    the platform adapter registry.

    Args:
        account_name: Unique account identifier from config.
        account: AccountConfig with platform, tier, etc.
        platform_creds: PlatformCredentialConfig with client_id/secret.
        env: Environment variables dict (unused for now, reserved for future).
        db_path: Path to SQLite database for token storage.
        on_error: Optional callback for error reporting (currently unused,
            reserved for future auth.py integration).

    Returns:
        Configured PlatformAdapter instance.

    Raises:
        ConfigError: If platform is unknown or credentials missing.
    """
    _ensure_registered()
    platform = account.platform

    if not _platform_registry.has(platform):
        logger.warning("Unknown platform '%s' for account '%s'", platform, account_name)
        raise ConfigError(f"Unknown platform: '{platform}'")

    return _platform_registry.create(
        platform,
        account_name=account_name,
        account=account,
        platform_creds=platform_creds,
        db_path=db_path,
    )
