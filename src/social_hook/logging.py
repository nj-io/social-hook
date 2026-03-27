"""Unified logging pipeline — multi-sink LogBus on stdlib logging.

Reusable component: imports only constants.CONFIG_DIR_NAME (for default log_dir).
All sink dependencies are injected via constructor args or setup_logging() params.

Architecture:
    setup_logging(component) attaches LogBus to logging.getLogger("social_hook")
        LogBus fans out LogRecords to registered sinks:
        - FileSink       -> JSON lines -> ~/.social-hook/logs/<component>.log
        - DbSink         -> WARNING+   -> ErrorFeed.emit() -> system_errors table
        - NotificationSink -> ERROR/CRITICAL -> callback -> notifications
        - ConsoleSink    -> ERROR+     -> stderr
"""

from __future__ import annotations

import json
import logging
import re
import sys
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING, Any

from social_hook.constants import CONFIG_DIR_NAME

if TYPE_CHECKING:
    from social_hook.error_feed import ErrorFeed

# ---------------------------------------------------------------------------
# Thread-local context for component / run_id injection
# ---------------------------------------------------------------------------

_context = threading.local()


def set_run_id(run_id: str) -> None:
    """Set the run_id for the current thread. Propagates to all subsequent log records."""
    _context.run_id = run_id


# ---------------------------------------------------------------------------
# ContextFilter — injects component + run_id into every record
# ---------------------------------------------------------------------------


