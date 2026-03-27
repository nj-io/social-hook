"""Pydantic models for LLM tool call validation."""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from social_hook.errors import MalformedResponseError

# =============================================================================
# Schema-specific Enums (str enums for Pydantic JSON serialization)
# =============================================================================


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


class CommitClassification(str, Enum):
    """Classification of commit significance for stage 1 analysis."""

    trivial = "trivial"
    routine = "routine"
    notable = "notable"
    significant = "significant"


# =============================================================================
# Pydantic Models (LLM response validation)
# =============================================================================


class TargetAction(str, Enum):
    """Actions the evaluator can assign per target."""

    skip = "skip"
    draft = "draft"
    hold = "hold"


class TopicSuggestion(BaseModel):
    """A topic suggestion from the commit analyzer."""

    title: str
    description: str | None = None
    strategy_type: str = "code-driven"  # "code-driven" or "positioning"


class CommitAnalysis(BaseModel):
    """Structured analysis of a commit."""

    summary: str
    technical_detail: str | None = None
    episode_tags: list[str] = []
    classification: CommitClassification | None = None
    topic_suggestions: list[TopicSuggestion] = []


class ContextSourceSpec(BaseModel):
    """Specifies what context the drafter should receive."""

    model_config = ConfigDict(extra="forbid")

    types: list[str]  # "brief", "commits", "topic", "operator_suggestion"
    topic_id: str | None = None
    suggestion_id: str | None = None


class StrategyDecisionInput(BaseModel):
    """Per-strategy decision from the evaluator."""

    action: TargetAction
    reason: str
    consolidate_with: list[str] | None = None
    arc_id: str | None = None
    new_arc_theme: str | None = None
    reference_posts: list[str] | None = None
    angle: str | None = None
    post_category: PostCategorySchema | None = None
    media_tool: MediaTool | None = None
    include_project_docs: bool | None = None
    topic_id: str | None = None
    context_source: ContextSourceSpec | None = None


class QueueAction(BaseModel):
    """An action to take on a pending draft."""

    action: Literal["supersede", "merge", "drop"]
    draft_id: str
    reason: str
    merge_group: str | None = None
    merge_instruction: str | None = None


