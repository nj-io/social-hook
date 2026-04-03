"""Tests for the system error feed (Chunk 5).

Each test uses a fresh ErrorFeed() instance to avoid state leaks.
"""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from social_hook.error_feed import ErrorFeed, ErrorSeverity

_CREATE_TABLE_SQL = """\
CREATE TABLE IF NOT EXISTS system_errors (
    id TEXT PRIMARY KEY,
    severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'error', 'critical')),
    message TEXT NOT NULL,
    context TEXT DEFAULT '{}',
    source TEXT DEFAULT '',
    component TEXT DEFAULT '',
    run_id TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_system_errors_severity ON system_errors(severity, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_system_errors_component ON system_errors(component, created_at DESC);
"""


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    """Create a temp DB with the system_errors table."""
    path = str(tmp_path / "test_errors.db")
    conn = sqlite3.connect(path)
    conn.executescript(_CREATE_TABLE_SQL)
    conn.close()
    return path


@pytest.fixture
def feed() -> ErrorFeed:
    """Fresh ErrorFeed with no DB (in-memory only)."""
    return ErrorFeed()


@pytest.fixture
def db_feed(db_path: str) -> ErrorFeed:
    """Fresh ErrorFeed wired to a temp DB."""
    f = ErrorFeed(db_path=db_path)
    return f


# =============================================================================
# Emit at each severity level
# =============================================================================


class TestEmitSeverities:
    def test_emit_info(self, feed: ErrorFeed):
        feed.emit(ErrorSeverity.INFO, "info message")
        recent = feed.get_recent()
        assert len(recent) == 1
        assert recent[0].severity == ErrorSeverity.INFO
        assert recent[0].message == "info message"

    def test_emit_warning(self, feed: ErrorFeed):
        feed.emit(ErrorSeverity.WARNING, "warning message")
        recent = feed.get_recent()
        assert len(recent) == 1
        assert recent[0].severity == ErrorSeverity.WARNING

    def test_emit_error(self, feed: ErrorFeed):
        feed.emit(ErrorSeverity.ERROR, "error message")
        recent = feed.get_recent()
        assert len(recent) == 1
        assert recent[0].severity == ErrorSeverity.ERROR

    def test_emit_critical(self, feed: ErrorFeed):
        feed.emit(ErrorSeverity.CRITICAL, "critical message")
        recent = feed.get_recent()
        assert len(recent) == 1
        assert recent[0].severity == ErrorSeverity.CRITICAL

    def test_emit_with_context_and_source(self, feed: ErrorFeed):
        feed.emit(
            ErrorSeverity.ERROR,
            "auth failed",
            context={"account": "main"},
            source="auth",
        )
        recent = feed.get_recent()
        assert recent[0].context == {"account": "main"}
        assert recent[0].source == "auth"


# =============================================================================
# Sender callback routing
# =============================================================================


class TestSenderCallback:
    def test_critical_triggers_sender(self, feed: ErrorFeed):
        sender = MagicMock()
        feed.set_sender(sender)
        feed.emit(ErrorSeverity.CRITICAL, "critical event", source="scheduler")
        sender.assert_called_once()
        args = sender.call_args[0]
        assert args[0] == "critical"
        assert "critical event" in args[1]

    def test_error_triggers_sender(self, feed: ErrorFeed):
        sender = MagicMock()
        feed.set_sender(sender)
        feed.emit(ErrorSeverity.ERROR, "error event")
        sender.assert_called_once()
        args = sender.call_args[0]
        assert args[0] == "error"

    def test_info_does_not_trigger_sender(self, feed: ErrorFeed):
        sender = MagicMock()
        feed.set_sender(sender)
        feed.emit(ErrorSeverity.INFO, "info event")
        sender.assert_not_called()

    def test_warning_does_not_trigger_sender(self, feed: ErrorFeed):
        sender = MagicMock()
        feed.set_sender(sender)
        feed.emit(ErrorSeverity.WARNING, "warning event")
        sender.assert_not_called()


# =============================================================================
# Ring buffer caps at max_recent
# =============================================================================


class TestRingBuffer:
    def test_caps_at_max_recent(self):
        feed = ErrorFeed(max_recent=5)
        for i in range(10):
            feed.emit(ErrorSeverity.INFO, f"msg {i}")
        recent = feed.get_recent()
        assert len(recent) == 5
        # Newest first
        assert recent[0].message == "msg 9"
        assert recent[4].message == "msg 5"


# =============================================================================
# Health status counts
# =============================================================================


