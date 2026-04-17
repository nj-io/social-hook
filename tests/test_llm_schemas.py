"""Tests for MediaSpecItem and CreateDraftInput multi-media schema."""

import pytest

from social_hook.errors import MalformedResponseError
from social_hook.llm.schemas import CreateDraftInput, MediaSpecItem


class TestMediaSpecItemValidation:
    """Tool name validation on MediaSpecItem."""

    def test_accepts_all_known_tools(self):
        for tool in ("nano_banana_pro", "mermaid", "ray_so", "playwright", "legacy_upload"):
            item = MediaSpecItem(id="media_000000000001", tool=tool, spec={})
            assert item.tool == tool

    def test_rejects_unknown_tool(self):
        with pytest.raises(ValueError, match="Unknown tool"):
            MediaSpecItem(id="media_000000000001", tool="dalle", spec={})

    def test_none_is_not_a_valid_tool(self):
        """The legacy MediaTool.none value is NOT a valid MediaSpecItem tool."""
        with pytest.raises(ValueError, match="Unknown tool"):
            MediaSpecItem(id="media_000000000001", tool="none", spec={})

    def test_defaults_for_optional_fields(self):
        item = MediaSpecItem(
            id="media_abcdef012345",
            tool="mermaid",
            spec={"diagram": "graph LR\n A-->B"},
        )
        assert item.caption is None
        assert item.user_uploaded is False

    def test_rejects_extra_fields(self):
        """MediaSpecItem uses ConfigDict(extra='forbid')."""
        with pytest.raises(ValueError):
            MediaSpecItem(
                id="media_000000000001",
                tool="mermaid",
                spec={},
                bogus_field="x",
            )


class TestCreateDraftInputMediaSpecs:
    """CreateDraftInput with multi-media parallel-array semantics."""

    def test_empty_media_specs_default(self):
        inp = CreateDraftInput.validate({"content": "hi", "platform": "x", "reasoning": "because"})
        assert inp.media_specs == []

    def test_media_specs_list_accepted(self):
        raw = {
            "content": "hi ![cap](media:media_aaaaaaaaaaaa)",
            "platform": "x",
            "reasoning": "because",
            "media_specs": [
                {
                    "id": "media_aaaaaaaaaaaa",
                    "tool": "mermaid",
                    "spec": {"diagram": "A-->B"},
                    "caption": "cap",
                }
            ],
        }
        inp = CreateDraftInput.validate(raw)
        assert len(inp.media_specs) == 1
        assert inp.media_specs[0].tool == "mermaid"
        assert inp.media_specs[0].caption == "cap"

    def test_unknown_tool_fails_validation(self):
        """Structural validation: an unknown tool name bubbles up as MalformedResponseError."""
        raw = {
            "content": "hi",
            "platform": "x",
            "reasoning": "because",
            "media_specs": [{"id": "media_000000000001", "tool": "dalle", "spec": {}}],
        }
        with pytest.raises(MalformedResponseError):
            CreateDraftInput.validate(raw)


class TestToolSchema:
    """The JSON Schema emitted by CreateDraftInput.to_tool_schema()."""

    def test_schema_has_media_specs_not_singular(self):
        schema = CreateDraftInput.to_tool_schema()
        props = schema["input_schema"]["properties"]
        assert "media_specs" in props
        assert "media_type" not in props
        assert "media_spec" not in props

    def test_media_specs_items_shape(self):
        schema = CreateDraftInput.to_tool_schema()
        items = schema["input_schema"]["properties"]["media_specs"]["items"]
        assert items["required"] == ["id", "tool", "spec"]
        assert items["additionalProperties"] is False
        id_schema = items["properties"]["id"]
        assert id_schema["pattern"] == "^media_[a-f0-9]{12}$"
        tool_enum = set(items["properties"]["tool"]["enum"])
        assert tool_enum == {"nano_banana_pro", "mermaid", "ray_so", "playwright", "legacy_upload"}

    def test_media_specs_has_default_empty_array(self):
        schema = CreateDraftInput.to_tool_schema()
        assert schema["input_schema"]["properties"]["media_specs"]["default"] == []
