"""Per-project configuration loading."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from social_hook.errors import ConfigError


@dataclass
class ProjectConfig:
    """Per-project configuration loaded from project repository."""

    # social-context.md contents
    social_context: Optional[str] = None

    # content-config.yaml parsed data
    content_config: dict[str, Any] = field(default_factory=dict)

    # memories.md contents
    memories: Optional[str] = None

    # Path to the project
    repo_path: Optional[str] = None


def load_project_config(repo_path: str | Path) -> ProjectConfig:
    """Load per-project configuration from a repository.

    Loads from .social-hook/ subdirectory:
    - social-context.md: Voice, style, audience, themes, pet peeves
    - content-config.yaml: Platform settings, tools, posting rules
    - memories.md: Accumulated feedback history

    Args:
        repo_path: Path to the project repository

    Returns:
        ProjectConfig with loaded data (missing files return None/defaults)

    Raises:
        ConfigError: If YAML is invalid
    """
    repo_path = Path(repo_path)
    config_dir = repo_path / ".social-hook"
    config = ProjectConfig(repo_path=str(repo_path))

    # Load social-context.md
    social_context_path = config_dir / "social-context.md"
    if social_context_path.exists():
        config.social_context = social_context_path.read_text()

    # Load content-config.yaml
    content_config_path = config_dir / "content-config.yaml"
    if content_config_path.exists():
        try:
            content = content_config_path.read_text()
            config.content_config = yaml.safe_load(content) or {}
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in {content_config_path}: {e}") from e

    # Load memories.md
    memories_path = config_dir / "memories.md"
    if memories_path.exists():
        config.memories = memories_path.read_text()

    return config


def save_memory(
    repo_path: str | Path,
    context: str,
    feedback: str,
    draft_id: str,
) -> None:
    """Add a memory entry to the project's memories.md file.

    Args:
        repo_path: Path to the project repository
        context: Brief description of content type
        feedback: Quoted human feedback text
        draft_id: Reference to original draft
    """
    from datetime import date

    repo_path = Path(repo_path)
    config_dir = repo_path / ".social-hook"
    config_dir.mkdir(parents=True, exist_ok=True)
    memories_path = config_dir / "memories.md"

    # Parse existing memories
    memories = []
    if memories_path.exists():
        content = memories_path.read_text()
        memories = _parse_memories(content)

    # Add new memory
    memories.append({
        "date": date.today().isoformat(),
        "context": context,
        "feedback": feedback,
        "draft_id": draft_id,
    })

    # Keep only most recent 100
    if len(memories) > 100:
        memories = memories[-100:]

    # Write back
    _write_memories(memories_path, memories)


def _parse_memories(content: str) -> list[dict]:
    """Parse memories.md markdown table into list of dicts."""
    memories = []
    lines = content.strip().split("\n")

    # Find table rows (skip header and separator)
    in_table = False
    for line in lines:
        line = line.strip()
        if line.startswith("| Date"):
            in_table = True
            continue
        if line.startswith("|---"):
            continue
        if in_table and line.startswith("|"):
            parts = [p.strip() for p in line.split("|")]
            # parts[0] is empty (before first |), parts[-1] is empty (after last |)
            if len(parts) >= 5:
                memories.append({
                    "date": parts[1],
                    "context": parts[2],
                    "feedback": parts[3],
                    "draft_id": parts[4],
                })

    return memories


def _write_memories(path: Path, memories: list[dict]) -> None:
    """Write memories list back to markdown file."""
    lines = [
        "# Voice Memories",
        "",
        "| Date | Context | Feedback | Draft ID |",
        "|------|---------|----------|----------|",
    ]

    for m in memories:
        lines.append(f"| {m['date']} | {m['context']} | {m['feedback']} | {m['draft_id']} |")

    path.write_text("\n".join(lines) + "\n")
