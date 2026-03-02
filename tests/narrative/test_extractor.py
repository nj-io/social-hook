"""Tests for narrative.extractor — NarrativeExtractor + ExtractNarrativeInput schema."""

import pytest

from social_hook.errors import MalformedResponseError
from social_hook.llm.base import NormalizedResponse, NormalizedToolCall, NormalizedUsage
from social_hook.llm.schemas import ExtractNarrativeInput, extract_tool_call
from social_hook.narrative.extractor import NarrativeExtractor


# =============================================================================
# Helpers
# =============================================================================


def _valid_extract_data(**overrides):
    """Return valid extract_narrative tool input data with optional overrides."""
    data = {
        "summary": "Implemented caching layer for API responses. Chose Redis over Memcached for persistence.",
        "key_decisions": [
            "Used Redis instead of Memcached for TTL support",
            "Chose write-through caching strategy",
        ],
        "rejected_approaches": [
            "Tried in-memory LRU cache but it didn't survive restarts",
        ],
        "aha_moments": [
            "Discovered the API already had ETag support we could leverage",
        ],
        "challenges": [
            "Cache invalidation across multiple service instances",
        ],
        "narrative_arc": "Started with a simple in-memory cache, hit scaling issues, pivoted to Redis with write-through strategy.",
        "relevant_for_social": True,
        "social_hooks": [
            "We threw away our first caching approach after 2 hours. Here's why the rewrite was worth it.",
            "The API already had the feature we were building. We just didn't know it.",
        ],
    }
    data.update(overrides)
    return data


def _mock_response(tool_name, tool_input):
    """Build a NormalizedResponse with a single tool call."""
    return NormalizedResponse(
        content=[
            NormalizedToolCall(type="tool_use", name=tool_name, input=tool_input),
        ],
        usage=NormalizedUsage(input_tokens=500, output_tokens=300),
    )


class _MockLLMClient:
    """Mock LLMClient that returns a fixed response."""

    provider = "mock"
    model = "mock-model"

    def __init__(self, response):
        self.response = response
        self.last_call = None

    def complete(self, **kwargs):
        self.last_call = kwargs
        return self.response


# =============================================================================
# ExtractNarrativeInput.validate() tests
# =============================================================================


class TestExtractNarrativeInputValidate:
    """Validate ExtractNarrativeInput with various inputs."""

    def test_valid_full_data(self):
        result = ExtractNarrativeInput.validate(_valid_extract_data())
        assert result.summary.startswith("Implemented caching")
        assert len(result.key_decisions) == 2
        assert len(result.rejected_approaches) == 1
        assert len(result.aha_moments) == 1
        assert len(result.challenges) == 1
        assert result.relevant_for_social is True
        assert len(result.social_hooks) == 2

    def test_valid_not_relevant(self):
        result = ExtractNarrativeInput.validate(
            _valid_extract_data(relevant_for_social=False, social_hooks=[])
        )
        assert result.relevant_for_social is False
        assert result.social_hooks == []

    def test_valid_empty_lists(self):
        result = ExtractNarrativeInput.validate(
            _valid_extract_data(
                key_decisions=[],
                rejected_approaches=[],
                aha_moments=[],
                challenges=[],
                social_hooks=[],
            )
        )
        assert result.key_decisions == []
        assert result.rejected_approaches == []

    def test_missing_summary_raises(self):
        data = _valid_extract_data()
        del data["summary"]
        with pytest.raises(MalformedResponseError, match="extract_narrative"):
            ExtractNarrativeInput.validate(data)

    def test_missing_key_decisions_raises(self):
        data = _valid_extract_data()
        del data["key_decisions"]
        with pytest.raises(MalformedResponseError, match="extract_narrative"):
            ExtractNarrativeInput.validate(data)

    def test_missing_narrative_arc_raises(self):
        data = _valid_extract_data()
        del data["narrative_arc"]
        with pytest.raises(MalformedResponseError, match="extract_narrative"):
            ExtractNarrativeInput.validate(data)

    def test_missing_relevant_for_social_raises(self):
        data = _valid_extract_data()
        del data["relevant_for_social"]
        with pytest.raises(MalformedResponseError, match="extract_narrative"):
            ExtractNarrativeInput.validate(data)

    def test_wrong_type_for_summary_raises(self):
        with pytest.raises(MalformedResponseError, match="extract_narrative"):
            ExtractNarrativeInput.validate(_valid_extract_data(summary=123))

    def test_wrong_type_for_key_decisions_raises(self):
        with pytest.raises(MalformedResponseError, match="extract_narrative"):
            ExtractNarrativeInput.validate(_valid_extract_data(key_decisions="not a list"))


