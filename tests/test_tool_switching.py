"""Tests for tool switching, spec generation, and new media button handlers."""

from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

from social_hook.adapters.models import MediaResult
from social_hook.bot.buttons import (
    btn_edit_media,
    btn_media_confirm_gen,
    btn_media_gen_spec,
    btn_media_pick_tool,
    btn_media_upload,
)
from social_hook.bot.commands import _handle_pending_reply, _save_media_spec, _save_media_upload
from social_hook.llm.prompts import assemble_spec_generation_prompt, build_spec_generation_tool
from social_hook.messaging.base import PlatformCapabilities, SendResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class FakeDraft:
    """Minimal draft stand-in for tests."""

    id: str = "draft_test123456"
    project_id: str = "proj_abc"
    status: str = "draft"
    media_paths: list = field(default_factory=list)
    media_type: str | None = "mermaid"
    media_spec: dict | None = field(default_factory=lambda: {"diagram": "A-->B"})
    media_spec_used: dict | None = None
    content: str = "Check out our new feature!"
    platform: str = "x"


@dataclass
class FakePending:
    type: str
    draft_id: str
    timestamp: float = 0.0


def _make_adapter():
    adapter = MagicMock()
    adapter.send_message.return_value = SendResult(success=True)
    adapter.answer_callback.return_value = True
    adapter.get_capabilities.return_value = PlatformCapabilities(supports_media=True)
    adapter.send_media.return_value = SendResult(success=True)
    return adapter


# ---------------------------------------------------------------------------
# btn_edit_media — media-less flow
# ---------------------------------------------------------------------------


class TestEditMediaMedialess:
    @patch("social_hook.bot.buttons._get_conn")
    def test_no_media_shows_add_buttons(self, mock_conn):
        """When draft has no media, show Add media / Upload file buttons."""
        draft = FakeDraft(status="draft", media_paths=[])
        conn = MagicMock()
        mock_conn.return_value = conn

        with (
            patch("social_hook.db.get_draft", return_value=draft),
            patch("social_hook.bot.commands.set_chat_draft_context"),
        ):
            adapter = _make_adapter()
            btn_edit_media(adapter, "c1", "cb1", "draft_test123456", None)

        # Should have sent a message with buttons
        call_args = adapter.send_message.call_args_list
        # Find the call with buttons (not the answer_callback)
        button_calls = [c for c in call_args if hasattr(c[0][1], "buttons") and c[0][1].buttons]
        assert len(button_calls) >= 1
        msg = button_calls[0][0][1]
        assert "No media" in msg.text
        actions = [b.action for row in msg.buttons for b in row.buttons]
        assert "media_pick_tool" in actions
        assert "media_upload" in actions

    @patch("social_hook.bot.buttons._get_conn")
    def test_has_media_shows_switch_tool(self, mock_conn):
        """When draft has media, show Switch tool button alongside regen/remove."""
        draft = FakeDraft(status="draft", media_paths=["/tmp/img.png"])
        conn = MagicMock()
        mock_conn.return_value = conn

        with (
            patch("social_hook.db.get_draft", return_value=draft),
            patch("social_hook.bot.commands.set_chat_draft_context"),
        ):
            adapter = _make_adapter()
            btn_edit_media(adapter, "c1", "cb1", "draft_test123456", None)

        call_args = adapter.send_message.call_args_list
        button_calls = [c for c in call_args if hasattr(c[0][1], "buttons") and c[0][1].buttons]
        assert len(button_calls) >= 1
        msg = button_calls[0][0][1]
        actions = [b.action for row in msg.buttons for b in row.buttons]
        assert "media_pick_tool" in actions
        assert "media_regen" in actions
        assert "media_retry" in actions
        assert "media_remove" in actions


# ---------------------------------------------------------------------------
# btn_media_pick_tool
# ---------------------------------------------------------------------------


