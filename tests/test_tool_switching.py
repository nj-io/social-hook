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
    """Minimal draft stand-in for tests.

    Multi-media surface: parallel arrays (media_specs, media_paths,
    media_errors, media_specs_used) replace the dropped singular
    media_type/media_spec/media_spec_used columns. Seeded with one
    mermaid slot by default so tests that expect an existing item work.
    """

    id: str = "draft_test123456"
    project_id: str = "proj_abc"
    status: str = "draft"
    media_paths: list = field(default_factory=list)
    media_specs: list = field(
        default_factory=lambda: [
            {
                "id": "media_aaa111bbb222",
                "tool": "mermaid",
                "spec": {"diagram": "A-->B"},
                "caption": None,
                "user_uploaded": False,
            }
        ]
    )
    media_errors: list = field(default_factory=lambda: [None])
    media_specs_used: list = field(default_factory=list)
    content: str = "Check out our new feature!"
    platform: str = "x"
    vehicle: str = "single"


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
        draft = FakeDraft(status="draft", media_paths=[], media_specs=[])
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
        assert "No media" in msg.text
        actions = [b.action for row in msg.buttons for b in row.buttons]
        # Multi-media no-items view: Add media + Upload file.
        assert "media_add" in actions
        assert "media_upload" in actions

    @patch("social_hook.bot.buttons._get_conn")
    def test_has_media_shows_switch_tool(self, mock_conn):
        """When draft has media, show per-item Regen/Retry/Edit spec/Preview/Remove buttons."""
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
        # Multi-media layout: header bar (Add/Regen-all/Replan) + per-item rows.
        assert len(button_calls) >= 2
        all_actions = [
            b.action
            for msg_call in button_calls
            for row in msg_call[0][1].buttons
            for b in row.buttons
        ]
        # Bulk header actions:
        assert "media_add" in all_actions
        assert "media_regen_all" in all_actions
        assert "media_replan_specs" in all_actions
        # Per-item actions (Edit spec replaces legacy Switch tool):
        assert "media_regen" in all_actions
        assert "media_retry" in all_actions
        assert "media_gen_spec" in all_actions  # "Edit spec" on per-item row
        assert "media_remove" in all_actions


# ---------------------------------------------------------------------------
# btn_media_pick_tool
# ---------------------------------------------------------------------------


class TestMediaPickTool:
    @patch("social_hook.bot.buttons._get_conn")
    def test_shows_all_available_tools(self, mock_conn):
        """With explicit media_id (3-part payload), show tool picker directly.

        Multi-media: pick_tool now prompts "which item?" first when a draft
        has ≥1 items and the payload has no media_id. Passing a 3-part
        payload `draft_id:media_id` bypasses that and shows the tool list.
        """
        draft = FakeDraft(status="draft")
        conn = MagicMock()
        mock_conn.return_value = conn
        adapter = _make_adapter()
        with (
            patch("social_hook.db.get_draft", return_value=draft),
            patch(
                "social_hook.adapters.registry.list_available_tools",
                return_value=[
                    {"name": "mermaid", "display_name": "Mermaid Diagrams"},
                    {"name": "ray_so", "display_name": "Code Screenshots"},
                ],
            ),
        ):
            btn_media_pick_tool(adapter, "c1", "cb1", "draft_test123456:media_aaa111bbb222", None)

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
        """Without config, falls back to manual spec entry prompt.

        Payload names an existing media_id so no new slot is appended.
        """
        draft = FakeDraft(status="draft")  # Seeded with media_aaa111bbb222.
        conn = MagicMock()
        mock_conn.return_value = conn

        with (
            patch("social_hook.db.get_draft", return_value=draft),
            patch("social_hook.db.operations.update_draft_media"),
        ):
            adapter = _make_adapter()
            btn_media_gen_spec(
                adapter,
                "c1",
                "cb1",
                "draft_test123456:media_aaa111bbb222|mermaid",
                None,
            )

        sent_texts = [call[0][2] for call in mock_send.call_args_list]
        assert any("Reply with JSON spec" in t for t in sent_texts)


# ---------------------------------------------------------------------------
# btn_media_confirm_gen
# ---------------------------------------------------------------------------


