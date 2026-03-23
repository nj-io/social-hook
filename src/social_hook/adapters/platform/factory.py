"""Platform adapter factory -- routes platform name to adapter class."""

from social_hook.adapters import auth
from social_hook.errors import ConfigError

X_TOKEN_URL = "https://api.x.com/2/oauth2/token"


def create_adapter(platform: str, config, db_path: str | None = None):
    """Create a platform adapter by name.

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
        token_kwargs = dict(client_id=client_id, client_secret=client_secret, token_url=X_TOKEN_URL)
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
