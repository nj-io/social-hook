"""Narrative JSONL storage — append-only log of extracted session narratives."""

import datetime
import json
from pathlib import Path
from typing import Any

from social_hook.filesystem import get_narratives_path
from social_hook.llm.schemas import ExtractNarrativeInput


def _narratives_file(project_id: str) -> Path:
    """Return the JSONL path for a project, creating the parent dir if needed."""
    path = get_narratives_path() / f"{project_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def save_narrative(
    project_id: str, extraction: Any, session_id: str, trigger: str
) -> Path:
    """Save an extracted narrative to JSONL storage.

    Storage: ~/.social-hook/narratives/{project-id}.jsonl — append-only,
    one JSON line per compact event.

    Each line: { timestamp, session_id, trigger, summary, key_decisions,
    rejected_approaches, aha_moments, challenges, narrative_arc,
    relevant_for_social, social_hooks }

    Uses append mode ('a'). Single-line JSONL appends under the OS pipe
    buffer size are atomic.

    Args:
        project_id: Project identifier.
        extraction: ExtractNarrativeInput (or any object with the extraction fields).
        session_id: Claude Code session ID.
        trigger: What triggered the compact (e.g. "auto", "manual").

    Returns:
        Path to the narratives JSONL file.
    """
    record: dict[str, Any] = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "session_id": session_id,
        "trigger": trigger,
    }
    for field in ExtractNarrativeInput.model_fields:
        record[field] = getattr(extraction, field)

    path = _narratives_file(project_id)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return path


def load_recent_narratives(project_id: str, limit: int = 5) -> list[dict]:
    """Load N most recent narratives where relevant_for_social is True.

    Deduplicates by session_id (keeps latest per session) since a single
    long session can trigger multiple auto-compactions.

    Args:
        project_id: Project identifier.
        limit: Max narratives to return (default 5).

    Returns:
        List of narrative dicts, most recent first.
    """
    path = _narratives_file(project_id)
    if not path.exists():
        return []

    entries: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict):
                continue
            entries.append(entry)

    # Filter to relevant_for_social only.
    relevant = [e for e in entries if e.get("relevant_for_social") is True]

    # Deduplicate by session_id — keep the latest (last occurrence) per session.
    seen: dict[str, dict] = {}
    for entry in relevant:
        sid = entry.get("session_id")
        if sid is not None:
            seen[sid] = entry  # later entries overwrite earlier ones
        else:
            # Entries without session_id are kept as-is (shouldn't happen normally).
            seen[id(entry)] = entry

    deduped = list(seen.values())

    # Sort by timestamp descending (most recent first).
    deduped.sort(key=lambda e: e.get("timestamp", ""), reverse=True)

    return deduped[:limit]


def cleanup_old_narratives(project_id: str, max_age_days: int = 90) -> int:
    """Remove narratives older than max_age_days.

    Rewrites the file without old entries (since JSONL is append-only,
    we read all, filter, rewrite).

    Args:
        project_id: Project identifier.
        max_age_days: Max age in days (default 90).

    Returns:
        Number of entries removed.
    """
    path = _narratives_file(project_id)
    if not path.exists():
        return 0

    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=max_age_days
    )

    kept: list[str] = []
    removed = 0

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                entry = json.loads(stripped)
            except json.JSONDecodeError:
                # Keep unparseable lines to avoid silent data loss.
                kept.append(stripped)
                continue

            ts_str = entry.get("timestamp", "") if isinstance(entry, dict) else ""
            try:
                ts = datetime.datetime.fromisoformat(ts_str)
            except (ValueError, TypeError):
                # No valid timestamp — keep to avoid data loss.
                kept.append(stripped)
                continue

            if ts < cutoff:
                removed += 1
            else:
                kept.append(stripped)

    # Rewrite the file with kept entries.
    with open(path, "w", encoding="utf-8") as f:
        for entry_line in kept:
            f.write(entry_line + "\n")

    return removed
