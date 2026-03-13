"""Shared CLI utilities."""

import os


def resolve_project(project: str | None = None) -> str:
    """Resolve project path, defaulting to cwd.

    Args:
        project: Explicit path, or None to use current directory.

    Returns:
        Resolved absolute path.
    """
    return os.path.realpath(project or os.getcwd())
