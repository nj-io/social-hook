"""JSON logging setup for social-hook."""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class JsonFormatter(logging.Formatter):
    """Format log records as JSON."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "component": getattr(record, "component", "unknown"),
            "message": record.getMessage(),
        }

        # Add extra fields from record
        if hasattr(record, "event"):
            log_entry["event"] = record.event
        if hasattr(record, "project_id"):
            log_entry["project_id"] = record.project_id
        if hasattr(record, "decision"):
            log_entry["decision"] = record.decision
        if hasattr(record, "draft_id"):
            log_entry["draft_id"] = record.draft_id

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


class ComponentLogger(logging.LoggerAdapter):
    """Logger adapter that includes component name and extra fields."""

    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        # Move extra kwargs to the extra dict
        extra = kwargs.get("extra", {})
        for key in list(kwargs.keys()):
            if key not in ("exc_info", "stack_info", "stacklevel", "extra"):
                extra[key] = kwargs.pop(key)
        kwargs["extra"] = {**self.extra, **extra}
        return msg, kwargs


def setup_logging(
    component: str,
    level: int = logging.INFO,
    log_dir: Optional[str | Path] = None,
    force_new: bool = False,
) -> ComponentLogger:
    """Set up JSON logging for a component.

    Args:
        component: Component name (e.g., "trigger", "scheduler", "bot")
        level: Logging level (default: INFO)
        log_dir: Log directory (default: ~/.social-hook/logs/)
        force_new: If True, clear existing handlers and create new ones

    Returns:
        Logger configured for JSON output to component-specific file
    """
    if log_dir is None:
        log_dir = Path.home() / ".social-hook" / "logs"
    else:
        log_dir = Path(log_dir)

    # Ensure log directory exists
    log_dir.mkdir(parents=True, exist_ok=True)

    # Get or create logger for this component
    logger = logging.getLogger(f"social_hook.{component}")
    logger.setLevel(level)

    # Clear existing handlers if force_new or if log_dir changed
    log_file = log_dir / f"{component}.log"
    needs_setup = force_new or not logger.handlers

    if not needs_setup:
        # Check if any existing file handler points to a different directory
        for handler in logger.handlers:
            if isinstance(handler, logging.FileHandler):
                if Path(handler.baseFilename) != log_file:
                    needs_setup = True
                    break

    if needs_setup:
        # Clear existing handlers
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)

        # File handler for component-specific log
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(JsonFormatter())
        logger.addHandler(file_handler)

        # Also log errors to stderr for visibility
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(logging.ERROR)
        stderr_handler.setFormatter(JsonFormatter())
        logger.addHandler(stderr_handler)

    return ComponentLogger(logger, {"component": component})


def get_logger(component: str) -> ComponentLogger:
    """Get an existing logger for a component.

    This is a convenience function for getting a logger that was
    previously set up with setup_logging().
    """
    logger = logging.getLogger(f"social_hook.{component}")
    return ComponentLogger(logger, {"component": component})