class LogEvaluationInput(BaseModel):
    """Evaluator tool call: log_evaluation (multi-target format)."""

    commit_analysis: CommitAnalysis
    strategies: dict[str, StrategyDecisionInput]
    queue_actions: dict[str, list[QueueAction]] | None = None

    @model_validator(mode="before")
    @classmethod
    def _remap_targets_key(cls, data: dict) -> dict:
        if isinstance(data, dict) and "targets" in data and "strategies" not in data:
            data["strategies"] = data.pop("targets")
        return data

    @classmethod
    def to_tool_schema(cls) -> dict[str, Any]:
        """Return JSON schema dict for Claude's tools parameter."""
        return {
            "name": "log_evaluation",
            "description": "Record the evaluation for a commit with per-target decisions and optional queue management",
            "input_schema": {
                "type": "object",
                "properties": {
                    "commit_analysis": {
                        "type": "object",
                        "description": "Structured analysis of the commit",
                        "properties": {
                            "summary": {
                                "type": "string",
                                "description": "1-2 sentence summary of what this commit does",
                            },
                            "technical_detail": {
                                "type": "string",
                                "description": "Optional deeper technical context",
                            },
                            "episode_tags": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Tags for categorizing this commit (e.g. 'refactor', 'feature', 'bugfix')",
                            },
                        },
                        "required": ["summary"],
                    },
                    "targets": {
                        "type": "object",
                        "description": "Per-target decisions. Use 'default' for the primary decision.",
                        "additionalProperties": {
                            "type": "object",
                            "properties": {
                                "action": {
                                    "type": "string",
                                    "enum": ["skip", "draft", "hold"],
                                    "description": "skip = not worth posting, draft = create content now, hold = save for consolidation later",
                                },
                                "reason": {
                                    "type": "string",
                                    "description": "Explanation for this decision",
                                },
                                "consolidate_with": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "IDs of held decisions to consolidate into this draft",
                                },
                                "arc_id": {
                                    "type": "string",
                                    "description": "ID of an existing active arc this commit continues",
                                },
                                "new_arc_theme": {
                                    "type": "string",
                                    "description": "Theme for a NEW narrative arc (mutually exclusive with arc_id)",
                                },
                                "reference_posts": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "IDs of previous posts to reference or build upon",
                                },
                                "angle": {
                                    "type": "string",
                                    "description": "The hook/angle for the post",
                                },
                                "post_category": {
                                    "type": "string",
                                    "enum": [e.value for e in PostCategorySchema],
                                },
                                "media_tool": {
                                    "type": "string",
                                    "enum": [e.value for e in MediaTool],
                                },
                                "include_project_docs": {
                                    "type": "boolean",
                                    "description": "Set true when the Drafter needs project-level documentation",
                                },
                                "topic_id": {
                                    "type": "string",
                                    "description": "ID of the content topic this relates to",
                                },
                                "context_source": {
                                    "type": "object",
                                    "description": "What context the drafter should receive",
                                    "properties": {
                                        "types": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "description": "Context types: brief, commits, topic, operator_suggestion",
                                        },
                                        "topic_id": {
                                            "type": "string",
                                            "description": "Topic ID for topic context",
                                        },
                                        "suggestion_id": {
                                            "type": "string",
                                            "description": "Suggestion ID for operator suggestion context",
                                        },
                                    },
                                    "required": ["types"],
                                },
                            },
                            "required": ["action", "reason"],
                        },
                    },
                    "queue_actions": {
                        "type": "object",
                        "description": "Actions to take on pending drafts, keyed by target name",
                        "additionalProperties": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "action": {
                                        "type": "string",
                                        "enum": ["supersede", "merge", "drop"],
                                        "description": "supersede = replace with new draft, merge = combine into new draft, drop = discard",
                                    },
                                    "draft_id": {
                                        "type": "string",
                                        "description": "ID of the pending draft to act on",
                                    },
                                    "reason": {
                                        "type": "string",
                                        "description": "Why this action is being taken",
                                    },
                                    "merge_group": {
                                        "type": "string",
                                        "description": "Group label for merge actions. Drafts sharing the same merge_group are combined into one replacement draft. Required for merge actions.",
                                    },
                                    "merge_instruction": {
                                        "type": "string",
                                        "description": "Creative direction for the drafter on HOW to consolidate the drafts in this merge group. Describe the narrative strategy, which elements to keep, and what angle the replacement should take. Only needed on the first action in the group.",
                                    },
                                },
                                "required": ["action", "draft_id", "reason"],
                            },
                        },
                    },
                },
                "required": ["commit_analysis", "targets"],
            },
        }

    @classmethod
    def validate(cls, data: dict[str, Any]) -> "LogEvaluationInput":
        """Validate tool call input data."""
        try:
            return cls.model_validate(data)
        except ValidationError as e:
            raise MalformedResponseError(f"Invalid log_evaluation input: {e}") from e


class CreateDraftInput(BaseModel):
    """Drafter tool call: create_draft."""

    content: str
    platform: str
    reasoning: str
    media_type: MediaTool | None = None
    media_spec: dict[str, Any] | None = None
    format_hint: str | None = None
    beat_count: int | None = None

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
                        "description": (
                            "Specification for media generation. Required when media_type is not 'none'. "
                            "Fields depend on tool: ray_so needs {code, language?, title?}, "
                            "mermaid needs {diagram}, nano_banana_pro needs {prompt}, "
                            "playwright needs {url, selector?}."
                        ),
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
        # Extract text from each item and join with double newlines so
        # _parse_thread_tweets() can split on the numbered "1/, 2/" pattern.
        if isinstance(data.get("content"), list):
            items = data["content"]
            if items and isinstance(items[0], dict) and "content" in items[0]:
                joined = "\n\n".join(item["content"] for item in items)
            else:
                joined = "\n\n".join(str(item) for item in items)
            data = {**data, "content": joined}
        try:
            return cls.model_validate(data)
        except ValidationError as e:
            raise MalformedResponseError(f"Invalid create_draft input: {e}") from e


