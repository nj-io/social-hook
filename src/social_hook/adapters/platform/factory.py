"""Platform adapter factory -- routes platform name to adapter class."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from social_hook.adapters import auth
from social_hook.errors import ConfigError

if TYPE_CHECKING:
    from social_hook.adapters.platform.base import PlatformAdapter
    from social_hook.config.targets import AccountConfig, PlatformCredentialConfig

logger = logging.getLogger(__name__)

# Platform-specific token refresh URLs
_REFRESH_URLS: dict[str, str] = {
    "x": "https://api.x.com/2/oauth2/token",
    "linkedin": "https://www.linkedin.com/oauth/v2/accessToken",
}


def create_adapter(platform: str, config, db_path: str | None = None):
    """Create a platform adapter by name (legacy interface).

    Args:
        platform: Platform name (e.g., "x", "linkedin").
        config: Global Config object (for credentials via config.env).
        db_path: Path to SQLite database (required for X OAuth 2.0 tokens).

    Returns:
        Configured PlatformAdapter instance.

    Raises:
        ConfigError: If platform is unknown or credentials missing.
    """
    if platform == "x":
        from social_hook.adapters.platform.x import XAdapter

        client_id = config.env.get("X_CLIENT_ID", "")
        client_secret = config.env.get("X_CLIENT_SECRET", "")

        if not client_id:
            raise ConfigError("X_CLIENT_ID not configured in .env")
        if not db_path:
            raise ConfigError("db_path required for X adapter (OAuth 2.0 tokens stored in DB)")

        x_config = config.platforms.get("x")
        tier = (x_config.account_tier if x_config else None) or "free"

        account_name = "x"  # pre-targets: one account per platform
        token_kwargs = dict(
            client_id=client_id, client_secret=client_secret, token_url=_REFRESH_URLS["x"]
        )
        access_token = auth.refresh_and_get_token(db_path, account_name, "x", **token_kwargs)

        def refresher():
            return auth.refresh_and_get_token(db_path, account_name, "x", **token_kwargs)

        return XAdapter(access_token, tier=tier, token_refresher=refresher)

    elif platform == "linkedin":
        from social_hook.adapters.platform.linkedin import LinkedInAdapter

        access_token = config.env.get("LINKEDIN_ACCESS_TOKEN", "")
        if not access_token:
            raise ConfigError("Missing LinkedIn access token")
        return LinkedInAdapter(access_token)

    else:
        raise ConfigError(f"Unknown platform: {platform}")


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

    Routes by account.platform to the appropriate adapter class.
    Builds a token_refresher closure for OAuth 2.0 token management.

    Args:
        account_name: Unique account identifier from config.
        account: AccountConfig with platform, tier, etc.
        platform_creds: PlatformCredentialConfig with client_id/secret.
        env: Environment variables dict (unused for now, reserved for future).
        db_path: Path to SQLite database for token storage.
        on_error: Optional callback for error reporting.

    Returns:
        Configured PlatformAdapter instance.

    Raises:
        ConfigError: If platform is unknown or credentials missing.
    """
    platform = account.platform

    if platform == "x":
        from social_hook.adapters.platform.x import XAdapter

        if not platform_creds.client_id:
            raise ConfigError(f"X client_id not configured for account '{account_name}'")

        tier = account.tier or "free"
        refresh_url = _REFRESH_URLS["x"]

        token_kwargs = dict(
            client_id=platform_creds.client_id,
            client_secret=platform_creds.client_secret,
            token_url=refresh_url,
            on_error=on_error,
        )
        access_token = auth.refresh_and_get_token(db_path, account_name, "x", **token_kwargs)

        def x_refresher():
            return auth.refresh_and_get_token(db_path, account_name, "x", **token_kwargs)

        logger.info("Created X adapter for account '%s' (tier=%s)", account_name, tier)
        return XAdapter(access_token, tier=tier, token_refresher=x_refresher)

    elif platform == "linkedin":
        from social_hook.adapters.platform.linkedin import LinkedInAdapter

        if not platform_creds.client_id:
            raise ConfigError(f"LinkedIn client_id not configured for account '{account_name}'")

        refresh_url = _REFRESH_URLS["linkedin"]

        token_kwargs = dict(
            client_id=platform_creds.client_id,
            client_secret=platform_creds.client_secret,
            token_url=refresh_url,
            on_error=on_error,
        )
        access_token = auth.refresh_and_get_token(db_path, account_name, "linkedin", **token_kwargs)

        def linkedin_refresher():
            return auth.refresh_and_get_token(db_path, account_name, "linkedin", **token_kwargs)

        logger.info("Created LinkedIn adapter for account '%s'", account_name)
        return LinkedInAdapter(access_token, token_refresher=linkedin_refresher)

    else:
        logger.warning("Unknown platform '%s' for account '%s'", platform, account_name)
        raise ConfigError(f"Unknown platform: '{platform}'")
