"""Thin wrapper for memory operations (delegates to config.project)."""

from pathlib import Path
from typing import Union

from social_hook.config.project import _parse_memories, save_memory as _save_memory
from social_hook.constants import CONFIG_DIR_NAME


def add_memory(
    repo_path: Union[str, Path],
    context: str,
    feedback: str,
    draft_id: str,
) -> None:
    """Add a memory entry to the project's memories.md file.

    Args:
        repo_path: Path to the project repository (filesystem path, not project_id)
        context: Brief description of content type
        feedback: Quoted human feedback text
        draft_id: Reference to original draft
    """
    _save_memory(repo_path, context, feedback, draft_id)


def parse_memories_file(repo_path: Union[str, Path]) -> list[dict]:
    """Parse memories from a project's memories.md file.

    Args:
        repo_path: Path to the project repository (filesystem path, not project_id)

    Returns:
        List of memory dicts with date, context, feedback, draft_id keys.
        Empty list if file doesn't exist.
    """
    memories_path = Path(repo_path) / CONFIG_DIR_NAME / "memories.md"
    if not memories_path.exists():
        return []
    content = memories_path.read_text(encoding="utf-8")
    return _parse_memories(content)