class TestMediaPickTool:
    def test_shows_all_available_tools(self):
        adapter = _make_adapter()
        with patch(
            "social_hook.adapters.registry.list_available_tools",
            return_value=[
                {"name": "mermaid", "display_name": "Mermaid Diagrams"},
                {"name": "ray_so", "display_name": "Code Screenshots"},
            ],
        ):
            btn_media_pick_tool(adapter, "c1", "cb1", "draft_test123456", None)

        call_args = adapter.send_message.call_args_list
        button_calls = [c for c in call_args if hasattr(c[0][1], "buttons") and c[0][1].buttons]
        assert len(button_calls) == 1
        msg = button_calls[0][0][1]
        assert "Pick a media tool" in msg.text
        actions = [b.action for row in msg.buttons for b in row.buttons]
        assert all(a == "media_gen_spec" for a in actions)
        payloads = [b.payload for row in msg.buttons for b in row.buttons]
        assert any("mermaid" in p for p in payloads)
        assert any("ray_so" in p for p in payloads)


# ---------------------------------------------------------------------------
# btn_media_gen_spec — LLM-assisted flow
# ---------------------------------------------------------------------------


class TestMediaGenSpec:
    @patch("social_hook.bot.buttons._get_conn")
    @patch("social_hook.bot.buttons._send")
    def test_invalid_payload(self, mock_send, mock_conn):
        adapter = _make_adapter()
        btn_media_gen_spec(adapter, "c1", "cb1", "invalid_no_pipe", None)
        mock_send.assert_any_call(adapter, "c1", "Invalid tool selection.")

    @patch("social_hook.bot.buttons._get_conn")
    @patch("social_hook.bot.buttons._send")
    def test_guard_blocks_posted(self, mock_send, mock_conn):
        draft = FakeDraft(status="posted")
        conn = MagicMock()
        mock_conn.return_value = conn

        with (
            patch("social_hook.db.get_draft", return_value=draft),
            patch("social_hook.db.update_draft"),
        ):
            adapter = _make_adapter()
            btn_media_gen_spec(adapter, "c1", "cb1", "draft_test123456|mermaid", None)

        mock_send.assert_any_call(adapter, "c1", "Cannot edit media \u2014 draft is posted.")

    @patch("social_hook.bot.buttons._get_conn")
    @patch("social_hook.bot.buttons._send")
    def test_manual_spec_fallback(self, mock_send, mock_conn):
        """Without config, falls back to manual spec entry prompt."""
        draft = FakeDraft(status="draft")
        conn = MagicMock()
        mock_conn.return_value = conn

        with (
            patch("social_hook.db.get_draft", return_value=draft),
            patch("social_hook.db.update_draft"),
        ):
            adapter = _make_adapter()
            btn_media_gen_spec(adapter, "c1", "cb1", "draft_test123456|mermaid", None)

        # Should have shown schema and asked for JSON
        sent_texts = [call[0][2] for call in mock_send.call_args_list]
        assert any("Reply with JSON spec" in t for t in sent_texts)


# ---------------------------------------------------------------------------
# btn_media_confirm_gen
# ---------------------------------------------------------------------------


class TestMediaConfirmGen:
    @patch("social_hook.bot.buttons._get_conn")
    @patch("social_hook.bot.buttons._send")
    def test_generates_media_successfully(self, mock_send, mock_conn):
        draft = FakeDraft(
            status="draft",
            media_type="mermaid",
            media_spec={"diagram": "A-->B"},
        )
        conn = MagicMock()
        mock_conn.return_value = conn

        mock_media_adapter = MagicMock()
        mock_media_adapter.generate.return_value = MediaResult(
            success=True, file_path="/new/diagram.png"
        )

        with (
            patch("social_hook.db.get_draft", return_value=draft),
            patch("social_hook.db.update_draft"),
            patch("social_hook.db.operations.insert_draft_change"),
            patch("social_hook.db.operations.get_sister_drafts", return_value=[]),
            patch(
                "social_hook.adapters.registry.get_media_adapter",
                return_value=mock_media_adapter,
            ),
            patch("social_hook.filesystem.generate_id", return_value="change_abc"),
            patch(
                "social_hook.filesystem.get_base_path",
                return_value=MagicMock(
                    __truediv__=MagicMock(
                        return_value=MagicMock(__truediv__=MagicMock(return_value="/tmp/cache"))
                    )
                ),
            ),
        ):
            adapter = _make_adapter()
            btn_media_confirm_gen(adapter, "c1", "cb1", "draft_test123456", None)

        mock_media_adapter.generate.assert_called_once()
        mock_send.assert_any_call(adapter, "c1", "Media generated successfully.")

    @patch("social_hook.bot.buttons._get_conn")
    @patch("social_hook.bot.buttons._send")
    def test_no_spec_error(self, mock_send, mock_conn):
        draft = FakeDraft(status="draft", media_spec=None)
        conn = MagicMock()
        mock_conn.return_value = conn

        with patch("social_hook.db.get_draft", return_value=draft):
            adapter = _make_adapter()
            btn_media_confirm_gen(adapter, "c1", "cb1", "draft_test123456", None)

        mock_send.assert_any_call(adapter, "c1", "No media spec configured. Pick a tool first.")


