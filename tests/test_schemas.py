"""Tests for LLM tool call schemas (T12)."""

import pytest

from social_hook.errors import MalformedResponseError
from social_hook.llm.schemas import (
    CreateDraftInput,
    DecisionTypeSchema,
    EpisodeTypeSchema,
    ExpertAction,
    ExpertResponseInput,
    GatekeeperOperation,
    LogDecisionInput,
    MediaTool,
    PostCategorySchema,
    RouteAction,
    RouteActionInput,
    extract_tool_call,
)


# =============================================================================
# T12: Schema Enum Tests
# =============================================================================


class TestSchemaEnums:
    """T12: Verify schema enums have correct values."""

    def test_decision_type_schema_values(self):
        assert DecisionTypeSchema.post_worthy.value == "post_worthy"
        assert DecisionTypeSchema.not_post_worthy.value == "not_post_worthy"
        assert DecisionTypeSchema.consolidate.value == "consolidate"
        assert DecisionTypeSchema.deferred.value == "deferred"

    def test_episode_type_schema_values(self):
        assert EpisodeTypeSchema.decision.value == "decision"
        assert EpisodeTypeSchema.before_after.value == "before_after"
        assert EpisodeTypeSchema.synthesis.value == "synthesis"

    def test_media_tool_values(self):
        assert MediaTool.mermaid.value == "mermaid"
        assert MediaTool.nano_banana_pro.value == "nano_banana_pro"
        assert MediaTool.none.value == "none"

    def test_route_action_values(self):
        assert RouteAction.handle_directly.value == "handle_directly"
        assert RouteAction.escalate_to_expert.value == "escalate_to_expert"

    def test_gatekeeper_operation_values(self):
        ops = [e.value for e in GatekeeperOperation]
        assert "approve" in ops
        assert "schedule" in ops
        assert "reject" in ops
        assert "cancel" in ops
        assert "substitute" in ops
        assert "query" in ops

    def test_expert_action_values(self):
        assert ExpertAction.refine_draft.value == "refine_draft"
        assert ExpertAction.answer_question.value == "answer_question"
        assert ExpertAction.save_context_note.value == "save_context_note"


# =============================================================================
# T12: LogDecisionInput Tests
# =============================================================================


class TestLogDecisionInput:
    """T12: Evaluator schema validation."""

    def test_valid_minimal(self):
        result = LogDecisionInput.validate({
            "decision": "post_worthy",
            "reasoning": "Important feature added",
        })
        assert result.decision == DecisionTypeSchema.post_worthy
        assert result.reasoning == "Important feature added"
        assert result.episode_type is None

    def test_valid_full(self):
        result = LogDecisionInput.validate({
            "decision": "post_worthy",
            "reasoning": "Major architecture change",
            "episode_type": "decision",
            "post_category": "arc",
            "arc_id": "arc_123",
            "media_tool": "mermaid",
        })
        assert result.episode_type == EpisodeTypeSchema.decision
        assert result.post_category == PostCategorySchema.arc
        assert result.arc_id == "arc_123"
        assert result.media_tool == MediaTool.mermaid

    def test_invalid_decision_type(self):
        with pytest.raises(MalformedResponseError):
            LogDecisionInput.validate({
                "decision": "invalid_type",
                "reasoning": "Test",
            })

    def test_missing_required_field(self):
        with pytest.raises(MalformedResponseError):
            LogDecisionInput.validate({
                "decision": "post_worthy",
                # missing reasoning
            })

    def test_invalid_episode_type(self):
        with pytest.raises(MalformedResponseError):
            LogDecisionInput.validate({
                "decision": "post_worthy",
                "reasoning": "Test",
                "episode_type": "invalid_episode",
            })

    def test_invalid_media_type(self):
        with pytest.raises(MalformedResponseError):
            LogDecisionInput.validate({
                "decision": "post_worthy",
                "reasoning": "Test",
                "media_tool": "photoshop",
            })

    def test_tool_schema_structure(self):
        schema = LogDecisionInput.to_tool_schema()
        assert schema["name"] == "log_decision"
        assert "input_schema" in schema
        assert "decision" in schema["input_schema"]["properties"]
        assert schema["input_schema"]["required"] == ["decision", "reasoning"]

    def test_not_post_worthy_minimal(self):
        result = LogDecisionInput.validate({
            "decision": "not_post_worthy",
            "reasoning": "Minor typo fix",
        })
        assert result.decision == DecisionTypeSchema.not_post_worthy


