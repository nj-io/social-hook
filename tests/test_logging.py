"""Tests for the unified logging pipeline (LogBus, sinks, setup_logging)."""

import contextlib
import json
import logging
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from social_hook.logging import (
    ComponentLogger,
    ConsoleSink,
    ContextFilter,
    DbSink,
    FileSink,
    LogBus,
    NotificationSink,
    _context,
    set_run_id,
    setup_logging,
)


@pytest.fixture(autouse=True)
def _clean_loggers():
    """Remove LogBus handlers from social_hook logger after each test."""
    yield
    root = logging.getLogger("social_hook")
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        if hasattr(handler, "close"):
            handler.close()
    for f in root.filters[:]:
        root.removeFilter(f)
    for attr in ("component", "run_id"):
        with contextlib.suppress(AttributeError):
            delattr(_context, attr)


# =============================================================================
# LogBus routing
# =============================================================================


class TestLogBus:
    def test_routes_records_to_all_sinks(self):
        bus = LogBus()
        sink_a = MagicMock()
        sink_b = MagicMock()
        bus.sinks = [sink_a, sink_b]
        bus.addFilter(ContextFilter())

        record = logging.LogRecord("test", logging.ERROR, "", 0, "test message", (), None)
        bus.handle(record)

        sink_a.handle.assert_called_once_with(record)
        sink_b.handle.assert_called_once_with(record)

    def test_exception_isolation(self):
        """A failing sink does NOT prevent other sinks from receiving the record."""
        bus = LogBus()
        failing_sink = MagicMock()
        failing_sink.handle.side_effect = PermissionError("disk full")
        good_sink = MagicMock()
        bus.sinks = [failing_sink, good_sink]
        bus.addFilter(ContextFilter())

        record = logging.LogRecord("test", logging.ERROR, "", 0, "test message", (), None)
        bus.handle(record)

        failing_sink.handle.assert_called_once()
        good_sink.handle.assert_called_once_with(record)

    def test_level_filtering(self):
        bus = LogBus()
        bus.setLevel(logging.WARNING)
        sink = MagicMock()
        bus.sinks = [sink]
        bus.addFilter(ContextFilter())

        info_record = logging.LogRecord("test", logging.INFO, "", 0, "info", (), None)
        warn_record = logging.LogRecord("test", logging.WARNING, "", 0, "warn", (), None)
        bus.handle(info_record)
        bus.handle(warn_record)

        # Only WARNING should pass
        assert sink.handle.call_count == 1
        assert sink.handle.call_args[0][0] == warn_record


# =============================================================================
# FileSink
# =============================================================================


class TestFileSink:
    def test_writes_json_lines(self, tmp_path: Path):
        sink = FileSink(tmp_path, "test_component")
        record = logging.LogRecord("social_hook.test", logging.INFO, "", 0, "hello world", (), None)
        record.component = "test_component"  # type: ignore[attr-defined]
        record.run_id = "run_123"  # type: ignore[attr-defined]
        sink.handle(record)
        sink.close()

        log_file = tmp_path / "test_component.log"
        assert log_file.exists()
        line = log_file.read_text().strip()
        data = json.loads(line)
        assert data["level"] == "INFO"
        assert data["message"] == "hello world"
        assert data["component"] == "test_component"
        assert data["run_id"] == "run_123"
        assert "timestamp" in data


# =============================================================================
# DbSink
# =============================================================================


