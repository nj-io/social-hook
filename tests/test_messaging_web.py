"""Tests for WebAdapter — SQLite-backed messaging adapter."""

import json
import sqlite3
import tempfile
import threading
from pathlib import Path

import pytest

from social_hook.messaging.base import (
    Button,
    ButtonRow,
    OutboundMessage,
    PlatformCapabilities,
    SendResult,
)
from social_hook.messaging.web import WebAdapter


@pytest.fixture
def db_path(tmp_path):
    """Return a temporary SQLite database path."""
    return str(tmp_path / "test_web.db")


@pytest.fixture
def adapter(db_path):
    """Return a WebAdapter connected to a temp database."""
    return WebAdapter(db_path=db_path)


def _get_events(db_path):
    """Read all events from the database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM web_events ORDER BY id").fetchall()
    conn.close()
    return rows


class TestSendMessage:
    def test_send_message_writes_event(self, adapter, db_path):
        """send_message should insert a 'message' event into web_events."""
        msg = OutboundMessage(text="Hello, world!")
        result = adapter.send_message("chat_1", msg)

        assert result.success is True
        assert result.message_id is not None

        events = _get_events(db_path)
        assert len(events) == 1
        assert events[0]["type"] == "message"

        data = json.loads(events[0]["data"])
        assert data["chat_id"] == "chat_1"
        assert data["text"] == "Hello, world!"

    def test_send_message_with_buttons(self, adapter, db_path):
        """send_message should serialize buttons into the event data."""
        buttons = [
            ButtonRow(buttons=[
                Button(label="Approve", action="approve", payload="draft_123"),
                Button(label="Reject", action="reject", payload="draft_123"),
            ]),
            ButtonRow(buttons=[
                Button(label="Edit", action="edit", payload="draft_123"),
            ]),
        ]
        msg = OutboundMessage(text="Review this draft", buttons=buttons)
        result = adapter.send_message("chat_1", msg)

        assert result.success is True

        events = _get_events(db_path)
        data = json.loads(events[0]["data"])
        assert "buttons" in data
        assert len(data["buttons"]) == 2
        assert len(data["buttons"][0]) == 2
        assert data["buttons"][0][0]["label"] == "Approve"
        assert data["buttons"][0][0]["action"] == "approve"
        assert data["buttons"][0][0]["payload"] == "draft_123"
        assert len(data["buttons"][1]) == 1
        assert data["buttons"][1][0]["label"] == "Edit"


class TestEditMessage:
    def test_edit_message_writes_event(self, adapter, db_path):
        """edit_message should insert an 'edit' event."""
        msg = OutboundMessage(text="Updated content")
        result = adapter.edit_message("chat_1", "msg_5", msg)

        assert result.success is True

        events = _get_events(db_path)
        assert len(events) == 1
        assert events[0]["type"] == "edit"

        data = json.loads(events[0]["data"])
        assert data["chat_id"] == "chat_1"
        assert data["message_id"] == "msg_5"
        assert data["text"] == "Updated content"


class TestAnswerCallback:
    def test_answer_callback_writes_event(self, adapter, db_path):
        """answer_callback should insert a 'callback_ack' event."""
        result = adapter.answer_callback("cb_42", text="Done!")

        assert result is True

        events = _get_events(db_path)
        assert len(events) == 1
        assert events[0]["type"] == "callback_ack"

        data = json.loads(events[0]["data"])
        assert data["callback_id"] == "cb_42"
        assert data["text"] == "Done!"


class TestSendMedia:
    def test_send_media_writes_event(self, adapter, db_path):
        """send_media should insert a 'media' event with file_path."""
        result = adapter.send_media("chat_1", "/tmp/image.png", caption="Screenshot")

        assert result.success is True

        events = _get_events(db_path)
        assert len(events) == 1
        assert events[0]["type"] == "media"

        data = json.loads(events[0]["data"])
        assert data["chat_id"] == "chat_1"
        assert data["file_path"] == "/tmp/image.png"
        assert data["caption"] == "Screenshot"


class TestCapabilities:
    def test_get_capabilities(self, adapter):
        """get_capabilities should return high-limit web capabilities."""
        caps = adapter.get_capabilities()

        assert isinstance(caps, PlatformCapabilities)
        assert caps.max_message_length == 100000
        assert caps.supports_buttons is True
        assert caps.supports_media is True
        assert caps.max_media_per_message == 20


class TestPersistence:
    def test_events_persisted_to_db(self, adapter, db_path):
        """Events should be readable from a fresh connection."""
        adapter.send_message("c1", OutboundMessage(text="First"))
        adapter.send_message("c2", OutboundMessage(text="Second"))
        adapter.edit_message("c1", "1", OutboundMessage(text="Edited"))

        # Read from a fresh connection to verify persistence
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM web_events").fetchone()[0]
        conn.close()

        assert count == 3

    def test_event_json_format(self, adapter, db_path):
        """Each event should have id, type, data (JSON), and created_at."""
        adapter.send_message("chat_x", OutboundMessage(text="Test msg"))

        events = _get_events(db_path)
        event = events[0]

        assert event["id"] is not None
        assert event["type"] == "message"
        assert event["created_at"] is not None

        data = json.loads(event["data"])
        assert data["chat_id"] == "chat_x"
        assert data["text"] == "Test msg"

    def test_message_ids_increment(self, adapter):
        """Each send should return an incrementing message_id."""
        r1 = adapter.send_message("c", OutboundMessage(text="a"))
        r2 = adapter.send_message("c", OutboundMessage(text="b"))
        r3 = adapter.send_message("c", OutboundMessage(text="c"))

        assert int(r1.message_id) < int(r2.message_id) < int(r3.message_id)


class TestThreadSafety:
    def test_thread_safety(self, adapter, db_path):
        """Multiple threads writing concurrently should all persist."""
        errors = []

        def write_events(thread_id, count=10):
            try:
                for i in range(count):
                    adapter.send_message(
                        f"thread_{thread_id}",
                        OutboundMessage(text=f"msg_{i}"),
                    )
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=write_events, args=(t,))
            for t in range(3)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"

        events = _get_events(db_path)
        assert len(events) == 30  # 3 threads * 10 events each


class TestPlatform:
    def test_platform_is_web(self, adapter):
        """The platform property should be 'web'."""
        assert adapter.platform == "web"


class TestCleanup:
    def test_cleanup_old_events(self, db_path):
        """Events older than 7 days should be cleaned up after 100 writes."""
        adapter = WebAdapter(db_path=db_path)

        # Insert an old event directly
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO web_events (type, data, created_at) VALUES (?, ?, datetime('now', '-8 days'))",
            ("message", json.dumps({"text": "old"})),
        )
        conn.commit()
        conn.close()

        # Verify old event exists
        events = _get_events(db_path)
        assert len(events) == 1

        # Write 100 events to trigger cleanup
        for i in range(100):
            adapter.send_message("c", OutboundMessage(text=f"msg_{i}"))

        events = _get_events(db_path)
        # The old event should be gone, only the 100 new ones remain
        assert len(events) == 100

        # Verify no old events remain
        conn = sqlite3.connect(db_path)
        old_count = conn.execute(
            "SELECT COUNT(*) FROM web_events WHERE created_at < datetime('now', '-7 days')"
        ).fetchone()[0]
        conn.close()
        assert old_count == 0
