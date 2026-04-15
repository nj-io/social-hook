"""Tests for cross-post sync, preview, and sister draft operations."""

import json
import sqlite3
from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

from social_hook.bot.buttons import (
    btn_media_preview,
    btn_media_sync_siblings,
)
from social_hook.db.operations import get_sister_drafts, sync_media_to_drafts
from social_hook.messaging.base import PlatformCapabilities, SendResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class FakeDraft:
    id: str = "draft_src123456"
    project_id: str = "proj_abc"
    decision_id: str = "dec_shared"
    status: str = "draft"
    platform: str = "x"
    media_paths: list = field(default_factory=list)
    media_type: str | None = "mermaid"
    media_spec: dict | None = field(default_factory=lambda: {"diagram": "A-->B"})
    media_spec_used: dict | None = None
    content: str = "test"


def _make_adapter():
    adapter = MagicMock()
    adapter.send_message.return_value = SendResult(success=True)
    adapter.answer_callback.return_value = True
    adapter.get_capabilities.return_value = PlatformCapabilities(supports_media=True)
    return adapter


# ---------------------------------------------------------------------------
# DB operations: get_sister_drafts
# ---------------------------------------------------------------------------


class TestGetSisterDrafts:
    def _setup_db(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE drafts (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                decision_id TEXT,
                platform TEXT,
                status TEXT DEFAULT 'draft',
                content TEXT DEFAULT '',
                media_paths TEXT DEFAULT '[]',
                media_type TEXT,
                media_spec TEXT,
                media_spec_used TEXT,
                suggested_time TEXT,
                scheduled_time TEXT,
                reasoning TEXT,
                superseded_by TEXT,
                retry_count INTEGER DEFAULT 0,
                last_error TEXT,
                is_intro INTEGER DEFAULT 0,
                reference_type TEXT,
                vehicle TEXT NOT NULL DEFAULT 'single',
                reference_post_id TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE draft_changes (
                id TEXT PRIMARY KEY,
                draft_id TEXT,
                field TEXT,
                old_value TEXT,
                new_value TEXT,
                changed_by TEXT,
                changed_at TEXT DEFAULT (datetime('now'))
            )
        """)
        return conn

    def test_returns_sisters_only(self):
        conn = self._setup_db()
        conn.execute(
            "INSERT INTO drafts (id, project_id, decision_id, platform) VALUES (?, ?, ?, ?)",
            ("draft_a", "proj1", "dec_shared", "x"),
        )
        conn.execute(
            "INSERT INTO drafts (id, project_id, decision_id, platform) VALUES (?, ?, ?, ?)",
            ("draft_b", "proj1", "dec_shared", "linkedin"),
        )
        conn.execute(
            "INSERT INTO drafts (id, project_id, decision_id, platform) VALUES (?, ?, ?, ?)",
            ("draft_c", "proj1", "dec_other", "x"),
        )
        conn.commit()

        sisters = get_sister_drafts(conn, "draft_a")
        assert len(sisters) == 1
        assert sisters[0].id == "draft_b"

    def test_include_self(self):
        conn = self._setup_db()
        conn.execute(
            "INSERT INTO drafts (id, project_id, decision_id, platform) VALUES (?, ?, ?, ?)",
            ("draft_a", "proj1", "dec_shared", "x"),
        )
        conn.execute(
            "INSERT INTO drafts (id, project_id, decision_id, platform) VALUES (?, ?, ?, ?)",
            ("draft_b", "proj1", "dec_shared", "linkedin"),
        )
        conn.commit()

        sisters = get_sister_drafts(conn, "draft_a", include_self=True)
        assert len(sisters) == 2

    def test_no_sisters(self):
        conn = self._setup_db()
        conn.execute(
            "INSERT INTO drafts (id, project_id, decision_id, platform) VALUES (?, ?, ?, ?)",
            ("draft_a", "proj1", "dec_alone", "x"),
        )
        conn.commit()

        sisters = get_sister_drafts(conn, "draft_a")
        assert sisters == []

    def test_nonexistent_draft(self):
        conn = self._setup_db()
        sisters = get_sister_drafts(conn, "draft_missing")
        assert sisters == []


# ---------------------------------------------------------------------------
# DB operations: sync_media_to_drafts
# ---------------------------------------------------------------------------


class TestSyncMediaToDrafts:
    def _setup_db(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE drafts (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                decision_id TEXT,
                platform TEXT,
                status TEXT DEFAULT 'draft',
                content TEXT DEFAULT '',
                media_paths TEXT DEFAULT '[]',
                media_type TEXT,
                media_spec TEXT,
                media_spec_used TEXT,
                suggested_time TEXT,
                scheduled_time TEXT,
                reasoning TEXT,
                superseded_by TEXT,
                retry_count INTEGER DEFAULT 0,
                last_error TEXT,
                is_intro INTEGER DEFAULT 0,
                reference_type TEXT,
                vehicle TEXT NOT NULL DEFAULT 'single',
                reference_post_id TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        return conn

    def test_sync_copies_media(self):
        conn = self._setup_db()
        conn.execute(
            "INSERT INTO drafts (id, project_id, decision_id, platform, media_type, media_spec, media_paths) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("src", "p", "d", "x", "mermaid", '{"diagram": "A-->B"}', '["img.png"]'),
        )
        conn.execute(
            "INSERT INTO drafts (id, project_id, decision_id, platform) VALUES (?, ?, ?, ?)",
            ("tgt", "p", "d", "linkedin"),
        )
        conn.commit()

        count = sync_media_to_drafts(conn, "src", ["tgt"])
        assert count == 1

        row = conn.execute(
            "SELECT media_type, media_spec, media_paths FROM drafts WHERE id = 'tgt'"
        ).fetchone()
        assert row["media_type"] == "mermaid"
        assert json.loads(row["media_spec"]) == {"diagram": "A-->B"}
        assert json.loads(row["media_paths"]) == ["img.png"]

    def test_sync_nonexistent_source(self):
        conn = self._setup_db()
        count = sync_media_to_drafts(conn, "missing", ["tgt"])
        assert count == 0


# ---------------------------------------------------------------------------
# btn_media_preview
# ---------------------------------------------------------------------------


class TestMediaPreview:
    @patch("social_hook.bot.buttons._get_conn")
    @patch("social_hook.bot.buttons._send")
    def test_shows_preview_text(self, mock_send, mock_conn):
        draft = FakeDraft(media_type="mermaid", media_spec={"diagram": "A-->B"})
        conn = MagicMock()
        mock_conn.return_value = conn

        mock_adapter_instance = MagicMock()
        mock_adapter_instance.preview_text.return_value = "A-->B"

        with (
            patch("social_hook.db.get_draft", return_value=draft),
            patch(
                "social_hook.adapters.registry.get_media_adapter",
                return_value=mock_adapter_instance,
            ),
        ):
            adapter = _make_adapter()
            btn_media_preview(adapter, "c1", "cb1", "draft_src123456", None)

        sent_texts = [call[0][2] for call in mock_send.call_args_list]
        assert any("A-->B" in t for t in sent_texts)

    @patch("social_hook.bot.buttons._get_conn")
    @patch("social_hook.bot.buttons._send")
    def test_no_spec(self, mock_send, mock_conn):
        draft = FakeDraft(media_spec=None)
        conn = MagicMock()
        mock_conn.return_value = conn

        with patch("social_hook.db.get_draft", return_value=draft):
            adapter = _make_adapter()
            btn_media_preview(adapter, "c1", "cb1", "draft_src123456", None)

        mock_send.assert_any_call(adapter, "c1", "No media spec to preview.")


# ---------------------------------------------------------------------------
# btn_media_sync_siblings
# ---------------------------------------------------------------------------


class TestMediaSyncSiblings:
    @patch("social_hook.bot.buttons._get_conn")
    @patch("social_hook.bot.buttons._send")
    def test_syncs_to_editable_sisters(self, mock_send, mock_conn):
        source = FakeDraft(id="draft_src123456")
        sister = FakeDraft(id="draft_sis", platform="linkedin", status="draft")
        conn = MagicMock()
        mock_conn.return_value = conn

        with (
            patch("social_hook.db.get_draft", return_value=source),
            patch(
                "social_hook.db.operations.get_sister_drafts",
                return_value=[sister],
            ),
            patch(
                "social_hook.db.operations.sync_media_to_drafts",
                return_value=1,
            ),
        ):
            adapter = _make_adapter()
            btn_media_sync_siblings(adapter, "c1", "cb1", "draft_src123456", None)

        sent_texts = [call[0][2] for call in mock_send.call_args_list]
        assert any("Synced media to 1" in t for t in sent_texts)

    @patch("social_hook.bot.buttons._get_conn")
    @patch("social_hook.bot.buttons._send")
    def test_no_sisters(self, mock_send, mock_conn):
        source = FakeDraft()
        conn = MagicMock()
        mock_conn.return_value = conn

        with (
            patch("social_hook.db.get_draft", return_value=source),
            patch("social_hook.db.operations.get_sister_drafts", return_value=[]),
        ):
            adapter = _make_adapter()
            btn_media_sync_siblings(adapter, "c1", "cb1", "draft_src123456", None)

        mock_send.assert_any_call(adapter, "c1", "No sister drafts to sync to.")

    @patch("social_hook.bot.buttons._get_conn")
    @patch("social_hook.bot.buttons._send")
    def test_skips_non_editable_sisters(self, mock_send, mock_conn):
        source = FakeDraft()
        posted_sister = FakeDraft(id="draft_posted", status="posted", platform="linkedin")
        conn = MagicMock()
        mock_conn.return_value = conn

        with (
            patch("social_hook.db.get_draft", return_value=source),
            patch(
                "social_hook.db.operations.get_sister_drafts",
                return_value=[posted_sister],
            ),
        ):
            adapter = _make_adapter()
            btn_media_sync_siblings(adapter, "c1", "cb1", "draft_src123456", None)

        mock_send.assert_any_call(adapter, "c1", "No editable sister drafts to sync to.")
