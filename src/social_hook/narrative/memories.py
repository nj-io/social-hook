"""Thin wrapper for memory operations (delegates to config.project)."""

from pathlib import Path
from typing import Union

from social_hook.config.project import (
    _parse_memories,
    save_memory as _save_memory,
    list_memories,
    delete_memory,
    clear_memories,
)


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
    return list_memories(repo_path)


__all__ = [
    "add_memory",
    "parse_memories_file",
    "list_memories",
    "delete_memory",
    "clear_memories",
]