class TestDbSink:
    def test_calls_error_feed_for_warning_plus(self):
        mock_feed = MagicMock()
        sink = DbSink(mock_feed)

        record = logging.LogRecord(
            "social_hook.trigger", logging.WARNING, "", 0, "warn msg", (), None
        )
        record.component = "trigger"  # type: ignore[attr-defined]
        record.run_id = "run_1"  # type: ignore[attr-defined]
        sink.handle(record)

        mock_feed.emit.assert_called_once()
        call_kwargs = mock_feed.emit.call_args
        assert call_kwargs[0][0] == "warning"
        assert call_kwargs[0][1] == "warn msg"
        assert call_kwargs[1]["component"] == "trigger"
        assert call_kwargs[1]["run_id"] == "run_1"

    def test_skips_info_level(self):
        mock_feed = MagicMock()
        sink = DbSink(mock_feed)

        record = logging.LogRecord("social_hook.test", logging.INFO, "", 0, "info msg", (), None)
        sink.handle(record)
        mock_feed.emit.assert_not_called()

    def test_maps_error_severity(self):
        mock_feed = MagicMock()
        sink = DbSink(mock_feed)

        record = logging.LogRecord("social_hook.test", logging.ERROR, "", 0, "err", (), None)
        record.component = ""  # type: ignore[attr-defined]
        record.run_id = ""  # type: ignore[attr-defined]
        sink.handle(record)

        assert mock_feed.emit.call_args[0][0] == "error"

    def test_maps_critical_severity(self):
        mock_feed = MagicMock()
        sink = DbSink(mock_feed)

        record = logging.LogRecord("social_hook.test", logging.CRITICAL, "", 0, "crit", (), None)
        record.component = ""  # type: ignore[attr-defined]
        record.run_id = ""  # type: ignore[attr-defined]
        sink.handle(record)

        assert mock_feed.emit.call_args[0][0] == "critical"

    def test_extracts_context_fields(self):
        mock_feed = MagicMock()
        sink = DbSink(mock_feed)

        record = logging.LogRecord("social_hook.test", logging.ERROR, "", 0, "err", (), None)
        record.component = "trigger"  # type: ignore[attr-defined]
        record.run_id = "run_1"  # type: ignore[attr-defined]
        record.project_id = "proj_123"  # type: ignore[attr-defined]
        record.draft_id = "draft_456"  # type: ignore[attr-defined]
        sink.handle(record)

        call_kwargs = mock_feed.emit.call_args[1]
        assert call_kwargs["context"] == {"project_id": "proj_123", "draft_id": "draft_456"}

    def test_reentrant_guard_prevents_recursion(self):
        """If ErrorFeed.emit() fails and logs a warning, DbSink must not recurse."""
        mock_feed = MagicMock()
        sink = DbSink(mock_feed)

        # Simulate ErrorFeed.emit() failing — this would normally trigger
        # logger.warning() inside error_feed.py, which flows back through
        # LogBus → DbSink. The guard should prevent the second call.
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Simulate re-entry: another WARNING record arrives while we're in emit
                reentrant_record = logging.LogRecord(
                    "social_hook.error_feed", logging.WARNING, "", 0, "emit failed", (), None
                )
                reentrant_record.component = ""  # type: ignore[attr-defined]
                reentrant_record.run_id = ""  # type: ignore[attr-defined]
                sink.handle(reentrant_record)

        mock_feed.emit.side_effect = side_effect

        record = logging.LogRecord("social_hook.test", logging.WARNING, "", 0, "original", (), None)
        record.component = ""  # type: ignore[attr-defined]
        record.run_id = ""  # type: ignore[attr-defined]
        sink.handle(record)

        # Only the first call should go through — the reentrant one is dropped
        assert call_count == 1


# =============================================================================
# NotificationSink
# =============================================================================


class TestNotificationSink:
    def test_fires_for_error(self):
        callback = MagicMock()
        sink = NotificationSink(callback)

        record = logging.LogRecord("social_hook.test", logging.ERROR, "", 0, "error msg", (), None)
        record.name = "social_hook.test"
        sink.handle(record)
        callback.assert_called_once()
        args = callback.call_args[0]
        assert args[0] == "error"
        assert "error msg" in args[1]

    def test_fires_for_critical(self):
        callback = MagicMock()
        sink = NotificationSink(callback)

        record = logging.LogRecord(
            "social_hook.test", logging.CRITICAL, "", 0, "crit msg", (), None
        )
        sink.handle(record)
        callback.assert_called_once()
        assert callback.call_args[0][0] == "critical"

    def test_skips_warning(self):
        callback = MagicMock()
        sink = NotificationSink(callback)

        record = logging.LogRecord("social_hook.test", logging.WARNING, "", 0, "warn", (), None)
        sink.handle(record)
        callback.assert_not_called()

    def test_skips_info(self):
        callback = MagicMock()
        sink = NotificationSink(callback)

        record = logging.LogRecord("social_hook.test", logging.INFO, "", 0, "info", (), None)
        sink.handle(record)
        callback.assert_not_called()

    def test_escapes_markdown_special_chars(self):
        callback = MagicMock()
        sink = NotificationSink(callback)

        record = logging.LogRecord(
            "social_hook.test", logging.ERROR, "", 0, "error with _under_ and *bold*", (), None
        )
        sink.handle(record)
        msg = callback.call_args[0][1]
        assert "\\_under\\_" in msg
        assert "\\*bold\\*" in msg


# =============================================================================
# ConsoleSink
# =============================================================================


