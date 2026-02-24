"""Environment variable loading from .env files."""

import os
from pathlib import Path
from typing import Optional

from dotenv import dotenv_values

from social_hook.errors import ConfigError

# Required keys that must be present
REQUIRED_KEYS = []

# All known environment variable keys
KNOWN_KEYS = [
    # Required
    "ANTHROPIC_API_KEY",
    # Telegram (required for full functionality)
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_ALLOWED_CHAT_IDS",
    # X/Twitter (optional)
    "X_API_KEY",
    "X_API_SECRET",
    "X_ACCESS_TOKEN",
    "X_ACCESS_TOKEN_SECRET",
    # LinkedIn (optional)
    "LINKEDIN_CLIENT_ID",
    "LINKEDIN_CLIENT_SECRET",
    "LINKEDIN_ACCESS_TOKEN",
    # Media generation (optional)
    "GEMINI_API_KEY",
    # Additional LLM providers (optional)
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "OLLAMA_BASE_URL",
]

# Logical grouping for UI display
KEY_GROUPS = {
    "Core": ["ANTHROPIC_API_KEY"],
    "Telegram": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_CHAT_IDS"],
    "X / Twitter": ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"],
    "LinkedIn": ["LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET", "LINKEDIN_ACCESS_TOKEN"],
    "Media Generation": ["GEMINI_API_KEY"],
    "LLM Providers": ["OPENAI_API_KEY", "OPENROUTER_API_KEY", "OLLAMA_BASE_URL"],
}


def load_env(env_path: Optional[str | Path] = None) -> dict[str, str]:
    """Load environment variables from .env file.

    Args:
        env_path: Path to .env file. If None, uses ~/.social-hook/.env

    Returns:
        Dict of environment variables

    Raises:
        ConfigError: If required keys are missing
    """
    if env_path is None:
        env_path = Path.home() / ".social-hook" / ".env"
    else:
        env_path = Path(env_path)

    env_vars: dict[str, str] = {}

    # Load from file using python-dotenv (handles export, multiline, escapes, etc.)
    if env_path.exists():
        env_vars = {k: v for k, v in dotenv_values(env_path).items() if v is not None}

    # Environment variables override file
    for key in KNOWN_KEYS:
        if key in os.environ:
            env_vars[key] = os.environ[key]

    # Validate required keys
    missing = [key for key in REQUIRED_KEYS if key not in env_vars]
    if missing:
        raise ConfigError(f"Missing required: {', '.join(missing)}")

    return env_vars