class ContextFilter(logging.Filter):
    """Inject component and run_id from threading.local into every LogRecord.

    threading.local is used instead of contextvars because contextvars don't
    propagate to child threads on Python 3.10/3.11.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.component = getattr(_context, "component", "unknown")  # type: ignore[attr-defined]
        record.run_id = getattr(_context, "run_id", "")  # type: ignore[attr-defined]
        return True


# ---------------------------------------------------------------------------
# JsonFormatter — structured JSON log lines
# ---------------------------------------------------------------------------


class JsonFormatter(logging.Formatter):
    """Format log records as JSON."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "component": getattr(record, "component", "unknown"),
            "run_id": getattr(record, "run_id", ""),
            "message": record.getMessage(),
        }

        # Add extra fields from record
        for key in ("event", "project_id", "decision", "draft_id"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


# ---------------------------------------------------------------------------
# ComponentLogger — adapter that merges extra kwargs
# ---------------------------------------------------------------------------


class ComponentLogger(logging.LoggerAdapter):
    """Logger adapter that includes component name and extra fields."""

    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:  # type: ignore[override]
        extra = kwargs.get("extra", {})
        for key in list(kwargs.keys()):
            if key not in ("exc_info", "stack_info", "stacklevel", "extra"):
                extra[key] = kwargs.pop(key)
        kwargs["extra"] = {**(self.extra or {}), **extra}  # type: ignore[arg-type]
        return msg, kwargs


# ---------------------------------------------------------------------------
# Sinks
# ---------------------------------------------------------------------------


class FileSink:
    """JSON file sink with timed rotation (30-day, midnight UTC)."""

    def __init__(self, log_dir: Path, component: str) -> None:
        log_dir.mkdir(parents=True, exist_ok=True)
        self._handler = TimedRotatingFileHandler(
            log_dir / f"{component}.log",
            when="midnight",
            backupCount=30,
            utc=True,
        )
        self._handler.setFormatter(JsonFormatter())

    def handle(self, record: logging.LogRecord) -> None:
        self._handler.emit(record)

    def close(self) -> None:
        self._handler.close()


class DbSink:
    """Routes WARNING+ records to ErrorFeed.emit() for DB persistence.

    Maps logging levels to ErrorSeverity. Extracts context fields from
    the record's extra dict.
    """

    # logging.WARNING=30, ERROR=40, CRITICAL=50
    _LEVEL_MAP: dict[int, str] = {
        logging.WARNING: "warning",
        logging.ERROR: "error",
        logging.CRITICAL: "critical",
    }

    def __init__(self, error_feed: ErrorFeed) -> None:
        self._error_feed = error_feed
        # Re-entrancy guard: ErrorFeed.emit() logs warnings on failure via
        # logger.warning(), which flows back through LogBus → DbSink → emit().
        # Without this guard, that creates infinite recursion.
        self._in_emit = threading.local()

    def handle(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.WARNING:
            return
        if getattr(self._in_emit, "active", False):
            return  # prevent recursion

        self._in_emit.active = True
        try:
            severity_str = self._LEVEL_MAP.get(record.levelno, "error")

            # Extract context from record's extra dict
            context: dict[str, Any] = {}
            for key in ("project_id", "draft_id"):
                val = getattr(record, key, None)
                if val is not None:
                    context[key] = val

            component = getattr(record, "component", "")
            run_id = getattr(record, "run_id", "")

            # Pass severity as string — ErrorFeed.emit() accepts str | ErrorSeverity.
            # This avoids a runtime import from social_hook.error_feed, preserving
            # logging.py's reusability (only imports constants.CONFIG_DIR_NAME).
            self._error_feed.emit(
                severity_str,
                record.getMessage(),
                context=context,
                source=getattr(record, "name", ""),
                component=component,
                run_id=run_id,
            )
        finally:
            self._in_emit.active = False


# Markdown special chars that cause Telegram parse_mode=markdown failures
_MD_ESCAPE_RE = re.compile(r"([_*\[\]()~`>#+\-=|{}.!\\])")


class NotificationSink:
    """Routes ERROR/CRITICAL to a notification callback.

    Pre-escapes Markdown special chars to avoid Telegram parse failures.
    """

    def __init__(self, sender_callback: Callable[[str, str], None]) -> None:
        self._sender = sender_callback

    def handle(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.ERROR:
            return

        severity_str = record.levelname
        source = getattr(record, "name", "")
        message = record.getMessage()
        formatted = f"[{severity_str}] ({source}) {message}"
        # Escape markdown special chars
        safe_message = _MD_ESCAPE_RE.sub(r"\\\1", formatted)
        self._sender(severity_str.lower(), safe_message)


class ConsoleSink:
    """Routes ERROR+ to stderr with human-readable format."""

    def __init__(self) -> None:
        self._handler = logging.StreamHandler(sys.stderr)
        self._handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )

    def handle(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.ERROR:
            return
        self._handler.emit(record)

    def close(self) -> None:
        self._handler.close()


# ---------------------------------------------------------------------------
# LogBus — fans out records to registered sinks
# ---------------------------------------------------------------------------


class LogBus(logging.Handler):
    """Handler that fans out LogRecords to registered sinks.

    Overrides handle() instead of emit() to avoid holding the handler's
    lock during slow sink I/O (DB writes, HTTP notifications). Per-sink
    exceptions are caught — one failing sink never breaks others.
    """

    def __init__(self) -> None:
        super().__init__()
        self.sinks: list[Any] = []

    def handle(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        if record.levelno < self.level:
            return False
        # Apply filters (including ContextFilter)
        if not self.filter(record):
            return False
        for sink in self.sinks:
            try:
                sink.handle(record)
            except Exception as exc:
                # Can't use logger here (infinite recursion). Write to stderr.
                print(f"LogBus: sink {type(sink).__name__} failed: {exc}", file=sys.stderr)
        return True

    def emit(self, record: logging.LogRecord) -> None:
        # Not used — handle() does the work directly
        pass


# ---------------------------------------------------------------------------
# setup_logging — idempotent entry point
# ---------------------------------------------------------------------------


def setup_logging(
    component: str,
    *,
    notification_sender: Callable[[str, str], None] | None = None,
    error_feed: ErrorFeed | None = None,
    console: bool = True,
    level: int = logging.INFO,
    log_dir: str | Path | None = None,
) -> ComponentLogger:
    """Set up the unified logging pipeline for a component.

    Attaches LogBus to logging.getLogger("social_hook") with configured sinks.
    Idempotent — skips if LogBus is already attached.

    Args:
        component: Component name (e.g., "trigger", "scheduler", "bot")
        notification_sender: Callback(severity_str, message) for ERROR/CRITICAL
        error_feed: ErrorFeed instance for DB persistence (WARNING+)
        console: Whether to add ConsoleSink (ERROR+ to stderr)
        level: Logging level for the social_hook namespace
        log_dir: Log directory (default: ~/.social-hook/logs/)

    Returns:
        ComponentLogger wrapping social_hook.<component>
    """
    # Set component in threading.local for ContextFilter
    _context.component = component

    root_logger = logging.getLogger("social_hook")

    # Idempotent: skip if LogBus already attached
    for handler in root_logger.handlers:
        if isinstance(handler, LogBus):
            return ComponentLogger(
                logging.getLogger(f"social_hook.{component}"),
                {"component": component},
            )

    root_logger.setLevel(level)

    # Resolve log directory
    resolved_log_dir = (
        Path(log_dir) if log_dir is not None else Path.home() / CONFIG_DIR_NAME / "logs"
    )

    # Build LogBus with sinks
    bus = LogBus()

    # ContextFilter on the handler so it runs for propagated records too
    bus.addFilter(ContextFilter())

    # FileSink — always
    bus.sinks.append(FileSink(resolved_log_dir, component))

    # DbSink — if error_feed provided
    if error_feed is not None:
        bus.sinks.append(DbSink(error_feed))

    # NotificationSink — if sender provided
    if notification_sender is not None:
        bus.sinks.append(NotificationSink(notification_sender))

    # ConsoleSink — if requested
    if console:
        bus.sinks.append(ConsoleSink())

    root_logger.addHandler(bus)

    return ComponentLogger(
        logging.getLogger(f"social_hook.{component}"),
        {"component": component},
    )


def get_logger(component: str) -> ComponentLogger:
    """Get an existing logger for a component.

    Convenience function for getting a logger that was
    previously set up with setup_logging().
    """
    logger = logging.getLogger(f"social_hook.{component}")
    return ComponentLogger(logger, {"component": component})
