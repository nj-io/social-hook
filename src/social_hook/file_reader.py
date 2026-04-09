"""Token-budgeted file reader with path traversal protection.

Zero social-hook imports — reusable across projects.
Loads files within a token budget, skipping binary/missing/unreadable files.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

# Default extensions considered safe to read as text
DEFAULT_TEXT_EXTENSIONS = {
    ".md",
    ".txt",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".yaml",
    ".yml",
    ".toml",
    ".json",
    ".rs",
    ".go",
    ".sql",
    ".sh",
    ".rst",
    ".html",
    ".css",
    ".cfg",
    ".ini",
    ".env.example",
    ".csv",
}


def _default_token_count(text: str) -> int:
    """Approximate token count: ~4 chars per token."""
    return len(text) // 4


def read_files_within_budget(
    paths: list[str | Path],
    base_dir: str | Path,
    max_tokens: int = 10_000,
    extensions: set[str] | None = None,
    count_fn: Callable[[str], int] | None = None,
) -> tuple[str, int]:
    """Read files within a token budget.

    Returns (assembled_text, tokens_used).

    Features:
    - Path traversal protection via resolve().is_relative_to(base_dir)
    - Deduplication by resolved path
    - Skips binary files (by extension), missing files, encoding errors
    - Logs skipped files at debug level

    Args:
        paths: File paths to read (relative to base_dir or absolute)
        base_dir: Base directory — paths must resolve within this
        max_tokens: Maximum token budget for assembled output
        extensions: Allowed file extensions (default: common text types)
        count_fn: Token counting function (default: len(text) // 4)
    """
    if extensions is None:
        extensions = DEFAULT_TEXT_EXTENSIONS
    if count_fn is None:
        count_fn = _default_token_count

    base = Path(base_dir).resolve()
    parts: list[str] = []
    tokens_used = 0
    seen: set[Path] = set()

    for raw_path in paths:
        p = Path(raw_path)
        # Resolve relative paths against base_dir
        if not p.is_absolute():
            p = base / p
        resolved = p.resolve()

        # Path traversal protection
        if not resolved.is_relative_to(base):
            logger.debug("Skipping path outside base_dir: %s", raw_path)
            continue

        # Deduplication
        if resolved in seen:
            logger.debug("Skipping duplicate path: %s", raw_path)
            continue
        seen.add(resolved)

        # Existence check
        if not resolved.exists() or not resolved.is_file():
            logger.debug("Skipping missing file: %s", raw_path)
            continue

        # Extension check
        suffix = resolved.suffix.lower()
        if extensions and suffix not in extensions:
            logger.debug("Skipping non-text extension: %s", raw_path)
            continue

        # Read file
        try:
            content = resolved.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            logger.debug("Skipping unreadable file %s: %s", raw_path, e)
            continue

        file_tokens = count_fn(content)

        # Budget check
        if tokens_used + file_tokens > max_tokens:
            remaining = max_tokens - tokens_used
            if remaining >= 100:
                # Truncate to fit
                # Estimate chars for remaining tokens (4 chars/token)
                char_budget = remaining * 4
                content = content[:char_budget] + "\n[...truncated]"
                rel = resolved.relative_to(base) if resolved.is_relative_to(base) else resolved
                parts.append(f"### {rel}\n{content}")
                tokens_used = max_tokens
            break

        rel = resolved.relative_to(base) if resolved.is_relative_to(base) else resolved
        parts.append(f"### {rel}\n{content}")
        tokens_used += file_tokens

    return "\n\n".join(parts), tokens_used