class RouteActionInput(BaseModel):
    """Gatekeeper tool call: route_action."""

    action: RouteAction
    operation: GatekeeperOperation | None = None
    params: dict[str, Any] | None = None
    escalation_reason: str | None = None
    escalation_context: str | None = None

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
    refined_content: str | None = None
    refined_media_spec: dict[str, Any] | None = None
    answer: str | None = None
    context_note: str | None = None

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
                    "refined_media_spec": {
                        "type": "object",
                        "description": (
                            "For refine_draft: updated media spec. Use when user feedback "
                            "is about the media (code snippet, diagram, image). "
                            "Fields depend on tool: ray_so needs {code, language?, title?}, "
                            "mermaid needs {diagram}, nano_banana_pro needs {prompt}, "
                            "playwright needs {url, selector?}."
                        ),
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
# Stage 1: Commit Analysis (standalone analyzer)
# =============================================================================


class BriefUpdateInstructions(BaseModel):
    """Instructions for incrementally updating brief sections after a commit."""

    sections_to_update: dict[str, str] = {}
    new_facts: list[str] = []


class CommitAnalysisResult(BaseModel):
    """Stage 1 analyzer output: commit classification, tags, summary, brief instructions, topic suggestions."""

    commit_analysis: CommitAnalysis
    brief_update: BriefUpdateInstructions
    topic_suggestions: list[TopicSuggestion] = []

    @classmethod
    def to_tool_schema(cls) -> dict[str, Any]:
        """Return JSON schema dict for the log_commit_analysis tool."""
        return {
            "name": "log_commit_analysis",
            "description": "Record the stage 1 commit analysis: classification, tags, summary, and brief update instructions",
            "input_schema": {
                "type": "object",
                "properties": {
                    "commit_analysis": {
                        "type": "object",
                        "description": "Structured analysis of the commit",
                        "properties": {
                            "summary": {
                                "type": "string",
                                "description": "1-2 sentence summary of what this commit does",
                            },
                            "technical_detail": {
                                "type": "string",
                                "description": "Optional deeper technical context",
                            },
                            "episode_tags": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Freeform tags categorizing this commit (e.g. 'refactor', 'feature', 'bugfix', 'performance')",
                            },
                            "classification": {
                                "type": "string",
                                "enum": [e.value for e in CommitClassification],
                                "description": "Significance level: trivial (whitespace/typos), routine (small fix/refactor), notable (new feature/significant fix), significant (architectural change/major feature)",
                            },
                        },
                        "required": ["summary", "classification", "episode_tags"],
                    },
                    "topic_suggestions": {
                        "type": "array",
                        "description": "Content topics suggested by this commit. Only include when the commit touches a subject area worth writing about.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {
                                    "type": "string",
                                    "description": "Short topic title (2-5 words)",
                                },
                                "description": {
                                    "type": "string",
                                    "description": "1-2 sentences on what this topic covers",
                                },
                                "strategy_type": {
                                    "type": "string",
                                    "enum": ["code-driven", "positioning"],
                                    "description": "code-driven for technical audiences, positioning for product/marketing audiences",
                                },
                            },
                            "required": ["title", "strategy_type"],
                        },
                    },
                    "brief_update": {
                        "type": "object",
                        "description": "Instructions for updating the project brief",
                        "properties": {
                            "sections_to_update": {
                                "type": "object",
                                "description": "Map of brief section name to text to add/update in that section",
                                "additionalProperties": {"type": "string"},
                            },
                            "new_facts": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "New project facts learned from this commit",
                            },
                        },
                    },
                },
                "required": ["commit_analysis", "brief_update"],
            },
        }

    @classmethod
    def validate(cls, data: dict[str, Any]) -> "CommitAnalysisResult":
        """Validate tool call input data."""
        try:
            return cls.model_validate(data)
        except ValidationError as e:
            raise MalformedResponseError(f"Invalid log_commit_analysis input: {e}") from e