class TestHealthStatus:
    def test_counts_correctly(self, feed: ErrorFeed):
        feed.emit(ErrorSeverity.INFO, "i1")
        feed.emit(ErrorSeverity.INFO, "i2")
        feed.emit(ErrorSeverity.WARNING, "w1")
        feed.emit(ErrorSeverity.ERROR, "e1")
        feed.emit(ErrorSeverity.CRITICAL, "c1")
        feed.emit(ErrorSeverity.CRITICAL, "c2")

        status = feed.get_health_status()
        assert status["info"] == 2
        assert status["warning"] == 1
        assert status["error"] == 1
        assert status["critical"] == 2

    def test_empty_feed_returns_zero_counts(self, feed: ErrorFeed):
        status = feed.get_health_status()
        assert status == {"info": 0, "warning": 0, "error": 0, "critical": 0}


# =============================================================================
# Emit never raises even if sender callback fails
# =============================================================================


class TestEmitNeverRaises:
    def test_emit_survives_sender_exception(self, feed: ErrorFeed):
        def bad_sender(sev, msg):
            raise RuntimeError("sender exploded")

        feed.set_sender(bad_sender)
        # Should not raise
        feed.emit(ErrorSeverity.CRITICAL, "test")
        # Error still recorded in-memory
        assert len(feed.get_recent()) == 1

    def test_emit_survives_bad_context(self, feed: ErrorFeed):
        # Should not raise even with unusual inputs
        feed.emit(ErrorSeverity.INFO, "test", context=None, source="")
        assert len(feed.get_recent()) == 1


# =============================================================================
# DB persistence
# =============================================================================


class TestDBPersistence:
    def test_emit_persists_to_db(self, db_feed: ErrorFeed, db_path: str):
        db_feed.emit(
            ErrorSeverity.ERROR,
            "db error",
            context={"key": "val"},
            source="test",
        )
        # Read directly from DB to verify
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM system_errors").fetchone()
        conn.close()
        assert row is not None
        assert row["severity"] == "error"
        assert row["message"] == "db error"
        assert row["source"] == "test"
        assert '"key"' in row["context"]

    def test_get_recent_reads_from_db(self, db_feed: ErrorFeed):
        db_feed.emit(ErrorSeverity.WARNING, "first")
        db_feed.emit(ErrorSeverity.ERROR, "second")

        # Create a separate feed pointing at the same DB to prove it reads from DB
        feed2 = ErrorFeed(db_path=db_feed._db_path)
        recent = feed2.get_recent()
        assert len(recent) == 2
        # Newest first
        assert recent[0].message == "second"
        assert recent[1].message == "first"

    def test_get_health_status_reads_from_db(self, db_feed: ErrorFeed):
        db_feed.emit(ErrorSeverity.INFO, "i1")
        db_feed.emit(ErrorSeverity.ERROR, "e1")
        db_feed.emit(ErrorSeverity.ERROR, "e2")

        # Separate feed, same DB
        feed2 = ErrorFeed(db_path=db_feed._db_path)
        status = feed2.get_health_status()
        assert status["info"] == 1
        assert status["error"] == 2
        assert status["warning"] == 0
        assert status["critical"] == 0

    def test_graceful_fallback_no_db(self, feed: ErrorFeed):
        """get_recent() returns in-memory data when db_path is None."""
        feed.emit(ErrorSeverity.INFO, "in-memory only")
        recent = feed.get_recent()
        assert len(recent) == 1
        assert recent[0].message == "in-memory only"

    def test_set_db_path_after_construction(self, db_path: str):
        feed = ErrorFeed()
        feed.emit(ErrorSeverity.INFO, "before db")
        # Set DB path later
        feed.set_db_path(db_path)
        feed.emit(ErrorSeverity.ERROR, "after db")

        # DB should only have the second error
        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT * FROM system_errors").fetchall()
        conn.close()
        assert len(rows) == 1

    def test_emit_survives_db_failure(self, tmp_path: Path):
        """emit() never raises even if DB write fails."""
        # Point at a path that won't have the table
        bad_db = str(tmp_path / "no_table.db")
        conn = sqlite3.connect(bad_db)
        conn.close()  # DB exists but no table

        feed = ErrorFeed(db_path=bad_db)
        # Should not raise
        feed.emit(ErrorSeverity.CRITICAL, "should not crash")
        # Error still in memory
        assert len(list(feed._recent)) == 1


# =============================================================================
# Module-level singleton
# =============================================================================


