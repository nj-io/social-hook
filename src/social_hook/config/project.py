"""Per-project configuration loading."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from social_hook.errors import ConfigError


@dataclass
class ContextConfig:
    """Controls how much historical context is included in LLM prompts."""

    recent_decisions: int = 30
    recent_posts: int = 15
    max_tokens: int = 150000
    include_readme: bool = True
    include_claude_md: bool = True
    max_doc_tokens: int = 10000


@dataclass
class StrategyConfig:
    """Narrative strategy thresholds."""

    narrative_debt_threshold: int = 3
    arc_stagnation_days: int = 14
    strategy_moment_max_gap_days: int = 7


@dataclass
class ProjectConfig:
    """Per-project configuration loaded from project repository."""

    # social-context.md contents
    social_context: Optional[str] = None

    # content-config.yaml parsed data
    content_config: dict[str, Any] = field(default_factory=dict)

    # memories.md contents
    memories: Optional[str] = None

    # context-notes.md contents
    context_notes: Optional[str] = None

    # Path to the project
    repo_path: Optional[str] = None

    # Typed config sections (parsed from content_config)
    context: ContextConfig = field(default_factory=ContextConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)


def load_project_config(
    repo_path: str | Path,
    global_base: Optional[Path] = None,
) -> ProjectConfig:
    """Load per-project configuration with global fallback.

    Lookup order for social-context.md and content-config.yaml:
      1. {repo}/.social-hook/{file} (project-specific)
      2. ~/.social-hook/{file} (global default)
      3. None/{} (graceful degradation)

    memories.md is project-only (no fallback).

    Args:
        repo_path: Path to the project repository.
        global_base: Override for global config directory. Defaults to ~/.social-hook/.
            This parameter exists for test isolation only - do not use in production code.

    Returns:
        ProjectConfig with loaded data (missing files return None/defaults)

    Raises:
        ConfigError: If YAML is invalid
    """
    repo_path = Path(repo_path)
    if global_base is None:
        global_base = Path.home() / ".social-hook"

    project_config_dir = repo_path / ".social-hook"
    config = ProjectConfig(repo_path=str(repo_path))

    # Load social-context.md (project → global → None)
    config.social_context = _load_with_fallback(
        project_config_dir / "social-context.md",
        global_base / "social-context.md",
    )

    # Load content-config.yaml (project → global → {})
    config.content_config = _load_yaml_with_fallback(
        project_config_dir / "content-config.yaml",
        global_base / "content-config.yaml",
    )

    # Load memories.md (project-only, no fallback)
    memories_path = project_config_dir / "memories.md"
    if memories_path.exists():
        config.memories = memories_path.read_text(encoding="utf-8")

    # Load context-notes.md (project-only, no fallback)
    context_notes_path = project_config_dir / "context-notes.md"
    if context_notes_path.exists():
        config.context_notes = context_notes_path.read_text(encoding="utf-8")

    # Parse typed config sections from content_config
    config.context = _parse_context_config(config.content_config.get("context", {}))
    config.strategy = _parse_strategy_config(config.content_config.get("strategy", {}))

    return config


def _load_with_fallback(project_path: Path, global_path: Path) -> Optional[str]:
    """Load text file with project → global fallback."""
    if project_path.exists():
        return project_path.read_text(encoding="utf-8")
    if global_path.exists():
        return global_path.read_text(encoding="utf-8")
    return None


def _load_yaml_with_fallback(project_path: Path, global_path: Path) -> dict:
    """Load YAML file with project → global fallback."""
    for path in [project_path, global_path]:
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8")
                return yaml.safe_load(content) or {}
            except yaml.YAMLError as e:
                raise ConfigError(f"Invalid YAML in {path}: {e}") from e
    return {}


def _parse_context_config(data: dict) -> ContextConfig:
    """Parse context section from content-config.yaml."""
    if not data:
        return ContextConfig()
    return ContextConfig(
        recent_decisions=data.get("recent_decisions", 30),
        recent_posts=data.get("recent_posts", 15),
        max_tokens=data.get("max_tokens", 150000),
        include_readme=data.get("include_readme", True),
        include_claude_md=data.get("include_claude_md", True),
        max_doc_tokens=data.get("max_doc_tokens", 10000),
    )


def _parse_strategy_config(data: dict) -> StrategyConfig:
    """Parse strategy section from content-config.yaml."""
    if not data:
        return StrategyConfig()
    return StrategyConfig(
        narrative_debt_threshold=data.get("narrative_debt_threshold", 3),
        arc_stagnation_days=data.get("arc_stagnation_days", 14),
        strategy_moment_max_gap_days=data.get("strategy_moment_max_gap_days", 7),
    )


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
        content = memories_path.read_text(encoding="utf-8")
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

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# =============================================================================
# Context Notes (expert-generated notes persisted to disk)
# =============================================================================


def save_context_note(
    repo_path: str | Path,
    note: str,
    source: str,
) -> None:
    """Save a context note from the Expert agent.

    Args:
        repo_path: Path to the project repository
        note: The context note text
        source: Origin of the note (e.g. "expert:draft_123")
    """
    from datetime import date

    repo_path = Path(repo_path)
    config_dir = repo_path / ".social-hook"
    config_dir.mkdir(parents=True, exist_ok=True)
    notes_path = config_dir / "context-notes.md"

    notes = []
    if notes_path.exists():
        content = notes_path.read_text(encoding="utf-8")
        notes = _parse_context_notes(content)

    notes.append({
        "date": date.today().isoformat(),
        "note": note,
        "source": source,
    })

    # Cap at 50 notes (more focused than memories)
    if len(notes) > 50:
        notes = notes[-50:]

    _write_context_notes(notes_path, notes)


def load_context_notes(repo_path: str | Path) -> list[dict]:
    """Load context notes from a project's context-notes.md file.

    Args:
        repo_path: Path to the project repository

    Returns:
        List of note dicts with date, note, source keys.
        Empty list if file doesn't exist.
    """
    notes_path = Path(repo_path) / ".social-hook" / "context-notes.md"
    if not notes_path.exists():
        return []
    content = notes_path.read_text(encoding="utf-8")
    return _parse_context_notes(content)


def _parse_context_notes(content: str) -> list[dict]:
    """Parse context-notes.md markdown table into list of dicts."""
    notes = []
    lines = content.strip().split("\n")

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
            if len(parts) >= 4:
                notes.append({
                    "date": parts[1],
                    "note": parts[2],
                    "source": parts[3],
                })

    return notes


def _write_context_notes(path: Path, notes: list[dict]) -> None:
    """Write context notes list back to markdown file."""
    lines = [
        "# Context Notes",
        "",
        "| Date | Note | Source |",
        "|------|------|--------|",
    ]

    for n in notes:
        lines.append(f"| {n['date']} | {n['note']} | {n['source']} |")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