# ---------------------------------------------------------------------------
# btn_media_upload
# ---------------------------------------------------------------------------


class TestMediaUploadButton:
    @patch("social_hook.bot.buttons._get_conn")
    @patch("social_hook.bot.buttons._send")
    def test_sets_pending_reply(self, mock_send, mock_conn):
        draft = FakeDraft(status="draft")
        conn = MagicMock()
        mock_conn.return_value = conn

        with patch("social_hook.db.get_draft", return_value=draft):
            adapter = _make_adapter()
            btn_media_upload(adapter, "c1", "cb1", "draft_test123456", None)

        mock_send.assert_any_call(
            adapter, "c1", "Send a media file (image/photo) to attach to `draft_test12`."
        )

    @patch("social_hook.bot.buttons._get_conn")
    @patch("social_hook.bot.buttons._send")
    def test_guard_blocks_posted(self, mock_send, mock_conn):
        draft = FakeDraft(status="posted")
        conn = MagicMock()
        mock_conn.return_value = conn

        with patch("social_hook.db.get_draft", return_value=draft):
            adapter = _make_adapter()
            btn_media_upload(adapter, "c1", "cb1", "draft_test123456", None)

        mock_send.assert_any_call(adapter, "c1", "Cannot edit media \u2014 draft is posted.")


# ---------------------------------------------------------------------------
# _save_media_spec (pending reply handler)
# ---------------------------------------------------------------------------


class TestSaveMediaSpec:
    @patch("social_hook.bot.commands._get_conn")
    @patch("social_hook.bot.commands._send")
    def test_valid_json_triggers_generation(self, mock_send, mock_conn):
        draft = FakeDraft(status="draft", media_type="mermaid")
        conn = MagicMock()
        mock_conn.return_value = conn

        with (
            patch("social_hook.db.get_draft", return_value=draft),
            patch("social_hook.db.update_draft"),
            patch("social_hook.bot.buttons.btn_media_confirm_gen") as mock_confirm,
        ):
            adapter = _make_adapter()
            _save_media_spec(adapter, "c1", "draft_test123456", '{"diagram": "X-->Y"}', None)

        mock_confirm.assert_called_once()

    @patch("social_hook.bot.commands._get_conn")
    @patch("social_hook.bot.commands._send")
    def test_invalid_json_reprompts(self, mock_send, mock_conn):
        draft = FakeDraft(status="draft")
        conn = MagicMock()
        mock_conn.return_value = conn

        with patch("social_hook.db.get_draft", return_value=draft):
            adapter = _make_adapter()
            _save_media_spec(adapter, "c1", "draft_test123456", "not valid json", None)

        sent_texts = [call[0][2] for call in mock_send.call_args_list]
        assert any("Invalid JSON" in t for t in sent_texts)

    @patch("social_hook.bot.commands._get_conn")
    @patch("social_hook.bot.commands._send")
    def test_markdown_code_block_stripped(self, mock_send, mock_conn):
        draft = FakeDraft(status="draft", media_type="mermaid")
        conn = MagicMock()
        mock_conn.return_value = conn

        with (
            patch("social_hook.db.get_draft", return_value=draft),
            patch("social_hook.db.update_draft"),
            patch("social_hook.bot.buttons.btn_media_confirm_gen") as mock_confirm,
        ):
            adapter = _make_adapter()
            _save_media_spec(
                adapter,
                "c1",
                "draft_test123456",
                '```json\n{"diagram": "X-->Y"}\n```',
                None,
            )

        mock_confirm.assert_called_once()


# ---------------------------------------------------------------------------
# _save_media_upload
# ---------------------------------------------------------------------------