class TestConsoleSink:
    def test_writes_to_stderr_for_error(self):
        sink = ConsoleSink()
        record = logging.LogRecord("social_hook.test", logging.ERROR, "", 0, "stderr msg", (), None)
        with patch.object(sys, "stderr", new_callable=StringIO) as mock_stderr:
            # Re-create handler with the mocked stderr
            sink._handler = logging.StreamHandler(mock_stderr)
            sink._handler.setFormatter(
                logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
            )
            sink.handle(record)
            output = mock_stderr.getvalue()
            assert "stderr msg" in output
            assert "ERROR" in output

    def test_skips_warning(self):
        sink = ConsoleSink()
        record = logging.LogRecord("social_hook.test", logging.WARNING, "", 0, "warn", (), None)
        with patch.object(sys, "stderr", new_callable=StringIO) as mock_stderr:
            sink._handler = logging.StreamHandler(mock_stderr)
            sink.handle(record)
            assert mock_stderr.getvalue() == ""


# =============================================================================
# ContextFilter
# =============================================================================


class TestContextFilter:
    def test_injects_component_and_run_id(self):
        _context.component = "trigger"
        _context.run_id = "run_abc"
        cf = ContextFilter()

        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        result = cf.filter(record)
        assert result is True
        assert record.component == "trigger"  # type: ignore[attr-defined]
        assert record.run_id == "run_abc"  # type: ignore[attr-defined]

    def test_defaults_when_not_set(self):
        cf = ContextFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        cf.filter(record)
        assert record.component == "unknown"  # type: ignore[attr-defined]
        assert record.run_id == ""  # type: ignore[attr-defined]


# =============================================================================
# set_run_id
# =============================================================================


class TestSetRunId:
    def test_propagates_to_records(self):
        set_run_id("run_xyz")
        cf = ContextFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        cf.filter(record)
        assert record.run_id == "run_xyz"  # type: ignore[attr-defined]


# =============================================================================
# setup_logging
# =============================================================================


class TestSetupLogging:
    def test_returns_component_logger(self, tmp_path: Path):
        logger = setup_logging("test", log_dir=tmp_path)
        assert isinstance(logger, ComponentLogger)

    def test_idempotent(self, tmp_path: Path):
        setup_logging("test", log_dir=tmp_path)
        setup_logging("test2", log_dir=tmp_path)

        root = logging.getLogger("social_hook")
        bus_count = sum(1 for h in root.handlers if isinstance(h, LogBus))
        assert bus_count == 1

    def test_creates_file_sink(self, tmp_path: Path):
        logger = setup_logging("mycomp", log_dir=tmp_path)
        logger.info("test message")

        log_file = tmp_path / "mycomp.log"
        assert log_file.exists()
        content = log_file.read_text().strip()
        data = json.loads(content)
        assert data["message"] == "test message"
        assert data["component"] == "mycomp"

    def test_wires_db_sink_when_error_feed_provided(self, tmp_path: Path):
        mock_feed = MagicMock()
        logger = setup_logging("test", log_dir=tmp_path, error_feed=mock_feed)
        logger.warning("db test")

        mock_feed.emit.assert_called_once()

    def test_no_db_sink_without_error_feed(self, tmp_path: Path):
        setup_logging("test", log_dir=tmp_path)

        root = logging.getLogger("social_hook")
        bus = next(h for h in root.handlers if isinstance(h, LogBus))
        db_sinks = [s for s in bus.sinks if isinstance(s, DbSink)]
        assert len(db_sinks) == 0

    def test_wires_notification_sink(self, tmp_path: Path):
        callback = MagicMock()
        logger = setup_logging("test", log_dir=tmp_path, notification_sender=callback)
        logger.error("notify test")

        callback.assert_called_once()

    def test_console_sink_added_by_default(self, tmp_path: Path):
        setup_logging("test", log_dir=tmp_path)

        root = logging.getLogger("social_hook")
        bus = next(h for h in root.handlers if isinstance(h, LogBus))
        console_sinks = [s for s in bus.sinks if isinstance(s, ConsoleSink)]
        assert len(console_sinks) == 1

    def test_no_console_sink_when_disabled(self, tmp_path: Path):
        setup_logging("test", log_dir=tmp_path, console=False)

        root = logging.getLogger("social_hook")
        bus = next(h for h in root.handlers if isinstance(h, LogBus))
        console_sinks = [s for s in bus.sinks if isinstance(s, ConsoleSink)]
        assert len(console_sinks) == 0

    def test_context_filter_sets_component(self, tmp_path: Path):
        logger = setup_logging("mycomp", log_dir=tmp_path)
        logger.info("ctx test")

        log_file = tmp_path / "mycomp.log"
        data = json.loads(log_file.read_text().strip())
        assert data["component"] == "mycomp"

    def test_run_id_propagates(self, tmp_path: Path):
        logger = setup_logging("test", log_dir=tmp_path)
        set_run_id("run_999")
        logger.info("run test")

        log_file = tmp_path / "test.log"
        data = json.loads(log_file.read_text().strip())
        assert data["run_id"] == "run_999"
