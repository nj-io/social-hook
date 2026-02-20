"""Narrative management module for social-hook."""

from social_hook.narrative.arcs import create_arc, get_active_arcs, get_arc, update_arc
from social_hook.narrative.debt import (
    get_narrative_debt,
    increment_narrative_debt,
    is_debt_high,
    reset_narrative_debt,
)
from social_hook.narrative.lifecycle import (
    check_strategy_triggers,
    detect_lifecycle_phase,
    record_strategy_moment,
)
from social_hook.narrative.memories import add_memory, parse_memories_file
from social_hook.narrative.transcript import (
    discover_transcript_path,
    filter_for_extraction,
    format_for_prompt,
    read_transcript,
    truncate_to_budget,
)

__all__ = [
    # Memories
    "add_memory",
    "parse_memories_file",
    # Transcript
    "read_transcript",
    "discover_transcript_path",
    "filter_for_extraction",
    "format_for_prompt",
    "truncate_to_budget",
    # Lifecycle
    "detect_lifecycle_phase",
    "check_strategy_triggers",
    "record_strategy_moment",
    # Arcs
    "create_arc",
    "get_active_arcs",
    "get_arc",
    "update_arc",
    # Debt
    "get_narrative_debt",
    "increment_narrative_debt",
    "reset_narrative_debt",
    "is_debt_high",
]
