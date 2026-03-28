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


def _get_oauth_token_and_refresher(
    db_path: str, account_name: str, platform: str, platform_creds
) -> tuple[str, Callable[[], str]]:
    """Build an OAuth access token and refresher closure for any platform.

    Args:
        db_path: Path to SQLite database for token storage.
        account_name: Account identifier for token lookup.
        platform: Platform name (e.g., "x", "linkedin").
        platform_creds: PlatformCredentialConfig with client_id/secret.

    Returns:
        Tuple of (access_token, refresher_callable).
    """
    refresh_urls = {
        "x": "https://api.x.com/2/oauth2/token",
        "linkedin": "https://www.linkedin.com/oauth/v2/accessToken",
    }
    token_url = refresh_urls.get(platform, "")
    token_kwargs = dict(
        client_id=platform_creds.client_id,
        client_secret=platform_creds.client_secret,
        token_url=token_url,
    )
    access_token = auth.refresh_and_get_token(db_path, account_name, platform, **token_kwargs)

    def refresher():
        return auth.refresh_and_get_token(db_path, account_name, platform, **token_kwargs)

    return access_token, refresher


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

    if account is not None:
        # Targets path
        if not platform_creds.client_id:
            raise ConfigError(f"X client_id not configured for account '{account_name}'")

        tier = account.tier or "free"
        access_token, refresher = _get_oauth_token_and_refresher(
            db_path, account_name, "x", platform_creds
        )
        logger.info("Created X adapter for account '%s' (tier=%s)", account_name, tier)
        return XAdapter(access_token, tier=tier, token_refresher=refresher)

    # Legacy path
    from social_hook.filesystem import get_db_path

    client_id = config.env.get("X_CLIENT_ID", "")
    client_secret = config.env.get("X_CLIENT_SECRET", "")

    if not client_id:
        raise ConfigError("X_CLIENT_ID not configured in .env")

    token_db = str(get_db_path())
    x_config = config.platforms.get("x")
    tier = (x_config.account_tier if x_config else None) or "free"

    # Build a simple creds-like object for the shared helper
    class _LegacyCreds:
        def __init__(self, cid, cs):
            self.client_id = cid
            self.client_secret = cs

    access_token, refresher = _get_oauth_token_and_refresher(
        token_db, "x", "x", _LegacyCreds(client_id, client_secret)
    )
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

    if account is not None:
        # Targets path
        if not platform_creds.client_id:
            raise ConfigError(f"LinkedIn client_id not configured for account '{account_name}'")

        access_token, refresher = _get_oauth_token_and_refresher(
            db_path, account_name, "linkedin", platform_creds
        )
        entity = account.entity
        logger.info(
            "Created LinkedIn adapter for account '%s' (entity=%s)",
            account_name,
            entity or "personal",
        )
        return LinkedInAdapter(access_token, entity=entity, token_refresher=refresher)

    # Legacy path
    access_token = config.env.get("LINKEDIN_ACCESS_TOKEN", "")
    if not access_token:
        raise ConfigError("Missing LinkedIn access token")
    return LinkedInAdapter(access_token)


# Register at module load (lazy imports inside each factory function)
_platform_registry.register("x", _create_x, metadata={"display_name": "X/Twitter"})
_platform_registry.register("linkedin", _create_linkedin, metadata={"display_name": "LinkedIn"})


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
