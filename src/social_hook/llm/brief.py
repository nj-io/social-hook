"""Project brief — structured, incrementally maintained project understanding.

Universal brief system with freeform sections. Any ## Heading is accepted;
suggested defaults include What It Does, Key Capabilities, Technical
Architecture, and Current State, but operators and LLMs can add any section.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any

from social_hook.llm._usage_logger import log_usage
from social_hook.llm.base import LLMClient

logger = logging.getLogger(__name__)

# Suggested section headings (hints for LLM, not enforced)
SUGGESTED_SECTIONS = [
    "What It Does",
    "Key Capabilities",
    "Technical Architecture",
    "Current State",
]

# Backward-compatible alias — callers that reference BRIEF_SECTIONS still work.
# Maps slug -> heading for the original four sections.
BRIEF_SECTIONS = {
    "what_it_does": "What It Does",
    "key_capabilities": "Key Capabilities",
    "technical_architecture": "Technical Architecture",
    "current_state": "Current State",
}

# Tool schema for initial brief generation — freeform sections
GENERATE_BRIEF_TOOL = {
    "name": "generate_brief",
    "description": (
        "Generate a structured project brief from discovery output. "
        "Use any section headings that fit the project. Suggested sections: "
        "What It Does, Key Capabilities, Technical Architecture, Current State. "
        "Add or omit sections as appropriate. Note what seems missing "
        "(e.g. 'No target audience described — consider adding one')."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sections": {
                "type": "object",
                "description": (
                    "Map of section heading to section content. "
                    "Keys are human-readable headings (e.g. 'What It Does'). "
                    "Values are the section text (~200-600 tokens each)."
                ),
                "additionalProperties": {"type": "string"},
            },
        },
        "required": ["sections"],
    },
}

# Tool schema for brief update — dynamic sections
UPDATE_BRIEF_TOOL = {
    "name": "update_brief",
    "description": (
        "Return the updated project brief sections based on the commit analysis. "
        "Return ALL sections (changed and unchanged). You may add new sections."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sections": {
                "type": "object",
                "description": (
                    "Map of section heading to section content. "
                    "Include all existing sections (changed or not) plus any new ones."
                ),
                "additionalProperties": {"type": "string"},
            },
            "updated_sections": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of section headings that were actually changed or added",
            },
        },
        "required": ["sections", "updated_sections"],
    },
}


def _heading_to_slug(heading: str) -> str:
    """Convert a heading like 'What It Does' to a slug like 'what_it_does'."""
    return re.sub(r"[^a-z0-9]+", "_", heading.lower()).strip("_")


def _sections_to_markdown(sections: dict[str, str]) -> str:
    """Convert section dict to markdown brief.

    Keys are slugs or headings. For known slugs (BRIEF_SECTIONS keys),
    the canonical heading is used. Otherwise, the key is title-cased.
    """
    parts = []
    for key, content in sections.items():
        if not content:
            continue
        # Map slug to heading for known sections
        heading = BRIEF_SECTIONS.get(key, key)
        # If the key looks like a heading already (has spaces/caps), use it directly
        if key not in BRIEF_SECTIONS and not key.startswith("_"):
            heading = key
        parts.append(f"## {heading}\n\n{content}")
    return "\n\n".join(parts)


def get_brief_sections(brief: str) -> dict[str, str]:
    """Parse brief markdown into named sections.

    Accepts ANY ## Heading — returns a dict mapping slug keys to content.
    Known headings (What It Does, etc.) map to their canonical slug keys
    for backward compatibility. Unknown headings are slugified.

    Returns empty dict if brief is empty or unparseable.
    """
    if not brief:
        return {}

    sections: dict[str, str] = {}
    # Build reverse mapping: heading -> canonical key
    heading_to_key = {heading: key for key, heading in BRIEF_SECTIONS.items()}

    # Match ## Heading lines and capture content until next ## or end
    pattern = r"^## (.+?)$"
    matches = list(re.finditer(pattern, brief, re.MULTILINE))

    for i, match in enumerate(matches):
        heading = match.group(1).strip()
        # Use canonical key for known headings, slugify for unknown
        key = heading_to_key.get(heading, _heading_to_slug(heading))

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
    section_hints: list[str] | None = None,
) -> str:
    """Generate initial brief from discovery summary.

    Called by discovery when a project is first discovered.
    Returns structured markdown brief (~1-2K tokens).

    Args:
        discovery_summary: Project discovery text to base the brief on
        client: LLM client
        db: Optional DB context for usage tracking
        project_id: Optional project ID for usage tracking
        section_hints: Optional list of suggested section headings
    """
    hints = section_hints or SUGGESTED_SECTIONS
    hint_text = ", ".join(hints)
    system_prompt = (
        "You are generating a structured project brief from a project discovery summary. "
        "Break the summary into focused sections. Be concise and factual. "
        "Do not invent details not present in the summary. "
        f"Suggested sections: {hint_text}. "
        "Add or omit sections as appropriate for this project."
    )

    response = client.complete(
        messages=[{"role": "user", "content": discovery_summary}],
        tools=[GENERATE_BRIEF_TOOL],
        system=system_prompt,
        max_tokens=8192,
    )
    log_usage(
        db, "brief_generate", getattr(client, "full_id", "unknown"), response.usage, project_id
    )

    tool_input = _extract_brief_tool_input(response, "generate_brief")
    if tool_input is None:
        logger.warning("Brief generation failed: no generate_brief tool call")
        return ""

    # New freeform format: sections dict
    raw_sections = tool_input.get("sections")
    if isinstance(raw_sections, dict):
        return _sections_to_markdown(raw_sections)

    # Backward compat: old-style flat keys
    sections = {key: tool_input.get(key, "") for key in BRIEF_SECTIONS if tool_input.get(key)}
    return _sections_to_markdown(sections)


def update_brief_from_commit(
    current_brief: str,
    commit_analysis_summary: str,
    commit_analysis_tags: list[str],
    client: LLMClient,
    section_metadata: dict[str, dict] | None = None,
    db: Any = None,
    project_id: str | None = None,
    sections_to_update: dict[str, str] | None = None,
    new_facts: list[str] | None = None,
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
        sections_to_update: Analyzer guidance — section-name -> update text
        new_facts: Analyzer guidance — new facts to incorporate

    Returns:
        Tuple of (updated_brief, updated_metadata, list_of_changed_section_keys)
    """
    if not current_brief:
        logger.warning("Cannot update empty brief")
        return current_brief, section_metadata or {}, []

    if section_metadata is None:
        section_metadata = {}

    # Parse current sections dynamically
    current_sections = get_brief_sections(current_brief)

    # Build metadata context for the LLM — dynamic, based on actual sections
    metadata_lines = []
    for key in current_sections:
        # Use canonical heading for known keys, otherwise title-case the slug
        heading = BRIEF_SECTIONS.get(key, key)
        meta = section_metadata.get(key, {})
        edited_by = meta.get("last_edited_by", "system")
        if edited_by == "operator":
            metadata_lines.append(
                f"- '{heading}': OPERATOR-EDITED — only update if the commit directly contradicts this section"
            )
        else:
            metadata_lines.append(f"- '{heading}': system-managed — update freely if relevant")

    metadata_context = "\n".join(metadata_lines) if metadata_lines else "No section metadata."

    commit_context = f"Summary: {commit_analysis_summary}"
    if commit_analysis_tags:
        commit_context += f"\nTags: {', '.join(commit_analysis_tags)}"

    # Include analyzer guidance if provided
    guidance_text = ""
    if sections_to_update:
        guidance_text += "\n\nAnalyzer guidance — sections to update:\n"
        for section_name, update_text in sections_to_update.items():
            guidance_text += f"- {section_name}: {update_text}\n"
    if new_facts:
        guidance_text += "\nNew facts to incorporate:\n"
        for fact in new_facts:
            guidance_text += f"- {fact}\n"

    system_prompt = (
        "You are updating a project brief based on a new commit. "
        "Only change sections that are affected by the commit. "
        "Preserve the existing content for unaffected sections exactly as-is. "
        "You may add new sections if the commit reveals important project aspects "
        "not covered by existing sections.\n\n"
        "Section edit rules:\n"
        f"{metadata_context}\n\n"
        "Return ALL sections (changed and unchanged) plus any new ones. "
        "In 'updated_sections', list ONLY the section headings you actually changed or added."
    )

    user_message = (
        f"Current brief:\n\n{current_brief}\n\n---\n\nNew commit:\n{commit_context}{guidance_text}"
    )

    response = client.complete(
        messages=[{"role": "user", "content": user_message}],
        tools=[UPDATE_BRIEF_TOOL],
        system=system_prompt,
        max_tokens=8192,
    )
    log_usage(db, "brief_update", getattr(client, "full_id", "unknown"), response.usage, project_id)

    tool_input = _extract_brief_tool_input(response, "update_brief")
    if tool_input is None:
        logger.warning("Brief update failed: no update_brief tool call")
        return current_brief, section_metadata, []

    updated_sections_keys = tool_input.get("updated_sections", [])

    # Extract sections from tool output — support both freeform and legacy formats
    raw_sections = tool_input.get("sections")
    if isinstance(raw_sections, dict):
        llm_sections = raw_sections
    else:
        # Legacy flat-key format
        llm_sections = {
            key: tool_input.get(key, "")
            for key in list(BRIEF_SECTIONS.keys()) + list(current_sections.keys())
            if tool_input.get(key)
        }

    # Build updated sections, respecting operator edits
    new_sections: dict[str, str] = {}
    now_iso = datetime.now(timezone.utc).isoformat()

    # Build slug -> original heading mapping for LLM sections lookup
    slug_to_heading: dict[str, str] = {}
    for k in llm_sections:
        slug = _heading_to_slug(k) if k not in current_sections else k
        slug_to_heading[slug] = k

    # Process all keys: current sections + any new ones from LLM
    all_keys = list(current_sections.keys())
    for slug in slug_to_heading:
        if slug not in all_keys:
            all_keys.append(slug)

    for key in all_keys:
        # Try to find the LLM value — check by slug, original heading, and canonical heading
        llm_value = llm_sections.get(key, "")
        if not llm_value:
            # Try the original heading that maps to this slug
            orig_heading = slug_to_heading.get(key)
            if orig_heading:
                llm_value = llm_sections.get(orig_heading, "")
        if not llm_value:
            # Try canonical heading for known sections
            heading = BRIEF_SECTIONS.get(key, key)
            llm_value = llm_sections.get(heading, "")

        meta = section_metadata.get(key, {})

        # Determine if the LLM marked this section as updated
        # Check slug, canonical heading, and original heading forms in updated_sections_keys
        heading = BRIEF_SECTIONS.get(key, key)
        orig_heading = slug_to_heading.get(key, "")
        is_updated = (
            key in updated_sections_keys
            or heading in updated_sections_keys
            or orig_heading in updated_sections_keys
        )

        if is_updated:
            if meta.get("last_edited_by") == "operator":
                new_sections[key] = llm_value
            else:
                new_sections[key] = llm_value
                section_metadata[key] = {
                    "last_edited_by": "system",
                    "last_edited_at": now_iso,
                }
        else:
            # Section unchanged — preserve current content
            preserved: str = current_sections.get(key, llm_value)  # type: ignore[assignment]
            new_sections[key] = preserved

    updated_brief = _sections_to_markdown(new_sections)
    return updated_brief, section_metadata, updated_sections_keys


