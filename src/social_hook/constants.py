"""Central branding and naming constants.

Zero internal dependencies — importable anywhere without circular risk.
"""

# Display name (UI headers, bot text, welcome messages)
PROJECT_NAME = "Social Hook"

# CLI binary name, config directory, systemd prefix
PROJECT_SLUG = "social-hook"

# One-line description (CLI help, pyproject.toml)
PROJECT_DESCRIPTION = "Automated social media content from development activity"

# Config directory (dot-prefixed, in $HOME and project repos)
CONFIG_DIR_NAME = ".social-hook"

# SQLite database filename (inside CONFIG_DIR_NAME)
DB_FILENAME = "social-hook.db"

# Python module name (documentation/reference only)
MODULE_NAME = "social_hook"

# GitHub repository (owner/repo)
GITHUB_REPO = "nj-io/social-hook"
