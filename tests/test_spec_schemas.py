"""Tests for media adapter spec schemas, preview text, and registry helpers."""

from social_hook.adapters.media.base import MediaAdapter
from social_hook.adapters.media.mermaid import MermaidAdapter
from social_hook.adapters.media.nanabananapro import NanaBananaAdapter
from social_hook.adapters.media.playwright import PlaywrightAdapter
from social_hook.adapters.media.rayso import RaySoAdapter
from social_hook.adapters.registry import (
    get_blank_template,
    get_tool_spec_schema,
    list_available_tools,
)

# --- spec_schema() tests ---


class TestBaseAdapterSchema:
    def test_default_schema_is_empty(self):
        schema = MediaAdapter.spec_schema()
        assert schema == {"required": {}, "optional": {}}


class TestMermaidSchema:
    def test_required_keys(self):
        schema = MermaidAdapter.spec_schema()
        assert "diagram" in schema["required"]

    def test_optional_keys(self):
        schema = MermaidAdapter.spec_schema()
        assert "theme" in schema["optional"]
        assert "format" in schema["optional"]
        assert "width" in schema["optional"]
        assert "height" in schema["optional"]


class TestNanaBananaSchema:
    def test_required_keys(self):
        schema = NanaBananaAdapter.spec_schema()
        assert "prompt" in schema["required"]

    def test_optional_is_empty(self):
        schema = NanaBananaAdapter.spec_schema()
        assert schema["optional"] == {}


class TestRaySoSchema:
    def test_required_keys(self):
        schema = RaySoAdapter.spec_schema()
        assert "code" in schema["required"]

    def test_optional_keys(self):
        schema = RaySoAdapter.spec_schema()
        assert "language" in schema["optional"]
        assert "theme" in schema["optional"]
        assert "padding" in schema["optional"]
        assert "title" in schema["optional"]


class TestPlaywrightSchema:
    def test_required_keys(self):
        schema = PlaywrightAdapter.spec_schema()
        assert "url" in schema["required"]

    def test_optional_keys(self):
        schema = PlaywrightAdapter.spec_schema()
        assert "selector" in schema["optional"]
        assert "width" in schema["optional"]
        assert "height" in schema["optional"]
        assert "full_page" in schema["optional"]


# --- preview_text() tests ---


class TestMermaidPreviewText:
    def test_returns_diagram(self):
        adapter = MermaidAdapter()
        assert adapter.preview_text({"diagram": "graph TD; A-->B"}) == "graph TD; A-->B"

    def test_returns_code_fallback(self):
        adapter = MermaidAdapter()
        assert adapter.preview_text({"code": "graph LR; X-->Y"}) == "graph LR; X-->Y"

    def test_empty_spec(self):
        adapter = MermaidAdapter()
        assert adapter.preview_text({}) == "No diagram specified"


class TestNanaBananaPreviewText:
    def test_returns_prompt(self):
        adapter = NanaBananaAdapter(api_key="test-key")
        assert adapter.preview_text({"prompt": "a cat"}) == "a cat"

    def test_empty_spec(self):
        adapter = NanaBananaAdapter(api_key="test-key")
        assert adapter.preview_text({}) == "No prompt specified"


class TestRaySoPreviewText:
    def test_returns_code(self):
        adapter = RaySoAdapter()
        assert adapter.preview_text({"code": "print('hi')"}) == "print('hi')"

    def test_empty_spec(self):
        adapter = RaySoAdapter()
        assert adapter.preview_text({}) == "No code specified"


class TestPlaywrightPreviewText:
    def test_returns_url(self):
        adapter = PlaywrightAdapter()
        assert adapter.preview_text({"url": "https://example.com"}) == "https://example.com"

    def test_empty_spec(self):
        adapter = PlaywrightAdapter()
        assert adapter.preview_text({}) == "No URL specified"


# --- Registry helper tests ---


class TestGetToolSpecSchema:
    def test_known_tool(self):
        schema = get_tool_spec_schema("mermaid")
        assert "diagram" in schema["required"]

    def test_unknown_tool(self):
        schema = get_tool_spec_schema("nonexistent_tool")
        assert schema == {"required": {}, "optional": {}}

    def test_all_tools_have_schemas(self):
        for name in ["mermaid", "nano_banana_pro", "ray_so", "playwright"]:
            schema = get_tool_spec_schema(name)
            assert "required" in schema
            assert "optional" in schema
            assert len(schema["required"]) > 0


class TestGetBlankTemplate:
    def test_mermaid_template(self):
        tmpl = get_blank_template("mermaid")
        assert tmpl == {"diagram": ""}

    def test_nano_banana_template(self):
        tmpl = get_blank_template("nano_banana_pro")
        assert tmpl == {"prompt": ""}

    def test_rayso_template(self):
        tmpl = get_blank_template("ray_so")
        assert tmpl == {"code": ""}

    def test_playwright_template(self):
        tmpl = get_blank_template("playwright")
        assert tmpl == {"url": ""}

    def test_unknown_tool_template(self):
        tmpl = get_blank_template("nonexistent")
        assert tmpl == {}


class TestListAvailableTools:
    def test_returns_four_tools(self):
        tools = list_available_tools()
        assert len(tools) == 4

    def test_tool_names(self):
        tools = list_available_tools()
        names = [t["name"] for t in tools]
        assert "mermaid" in names
        assert "nano_banana_pro" in names
        assert "ray_so" in names
        assert "playwright" in names

    def test_metadata_fields(self):
        tools = list_available_tools()
        for tool in tools:
            assert "name" in tool
            assert "display_name" in tool
            assert "description" in tool
            assert "required_fields" in tool
            assert len(tool["display_name"]) > 0
            assert len(tool["description"]) > 0
            assert len(tool["required_fields"]) > 0

    def test_display_names(self):
        tools = list_available_tools()
        by_name = {t["name"]: t for t in tools}
        assert by_name["mermaid"]["display_name"] == "Mermaid"
        assert by_name["nano_banana_pro"]["display_name"] == "Nano Banana Pro"
        assert by_name["ray_so"]["display_name"] == "Ray.so"
        assert by_name["playwright"]["display_name"] == "Playwright"