# =============================================================================
# T12: CreateDraftInput Tests
# =============================================================================


class TestCreateDraftInput:
    """T12: Drafter schema validation."""

    def test_valid_minimal(self):
        result = CreateDraftInput.validate({
            "content": "Just shipped a new feature!",
            "platform": "x",
            "reasoning": "Milestone worth sharing",
        })
        assert result.content == "Just shipped a new feature!"
        assert result.platform == "x"
        assert result.media_type is None

    def test_valid_with_media(self):
        result = CreateDraftInput.validate({
            "content": "Architecture overview",
            "platform": "linkedin",
            "reasoning": "Technical deep-dive",
            "media_type": "mermaid",
            "media_spec": {"diagram": "graph LR; A-->B"},
        })
        assert result.media_type == MediaTool.mermaid
        assert result.media_spec == {"diagram": "graph LR; A-->B"}

    def test_custom_platform_accepted(self):
        """Platform is now a free-form string — custom platforms are valid."""
        result = CreateDraftInput.validate({
            "content": "Test",
            "platform": "blog",
            "reasoning": "Test",
        })
        assert result.platform == "blog"

    def test_missing_content(self):
        with pytest.raises(MalformedResponseError):
            CreateDraftInput.validate({
                "platform": "x",
                "reasoning": "Test",
            })

    def test_tool_schema_structure(self):
        schema = CreateDraftInput.to_tool_schema()
        assert schema["name"] == "create_draft"
        assert "content" in schema["input_schema"]["properties"]
        assert "platform" in schema["input_schema"]["properties"]
        assert set(schema["input_schema"]["required"]) == {
            "content", "platform", "reasoning"
        }


# =============================================================================
# T12: RouteActionInput Tests
# =============================================================================


class TestRouteActionInput:
    """T12: Gatekeeper schema validation."""

    def test_handle_directly_approve(self):
        result = RouteActionInput.validate({
            "action": "handle_directly",
            "operation": "approve",
        })
        assert result.action == RouteAction.handle_directly
        assert result.operation == GatekeeperOperation.approve

    def test_handle_directly_schedule(self):
        result = RouteActionInput.validate({
            "action": "handle_directly",
            "operation": "schedule",
            "params": {"time": "2026-01-15T14:00:00"},
        })
        assert result.params == {"time": "2026-01-15T14:00:00"}

    def test_escalate_to_expert(self):
        result = RouteActionInput.validate({
            "action": "escalate_to_expert",
            "escalation_reason": "Creative request",
            "escalation_context": "User wants a more casual tone",
        })
        assert result.action == RouteAction.escalate_to_expert
        assert result.escalation_reason == "Creative request"

    def test_cancel_operation(self):
        result = RouteActionInput.validate({
            "action": "handle_directly",
            "operation": "cancel",
        })
        assert result.operation == GatekeeperOperation.cancel

    def test_invalid_action(self):
        with pytest.raises(MalformedResponseError):
            RouteActionInput.validate({
                "action": "invalid_action",
            })

    def test_tool_schema_has_cancel(self):
        schema = RouteActionInput.to_tool_schema()
        operations = schema["input_schema"]["properties"]["operation"]["enum"]
        assert "cancel" in operations

    def test_tool_schema_structure(self):
        schema = RouteActionInput.to_tool_schema()
        assert schema["name"] == "route_action"
        assert schema["input_schema"]["required"] == ["action"]


# =============================================================================
# T12: ExpertResponseInput Tests
# =============================================================================


