"""Two-pass project discovery: file selection + summary generation."""

import json
import logging
import os
import sqlite3
from fnmatch import fnmatch
from pathlib import Path
from typing import Optional

from social_hook.db import operations as ops
from social_hook.llm._usage_logger import log_usage
from social_hook.llm.base import LLMClient, NormalizedResponse
from social_hook.llm.prompts import count_tokens

logger = logging.getLogger(__name__)

# File extensions to include in project file listing
DISCOVERY_EXTENSIONS = {
    ".md", ".py", ".ts", ".tsx", ".yaml", ".yml",
    ".toml", ".json", ".rs", ".go",
}

# Directories to skip during file listing
IGNORE_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", "target", "vendor",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "egg-info",
}

# Tool schemas for two-pass discovery
SELECT_FILES_TOOL = {
    "name": "select_files",
    "description": "Select the most important files for understanding this project",
    "input_schema": {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of file paths to read for project understanding",
            },
            "reasoning": {
                "type": "string",
                "description": "Why these files were selected",
            },
        },
        "required": ["files", "reasoning"],
    },
}

GENERATE_SUMMARY_TOOL = {
    "name": "generate_summary",
    "description": "Generate a comprehensive project summary",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "Comprehensive project summary (~500-800 tokens)",
            },
        },
        "required": ["summary"],
    },
}


def _should_ignore_dir(dirname: str) -> bool:
    """Check if a directory should be ignored during file listing."""
    return dirname in IGNORE_DIRS or dirname.endswith(".egg-info")


def list_project_files(
    repo_path: str,
    extensions: Optional[set[str]] = None,
    ignore_dirs: Optional[set[str]] = None,
    max_files: int = 500,
) -> str:
    """Walk repo tree and return formatted file listing.

    Args:
        repo_path: Path to the repository root
        extensions: File extensions to include (default: DISCOVERY_EXTENSIONS)
        ignore_dirs: Directory names to skip (default: IGNORE_DIRS)
        max_files: Maximum files to list

    Returns:
        Formatted string with one "path (size)" per line
    """
    if extensions is None:
        extensions = DISCOVERY_EXTENSIONS
    if ignore_dirs is None:
        ignore_dirs = IGNORE_DIRS

    entries = []
    repo = Path(repo_path)

    for dirpath, dirnames, filenames in os.walk(repo):
        # Prune ignored directories in-place
        dirnames[:] = [
            d for d in dirnames
            if not _should_ignore_dir(d)
        ]

        rel_dir = Path(dirpath).relative_to(repo)
        for fname in sorted(filenames):
            if len(entries) >= max_files:
                break

            fpath = Path(dirpath) / fname
            suffix = fpath.suffix.lower()
            if suffix not in extensions:
                continue

            rel_path = rel_dir / fname
            try:
                size = fpath.stat().st_size
                if size < 1024:
                    size_str = f"{size}B"
                elif size < 1024 * 1024:
                    size_str = f"{size // 1024}KB"
                else:
                    size_str = f"{size // (1024 * 1024)}MB"
                entries.append(f"{rel_path} ({size_str})")
            except OSError:
                continue

        if len(entries) >= max_files:
            break

    return "\n".join(entries)


def _extract_tool_input(response: NormalizedResponse, tool_name: str) -> Optional[dict]:
    """Extract tool call input from a NormalizedResponse."""
    for content in response.content:
        if content.type == "tool_use" and content.name == tool_name:
            return content.input
    return None


def _resolve_project_doc_globs(repo_path: str, globs: list[str]) -> list[str]:
    """Resolve glob patterns from project_docs config into file paths."""
    repo = Path(repo_path)
    resolved = []
    for pattern in globs:
        for match in sorted(repo.glob(pattern)):
            if match.is_file():
                rel = str(match.relative_to(repo))
                if rel not in resolved:
                    resolved.append(rel)
    return resolved