# =============================================================================
# ExtractNarrativeInput.to_tool_schema() tests
# =============================================================================


class TestExtractNarrativeInputToolSchema:
    """Verify tool schema structure."""

    def test_schema_name(self):
        schema = ExtractNarrativeInput.to_tool_schema()
        assert schema["name"] == "extract_narrative"

    def test_schema_has_input_schema(self):
        schema = ExtractNarrativeInput.to_tool_schema()
        assert "input_schema" in schema
        assert schema["input_schema"]["type"] == "object"

    def test_schema_has_all_properties(self):
        schema = ExtractNarrativeInput.to_tool_schema()
        props = schema["input_schema"]["properties"]
        expected_fields = [
            "summary",
            "key_decisions",
            "rejected_approaches",
            "aha_moments",
            "challenges",
            "narrative_arc",
            "relevant_for_social",
            "social_hooks",
        ]
        for field in expected_fields:
            assert field in props, f"Missing property: {field}"

    def test_schema_required_fields(self):
        schema = ExtractNarrativeInput.to_tool_schema()
        required = schema["input_schema"]["required"]
        assert set(required) == {
            "summary",
            "key_decisions",
            "rejected_approaches",
            "aha_moments",
            "challenges",
            "narrative_arc",
            "relevant_for_social",
            "social_hooks",
        }

    def test_array_fields_have_items(self):
        schema = ExtractNarrativeInput.to_tool_schema()
        props = schema["input_schema"]["properties"]
        array_fields = [
            "key_decisions",
            "rejected_approaches",
            "aha_moments",
            "challenges",
            "social_hooks",
        ]
        for field in array_fields:
            assert props[field]["type"] == "array", f"{field} should be array"
            assert "items" in props[field], f"{field} should have items"

    def test_boolean_field_type(self):
        schema = ExtractNarrativeInput.to_tool_schema()
        props = schema["input_schema"]["properties"]
        assert props["relevant_for_social"]["type"] == "boolean"


# =============================================================================
# extract_tool_call integration with "extract_narrative"
# =============================================================================


class TestExtractToolCallIntegration:
    """Verify extract_tool_call works with extract_narrative tool name."""

    def test_extracts_extract_narrative_tool(self):
        data = _valid_extract_data()
        response = _mock_response("extract_narrative", data)
        result = extract_tool_call(response, "extract_narrative")
        assert result["summary"] == data["summary"]

    def test_raises_when_no_extract_narrative(self):
        response = _mock_response("log_decision", {"decision": "post_worthy"})
        with pytest.raises(MalformedResponseError, match="No extract_narrative"):
            extract_tool_call(response, "extract_narrative")


# =============================================================================
# NarrativeExtractor tests
# =============================================================================


