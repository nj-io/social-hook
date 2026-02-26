"""Pydantic models for LLM tool call validation."""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ValidationError

from social_hook.errors import MalformedResponseError


# =============================================================================
# Schema-specific Enums (str enums for Pydantic JSON serialization)
# =============================================================================


class DecisionTypeSchema(str, Enum):
    """Evaluator decision types."""

    post_worthy = "post_worthy"
    not_post_worthy = "not_post_worthy"
    consolidate = "consolidate"
    deferred = "deferred"


class EpisodeTypeSchema(str, Enum):
    """Post structural categories."""

    decision = "decision"
    before_after = "before_after"
    demo_proof = "demo_proof"
    milestone = "milestone"
    postmortem = "postmortem"
    launch = "launch"
    synthesis = "synthesis"


class PostCategorySchema(str, Enum):
    """How each post relates to ongoing narrative."""

    arc = "arc"
    opportunistic = "opportunistic"
    experiment = "experiment"


class MediaTool(str, Enum):
    """Available media generation tools."""

    mermaid = "mermaid"
    nano_banana_pro = "nano_banana_pro"
    playwright = "playwright"
    ray_so = "ray_so"
    none = "none"


class RouteAction(str, Enum):
    """Gatekeeper routing actions."""

    handle_directly = "handle_directly"
    escalate_to_expert = "escalate_to_expert"


class GatekeeperOperation(str, Enum):
    """Operations the Gatekeeper can perform directly."""

    approve = "approve"
    schedule = "schedule"
    reject = "reject"
    cancel = "cancel"
    substitute = "substitute"
    query = "query"


class ExpertAction(str, Enum):
    """Actions the Expert can take."""

    refine_draft = "refine_draft"
    answer_question = "answer_question"
    save_context_note = "save_context_note"


# =============================================================================
# Pydantic Models (LLM response validation)
# =============================================================================


class LogDecisionInput(BaseModel):
    """Evaluator tool call: log_decision."""

    decision: DecisionTypeSchema
    reasoning: str
    angle: Optional[str] = None
    episode_type: Optional[EpisodeTypeSchema] = None
    post_category: Optional[PostCategorySchema] = None
    arc_id: Optional[str] = None
    media_tool: Optional[MediaTool] = None
    include_project_docs: Optional[bool] = None
    commit_summary: Optional[str] = None

    @classmethod
    def to_tool_schema(cls) -> dict[str, Any]:
        """Return JSON schema dict for Claude's tools parameter."""
        return {
            "name": "log_decision",
            "description": "Record the evaluation decision for a commit",
            "input_schema": {
                "type": "object",
                "properties": {
                    "decision": {
                        "type": "string",
                        "enum": [e.value for e in DecisionTypeSchema],
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Explanation for the decision",
                    },
                    "angle": {
                        "type": "string",
                        "description": "The hook/angle for the post (e.g. 'Introducing what this project does and why it matters')",
                    },
                    "include_project_docs": {
                        "type": "boolean",
                        "description": "Set true when the Drafter needs project-level documentation (README, CLAUDE.md) to write this post — e.g. introductions, synthesis, launches, or any post that needs to explain what the project is.",
                    },
                    "episode_type": {
                        "type": "string",
                        "enum": [e.value for e in EpisodeTypeSchema],
                    },
                    "post_category": {
                        "type": "string",
                        "enum": [e.value for e in PostCategorySchema],
                    },
                    "arc_id": {
                        "type": "string",
                        "description": "ID of active arc, if applicable",
                    },
                    "media_tool": {
                        "type": "string",
                        "enum": [e.value for e in MediaTool],
                    },
                    "commit_summary": {
                        "type": "string",
                        "description": "Brief 1-2 sentence summary of what this commit does, for consolidation batching.",
                    },
                },
                "required": ["decision", "reasoning"],
            },
        }

    @classmethod
    def validate(cls, data: dict[str, Any]) -> "LogDecisionInput":
        """Validate tool call input data."""
        try:
            return cls.model_validate(data)
        except ValidationError as e:
            raise MalformedResponseError(f"Invalid log_decision input: {e}") from e


class CreateDraftInput(BaseModel):
    """Drafter tool call: create_draft."""

    content: str
    platform: str
    reasoning: str
    media_type: Optional[MediaTool] = None
    media_spec: Optional[dict[str, Any]] = None
    format_hint: Optional[str] = None
    beat_count: Optional[int] = None

    @classmethod
    def to_tool_schema(cls) -> dict[str, Any]:
        """Return JSON schema dict for Claude's tools parameter."""
        return {
            "name": "create_draft",
            "description": "Create draft content for social media",
            "input_schema": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The post content",
                    },
                    "platform": {
                        "type": "string",
                        "description": "Target platform name (e.g., 'x', 'linkedin', 'blog')",
                    },
                    "media_type": {
                        "type": "string",
                        "enum": [e.value for e in MediaTool],
                    },
                    "media_spec": {
                        "type": "object",
                        "description": "Specification for media generation",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Why this angle/content was chosen",
                    },
                    "format_hint": {
                        "type": "string",
                        "enum": ["single", "thread"],
                        "description": "Recommended format. Use 'thread' when content has 4+ distinct beats/steps that benefit from visual separation.",
                    },
                    "beat_count": {
                        "type": "integer",
                        "description": "Number of distinct narrative beats/steps in this content.",
                    },
                },
                "required": ["content", "platform", "reasoning"],
            },
        }

    @classmethod
    def validate(cls, data: dict[str, Any]) -> "CreateDraftInput":
        """Validate tool call input data."""
        # LLM sometimes returns a list for content (thread format) instead of a string.
        # Convert to JSON string so validation passes and thread parsing works downstream.
        if isinstance(data.get("content"), list):
            import json
            data = {**data, "content": json.dumps(data["content"])}
        try:
            return cls.model_validate(data)
        except ValidationError as e:
            raise MalformedResponseError(f"Invalid create_draft input: {e}") from e