def discover_project(
    client: LLMClient,
    repo_path: str,
    project_docs: Optional[list[str]] = None,
    max_doc_tokens: int = 10000,
    db: Optional[object] = None,
    project_id: Optional[str] = None,
) -> tuple[Optional[str], list[str]]:
    """Two-pass project discovery: select files then generate summary.

    Pass 1: Given the file listing, LLM selects the most important files.
    Pass 2: Load selected files within token budget, generate summary.

    Args:
        client: LLM client for making API calls
        repo_path: Path to the repository
        project_docs: User-specified glob patterns for priority files
        max_doc_tokens: Token budget for file loading
        db: Optional DB context for usage tracking
        project_id: Optional project ID for usage tracking

    Returns:
        Tuple of (summary_text, selected_file_paths).
        Returns (None, []) on failure.
    """
    # Build file listing
    file_listing = list_project_files(repo_path)
    if not file_listing:
        logger.warning("No files found in %s for discovery", repo_path)
        return None, []

    # Resolve user-specified project docs
    priority_files = []
    if project_docs:
        priority_files = _resolve_project_doc_globs(repo_path, project_docs)

    # Pass 1: File selection
    system_prompt = (
        "You are analyzing a software project. Given the file listing below, "
        "select the most important files for understanding what this project does, "
        "its architecture, and current state. Select 5-15 files that would give "
        "the best overview. Prefer README, documentation, config files, and "
        "key source files."
    )

    user_message = file_listing
    if priority_files:
        user_message += (
            "\n\n--- PRIORITY FILES (user-specified, always include these) ---\n"
            + "\n".join(priority_files)
        )

    response = client.complete(
        messages=[{"role": "user", "content": user_message}],
        tools=[SELECT_FILES_TOOL],
        system=system_prompt,
        max_tokens=2048,
    )
    log_usage(db, "discovery_select", getattr(client, "full_id", "unknown"),
              response.usage, project_id)

    tool_input = _extract_tool_input(response, "select_files")
    if not tool_input or "files" not in tool_input:
        logger.warning("Discovery pass 1 failed: no select_files tool call")
        return None, []

    selected_files = tool_input["files"]

    # Ensure priority files are included
    for pf in priority_files:
        if pf not in selected_files:
            selected_files.insert(0, pf)

    # Pass 2: Load files within budget, generate summary
    repo = Path(repo_path)
    loaded_content = []
    tokens_used = 0

    # Load priority files first, then other selected files
    priority_set = set(priority_files)
    ordered_files = [f for f in selected_files if f in priority_set] + [f for f in selected_files if f not in priority_set]

    files_loaded = []
    for rel_path in ordered_files:
        fpath = repo / rel_path
        if not fpath.exists() or not fpath.is_file():
            continue
        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
            file_tokens = count_tokens(content)
            if tokens_used + file_tokens > max_doc_tokens:
                # Truncate this file to fit remaining budget
                remaining = max_doc_tokens - tokens_used
                if remaining > 100:  # Only include if meaningful
                    content = content[:remaining * 4] + "\n[...truncated]"
                    loaded_content.append(f"--- {rel_path} ---\n{content}")
                    files_loaded.append(rel_path)
                break
            loaded_content.append(f"--- {rel_path} ---\n{content}")
            files_loaded.append(rel_path)
            tokens_used += file_tokens
        except (OSError, UnicodeDecodeError):
            continue

    if not loaded_content:
        logger.warning("Discovery pass 2: no files could be loaded")
        return None, []

    summary_system = (
        "Generate a comprehensive project summary (~500-800 tokens) covering: "
        "what the project does, the problem it solves, architecture overview, "
        "key technologies, and current development state. Be specific and concrete."
    )

    summary_response = client.complete(
        messages=[{"role": "user", "content": "\n\n".join(loaded_content)}],
        tools=[GENERATE_SUMMARY_TOOL],
        system=summary_system,
        max_tokens=2048,
    )
    log_usage(db, "discovery_summarize", getattr(client, "full_id", "unknown"),
              summary_response.usage, project_id)

    summary_input = _extract_tool_input(summary_response, "generate_summary")
    if not summary_input or "summary" not in summary_input:
        logger.warning("Discovery pass 2 failed: no generate_summary tool call")
        return None, []

    return summary_input["summary"], files_loaded
