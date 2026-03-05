"""Platform adapter factory -- routes platform name to adapter class."""

from social_hook.errors import ConfigError


def create_adapter(platform: str, config):
    """Create a platform adapter by name.

    Args:
        platform: Platform name (e.g., "x", "linkedin").
        config: Global Config object (for credentials via config.env).

    Returns:
        Configured PlatformAdapter instance.

    Raises:
        ConfigError: If platform is unknown or credentials missing.
    """
    if platform == "x":
        from social_hook.adapters.platform.x import XAdapter

        api_key = config.env.get("X_API_KEY", "")
        api_secret = config.env.get("X_API_SECRET", "")
        access_token = config.env.get("X_ACCESS_TOKEN", "")
        access_secret = config.env.get("X_ACCESS_TOKEN_SECRET", "")

        if not all([api_key, api_secret, access_token, access_secret]):
            raise ConfigError("Missing X API credentials")

        x_config = config.platforms.get("x")
        tier = (x_config.account_tier if x_config else None) or "free"
        return XAdapter(api_key, api_secret, access_token, access_secret, tier=tier)

    elif platform == "linkedin":
        from social_hook.adapters.platform.linkedin import LinkedInAdapter

        access_token = config.env.get("LINKEDIN_ACCESS_TOKEN", "")
        if not access_token:
            raise ConfigError("Missing LinkedIn access token")
        return LinkedInAdapter(access_token)

    else:
        raise ConfigError(f"Unknown platform: {platform}")