class RouteActionInput(BaseModel):
    """Gatekeeper tool call: route_action."""

    action: RouteAction
    operation: Optional[GatekeeperOperation] = None
    params: Optional[dict[str, Any]] = None
    escalation_reason: Optional[str] = None
    escalation_context: Optional[str] = None

    @classmethod
    def to_tool_schema(cls) -> dict[str, Any]:
        """Return JSON schema dict for Claude's tools parameter."""
        return {
            "name": "route_action",
            "description": "Route user message to appropriate handler",
            "input_schema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [e.value for e in RouteAction],
                    },
                    "operation": {
                        "type": "string",
                        "enum": [e.value for e in GatekeeperOperation],
                        "description": "For handle_directly: which operation",
                    },
                    "params": {
                        "type": "object",
                        "description": "Parameters for the operation. For query: MUST include 'answer' with a specific response to the user's question.",
                    },
                    "escalation_reason": {
                        "type": "string",
                        "description": "For escalate: why escalating",
                    },
                    "escalation_context": {
                        "type": "string",
                        "description": "For escalate: context to pass to expert",
                    },
                },
                "required": ["action"],
            },
        }

    @classmethod
    def validate(cls, data: dict[str, Any]) -> "RouteActionInput":
        """Validate tool call input data."""
        try:
            return cls.model_validate(data)
        except ValidationError as e:
            raise MalformedResponseError(f"Invalid route_action input: {e}") from e


class ExtractNarrativeInput(BaseModel):
    """Extractor tool call: extract_narrative."""

    summary: str
    key_decisions: list[str]
    rejected_approaches: list[str]
    aha_moments: list[str]
    challenges: list[str]
    narrative_arc: str
    relevant_for_social: bool
    social_hooks: list[str]

    @classmethod
    def to_tool_schema(cls) -> dict[str, Any]:
        """Return JSON schema dict for Claude's tools parameter."""
        return {
            "name": "extract_narrative",
            "description": "Extract narrative elements from a development session transcript",
            "input_schema": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "2-3 sentence session summary",
                    },
                    "key_decisions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Decisions made and their reasoning",
                    },
                    "rejected_approaches": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Approaches that were tried and abandoned",
                    },
                    "aha_moments": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Surprising insights discovered during the session",
                    },
                    "challenges": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Difficulties encountered during the session",
                    },
                    "narrative_arc": {
                        "type": "string",
                        "description": "The story of the session as a narrative arc",
                    },
                    "relevant_for_social": {
                        "type": "boolean",
                        "description": "Whether this session has social-media-worthy content",
                    },
                    "social_hooks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Potential post angles for social media",
                    },
                },
                "required": [
                    "summary",
                    "key_decisions",
                    "rejected_approaches",
                    "aha_moments",
                    "challenges",
                    "narrative_arc",
                    "relevant_for_social",
                    "social_hooks",
                ],
            },
        }

    @classmethod
    def validate(cls, data: dict[str, Any]) -> "ExtractNarrativeInput":
        """Validate tool call input data."""
        try:
            return cls.model_validate(data)
        except ValidationError as e:
            raise MalformedResponseError(f"Invalid extract_narrative input: {e}") from e


class ExpertResponseInput(BaseModel):
    """Expert tool call: expert_response."""

    action: ExpertAction
    reasoning: str
    refined_content: Optional[str] = None
    answer: Optional[str] = None
    context_note: Optional[str] = None

    @classmethod
    def to_tool_schema(cls) -> dict[str, Any]:
        """Return JSON schema dict for Claude's tools parameter."""
        return {
            "name": "expert_response",
            "description": "Provide expert response to escalated request",
            "input_schema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [e.value for e in ExpertAction],
                    },
                    "refined_content": {
                        "type": "string",
                        "description": "For refine_draft: the new draft content",
                    },
                    "answer": {
                        "type": "string",
                        "description": "For answer_question: response to user's question",
                    },
                    "context_note": {
                        "type": "string",
                        "description": "For save_context_note: note to save",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Why this response/refinement",
                    },
                },
                "required": ["action", "reasoning"],
            },
        }

    @classmethod
    def validate(cls, data: dict[str, Any]) -> "ExpertResponseInput":
        """Validate tool call input data."""
        try:
            return cls.model_validate(data)
        except ValidationError as e:
            raise MalformedResponseError(f"Invalid expert_response input: {e}") from e


# =============================================================================
# Tool Call Extraction
# =============================================================================


def extract_tool_call(response: Any, expected_tool: str) -> dict[str, Any]:
    """Extract and validate tool call from Claude response.

    Args:
        response: Claude API response object
        expected_tool: Expected tool name (e.g., "log_decision")

    Returns:
        Tool call input dict

    Raises:
        MalformedResponseError: If no matching tool call found
    """
    for content in response.content:
        if content.type == "tool_use" and content.name == expected_tool:
            return content.input
    raise MalformedResponseError(f"No {expected_tool} tool call in response")
