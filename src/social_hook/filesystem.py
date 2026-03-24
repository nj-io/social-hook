"""File system setup and utilities."""

import os
import uuid
from pathlib import Path

from social_hook.constants import CONFIG_DIR_NAME, DB_FILENAME, PROJECT_NAME


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


def init_filesystem(base: str | Path | None = None) -> Path:
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
    base = Path.home() / CONFIG_DIR_NAME if base is None else Path(base)

    # Create directories
    directories = [
        base,
        base / "migrations",
        base / "logs",
        base / "media-cache",
        base / "prompts",
        base / "narratives",
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


ENV_EXAMPLE_CONTENT = f"""\
# {PROJECT_NAME} Configuration
# Copy this file to .env and fill in your values

# Claude API (required for anthropic/ provider)
ANTHROPIC_API_KEY=sk-ant-...

# Telegram (required for notifications)
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_ALLOWED_CHAT_IDS=123456789

# X/Twitter (optional)
X_CLIENT_ID=...
X_CLIENT_SECRET=...

# LinkedIn (optional)
LINKEDIN_CLIENT_ID=...
LINKEDIN_CLIENT_SECRET=...
LINKEDIN_ACCESS_TOKEN=...

# Media Generation (optional)
GEMINI_API_KEY=...

# OpenAI (required for openai/ provider)
OPENAI_API_KEY=sk-...

# OpenRouter (required for openrouter/ provider)
OPENROUTER_API_KEY=sk-or-v1-...

# Ollama (optional, defaults to localhost:11434)
OLLAMA_BASE_URL=http://localhost:11434/v1
"""


CONFIG_EXAMPLE_CONTENT = f"""\
# {PROJECT_NAME} Configuration
# Copy this file to config.yaml and customize

models:
  evaluator: anthropic/claude-opus-4-5     # or claude-cli/sonnet ($0 with subscription)
  drafter: anthropic/claude-opus-4-5       # or claude-cli/sonnet ($0 with subscription)
  gatekeeper: anthropic/claude-haiku-4-5   # or claude-cli/haiku ($0 with subscription)

platforms:
  x:
    enabled: true
    account_tier: free  # free, basic, premium, or premium_plus
  linkedin:
    enabled: false

media_generation:
  enabled: true
  tools:
    mermaid: true
    nano_banana_pro: true
    playwright: true
    ray_so: true

scheduling:
  timezone: America/Los_Angeles
  max_posts_per_day: 3
  min_gap_minutes: 30
  optimal_days: [Tue, Wed, Thu]
  optimal_hours: [9, 12, 17]

# Development journey capture (requires Claude Code)
journey_capture:
  enabled: false
  # model: anthropic/claude-sonnet-4-5  # defaults to evaluator model
"""


def get_base_path() -> Path:
    """Get the base path for social-hook data.

    Returns:
        Path to ~/.social-hook/
    """
    return Path.home() / CONFIG_DIR_NAME


def _detect_worktree_name() -> str | None:
    """Detect if running from a git worktree via PYTHONPATH.

    Returns worktree name if detected, None otherwise.
    """
    pythonpath = os.environ.get("PYTHONPATH", "")
    marker = ".claude/worktrees/"
    idx = pythonpath.find(marker)
    if idx == -1:
        return None
    after = pythonpath[idx + len(marker) :]
    # Extract worktree name (up to next / or end)
    name = after.split("/")[0]
    return name if name else None


def get_db_path() -> Path:
    """Get the path to the SQLite database.

    In worktrees (detected via PYTHONPATH containing .claude/worktrees/),
    uses a separate DB per worktree to avoid migration collisions. The main
    DB is copied on first use to bootstrap the worktree with existing data.

    Returns:
        Path to ~/.social-hook/social-hook.db (or social-hook-{worktree}.db)
    """
    base = get_base_path()
    worktree = _detect_worktree_name()
    if not worktree:
        return base / DB_FILENAME

    stem = Path(DB_FILENAME).stem
    suffix = Path(DB_FILENAME).suffix
    wt_db = base / f"{stem}-{worktree}{suffix}"

    if not wt_db.exists():
        main_db = base / DB_FILENAME
        if main_db.exists():
            import shutil

            shutil.copy2(main_db, wt_db)

    return wt_db


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


def get_narratives_path() -> Path:
    """Get the path to the narratives directory.

    Returns:
        Path to ~/.social-hook/narratives/
    """
    return get_base_path() / "narratives"


def cleanup_orphaned_media(conn, dry_run: bool = False) -> list[str]:
    """Remove media-cache directories not referenced by any draft.

    Scans media-cache/ for subdirectories and media-cache/uploads/ for
    per-draft upload directories.  Compares against all media_paths stored
    in the drafts table and deletes unreferenced directories.

    Args:
        conn: SQLite connection (read-only usage).
        dry_run: If True, report but don't delete.

    Returns:
        List of directory paths removed (or that would be removed).
    """
    import json
    import shutil

    media_root = get_base_path() / "media-cache"
    if not media_root.exists():
        return []

    # Collect all referenced paths from drafts
    rows = conn.execute("SELECT media_paths FROM drafts WHERE media_paths IS NOT NULL").fetchall()
    referenced: set[str] = set()
    for row in rows:
        raw = row[0] if row[0] else "[]"
        try:
            paths = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            continue
        for p in paths:
            # Normalize to absolute and add all parent dirs under media-cache
            pp = Path(p).resolve()
            referenced.add(str(pp))
            # Also mark the parent directory as referenced
            if pp.parent != media_root.resolve():
                referenced.add(str(pp.parent))

    removed: list[str] = []

    # Scan top-level directories in media-cache (excluding 'uploads')
    for child in sorted(media_root.iterdir()):
        if not child.is_dir():
            continue
        if child.name == "uploads":
            # Scan uploads subdirectories separately
            for upload_dir in sorted(child.iterdir()):
                if not upload_dir.is_dir():
                    continue
                resolved = str(upload_dir.resolve())
                if resolved not in referenced and not _dir_has_referenced_file(
                    upload_dir, referenced
                ):
                    removed.append(str(upload_dir))
                    if not dry_run:
                        shutil.rmtree(upload_dir)
        else:
            resolved = str(child.resolve())
            if resolved not in referenced and not _dir_has_referenced_file(child, referenced):
                removed.append(str(child))
                if not dry_run:
                    shutil.rmtree(child)

    return removed


def _dir_has_referenced_file(directory: Path, referenced: set[str]) -> bool:
    """Check if any file under directory is in the referenced set."""
    return any(f.is_file() and str(f.resolve()) in referenced for f in directory.rglob("*"))
