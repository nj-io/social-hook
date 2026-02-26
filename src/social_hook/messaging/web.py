"""SQLite-backed messaging adapter for web dashboard polling.

Writes all outbound messages to a `web_events` table.
Auto-creates the table on first use. Takes `db_path` as constructor param.

REUSABILITY: This file imports only from messaging.base (stdlib types)
and stdlib (sqlite3, json, threading). No project-specific domain concepts.
"""

import json
import sqlite3
import threading
from typing import Optional

from social_hook.messaging.base import (
    ButtonRow,
    MessagingAdapter,
    OutboundMessage,
    PlatformCapabilities,
    SendResult,
)


class WebAdapter(MessagingAdapter):
    """SQLite-backed MessagingAdapter for web dashboard communication."""

    platform = "web"

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._write_count = 0
        self._ensure_table()

    def send_message(self, chat_id: str, message: OutboundMessage) -> SendResult:
        """Write a message event to web_events."""
        data = {
            "chat_id": chat_id,
            "text": message.text,
            "parse_mode": message.parse_mode,
        }
        if message.buttons:
            data["buttons"] = self._serialize_buttons(message.buttons)
        row_id = self._insert_event("message", data)
        return SendResult(success=True, message_id=str(row_id))

    def edit_message(
        self, chat_id: str, message_id: str, message: OutboundMessage
    ) -> SendResult:
        """Write an edit event to web_events."""
        data = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": message.text,
            "parse_mode": message.parse_mode,
        }
        if message.buttons:
            data["buttons"] = self._serialize_buttons(message.buttons)
        row_id = self._insert_event("edit", data)
        return SendResult(success=True, message_id=str(row_id))

    def answer_callback(self, callback_id: str, text: str = "") -> bool:
        """Write a callback acknowledgment event to web_events."""
        data = {"callback_id": callback_id, "text": text}
        self._insert_event("callback_ack", data)
        return True

    def send_media(
        self,
        chat_id: str,
        file_path: str,
        caption: str = "",
        parse_mode: str = "markdown",
    ) -> SendResult:
        """Write a media event to web_events."""
        data = {
            "chat_id": chat_id,
            "file_path": file_path,
            "caption": caption,
            "parse_mode": parse_mode,
        }
        row_id = self._insert_event("media", data)
        return SendResult(success=True, message_id=str(row_id))

    def get_capabilities(self) -> PlatformCapabilities:
        """Return high-limit capabilities for the web platform."""
        return PlatformCapabilities(
            max_message_length=100000,
            supports_buttons=True,
            supports_inline_buttons=True,
            supports_message_editing=True,
            supports_markdown=True,
            supports_html=True,
            button_text_max_length=256,
            supports_media=True,
            max_media_per_message=20,
            supported_media_types=["png", "jpg", "jpeg", "gif", "svg", "webp"],
        )

    # --- Internal helpers ---

    def _ensure_table(self) -> None:
        """Create the web_events table if it doesn't exist."""
        with self._get_conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS web_events (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    type       TEXT NOT NULL,
                    data       TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_web_events_created
                    ON web_events(created_at);
                """
            )

    def _insert_event(self, event_type: str, data: dict) -> int:
        """Insert an event and return its row ID."""
        with self._lock:
            with self._get_conn() as conn:
                cursor = conn.execute(
                    "INSERT INTO web_events (type, data) VALUES (?, ?)",
                    (event_type, json.dumps(data)),
                )
                row_id = cursor.lastrowid
                conn.commit()

            self._write_count += 1
            if self._write_count % 100 == 0:
                self._cleanup_old_events()

        return row_id

    def _cleanup_old_events(self) -> None:
        """Delete events older than 7 days. Called amortized every 100 writes."""
        with self._get_conn() as conn:
            conn.execute(
                "DELETE FROM web_events WHERE created_at < datetime('now', '-7 days')"
            )
            conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a SQLite connection."""
        return sqlite3.connect(self._db_path)

    @staticmethod
    def _serialize_buttons(rows: list[ButtonRow]) -> list[list[dict]]:
        """Serialize ButtonRow list to JSON-compatible format."""
        return [
            [
                {"label": btn.label, "action": btn.action, "payload": btn.payload}
                for btn in row.buttons
            ]
            for row in rows
        ]