class TestNarrativeExtractor:
    """Tests for NarrativeExtractor.extract()."""

    def test_extract_returns_validated_input(self):
        data = _valid_extract_data()
        response = _mock_response("extract_narrative", data)
        client = _MockLLMClient(response)
        extractor = NarrativeExtractor(client)

        result = extractor.extract(
            transcript_text="[USER] Let's build caching\n\n[ASSISTANT] Sure.",
            project_name="my-project",
            cwd="/home/user/dev/my-project",
            db=None,
            project_id="proj_123",
        )

        assert isinstance(result, ExtractNarrativeInput)
        assert result.summary == data["summary"]
        assert result.relevant_for_social is True

    def test_extract_passes_correct_tool_schema(self):
        data = _valid_extract_data()
        response = _mock_response("extract_narrative", data)
        client = _MockLLMClient(response)
        extractor = NarrativeExtractor(client)

        extractor.extract(
            transcript_text="transcript",
            project_name="proj",
            cwd="/tmp",
            db=None,
            project_id="proj_1",
        )

        tools = client.last_call["tools"]
        assert len(tools) == 1
        assert tools[0]["name"] == "extract_narrative"

    def test_extract_prompt_includes_project_name(self):
        data = _valid_extract_data()
        response = _mock_response("extract_narrative", data)
        client = _MockLLMClient(response)
        extractor = NarrativeExtractor(client)

        extractor.extract(
            transcript_text="some transcript",
            project_name="awesome-project",
            cwd="/home/dev/awesome-project",
            db=None,
            project_id="proj_1",
        )

        user_msg = client.last_call["messages"][0]["content"]
        assert "awesome-project" in user_msg

    def test_extract_prompt_includes_transcript(self):
        data = _valid_extract_data()
        response = _mock_response("extract_narrative", data)
        client = _MockLLMClient(response)
        extractor = NarrativeExtractor(client)

        transcript = "[USER] How do we handle errors?\n\n[ASSISTANT] Let me think about this."
        extractor.extract(
            transcript_text=transcript,
            project_name="proj",
            cwd="/tmp",
            db=None,
            project_id="proj_1",
        )

        user_msg = client.last_call["messages"][0]["content"]
        assert "How do we handle errors?" in user_msg
        assert "Let me think about this." in user_msg

    def test_extract_prompt_includes_cwd(self):
        data = _valid_extract_data()
        response = _mock_response("extract_narrative", data)
        client = _MockLLMClient(response)
        extractor = NarrativeExtractor(client)

        extractor.extract(
            transcript_text="transcript",
            project_name="proj",
            cwd="/home/user/dev/my-project",
            db=None,
            project_id="proj_1",
        )

        user_msg = client.last_call["messages"][0]["content"]
        assert "/home/user/dev/my-project" in user_msg

    def test_extract_passes_operation_type(self):
        data = _valid_extract_data()
        response = _mock_response("extract_narrative", data)
        client = _MockLLMClient(response)
        extractor = NarrativeExtractor(client)

        extractor.extract(
            transcript_text="t",
            project_name="p",
            cwd="/tmp",
            db="mock_db",
            project_id="proj_1",
        )

        assert client.last_call["operation_type"] == "narrative_extract"
        assert client.last_call["db"] == "mock_db"
        assert client.last_call["project_id"] == "proj_1"

    def test_extract_does_not_pass_commit_hash(self):
        data = _valid_extract_data()
        response = _mock_response("extract_narrative", data)
        client = _MockLLMClient(response)
        extractor = NarrativeExtractor(client)

        extractor.extract(
            transcript_text="t",
            project_name="p",
            cwd="/tmp",
            db=None,
            project_id="proj_1",
        )

        # commit_hash should not be passed (or should be absent/None)
        assert "commit_hash" not in client.last_call or client.last_call.get("commit_hash") is None

    def test_extract_has_system_prompt(self):
        data = _valid_extract_data()
        response = _mock_response("extract_narrative", data)
        client = _MockLLMClient(response)
        extractor = NarrativeExtractor(client)

        extractor.extract(
            transcript_text="t",
            project_name="p",
            cwd="/tmp",
            db=None,
            project_id="proj_1",
        )

        system = client.last_call["system"]
        assert system is not None
        assert len(system) > 100  # Non-trivial system prompt

    def test_extract_raises_on_missing_tool_call(self):
        # Response with no tool call
        response = NormalizedResponse(
            content=[],
            usage=NormalizedUsage(),
        )
        client = _MockLLMClient(response)
        extractor = NarrativeExtractor(client)

        with pytest.raises(MalformedResponseError, match="No extract_narrative"):
            extractor.extract(
                transcript_text="t",
                project_name="p",
                cwd="/tmp",
                db=None,
                project_id="proj_1",
            )

    def test_extract_raises_on_invalid_tool_data(self):
        # Response with tool call but invalid data (missing required fields)
        response = _mock_response("extract_narrative", {"summary": "only summary"})
        client = _MockLLMClient(response)
        extractor = NarrativeExtractor(client)

        with pytest.raises(MalformedResponseError, match="extract_narrative"):
            extractor.extract(
                transcript_text="t",
                project_name="p",
                cwd="/tmp",
                db=None,
                project_id="proj_1",
            )
