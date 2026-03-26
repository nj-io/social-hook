"""System error feed — severity-leveled notifications.

Reusable component: follows messaging layer pattern.
Consumes MessagingAdapter to send notifications.
Zero social-hook domain logic.
"""

import json
import logging
import sqlite3
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class SystemError:
    severity: ErrorSeverity
    message: str
    context: dict = field(default_factory=dict)
    source: str = ""
    component: str = ""
    run_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ErrorFeed:
    """System-level error feed with severity routing.

    CRITICAL and ERROR always route to notifications regardless
    of notification_level. WARNING and INFO respect the setting.

    Read-only for operators — no acknowledge/dismiss/retry.

    DB-backed: all errors are persisted to the ``system_errors`` table
    so all processes (scheduler daemon, CLI, web server) can read
    from the same source. The in-memory deque is a fast cache for
    the current process; the DB is the source of truth.
    """

    def __init__(self, db_path: str | None = None, max_recent: int = 100):
        self._db_path = db_path
        self._max_recent = max_recent
        self._recent: deque[SystemError] = deque(maxlen=max_recent)
        self._send_callback: Callable[[str, str], None] | None = None
        self._on_persist_callback: Callable[[str, str, str], None] | None = None

    def set_db_path(self, db_path: str) -> None:
        """Set or update the DB path after construction.

        Called at startup when db_path is known (e.g., from get_db_path()).
        """
        self._db_path = db_path

    def set_sender(self, callback: Callable[[str, str], None]) -> None:
        """Set the notification sender (called with severity, formatted_message)."""
        self._send_callback = callback

    def set_on_persist(self, callback: Callable[[str, str, str], None]) -> None:
        """Set callback fired after DB write: (error_id, severity, component)."""
        self._on_persist_callback = callback

    def emit(
        self,
        severity: ErrorSeverity | str,
        message: str,
        context: dict | None = None,
        source: str = "",
        component: str = "",
        run_id: str = "",
    ) -> None:
        """Emit an error. Never raises — errors in the error feed are logged.

        Writes to both the in-memory deque (fast cache) and the
        system_errors DB table (cross-process persistence).
        """
        try:
            if isinstance(severity, str):
                severity = ErrorSeverity(severity)
            ctx = context or {}
            error = SystemError(
                severity=severity,
                message=message,
                context=ctx,
                source=source,
                component=component,
                run_id=run_id,
            )
            self._recent.append(error)

            # Persist to DB if available
            if self._db_path is not None:
                self._write_to_db(error)

            # CRITICAL and ERROR always route to notifications
            if (
                severity in (ErrorSeverity.CRITICAL, ErrorSeverity.ERROR)
                and self._send_callback is not None
            ):
                try:
                    formatted = self._format_message(error)
                    self._send_callback(severity.value, formatted)
                except Exception:
                    logger.warning(
                        "Error feed sender callback failed",
                        exc_info=True,
                    )
        except Exception:
            logger.warning(
                "Error feed emit failed for %s: %s",
                severity.value if isinstance(severity, ErrorSeverity) else severity,
                message,
                exc_info=True,
            )

    def get_recent(
        self,
        limit: int = 50,
        *,
        severity: str | None = None,
        component: str | None = None,
        source: str | None = None,
    ) -> list[SystemError]:
        """Return recent errors, newest first.

        Reads from the system_errors DB table (source of truth).
        Falls back to in-memory deque if db_path is not set.
        Optional filters narrow the result set (DB path only).
        """
        if self._db_path is not None:
            try:
                return self._read_from_db(
                    limit, severity=severity, component=component, source=source
                )
            except Exception:
                logger.warning(
                    "Error feed DB read failed, falling back to in-memory",
                    exc_info=True,
                )

        # In-memory fallback (newest first)
        items = list(self._recent)
        items.reverse()
        return items[:limit]

    def get_health_status(self) -> dict:
        """Return error counts by severity in last 24h.

        Reads from DB when db_path is set.
        Falls back to in-memory computation if db_path is not set.
        """
        if self._db_path is not None:
            try:
                return self._health_from_db()
            except Exception:
                logger.warning(
                    "Error feed DB health query failed, falling back to in-memory",
                    exc_info=True,
                )

        # In-memory fallback
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        counts: dict[str, int] = {}
        for sev in ErrorSeverity:
            counts[sev.value] = 0
        for error in self._recent:
            if error.timestamp >= cutoff:
                counts[error.severity.value] = counts.get(error.severity.value, 0) + 1
        return counts

    def _format_message(self, error: SystemError) -> str:
        """Format an error for notification display."""
        parts = [f"[{error.severity.value.upper()}]"]
        if error.source:
            parts.append(f"({error.source})")
        parts.append(error.message)
        return " ".join(parts)

    def _write_to_db(self, error: SystemError) -> None:
        """Persist a SystemError to the system_errors table."""
        assert self._db_path is not None
        error_id = str(uuid.uuid4())
        conn = sqlite3.connect(self._db_path, timeout=5)
        try:
            conn.execute(
                """INSERT INTO system_errors
                   (id, severity, message, context, source, component, run_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    error_id,
                    error.severity.value,
                    error.message,
                    json.dumps(error.context),
                    error.source,
                    error.component,
                    error.run_id,
                    error.timestamp.strftime("%Y-%m-%d %H:%M:%S.%f"),
                ),
            )
            conn.commit()
        finally:
            conn.close()

        # Fire on_persist callback after commit (never raises)
        if self._on_persist_callback is not None:
            try:
                self._on_persist_callback(error_id, error.severity.value, error.component)
            except Exception:
                logger.warning("on_persist callback failed", exc_info=True)

    def _read_from_db(
        self,
        limit: int,
        *,
        severity: str | None = None,
        component: str | None = None,
        source: str | None = None,
    ) -> list[SystemError]:
        """Read recent errors from the system_errors table.

        Optional filters narrow the result set.
        """
        assert self._db_path is not None
        conn = sqlite3.connect(self._db_path, timeout=5)
        try:
            conn.row_factory = sqlite3.Row
            query = "SELECT severity, message, context, source, component, run_id, created_at FROM system_errors"
            conditions: list[str] = []
            params: list[Any] = []
            if severity is not None:
                conditions.append("severity = ?")
                params.append(severity)
            if component is not None:
                conditions.append("component = ?")
                params.append(component)
            if source is not None:
                conditions.append("source = ?")
                params.append(source)
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            results: list[SystemError] = []
            for row in rows:
                try:
                    ctx = json.loads(row["context"]) if row["context"] else {}
                except (json.JSONDecodeError, TypeError):
                    ctx = {}
                ts_str = row["created_at"]
                try:
                    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
                        try:
                            ts = datetime.strptime(ts_str, fmt).replace(tzinfo=timezone.utc)
                            break
                        except ValueError:
                            continue
                    else:
                        ts = datetime.now(timezone.utc)
                except TypeError:
                    ts = datetime.now(timezone.utc)
                results.append(
                    SystemError(
                        severity=ErrorSeverity(row["severity"]),
                        message=row["message"],
                        context=ctx,
                        source=row["source"] or "",
                        component=row["component"] or "",
                        run_id=row["run_id"] or "",
                        timestamp=ts,
                    )
                )
            return results
        finally:
            conn.close()

    def _health_from_db(self) -> dict:
        """Query error counts by severity in last 24h from DB."""
        assert self._db_path is not None
        conn = sqlite3.connect(self._db_path, timeout=5)
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime(
                "%Y-%m-%d %H:%M:%S.%f"
            )
            rows = conn.execute(
                """SELECT severity, COUNT(*) as cnt
                   FROM system_errors
                   WHERE created_at >= ?
                   GROUP BY severity""",
                (cutoff,),
            ).fetchall()
            counts: dict[str, int] = {}
            for sev in ErrorSeverity:
                counts[sev.value] = 0
            for row in rows:
                counts[row[0]] = row[1]
            return counts
        finally:
            conn.close()


# Module-level singleton — db_path set at startup via set_db_path()
error_feed = ErrorFeed()

# Wiring guard — set_db_path/set_sender once per process
_error_feed_wired = False


def ensure_error_feed(config, db_path: str) -> None:
    """Wire the error feed singleton once per process.

    Safe to call repeatedly — only the first call takes effect.
    """
    global _error_feed_wired
    if _error_feed_wired:
        return
    from social_hook.notifications import send_notification

    error_feed.set_db_path(db_path)
    error_feed.set_sender(lambda sev, msg: send_notification(config, f"[{sev}] {msg}"))
    _error_feed_wired = True
