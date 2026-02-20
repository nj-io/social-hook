"""JSONL transcript reader and filter for Claude Code session transcripts."""

import json
from pathlib import Path
from typing import Optional


def read_transcript(path: str | Path) -> list[dict]:
    """Read JSONL transcript file. Skips malformed lines gracefully.

    Filters to only 'user' and 'assistant' type lines -- skips
    'progress' (51% of lines), 'system', 'queue-operation',
    'file-history-snapshot', 'summary', and any other non-conversational types.

    Args:
        path: Path to the JSONL transcript file.

    Returns:
        List of parsed user/assistant message dicts.
    """
    path = Path(path)
    messages: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(entry, dict):
                continue
            entry_type = entry.get("type")
            if entry_type in ("user", "assistant"):
                messages.append(entry)
    return messages


def discover_transcript_path(session_id: str, cwd: str) -> Optional[Path]:
    """Construct transcript path from session_id + cwd.

    Handles the empty transcript_path bug (anthropics/claude-code#13668).
    Encodes cwd as path-component: /Users/neil/dev/project -> -Users-neil-dev-project

    Args:
        session_id: The Claude Code session identifier.
        cwd: The current working directory of the session.

    Returns:
        Path to the JSONL transcript file if it exists, None otherwise.
    """
    encoded_cwd = cwd.replace("/", "-")
    transcript_path = (
        Path.home() / ".claude" / "projects" / encoded_cwd / f"{session_id}.jsonl"
    )
    if transcript_path.exists():
        return transcript_path
    return None


def filter_for_extraction(messages: list[dict]) -> list[dict]:
    """Strip tool_use, tool_result, and image content blocks (security).

    Keep text and thinking blocks. Filter out isSidechain messages.
    Filter out empty text blocks (whitespace-only preambles).
    Handles message.content as both string and array of content blocks.

    Args:
        messages: List of user/assistant message dicts from read_transcript.

    Returns:
        Filtered list of messages with only safe content blocks.
    """
    filtered: list[dict] = []
    for msg in messages:
        if msg.get("isSidechain"):
            continue
        message = msg.get("message", {})
        content = message.get("content")
        if content is None:
            continue

        if isinstance(content, str):
            if content.strip():
                filtered.append(msg)
            continue

        if not isinstance(content, list):
            continue

        kept_blocks: list[dict] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type in ("tool_use", "tool_result", "image"):
                continue
            if block_type == "text":
                text = block.get("text", "")
                if not text.strip():
                    continue
                kept_blocks.append(block)
            elif block_type == "thinking":
                kept_blocks.append(block)

        if kept_blocks:
            filtered_msg = dict(msg)
            filtered_msg["message"] = dict(message)
            filtered_msg["message"]["content"] = kept_blocks
            filtered.append(filtered_msg)

    return filtered


def format_for_prompt(messages: list[dict]) -> str:
    """Format filtered messages as [USER] / [ASSISTANT] / [ASSISTANT THINKING] blocks.

    Args:
        messages: Filtered list of messages from filter_for_extraction.

    Returns:
        Formatted string with labeled message blocks.
    """
    parts: list[str] = []
    for msg in messages:
        message = msg.get("message", {})
        role = message.get("role", "unknown")
        content = message.get("content")
        if content is None:
            continue

        if isinstance(content, str):
            label = role.upper()
            parts.append(f"[{label}] {content}")
            continue

        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "text":
                    label = role.upper()
                    parts.append(f"[{label}] {block.get('text', '')}")
                elif block_type == "thinking":
                    parts.append(
                        f"[{role.upper()} THINKING] {block.get('thinking', '')}"
                    )

    return "\n\n".join(parts)


def truncate_to_budget(text: str, max_chars: int = 100_000) -> str:
    """Truncate to stay within token budget (~25K tokens). Removes oldest first.

    Args:
        text: Formatted prompt text from format_for_prompt.
        max_chars: Maximum character count (default 100,000 ~ 25K tokens).

    Returns:
        Truncated text keeping the most recent content.
    """
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]