class TestModuleSingleton:
    def test_singleton_exists(self):
        from social_hook.error_feed import error_feed

        assert isinstance(error_feed, ErrorFeed)


# =============================================================================
# Component and run_id fields
# =============================================================================


class TestComponentRunId:
    def test_component_and_run_id_persisted(self, db_feed: ErrorFeed, db_path: str):
        db_feed.emit(
            ErrorSeverity.ERROR,
            "comp test",
            source="test",
            component="trigger",
            run_id="run_123",
        )
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM system_errors").fetchone()
        conn.close()
        assert row["component"] == "trigger"
        assert row["run_id"] == "run_123"

    def test_component_and_run_id_readable(self, db_feed: ErrorFeed):
        db_feed.emit(
            ErrorSeverity.WARNING,
            "readable test",
            component="scheduler",
            run_id="run_456",
        )
        recent = db_feed.get_recent()
        assert recent[0].component == "scheduler"
        assert recent[0].run_id == "run_456"

    def test_defaults_to_empty_string(self, db_feed: ErrorFeed, db_path: str):
        db_feed.emit(ErrorSeverity.INFO, "no component")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM system_errors").fetchone()
        conn.close()
        assert row["component"] == ""
        assert row["run_id"] == ""


# =============================================================================
# set_on_persist callback
# =============================================================================


class TestOnPersist:
    def test_callback_fires_after_db_write(self, db_feed: ErrorFeed):
        callback = MagicMock()
        db_feed.set_on_persist(callback)
        db_feed.emit(ErrorSeverity.ERROR, "persist test", component="web")

        callback.assert_called_once()
        args = callback.call_args[0]
        assert len(args[0]) == 36  # UUID
        assert args[1] == "error"
        assert args[2] == "web"

    def test_callback_not_called_without_db(self, feed: ErrorFeed):
        callback = MagicMock()
        feed.set_on_persist(callback)
        feed.emit(ErrorSeverity.ERROR, "no db")
        callback.assert_not_called()

    def test_callback_failure_does_not_break_emit(self, db_feed: ErrorFeed):
        def bad_callback(error_id, severity, component):
            raise RuntimeError("callback exploded")

        db_feed.set_on_persist(bad_callback)
        # Should not raise
        db_feed.emit(ErrorSeverity.CRITICAL, "survive callback failure")
        # Error still persisted
        recent = db_feed.get_recent()
        assert len(recent) == 1
        assert recent[0].message == "survive callback failure"


# =============================================================================
# Filter params in get_recent / _read_from_db
# =============================================================================


class TestFilterParams:
    def test_filter_by_severity(self, db_feed: ErrorFeed):
        db_feed.emit(ErrorSeverity.INFO, "info msg")
        db_feed.emit(ErrorSeverity.ERROR, "error msg")
        db_feed.emit(ErrorSeverity.WARNING, "warn msg")

        results = db_feed.get_recent(severity="error")
        assert len(results) == 1
        assert results[0].message == "error msg"

    def test_filter_by_component(self, db_feed: ErrorFeed):
        db_feed.emit(ErrorSeverity.ERROR, "trigger err", component="trigger")
        db_feed.emit(ErrorSeverity.ERROR, "web err", component="web")
        db_feed.emit(ErrorSeverity.ERROR, "trigger err2", component="trigger")

        results = db_feed.get_recent(component="trigger")
        assert len(results) == 2
        assert all(r.component == "trigger" for r in results)

    def test_filter_by_source(self, db_feed: ErrorFeed):
        db_feed.emit(ErrorSeverity.ERROR, "auth err", source="auth")
        db_feed.emit(ErrorSeverity.ERROR, "db err", source="database")

        results = db_feed.get_recent(source="auth")
        assert len(results) == 1
        assert results[0].source == "auth"

    def test_combined_filters(self, db_feed: ErrorFeed):
        db_feed.emit(ErrorSeverity.ERROR, "e1", component="trigger", source="auth")
        db_feed.emit(ErrorSeverity.WARNING, "w1", component="trigger", source="auth")
        db_feed.emit(ErrorSeverity.ERROR, "e2", component="web", source="auth")

        results = db_feed.get_recent(severity="error", component="trigger")
        assert len(results) == 1
        assert results[0].message == "e1"

    def test_no_filters_returns_all(self, db_feed: ErrorFeed):
        db_feed.emit(ErrorSeverity.INFO, "i1")
        db_feed.emit(ErrorSeverity.ERROR, "e1")
        results = db_feed.get_recent()
        assert len(results) == 2