class TestMediaConfirmGen:
    @patch("social_hook.bot.buttons._get_conn")
    @patch("social_hook.bot.buttons._send")
    def test_generates_media_successfully(self, mock_send, mock_conn):
        """Legacy 2-part payload operates on media_specs[0] via _parse_media_payload."""
        draft = FakeDraft(status="draft")  # default media_specs has one mermaid slot
        conn = MagicMock()
        mock_conn.return_value = conn

        mock_media_adapter = MagicMock()
        mock_media_adapter.generate.return_value = MediaResult(
            success=True, file_path="/new/diagram.png"
        )

        with (
            patch("social_hook.db.get_draft", return_value=draft),
            patch("social_hook.media_regen.ops.get_draft", return_value=draft),
            patch("social_hook.media_regen.ops.update_draft_media"),
            patch("social_hook.media_regen.ops.insert_draft_change"),
            patch("social_hook.media_regen.ops.emit_data_event"),
            patch("social_hook.db.operations.get_sister_drafts", return_value=[]),
            patch(
                "social_hook.adapters.registry.get_media_adapter",
                return_value=mock_media_adapter,
            ),
            patch("social_hook.media_regen.generate_id", return_value="change_abc"),
            patch(
                "social_hook.media_regen.get_base_path",
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
        """Legacy 2-part payload + no media_specs at all → handler aborts."""
        draft = FakeDraft(status="draft", media_specs=[])
        conn = MagicMock()
        mock_conn.return_value = conn

        with patch("social_hook.db.get_draft", return_value=draft):
            adapter = _make_adapter()
            btn_media_confirm_gen(adapter, "c1", "cb1", "draft_test123456", None)

        mock_send.assert_any_call(adapter, "c1", "No media slot configured — pick a tool first.")


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

        sent_texts = [call[0][2] for call in mock_send.call_args_list]
        assert any("Send a media file" in t for t in sent_texts)
        # Multi-media: prompt mentions 5 MiB limit + APPEND-as-new-slot semantics.
        assert any("5 MiB" in t for t in sent_texts)
        assert any("new media slot" in t for t in sent_texts)

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
        """Valid JSON updates the first media slot, dispatches confirm_gen."""
        draft = FakeDraft(status="draft")  # default has one mermaid slot
        conn = MagicMock()
        mock_conn.return_value = conn

        with (
            patch("social_hook.db.get_draft", return_value=draft),
            patch("social_hook.db.operations.update_draft_media"),
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
        draft = FakeDraft(status="draft")
        conn = MagicMock()
        mock_conn.return_value = conn

        with (
            patch("social_hook.db.get_draft", return_value=draft),
            patch("social_hook.db.operations.update_draft_media"),
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
        """_save_media_upload APPENDS a new slot via ops.append_draft_media."""
        draft = FakeDraft(status="draft", media_paths=[], media_specs=[])
        conn = MagicMock()
        mock_conn.return_value = conn

        with (
            patch("social_hook.db.get_draft", return_value=draft),
            patch(
                "social_hook.db.operations.append_draft_media",
                return_value="media_newxxx123456",
            ) as mock_append,
            patch("social_hook.db.operations.update_draft_media"),
            patch("social_hook.db.operations.insert_draft_change"),
            patch("social_hook.db.operations.emit_data_event"),
            patch("social_hook.filesystem.generate_id", return_value="change_abc"),
        ):
            adapter = _make_adapter()
            _save_media_upload(adapter, "c1", "draft_test123456", "/tmp/photo.jpg")

        mock_append.assert_called_once()
        # Appended slot should be user_uploaded legacy_upload pointing at the path.
        appended_spec = mock_append.call_args[0][2]
        assert appended_spec["tool"] == "legacy_upload"
        assert appended_spec["user_uploaded"] is True
        assert appended_spec["spec"]["path"] == "/tmp/photo.jpg"
        sent_texts = [call[0][2] for call in mock_send.call_args_list]
        assert any("Attached media_newxxx123456" in t for t in sent_texts)

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
        """Legacy type 'edit_media_spec' (no suffix) routes with media_id=None.

        Multi-media: the new type format is `edit_media_spec:{media_id}`,
        so the legacy form falls back to slot 0 (_save_media_spec picks it).
        """
        adapter = _make_adapter()
        pending = FakePending(type="edit_media_spec", draft_id="draft_x")
        _handle_pending_reply(adapter, "c1", pending, '{"code": "x"}', None)
        mock_save.assert_called_once_with(
            adapter, "c1", "draft_x", '{"code": "x"}', None, media_id=None
        )

    @patch("social_hook.bot.commands._save_media_spec")
    def test_routes_edit_media_spec_with_media_id(self, mock_save):
        """New suffix form passes media_id through."""
        adapter = _make_adapter()
        pending = FakePending(type="edit_media_spec:media_abc123", draft_id="draft_x")
        _handle_pending_reply(adapter, "c1", pending, '{"code": "x"}', None)
        mock_save.assert_called_once_with(
            adapter, "c1", "draft_x", '{"code": "x"}', None, media_id="media_abc123"
        )

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
