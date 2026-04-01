"""Enums, status constants, and helper predicates for social-hook models.

All enums must match DB CHECK constraints. Status group frozensets are
the single source of truth — never define inline status sets.
"""

from __future__ import annotations

from enum import Enum


class DraftStatus(Enum):
    """Status of a content draft."""

    DRAFT = "draft"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    POSTED = "posted"
    REJECTED = "rejected"
    FAILED = "failed"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"
    DEFERRED = "deferred"


# Single source of truth for status group checks.
# Import these instead of writing inline tuples.
TERMINAL_STATUSES = frozenset(
    {
        DraftStatus.POSTED.value,
        DraftStatus.REJECTED.value,
        DraftStatus.CANCELLED.value,
        DraftStatus.SUPERSEDED.value,
    }
)
PENDING_STATUSES = frozenset(
    {
        DraftStatus.DRAFT.value,
        DraftStatus.APPROVED.value,
        DraftStatus.SCHEDULED.value,
        DraftStatus.DEFERRED.value,
    }
)
EDITABLE_STATUSES = frozenset(
    {
        DraftStatus.DRAFT.value,
        DraftStatus.DEFERRED.value,
    }
)

TOPIC_STATUSES = frozenset({"uncovered", "holding", "partial", "covered", "dismissed"})
SUGGESTION_STATUSES = frozenset({"pending", "evaluated", "drafted", "dismissed"})


class DecisionType(Enum):
    """Evaluation decision for a commit."""

    DRAFT = "draft"
    HOLD = "hold"
    SKIP = "skip"
    IMPORTED = "imported"
    DEFERRED_EVAL = "deferred_eval"
    PROCESSING = "processing"


class PipelineStage:
    """Reusable pipeline stage identifiers for data_change events.

    Emitted as: emit_data_event("pipeline", stage, entity_id, project_id).
    Frontend PipelineToasts maps these to user-facing messages.
    """

    DISCOVERING = "discovering"
    ANALYZING = "analyzing"
    EVALUATING = "evaluating"
    DECIDING = "deciding"  # decision creation + arc activation + queue actions
    DRAFTING = "drafting"
    PROMOTING = "promoting"
    QUEUED = "queued"


class PostCategory(Enum):
    """How each post relates to ongoing narrative."""

    ARC = "arc"
    OPPORTUNISTIC = "opportunistic"
    EXPERIMENT = "experiment"


class PostFormat(Enum):
    """Format of a drafted post."""

    SINGLE = "single"
    THREAD = "thread"
    QUOTE = "quote"
    REPLY = "reply"


class LifecyclePhase(Enum):
    """Project lifecycle phases."""

    RESEARCH = "research"
    BUILD = "build"
    DEMO = "demo"
    LAUNCH = "launch"
    POST_LAUNCH = "post_launch"


class ArcStatus(Enum):
    """Status of a narrative arc."""

    PROPOSED = "proposed"
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


ARC_STATUSES = frozenset(s.value for s in ArcStatus)


def is_draftable(decision: str) -> bool:
    """Check if a decision indicates content should be drafted."""
    return decision == "draft"


def is_held(decision: str) -> bool:
    """Check if a decision is held for consolidation."""
    return decision == "hold"
