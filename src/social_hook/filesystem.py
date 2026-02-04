"""File system setup and utilities."""

import os
import uuid
from pathlib import Path
from typing import Optional


def generate_id(prefix: str) -> str:
    """Generate a unique ID with a prefix.

    Args:
        prefix: Prefix for the ID (e.g., "draft", "decision", "project")

    Returns:
        ID in format "{prefix}_{12_hex_chars}"

    Raises:
        ValueError: If prefix is empty
    """
    if not prefix:
        raise ValueError("Prefix cannot be empty")

    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def init_filesystem(base: Optional[str | Path] = None) -> Path:
    """Initialize the social-hook file system structure.

    Creates:
    - ~/.social-hook/
    - ~/.social-hook/migrations/
    - ~/.social-hook/logs/
    - ~/.social-hook/media-cache/
    - ~/.social-hook/prompts/
    - ~/.social-hook/.env.example (if not exists)
    - ~/.social-hook/config.yaml.example (if not exists)

    Args:
        base: Base directory (default: ~/.social-hook/)

    Returns:
        Path to base directory
    """
    if base is None:
        base = Path.home() / ".social-hook"
    else:
        base = Path(base)

    # Create directories
    directories = [
        base,
        base / "migrations",
        base / "logs",
        base / "media-cache",
        base / "prompts",
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

    # Create .env.example if it doesn't exist
    env_example = base / ".env.example"
    if not env_example.exists():
        env_example.write_text(ENV_EXAMPLE_CONTENT)

    # Create config.yaml.example if it doesn't exist
    config_example = base / "config.yaml.example"
    if not config_example.exists():
        config_example.write_text(CONFIG_EXAMPLE_CONTENT)

    # Ensure .env has restrictive permissions if it exists
    env_file = base / ".env"
    if env_file.exists():
        os.chmod(env_file, 0o600)

    return base


ENV_EXAMPLE_CONTENT = """\
# Social Hook Configuration
# Copy this file to .env and fill in your values

# Claude API (required)
ANTHROPIC_API_KEY=sk-ant-...

# Telegram (required for notifications)
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_ALLOWED_CHAT_IDS=123456789

# X/Twitter (optional)
X_API_KEY=...
X_API_SECRET=...
X_ACCESS_TOKEN=...
X_ACCESS_TOKEN_SECRET=...

# LinkedIn (optional)
LINKEDIN_CLIENT_ID=...
LINKEDIN_CLIENT_SECRET=...
LINKEDIN_ACCESS_TOKEN=...

# Image Generation (optional)
GEMINI_API_KEY=...
"""


CONFIG_EXAMPLE_CONTENT = """\
# Social Hook Configuration
# Copy this file to config.yaml and customize

models:
  evaluator: claude-opus-4-5     # Decides post-worthiness (claude-opus-4-5 or claude-sonnet-4-5)
  drafter: claude-opus-4-5       # Creates content (claude-opus-4-5 or claude-sonnet-4-5)
  gatekeeper: claude-haiku-4-5   # Handles simple Telegram interactions

platforms:
  x:
    enabled: true
    account_tier: free  # free, premium, or premium_plus
  linkedin:
    enabled: false

image_generation:
  enabled: true
  service: nano_banana_pro
  # Mermaid diagrams always available (no API key needed)

scheduling:
  timezone: America/Los_Angeles
  max_posts_per_day: 3
  min_gap_minutes: 30
  optimal_days: [Tue, Wed, Thu]
  optimal_hours: [9, 12, 17]
"""


def get_base_path() -> Path:
    """Get the base path for social-hook data.

    Returns:
        Path to ~/.social-hook/
    """
    return Path.home() / ".social-hook"


def get_db_path() -> Path:
    """Get the path to the SQLite database.

    Returns:
        Path to ~/.social-hook/social-hook.db
    """
    return get_base_path() / "social-hook.db"


def get_env_path() -> Path:
    """Get the path to the .env file.

    Returns:
        Path to ~/.social-hook/.env
    """
    return get_base_path() / ".env"


def get_config_path() -> Path:
    """Get the path to the config.yaml file.

    Returns:
        Path to ~/.social-hook/config.yaml
    """
    return get_base_path() / "config.yaml"


def get_logs_path() -> Path:
    """Get the path to the logs directory.

    Returns:
        Path to ~/.social-hook/logs/
    """
    return get_base_path() / "logs"