class TestExpertResponseInput:
    """T12: Expert schema validation."""

    def test_refine_draft(self):
        result = ExpertResponseInput.validate({
            "action": "refine_draft",
            "reasoning": "Adjusted tone per user request",
            "refined_content": "Updated post content here",
        })
        assert result.action == ExpertAction.refine_draft
        assert result.refined_content == "Updated post content here"

    def test_answer_question(self):
        result = ExpertResponseInput.validate({
            "action": "answer_question",
            "reasoning": "User asked about evaluation logic",
            "answer": "The commit was skipped because...",
        })
        assert result.answer == "The commit was skipped because..."

    def test_save_context_note(self):
        result = ExpertResponseInput.validate({
            "action": "save_context_note",
            "reasoning": "User provided feedback",
            "context_note": "Author prefers shorter posts",
        })
        assert result.context_note == "Author prefers shorter posts"

    def test_missing_reasoning(self):
        with pytest.raises(MalformedResponseError):
            ExpertResponseInput.validate({
                "action": "refine_draft",
                # missing reasoning
            })

    def test_invalid_action(self):
        with pytest.raises(MalformedResponseError):
            ExpertResponseInput.validate({
                "action": "invalid_action",
                "reasoning": "Test",
            })

    def test_tool_schema_structure(self):
        schema = ExpertResponseInput.to_tool_schema()
        assert schema["name"] == "expert_response"
        assert set(schema["input_schema"]["required"]) == {"action", "reasoning"}


# =============================================================================
# T12: extract_tool_call Tests
# =============================================================================


class _MockContent:
    """Mock content block from Claude response."""

    def __init__(self, content_type: str, name: str = "", input_data: dict = None):
        self.type = content_type
        self.name = name
        self.input = input_data or {}


class _MockResponse:
    """Mock Claude API response."""

    def __init__(self, content_blocks: list):
        self.content = content_blocks


class TestExtractToolCall:
    """T12: Tool call extraction."""

    def test_extract_matching_tool(self):
        response = _MockResponse([
            _MockContent("text"),
            _MockContent("tool_use", "log_decision", {"decision": "post_worthy"}),
        ])
        result = extract_tool_call(response, "log_decision")
        assert result["decision"] == "post_worthy"

    def test_missing_tool_raises(self):
        response = _MockResponse([
            _MockContent("text"),
        ])
        with pytest.raises(MalformedResponseError, match="No log_decision"):
            extract_tool_call(response, "log_decision")

    def test_wrong_tool_name_raises(self):
        response = _MockResponse([
            _MockContent("tool_use", "create_draft", {"content": "test"}),
        ])
        with pytest.raises(MalformedResponseError, match="No log_decision"):
            extract_tool_call(response, "log_decision")

    def test_extracts_first_matching_tool(self):
        response = _MockResponse([
            _MockContent("tool_use", "log_decision", {"decision": "first"}),
            _MockContent("tool_use", "log_decision", {"decision": "second"}),
        ])
        result = extract_tool_call(response, "log_decision")
        assert result["decision"] == "first"

    def test_mixed_content_types(self):
        response = _MockResponse([
            _MockContent("text"),
            _MockContent("tool_use", "other_tool", {}),
            _MockContent("tool_use", "log_decision", {"decision": "post_worthy"}),
            _MockContent("text"),
        ])
        result = extract_tool_call(response, "log_decision")
        assert result["decision"] == "post_worthy"

    def test_extract_tool_call_from_normalized_response(self):
        """Verify NormalizedResponse works with extract_tool_call (provider interop)."""
        from social_hook.llm.base import NormalizedResponse, NormalizedToolCall, NormalizedUsage

        tool_call = NormalizedToolCall(
            type="tool_use",
            name="log_decision",
            input={"decision": "post_worthy", "reasoning": "test", "episode_type": "standalone", "post_category": "feature_launch"},
        )
        response = NormalizedResponse(
            content=[tool_call],
            usage=NormalizedUsage(input_tokens=100, output_tokens=50),
        )

        result = extract_tool_call(response, "log_decision")
        assert result["decision"] == "post_worthy"
        assert result["reasoning"] == "test"
