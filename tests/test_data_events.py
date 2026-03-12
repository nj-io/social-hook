"""Tests for data event emission (WebSocket push notifications)."""

import json

from social_hook.db import emit_data_event
from social_hook.llm.dry_run import DryRunContext


class TestEmitDataEvent:
    """Test emit_data_event() writes correct rows to web_events."""

    def test_inserts_row_into_web_events(self, temp_db):
        """emit_data_event inserts a row with type='data_change'."""
        emit_data_event(temp_db, "draft", "created", "draft-123", "proj-1")

        row = temp_db.execute(
            "SELECT type, data FROM web_events ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        assert row[0] == "data_change"

    def test_payload_structure(self, temp_db):
        """Payload contains entity, action, entity_id, and project_id."""
        emit_data_event(temp_db, "decision", "updated", "dec-42", "proj-7")

        row = temp_db.execute("SELECT data FROM web_events ORDER BY id DESC LIMIT 1").fetchone()
        payload = json.loads(row[0])
        assert payload["entity"] == "decision"
        assert payload["action"] == "updated"
        assert payload["entity_id"] == "dec-42"
        assert payload["project_id"] == "proj-7"

    def test_defaults_for_optional_fields(self, temp_db):
        """entity_id and project_id default to empty string."""
        emit_data_event(temp_db, "post", "created")

        row = temp_db.execute("SELECT data FROM web_events ORDER BY id DESC LIMIT 1").fetchone()
        payload = json.loads(row[0])
        assert payload["entity_id"] == ""
        assert payload["project_id"] == ""

    def test_extra_fields_merged_into_payload(self, temp_db):
        """Extra dict fields are merged into the event payload."""
        emit_data_event(
            temp_db,
            "draft",
            "created",
            "draft-456",
            "proj-1",
            extra={"content": "hello world", "platform": "x"},
        )

        row = temp_db.execute("SELECT data FROM web_events ORDER BY id DESC LIMIT 1").fetchone()
        payload = json.loads(row[0])
        assert payload["content"] == "hello world"
        assert payload["platform"] == "x"
        # Core fields still present
        assert payload["entity"] == "draft"
        assert payload["entity_id"] == "draft-456"

    def test_extra_none_is_safe(self, temp_db):
        """Passing extra=None does not break anything."""
        emit_data_event(temp_db, "pipeline", "evaluating", "abc123", "p-1", extra=None)

        row = temp_db.execute("SELECT data FROM web_events ORDER BY id DESC LIMIT 1").fetchone()
        payload = json.loads(row[0])
        assert "content" not in payload
        assert payload["entity"] == "pipeline"

    def test_non_fatal_on_closed_connection(self, temp_db):
        """emit_data_event does not raise on a closed connection."""
        temp_db.close()
        # Should not raise
        emit_data_event(temp_db, "draft", "created", "d-1", "p-1")


class TestDryRunEmitDataEvent:
    """Test that DryRunContext.emit_data_event is a no-op in dry-run mode."""

    def test_dry_run_skips_emit(self, temp_db):
        """In dry-run mode, emit_data_event does not insert any row."""
        db = DryRunContext(temp_db, dry_run=True)

        # Get current count
        before = temp_db.execute("SELECT COUNT(*) FROM web_events").fetchone()[0]

        db.emit_data_event("draft", "created", "d-1", "p-1")

        after = temp_db.execute("SELECT COUNT(*) FROM web_events").fetchone()[0]
        assert after == before

    def test_non_dry_run_emits(self, temp_db):
        """In non-dry-run mode, emit_data_event inserts a row."""
        db = DryRunContext(temp_db, dry_run=False)

        before = temp_db.execute("SELECT COUNT(*) FROM web_events").fetchone()[0]

        db.emit_data_event("draft", "created", "d-1", "p-1")

        after = temp_db.execute("SELECT COUNT(*) FROM web_events").fetchone()[0]
        assert after == before + 1
