"""Tests for the `social-hook events` CLI command."""

import json
from unittest.mock import MagicMock

from typer.testing import CliRunner

from social_hook.cli import app
from social_hook.db import emit_data_event

runner = CliRunner()


def _patch_db(monkeypatch, temp_db):
    """Monkeypatch DB access so the events command uses temp_db."""
    monkeypatch.setattr("social_hook.filesystem.get_db_path", lambda: "fake")
    monkeypatch.setattr("social_hook.db.connection.init_database", lambda p: temp_db)

    # ResilientConnection creates its own connection to the db_path.
    # Replace it with a mock that returns temp_db directly.
    rc_mock = MagicMock()
    rc_mock.conn = temp_db
    rc_mock.check.return_value = temp_db
    monkeypatch.setattr("social_hook.db.connection.ResilientConnection", lambda p: rc_mock)


class TestEventsCli:
    """Test the events command outputs pipeline events."""

    def test_no_follow_prints_events_and_exits(self, temp_db, monkeypatch):
        """--no-follow prints existing events then exits."""
        emit_data_event(temp_db, "pipeline", "evaluating", "abc123", "proj-1")
        emit_data_event(
            temp_db,
            "draft",
            "created",
            "draft-1",
            "proj-1",
            extra={"content": "Hello world", "platform": "x"},
        )

        _patch_db(monkeypatch, temp_db)

        result = runner.invoke(app, ["events", "--since", "0", "--no-follow"])
        assert result.exit_code == 0
        assert "pipeline" in result.output or "draft" in result.output

    def test_json_mode_outputs_json_lines(self, temp_db, monkeypatch):
        """--json outputs one JSON object per line."""
        emit_data_event(
            temp_db,
            "draft",
            "created",
            "draft-2",
            "proj-1",
            extra={"content": "Test content", "platform": "linkedin"},
        )

        _patch_db(monkeypatch, temp_db)

        result = runner.invoke(app, ["--json", "events", "--since", "0", "--no-follow"])
        assert result.exit_code == 0
        lines = [ln for ln in result.output.strip().splitlines() if ln.strip()]
        assert len(lines) >= 1
        for line in lines:
            data = json.loads(line)
            assert "entity" in data

    def test_entity_filter(self, temp_db, monkeypatch):
        """--entity filters to only matching entity types."""
        emit_data_event(temp_db, "pipeline", "evaluating", "abc", "p-1")
        emit_data_event(
            temp_db,
            "draft",
            "created",
            "d-1",
            "p-1",
            extra={"content": "hi", "platform": "x"},
        )

        _patch_db(monkeypatch, temp_db)

        result = runner.invoke(
            app, ["--json", "events", "--since", "0", "--no-follow", "--entity", "draft"]
        )
        assert result.exit_code == 0
        lines = [ln for ln in result.output.strip().splitlines() if ln.strip()]
        for line in lines:
            data = json.loads(line)
            assert data["entity"] == "draft"

    def test_since_minus_one_skips_existing(self, temp_db, monkeypatch):
        """--since -1 (default) starts from current position, showing no old events."""
        emit_data_event(temp_db, "pipeline", "evaluating", "old", "p-1")

        _patch_db(monkeypatch, temp_db)

        result = runner.invoke(app, ["--json", "events", "--no-follow"])
        assert result.exit_code == 0
        lines = [ln for ln in result.output.strip().splitlines() if ln.strip()]
        assert len(lines) == 0