def generate_brief_from_docs(
    prompt_docs_paths: list[str],
    base_dir: str,
    client: LLMClient,
    db: Any = None,
    project_id: str | None = None,
    max_tokens: int = 20_000,
) -> str:
    """Generate a project brief from documentation files (non-git projects).

    Reads files via read_files_within_budget(), then generates a brief
    with content-appropriate section hints.

    Args:
        prompt_docs_paths: Relative file paths to read
        base_dir: Base directory for resolving paths
        client: LLM client
        db: Optional DB context for usage tracking
        project_id: Optional project ID for usage tracking
        max_tokens: Token budget for file reading

    Returns:
        Structured markdown brief, or empty string on failure
    """
    from social_hook.file_reader import read_files_within_budget

    text, tokens_used = read_files_within_budget(
        prompt_docs_paths,
        base_dir,
        max_tokens=max_tokens,
    )
    if not text:
        logger.warning("No readable docs found for brief generation")
        return ""

    # Use content-appropriate section hints for doc-based projects
    section_hints = [
        "What It Does",
        "Key Capabilities",
        "Target Audience",
        "Current State",
    ]

    return generate_initial_brief(
        discovery_summary=text,
        client=client,
        db=db,
        project_id=project_id,
        section_hints=section_hints,
    )


def _extract_brief_tool_input(response: Any, tool_name: str) -> dict | None:
    """Extract tool call input from a response, returning None on failure."""
    from social_hook.llm.base import ToolExtractionError, extract_tool_call

    try:
        return extract_tool_call(response, tool_name)
    except ToolExtractionError:
        return None