class TestSaveMediaUpload:
    @patch("social_hook.bot.commands._get_conn")
    @patch("social_hook.bot.commands._send")
    def test_attaches_file(self, mock_send, mock_conn):
        draft = FakeDraft(status="draft", media_paths=[])
        conn = MagicMock()
        mock_conn.return_value = conn

        with (
            patch("social_hook.db.get_draft", return_value=draft),
            patch("social_hook.db.update_draft") as mock_update,
            patch("social_hook.db.operations.insert_draft_change"),
            patch("social_hook.db.operations.emit_data_event"),
            patch("social_hook.filesystem.generate_id", return_value="change_abc"),
        ):
            adapter = _make_adapter()
            _save_media_upload(adapter, "c1", "draft_test123456", "/tmp/photo.jpg")

        mock_update.assert_called_once()
        mock_send.assert_any_call(adapter, "c1", "Media attached to `draft_test12`.")

    @patch("social_hook.bot.commands._get_conn")
    @patch("social_hook.bot.commands._send")
    def test_empty_path_error(self, mock_send, mock_conn):
        draft = FakeDraft(status="draft")
        conn = MagicMock()
        mock_conn.return_value = conn

        with patch("social_hook.db.get_draft", return_value=draft):
            adapter = _make_adapter()
            _save_media_upload(adapter, "c1", "draft_test123456", "  ")

        mock_send.assert_any_call(adapter, "c1", "No file received. Send a photo or file.")


# ---------------------------------------------------------------------------
# _handle_pending_reply routing
# ---------------------------------------------------------------------------


class TestPendingReplyRouting:
    @patch("social_hook.bot.commands._save_media_spec")
    def test_routes_edit_media_spec(self, mock_save):
        adapter = _make_adapter()
        pending = FakePending(type="edit_media_spec", draft_id="draft_x")
        _handle_pending_reply(adapter, "c1", pending, '{"code": "x"}', None)
        mock_save.assert_called_once_with(adapter, "c1", "draft_x", '{"code": "x"}', None)

    @patch("social_hook.bot.commands._save_media_upload")
    def test_routes_media_upload(self, mock_save):
        adapter = _make_adapter()
        pending = FakePending(type="media_upload", draft_id="draft_x")
        _handle_pending_reply(adapter, "c1", pending, "/tmp/photo.jpg", None)
        mock_save.assert_called_once_with(adapter, "c1", "draft_x", "/tmp/photo.jpg")


# ---------------------------------------------------------------------------
# assemble_spec_generation_prompt
# ---------------------------------------------------------------------------


class TestSpecGenerationPrompt:
    def test_includes_tool_and_content(self):
        schema = {
            "required": {"diagram": "Mermaid markup string"},
            "optional": {"theme": "Color theme"},
        }
        prompt = assemble_spec_generation_prompt(
            tool_name="mermaid",
            schema=schema,
            draft_content="We just shipped a new CI pipeline!",
        )
        assert "mermaid" in prompt
        assert "diagram" in prompt
        assert "CI pipeline" in prompt

    def test_output_is_string(self):
        prompt = assemble_spec_generation_prompt(
            tool_name="ray_so",
            schema={"required": {"code": "snippet"}},
            draft_content="Hello world",
        )
        assert isinstance(prompt, str)
        assert len(prompt) > 50


class TestBuildSpecGenerationTool:
    def test_required_fields_become_properties(self):
        schema = {"required": {"diagram": "Mermaid code"}, "optional": {}}
        tool = build_spec_generation_tool("mermaid", schema)
        assert tool["name"] == "generate_media_spec"
        assert "diagram" in tool["input_schema"]["properties"]
        assert tool["input_schema"]["required"] == ["diagram"]

    def test_optional_fields_included_not_required(self):
        schema = {"required": {"code": "snippet"}, "optional": {"theme": "color theme"}}
        tool = build_spec_generation_tool("ray_so", schema)
        assert "theme" in tool["input_schema"]["properties"]
        assert "theme" not in tool["input_schema"]["required"]

    def test_empty_schema(self):
        tool = build_spec_generation_tool("unknown", {"required": {}, "optional": {}})
        assert tool["input_schema"]["properties"] == {}
        assert tool["input_schema"]["required"] == []

    def test_tool_name_in_description(self):
        tool = build_spec_generation_tool("mermaid", {"required": {"x": "y"}, "optional": {}})
        assert "mermaid" in tool["description"]
