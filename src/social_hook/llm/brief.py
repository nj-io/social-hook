"""Project brief — structured, incrementally maintained project understanding.

Replaces the project summary. Structured sections:
- What It Does (user perspective)
- Key Capabilities (features and value props)
- Technical Architecture (system perspective)
- Current State (maturity, active work streams)
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any

from social_hook.llm._usage_logger import log_usage
from social_hook.llm.base import LLMClient

logger = logging.getLogger(__name__)

# Canonical section names and their markdown headings
BRIEF_SECTIONS = {
    "what_it_does": "What It Does",
    "key_capabilities": "Key Capabilities",
    "technical_architecture": "Technical Architecture",
    "current_state": "Current State",
}

# Tool schema for initial brief generation
GENERATE_BRIEF_TOOL = {
    "name": "generate_brief",
    "description": "Generate a structured project brief from discovery output",
    "input_schema": {
        "type": "object",
        "properties": {
            "what_it_does": {
                "type": "string",
                "description": (
                    "What the project does from a user perspective. "
                    "Problem it solves, who it's for, key value proposition. "
                    "~200-400 tokens."
                ),
            },
            "key_capabilities": {
                "type": "string",
                "description": (
                    "Features and value props. What the project can do, "
                    "what makes it interesting. Bullet points encouraged. "
                    "~300-600 tokens."
                ),
            },
            "technical_architecture": {
                "type": "string",
                "description": (
                    "System perspective: key components, tech stack, "
                    "how pieces fit together. ~300-600 tokens."
                ),
            },
            "current_state": {
                "type": "string",
                "description": (
                    "Maturity level, active work streams, what's being built "
                    "right now, what's stable vs in-progress. ~200-400 tokens."
                ),
            },
        },
        "required": ["what_it_does", "key_capabilities", "technical_architecture", "current_state"],
    },
}

# Tool schema for brief update
UPDATE_BRIEF_TOOL = {
    "name": "update_brief",
    "description": "Return the updated project brief sections based on the commit analysis",
    "input_schema": {
        "type": "object",
        "properties": {
            "what_it_does": {
                "type": "string",
                "description": "Updated 'What It Does' section, or unchanged text if no update needed",
            },
            "key_capabilities": {
                "type": "string",
                "description": "Updated 'Key Capabilities' section, or unchanged text if no update needed",
            },
            "technical_architecture": {
                "type": "string",
                "description": "Updated 'Technical Architecture' section, or unchanged text if no update needed",
            },
            "current_state": {
                "type": "string",
                "description": "Updated 'Current State' section, or unchanged text if no update needed",
            },
            "updated_sections": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of section keys that were actually changed (e.g. ['current_state'])",
            },
        },
        "required": [
            "what_it_does",
            "key_capabilities",
            "technical_architecture",
            "current_state",
            "updated_sections",
        ],
    },
}


def _sections_to_markdown(sections: dict[str, str]) -> str:
    """Convert section dict to markdown brief."""
    parts = []
    for key, heading in BRIEF_SECTIONS.items():
        content = sections.get(key, "")
        if content:
            parts.append(f"## {heading}\n\n{content}")
    return "\n\n".join(parts)


def get_brief_sections(brief: str) -> dict[str, str]:
    """Parse brief markdown into named sections.

    Returns dict with keys: what_it_does, key_capabilities,
    technical_architecture, current_state.
    Empty dict if brief is empty or unparseable.
    """
    if not brief:
        return {}

    sections: dict[str, str] = {}
    # Build reverse mapping: heading -> key
    heading_to_key = {heading: key for key, heading in BRIEF_SECTIONS.items()}

    # Match ## Heading lines and capture content until next ## or end
    pattern = r"^## (.+?)$"
    matches = list(re.finditer(pattern, brief, re.MULTILINE))

    for i, match in enumerate(matches):
        heading = match.group(1).strip()
        key = heading_to_key.get(heading)
        if key is None:
            logger.warning("Unknown brief section heading: %s", heading)
            continue

        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(brief)
        content = brief[start:end].strip()
        if content:
            sections[key] = content

    return sections


def generate_initial_brief(
    discovery_summary: str,
    client: LLMClient,
    db: Any = None,
    project_id: str | None = None,
) -> str:
    """Generate initial brief from discovery summary.

    Called by discovery when a project is first discovered.
    Returns structured markdown brief (~1-2K tokens).
    """
    system_prompt = (
        "You are generating a structured project brief from a project discovery summary. "
        "Break the summary into four focused sections. Be concise and factual. "
        "Do not invent details not present in the summary."
    )

    response = client.complete(
        messages=[{"role": "user", "content": discovery_summary}],
        tools=[GENERATE_BRIEF_TOOL],
        system=system_prompt,
        max_tokens=4096,
    )
    log_usage(
        db, "brief_generate", getattr(client, "full_id", "unknown"), response.usage, project_id
    )

    tool_input = _extract_brief_tool_input(response, "generate_brief")
    if tool_input is None:
        logger.warning("Brief generation failed: no generate_brief tool call")
        return ""

    sections = {key: tool_input.get(key, "") for key in BRIEF_SECTIONS}
    return _sections_to_markdown(sections)


def update_brief_from_commit(
    current_brief: str,
    commit_analysis_summary: str,
    commit_analysis_tags: list[str],
    client: LLMClient,
    section_metadata: dict[str, dict] | None = None,
    db: Any = None,
    project_id: str | None = None,
) -> tuple[str, dict[str, dict], list[str]]:
    """Incrementally update the brief based on a commit analysis.

    Args:
        current_brief: Current brief markdown
        commit_analysis_summary: The commit analysis summary text
        commit_analysis_tags: Episode tags from commit analysis
        client: LLM client for the update call
        section_metadata: Per-section edit metadata (last_edited_by, last_edited_at)
        db: Optional DB context for usage tracking
        project_id: Optional project ID for usage tracking

    Returns:
        Tuple of (updated_brief, updated_metadata, list_of_changed_section_keys)
    """
    if not current_brief:
        logger.warning("Cannot update empty brief")
        return current_brief, section_metadata or {}, []

    if section_metadata is None:
        section_metadata = {}

    # Build metadata context for the LLM
    metadata_lines = []
    for key, heading in BRIEF_SECTIONS.items():
        meta = section_metadata.get(key, {})
        edited_by = meta.get("last_edited_by", "system")
        if edited_by == "operator":
            metadata_lines.append(
                f"- '{heading}': OPERATOR-EDITED — only update if the commit directly contradicts this section"
            )
        else:
            metadata_lines.append(f"- '{heading}': system-managed — update freely if relevant")

    metadata_context = "\n".join(metadata_lines)

    commit_context = f"Summary: {commit_analysis_summary}"
    if commit_analysis_tags:
        commit_context += f"\nTags: {', '.join(commit_analysis_tags)}"

    system_prompt = (
        "You are updating a project brief based on a new commit. "
        "Only change sections that are affected by the commit. "
        "Preserve the existing content for unaffected sections exactly as-is.\n\n"
        "Section edit rules:\n"
        f"{metadata_context}\n\n"
        "Return ALL sections (changed or not). In 'updated_sections', list ONLY "
        "the section keys you actually changed."
    )

    user_message = f"Current brief:\n\n{current_brief}\n\n---\n\nNew commit:\n{commit_context}"

    response = client.complete(
        messages=[{"role": "user", "content": user_message}],
        tools=[UPDATE_BRIEF_TOOL],
        system=system_prompt,
        max_tokens=4096,
    )
    log_usage(db, "brief_update", getattr(client, "full_id", "unknown"), response.usage, project_id)

    tool_input = _extract_brief_tool_input(response, "update_brief")
    if tool_input is None:
        logger.warning("Brief update failed: no update_brief tool call")
        return current_brief, section_metadata, []

    updated_sections_keys = tool_input.get("updated_sections", [])

    # Build updated sections, respecting operator edits
    current_sections = get_brief_sections(current_brief)
    new_sections: dict[str, str] = {}
    now_iso = datetime.now(timezone.utc).isoformat()

    for key in BRIEF_SECTIONS:
        llm_value = tool_input.get(key, "")
        meta = section_metadata.get(key, {})

        if key in updated_sections_keys:
            # LLM wants to update this section
            if meta.get("last_edited_by") == "operator":
                # Preserve operator edits — only update if LLM explicitly changed it
                # (the LLM was instructed to only change if contradicted)
                new_sections[key] = llm_value
                # Keep operator ownership — they can re-edit if the system change was wrong
            else:
                new_sections[key] = llm_value
                section_metadata[key] = {
                    "last_edited_by": "system",
                    "last_edited_at": now_iso,
                }
        else:
            # Section unchanged — preserve current content
            new_sections[key] = current_sections.get(key, llm_value)

    updated_brief = _sections_to_markdown(new_sections)
    return updated_brief, section_metadata, updated_sections_keys


def _extract_brief_tool_input(response: Any, tool_name: str) -> dict | None:
    """Extract tool call input from a response, returning None on failure."""
    from social_hook.llm.base import ToolExtractionError, extract_tool_call

    try:
        return extract_tool_call(response, tool_name)
    except ToolExtractionError:
        return None
