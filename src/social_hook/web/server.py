"""FastAPI API server for the web dashboard."""

import asyncio
import json
import logging
import re
import sqlite3
import subprocess
import threading
import time
import uuid as _uuid
from collections.abc import Callable
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

import yaml
from fastapi import Body, FastAPI, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from starlette.websockets import WebSocket, WebSocketDisconnect

from social_hook import __version__
from social_hook.config.env import KEY_GROUPS, KNOWN_KEYS
from social_hook.config.project import DEFAULT_MEDIA_GUIDANCE
from social_hook.config.yaml import KNOWN_CHANNELS, Config
from social_hook.constants import CONFIG_DIR_NAME, PROJECT_DESCRIPTION, PROJECT_NAME, PROJECT_SLUG
from social_hook.db import operations as ops
from social_hook.db.connection import init_database
from social_hook.errors import ConfigError
from social_hook.filesystem import get_config_path, get_db_path, get_env_path, get_narratives_path
from social_hook.messaging.base import CallbackEvent, InboundMessage
from social_hook.messaging.gateway import GatewayEnvelope, GatewayHub
from social_hook.models import EDITABLE_STATUSES, PENDING_STATUSES, TERMINAL_STATUSES, PipelineStage
from social_hook.parsing import check_unknown_keys, safe_json_loads

logger = logging.getLogger(__name__)

# Background task staleness thresholds
_STALE_TASK_TIMEOUT_SECONDS = 600  # 10 min; longest expected task is ~5 min (LLM subprocess)
_STALE_CHECK_INTERVAL_TICKS = 60  # every 60 bridge-loop ticks (60 × 0.5s = 30s)


def _parse_episode_tags(decision) -> list | None:
    """Parse episode_tags from a Decision, handling both list and JSON-string forms.

    Returns a list (possibly empty), or None if the decision has no tags.
    """
    if decision is None:
        return None
    ep_tags = decision.episode_tags
    if isinstance(ep_tags, str):
        ep_tags = safe_json_loads(ep_tags, "decision.episode_tags", default=[])
    return ep_tags or None


# ---------------------------------------------------------------------------
# WebSocket gateway
# ---------------------------------------------------------------------------

_hub = GatewayHub()
_restore_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    # Ensure DB schema exists before any endpoint or bridge loop runs.
    # Safe on existing DBs (CREATE TABLE IF NOT EXISTS), required on fresh installs.
    db_path = get_db_path()
    init_database(db_path)
    _cleanup_stale_tasks(db_path)

    # Unified logging pipeline — replaces ensure_error_feed()
    from social_hook.error_feed import error_feed
    from social_hook.logging import setup_logging

    try:
        config = _get_config()
        error_feed.set_db_path(str(db_path))
        # Build notification sender
        sender: Callable | None = None
        try:
            from social_hook.notifications import send_notification

            # NotificationSink already formats as "[SEVERITY] (source) message"
            def _send_notification(_sev: str, msg: str) -> None:
                send_notification(config, msg)

            sender = _send_notification
        except Exception:
            pass
        setup_logging("web", error_feed=error_feed, notification_sender=sender, console=False)
    except Exception:
        logger.debug("Logging init failed (non-fatal)", exc_info=True)

    # Wire on_persist callback for WebSocket live updates (fire-and-forget).
    # Bounded to 10 concurrent threads to avoid storms.
    _persist_semaphore = threading.Semaphore(10)

    def _on_error_persisted(error_id, severity, component):
        if not _persist_semaphore.acquire(blocking=False):
            return  # drop under storm conditions

        def _emit():
            try:
                conn = sqlite3.connect(str(db_path), timeout=2)
                conn.row_factory = sqlite3.Row
                try:
                    ops.emit_data_event(
                        conn,
                        "system_error",
                        "created",
                        error_id,
                        extra={"severity": severity, "component": component},
                    )
                finally:
                    conn.close()
            except Exception:
                pass  # fire-and-forget: never block logging
            finally:
                _persist_semaphore.release()

        t = threading.Thread(target=_emit, daemon=True)
        t.start()

    error_feed.set_on_persist(_on_error_persisted)

    task = asyncio.create_task(_event_bridge_loop())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title=f"{PROJECT_NAME} Dashboard API", version=__version__, lifespan=lifespan)

# CORS: localhost only
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/branding")
def get_branding():
    return {"name": PROJECT_NAME, "slug": PROJECT_SLUG, "description": PROJECT_DESCRIPTION}


# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_config: Config | None = None
_adapter = None  # Lazy WebAdapter singleton

# OAuth 2.0 PKCE state store — maps (platform, state) to (verifier, redirect_uri, created_at)
# Entries older than _OAUTH_STATE_TTL_SECONDS are cleaned up on each new authorize request.
_OAUTH_STATE_TTL_SECONDS = 600  # 10 minutes
_oauth_pending: dict[tuple[str, str], tuple[str, str, float]] = {}


def _get_config() -> Config:
    """Return cached config, loading from disk on first call."""
    global _config
    if _config is None:
        _config = _load_config_from_disk()
    return _config


def _invalidate_config() -> None:
    """Force config reload on next access."""
    global _config
    _config = None


def _load_config_from_disk() -> Config:
    """Load config from ~/.social-hook/config.yaml."""
    from social_hook.config.yaml import load_full_config

    env_path = get_env_path()
    yaml_path = get_config_path()
    try:
        return load_full_config(env_path=env_path, yaml_path=yaml_path)
    except ConfigError:
        # If config is broken, return defaults
        return Config()


def _get_adapter(scope_id: str | None = None):
    """Return a WebAdapter, optionally scoped to a session.

    With no scope_id, returns a shared broadcast adapter (events visible to all).
    With a scope_id, returns a session-scoped adapter (events scoped to that session).
    """
    if scope_id is not None:
        from social_hook.messaging.web import WebAdapter

        return WebAdapter(db_path=str(get_db_path()), scope_id=scope_id)

    global _adapter
    if _adapter is None:
        from social_hook.messaging.web import WebAdapter

        _adapter = WebAdapter(db_path=str(get_db_path()))
    return _adapter


def _get_conn() -> sqlite3.Connection:
    """Get a SQLite connection to the main DB."""
    conn = sqlite3.connect(str(get_db_path()))
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Stale background task cleanup
# ---------------------------------------------------------------------------


def _cleanup_stale_tasks(db_path: Path) -> int:
    """Mark any 'running' tasks as 'failed' on server startup.

    After a restart, daemon threads from the previous process are dead,
    so any task still marked 'running' will never complete.
    Also resets any decisions stuck in 'evaluating' state back to 'imported'.
    No data events are emitted — no WebSocket clients exist at startup.

    Returns the number of tasks cleaned up.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(
            "UPDATE background_tasks SET status = 'failed',"
            " error = 'Interrupted by server restart',"
            " updated_at = datetime('now')"
            " WHERE status = 'running'"
        )
        conn.commit()
        count = cursor.rowcount
        if count:
            logger.info("Marked %d stale background task(s) as failed on startup", count)

        # Reset decisions stuck in 'evaluating' (retrigger was interrupted)
        eval_cursor = conn.execute(
            "UPDATE decisions SET decision = 'imported', reasoning = '' WHERE decision = 'evaluating'"
        )
        conn.commit()
        eval_count = eval_cursor.rowcount
        if eval_count:
            logger.info(
                "Reset %d 'evaluating' decision(s) back to 'imported' on startup", eval_count
            )

        return count + eval_count
    finally:
        conn.close()


def _expire_hung_tasks(conn: sqlite3.Connection) -> int:
    """Mark tasks running longer than the timeout as failed.

    Uses BEGIN IMMEDIATE to acquire a write lock before SELECT, preventing
    a race where a worker thread completes a task between SELECT and UPDATE.
    This is safe because bridge_conn is otherwise SELECT-only in the event
    bridge loop — no other DML will conflict with the explicit transaction.

    Emits data-change events for each expired task so connected frontends
    update immediately via the useBackgroundTasks WebSocket listener.

    Returns the number of tasks expired.
    """
    threshold = f"-{_STALE_TASK_TIMEOUT_SECONDS} seconds"
    try:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            "SELECT id, project_id FROM background_tasks"
            " WHERE status = 'running' AND created_at < datetime('now', ?)",
            (threshold,),
        ).fetchall()
        if rows:
            conn.execute(
                "UPDATE background_tasks SET status = 'failed',"
                " error = ?, updated_at = datetime('now')"
                " WHERE status = 'running' AND created_at < datetime('now', ?)",
                (f"Timed out after {_STALE_TASK_TIMEOUT_SECONDS} seconds", threshold),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        logger.debug("Failed to expire hung tasks", exc_info=True)
        return 0
    for r in rows:
        ops.emit_data_event(conn, "task", "failed", r["id"], r["project_id"])
    if rows:
        logger.info("Expired %d hung background task(s)", len(rows))
    return len(rows)


# ---------------------------------------------------------------------------
# Background task helper
# ---------------------------------------------------------------------------


def _run_background_task(
    task_type: str,
    ref_id: str,
    project_id: str,
    fn: Callable[[], Any],
    *,
    on_success: Callable[[Any], None] | None = None,
) -> str:
    """Run a blocking callable in a background thread with DB-persisted status.

    Inserts a row into ``background_tasks`` with status='running', launches
    ``fn`` in a daemon thread, and updates the row on completion or failure.
    Emits ``task`` data-change events so the frontend can react via WebSocket.

    Args:
        task_type: Task category (e.g. "create_draft", "consolidate").
        ref_id: Reference key the frontend uses to find this task
            (e.g. decision_id).  Must be unique across concurrently
            running tasks — ``useBackgroundTasks`` deduplicates by
            ref_id and will silently drop collisions.  Prefix with
            task_type when multiple task types target the same entity
            (e.g. ``f"summary:{project_id}"`` vs bare ``project_id``).
        project_id: Project this task belongs to.
        fn: Zero-arg callable that returns a JSON-serialisable result dict.
        on_success: Optional callback receiving ``fn``'s return value,
            called *after* the task row is marked completed.

    Returns:
        The generated task ID.
    """
    from social_hook.filesystem import generate_id

    task_id = generate_id("task")

    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO background_tasks (id, type, ref_id, project_id, status, created_at)"
            " VALUES (?, ?, ?, ?, 'running', datetime('now'))",
            (task_id, task_type, ref_id, project_id),
        )
        conn.commit()
        ops.emit_data_event(conn, "task", "started", task_id, project_id)
    finally:
        conn.close()

    def _worker() -> None:
        try:
            result = fn()
            conn2 = _get_conn()
            try:
                conn2.execute(
                    "UPDATE background_tasks SET status='completed', result=?,"
                    " updated_at=datetime('now') WHERE id=?",
                    (json.dumps(result), task_id),
                )
                conn2.commit()
                ops.emit_data_event(conn2, "task", "completed", task_id, project_id)
            finally:
                conn2.close()
            if on_success:
                on_success(result)
        except Exception:
            logger.exception("Background task %s failed", task_id)
            conn2 = _get_conn()
            try:
                import traceback

                error_msg = traceback.format_exc()[-500:]
                conn2.execute(
                    "UPDATE background_tasks SET status='failed', error=?,"
                    " updated_at=datetime('now') WHERE id=?",
                    (error_msg, task_id),
                )
                conn2.commit()
                ops.emit_data_event(conn2, "task", "failed", task_id, project_id)
                # Emit to error feed for visibility in System > Errors
                try:
                    from social_hook.error_feed import ErrorSeverity, error_feed

                    error_feed.emit(
                        ErrorSeverity.ERROR,
                        f"Background task '{task_type}' failed: {error_msg[:200]}",
                        source="background_task",
                        context={"task_id": task_id, "ref_id": ref_id, "project_id": project_id},
                    )
                except Exception:
                    pass  # error feed itself may not be initialized
            finally:
                conn2.close()

    threading.Thread(target=_worker, daemon=True).start()
    return task_id


def _sanitize_value(value: str) -> str:
    """Strip newlines and control characters from a value."""
    return re.sub(r"[\x00-\x1f\x7f]", "", value)


def _mask_key(value: str) -> str:
    """Mask an API key, showing only last 4 characters."""
    if len(value) <= 4:
        return "****"
    return f"****{value[-4:]}"


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------


class CommandRequest(BaseModel):
    text: str


class CallbackRequest(BaseModel):
    action: str
    payload: str


class MessageRequest(BaseModel):
    text: str


class EnvUpdate(BaseModel):
    key: str
    value: str | None = None  # None = delete


class SocialContextUpdate(BaseModel):
    project_path: str
    content: str


class ContentConfigUpdate(BaseModel):
    project_path: str
    content: str


class MemoryCreate(BaseModel):
    project_path: str
    context: str
    feedback: str
    draft_id: str = ""


class ValidateKeyRequest(BaseModel):
    provider: str
    key: str


# ---------------------------------------------------------------------------
# Bot interaction endpoints
# ---------------------------------------------------------------------------


def _get_events_since(last_id: int, session_id: str | None = None) -> list[dict]:
    """Query web_events for rows with id > last_id.

    If session_id is provided, returns only events that are either unscoped
    (broadcast, session_id IS NULL) or scoped to that specific session.
    """
    conn = _get_conn()
    try:
        if session_id:
            rows = conn.execute(
                "SELECT id, type, data, created_at FROM web_events "
                "WHERE id > ? AND (session_id IS NULL OR session_id = ?) "
                "ORDER BY id ASC",
                (last_id, session_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, type, data, created_at FROM web_events WHERE id > ? ORDER BY id ASC",
                (last_id,),
            ).fetchall()
        results = []
        for row in rows:
            parsed = safe_json_loads(row["data"], "web_events.data")
            if parsed is None:
                continue
            results.append(
                {
                    "id": row["id"],
                    "type": row["type"],
                    "data": parsed,
                    "created_at": row["created_at"],
                }
            )
        return results
    finally:
        conn.close()


@app.get("/api/events/history")
async def api_events_history(x_session_id: str = Header("web")):
    """Return all chat events for initial page load, scoped to session."""
    return {"events": _get_events_since(0, session_id=x_session_id)}


@app.post("/api/command")
async def api_command(body: CommandRequest, x_session_id: str = Header("web")):
    """Execute a bot command via the web adapter."""
    from social_hook.bot.commands import handle_command

    adapter = _get_adapter(scope_id=x_session_id)
    config = _get_config()
    chat_id = f"web:{x_session_id}"

    # Persist user event, run handler synchronously, return all events together.
    before_id = _max_event_id()
    adapter._insert_event("user", {"text": body.text})

    msg = InboundMessage(chat_id=chat_id, text=body.text, message_id="web_0")
    await asyncio.to_thread(handle_command, msg, adapter, config)

    events = _get_events_since(before_id, session_id=x_session_id)
    return {"events": events}


@app.post("/api/callback")
async def api_callback(body: CallbackRequest, x_session_id: str = Header("web")):
    """Execute a button callback via the web adapter."""
    from social_hook.bot.buttons import handle_callback

    adapter = _get_adapter(scope_id=x_session_id)
    config = _get_config()
    chat_id = f"web:{x_session_id}"

    before_id = _max_event_id()

    event = CallbackEvent(
        chat_id=chat_id,
        callback_id="web_0",
        action=body.action,
        payload=body.payload,
    )
    # Run in thread to avoid blocking the event loop and to allow
    # sync libraries (e.g. Playwright) that detect a running asyncio loop.
    await asyncio.to_thread(handle_callback, event, adapter, config)

    cb_conn = _get_conn()
    try:
        ops.emit_data_event(cb_conn, "draft", "updated", body.payload)
    finally:
        cb_conn.close()

    events = _get_events_since(before_id, session_id=x_session_id)
    return {"events": events}


@app.post("/api/message")
async def api_message(body: MessageRequest, x_session_id: str = Header("web")):
    """Send a free-text message via the web adapter."""
    from social_hook.bot.commands import handle_message

    adapter = _get_adapter(scope_id=x_session_id)
    config = _get_config()
    chat_id = f"web:{x_session_id}"

    # Persist user event, run handler synchronously, return all events together.
    before_id = _max_event_id()
    adapter._insert_event("user", {"text": body.text})

    msg = InboundMessage(chat_id=chat_id, text=body.text, message_id="web_0")
    await asyncio.to_thread(handle_message, msg, adapter, config)

    events = _get_events_since(before_id, session_id=x_session_id)
    return {"events": events}


def _max_event_id() -> int:
    """Get the current max event ID from web_events (0 if empty)."""
    conn = _get_conn()
    try:
        row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM web_events").fetchone()
        return row[0] if row else 0
    except Exception:
        return 0
    finally:
        conn.close()


@app.post("/api/events/clear")
async def api_clear_events(x_session_id: str = Header("web")):
    """Clear chat history from web_events and chat_messages for this session."""
    conn = _get_conn()
    chat_id = f"web:{x_session_id}"
    try:
        conn.execute("DELETE FROM web_events WHERE session_id = ?", (x_session_id,))
        with suppress(sqlite3.OperationalError):
            conn.execute("DELETE FROM chat_messages WHERE chat_id = ?", (chat_id,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# SSE endpoint
# ---------------------------------------------------------------------------


@app.get("/api/events")
async def api_events(lastId: int = Query(0), max_empty: int = Query(10)):
    """Server-Sent Events stream polling web_events."""

    def event_stream():
        current_id = lastId
        empty_polls = 0

        while empty_polls < max_empty:
            events = _get_events_since(current_id)
            if events:
                for ev in events:
                    yield f"id: {ev['id']}\ndata: {json.dumps(ev)}\n\n"
                    current_id = ev["id"]
                empty_polls = 0
            else:
                yield ": keepalive\n\n"
                empty_polls += 1
            time.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


# Per-connection session tracking for scoped event routing
_ws_sessions: dict[str, str] = {}  # client_id -> session_id


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    origin = ws.headers.get("origin", "")
    if origin and not re.match(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$", origin):
        await ws.close(code=4003)
        return
    await ws.accept()
    client_id = str(_uuid.uuid4())
    await _hub.connect(ws, client_id, channels=["web"])  # type: ignore[arg-type]
    try:
        while True:
            data = await ws.receive_json()
            try:
                envelope = GatewayEnvelope.from_dict(data)
            except (TypeError, KeyError):
                await _hub.send(
                    client_id,
                    GatewayEnvelope(type="error", payload={"message": "Invalid envelope"}),
                )
                continue
            await _handle_ws_envelope(envelope, client_id)
    except WebSocketDisconnect:
        pass
    finally:
        _ws_sessions.pop(client_id, None)
        await _hub.disconnect(client_id)


async def _handle_ws_envelope(envelope: GatewayEnvelope, client_id: str) -> None:
    if envelope.type == "command":
        command_type = envelope.payload.get("command")
        text = envelope.payload.get("text", "")
        session_id = _ws_sessions.get(client_id, "web")
        adapter = _get_adapter(scope_id=session_id)
        chat_id = f"web:{session_id}"
        adapter._insert_event("user", {"text": text})
        await _hub.send(client_id, GatewayEnvelope(type="ack", reply_to=envelope.id, payload={}))
        try:
            if command_type == "send_command":
                from social_hook.bot.commands import handle_command

                msg = InboundMessage(chat_id=chat_id, text=text, message_id="web_0")
                await asyncio.to_thread(handle_command, msg, adapter, _get_config())
            elif command_type == "send_callback":
                from social_hook.bot.buttons import handle_callback

                event = CallbackEvent(
                    chat_id=chat_id,
                    callback_id="ws",
                    action=envelope.payload.get("action", ""),
                    payload=envelope.payload.get("payload", ""),
                )
                await asyncio.to_thread(handle_callback, event, adapter, _get_config())
            elif command_type == "send_message":
                from social_hook.bot.commands import handle_message

                msg = InboundMessage(chat_id=chat_id, text=text, message_id="web_0")
                await asyncio.to_thread(handle_message, msg, adapter, _get_config())
            else:
                logger.warning("Unknown WS command type: %s from %s", command_type, client_id)
        except Exception as e:
            await _hub.send(
                client_id,
                GatewayEnvelope(type="error", reply_to=envelope.id, payload={"message": str(e)}),
            )
    elif envelope.type == "subscribe":
        # Register session_id for this WS connection
        session_id = envelope.payload.get("session_id", "web")
        _ws_sessions[client_id] = session_id
        last_seen_id = envelope.payload.get("last_seen_id", 0)
        # 0 means no replay needed (client loads history via REST on init)
        if last_seen_id:
            missed = _get_events_since(last_seen_id, session_id=session_id)
            for ev in missed:
                await _hub.send(client_id, GatewayEnvelope(type="event", channel="web", payload=ev))
        channel = envelope.payload.get("channel", "web")
        _hub.subscribe(client_id, channel)
    elif envelope.type == "unsubscribe":
        channel = envelope.payload.get("channel", "web")
        _hub.unsubscribe(client_id, channel)
    else:
        logger.warning("Unknown WS envelope type: %s from %s", envelope.type, client_id)


async def _event_bridge_loop():
    """Poll web_events and broadcast new entries to WS clients.

    Broadcast events (session_id IS NULL) go to all connections.
    Scoped events go only to the connection with a matching session_id.

    Detects DB file replacement (e.g. snapshot restore) via ResilientConnection
    and reconnects automatically.
    """
    from social_hook.db.connection import ResilientConnection

    db_path = get_db_path()
    rc = ResilientConnection(db_path)
    bridge_conn = rc.conn
    try:
        row = bridge_conn.execute("SELECT COALESCE(MAX(id), 0) FROM web_events").fetchone()
        last_id = row[0] if row else 0
        tick_count = 0
        while True:
            await asyncio.sleep(0.5)
            tick_count += 1
            # Check for DB file replacement (snapshot restore)
            prev_conn = bridge_conn
            bridge_conn = rc.check()
            if bridge_conn is not prev_conn:
                row = bridge_conn.execute("SELECT COALESCE(MAX(id), 0) FROM web_events").fetchone()
                max_id = row[0] if row else 0
                if max_id < last_id:
                    last_id = max(0, max_id - 1)  # Re-read latest event after DB change
            if tick_count % _STALE_CHECK_INTERVAL_TICKS == 0:
                _expire_hung_tasks(bridge_conn)
            if _hub.connection_count == 0:
                row = bridge_conn.execute("SELECT COALESCE(MAX(id), 0) FROM web_events").fetchone()
                last_id = row[0] if row else 0
                continue
            rows = bridge_conn.execute(
                "SELECT id, type, data, session_id, created_at FROM web_events WHERE id > ? ORDER BY id ASC",
                (last_id,),
            ).fetchall()
            for r in rows:
                parsed = safe_json_loads(r["data"], "web_events.data (ws bridge)")
                if parsed is None:
                    last_id = r["id"]
                    continue
                ev = {
                    "id": r["id"],
                    "type": r["type"],
                    "data": parsed,
                    "created_at": r["created_at"],
                }
                envelope = GatewayEnvelope(type="event", channel="web", payload=ev)
                event_session_id = r["session_id"]
                if event_session_id is None:
                    # Broadcast event (e.g., notifications from trigger pipeline)
                    await _hub.broadcast(envelope, channel="web")
                else:
                    # Scoped event -- send only to matching WS connection(s)
                    for cid, sid in list(_ws_sessions.items()):
                        if sid == event_session_id:
                            await _hub.send(cid, envelope)
                last_id = r["id"]
    except asyncio.CancelledError:
        pass
    finally:
        rc.close()


# ---------------------------------------------------------------------------
# Data query endpoints
# ---------------------------------------------------------------------------


@app.get("/api/drafts")
async def api_drafts(
    status: str | None = None,
    pending: bool = False,
    project_id: str | None = None,
    decision_id: str | None = None,
    commit: str | None = None,
    tag: str | None = None,
):
    """List drafts, optionally filtered by status, project, decision, commit, or tag."""
    from social_hook.db import operations as ops

    conn = _get_conn()
    try:
        draft_models = ops.get_drafts_filtered(
            conn,
            status=status,
            project_id=project_id,
            decision_id=decision_id,
            commit_hash=commit,
            tag=tag,
        )
        drafts = [d.to_dict() for d in draft_models]
        if pending:
            drafts = [d for d in drafts if d.get("status") in PENDING_STATUSES]
        return {"drafts": drafts}
    finally:
        conn.close()


@app.get("/api/drafts/{draft_id}")
async def api_draft_detail(draft_id: str):
    """Get draft detail including tweets, changes, and evaluator decision."""
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Draft not found")

        draft = dict(row)

        tweets = conn.execute(
            "SELECT * FROM draft_tweets WHERE draft_id = ? ORDER BY position ASC",
            (draft_id,),
        ).fetchall()
        draft["tweets"] = [dict(t) for t in tweets]

        changes = conn.execute(
            "SELECT * FROM draft_changes WHERE draft_id = ? ORDER BY changed_at DESC",
            (draft_id,),
        ).fetchall()
        draft["changes"] = [dict(c) for c in changes]

        # Embed evaluator decision data
        if draft.get("decision_id"):
            decision_row = conn.execute(
                "SELECT * FROM decisions WHERE id = ?", (draft["decision_id"],)
            ).fetchone()
            draft["decision"] = dict(decision_row) if decision_row else None
        else:
            draft["decision"] = None

        return draft
    finally:
        conn.close()


@app.put("/api/drafts/{draft_id}/media-spec")
async def api_update_draft_media_spec(draft_id: str, body: dict[str, Any] = Body(...)):
    """Update media_spec and optionally media_type on a draft."""
    media_spec = body.get("media_spec")
    media_type = body.get("media_type")
    if media_spec is None:
        raise HTTPException(status_code=400, detail="media_spec is required")
    conn = _get_conn()
    try:
        # Get old spec for audit trail
        draft = ops.get_draft(conn, draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")
        old_spec = draft.media_spec

        update_kwargs: dict[str, Any] = {"media_spec": media_spec}
        if media_type is not None:
            update_kwargs["media_type"] = media_type
        ops.update_draft(conn, draft_id, **update_kwargs)

        # Audit: create DraftChange record
        from social_hook.filesystem import generate_id
        from social_hook.models import DraftChange

        ops.insert_draft_change(
            conn,
            DraftChange(
                id=generate_id("change"),
                draft_id=draft_id,
                field="media_spec",
                old_value=json.dumps(old_spec)[:200] if old_spec else "null",
                new_value=json.dumps(media_spec)[:200],
                changed_by="human",
            ),
        )

        ops.emit_data_event(conn, "draft", "updated", draft_id, draft.project_id)
        return {"status": "updated"}
    finally:
        conn.close()


_ALLOWED_UPLOAD_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "svg"}
_MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB


@app.post("/api/drafts/{draft_id}/media-upload")
async def api_upload_draft_media(draft_id: str, file: UploadFile):
    """Upload a media file and attach it to a draft.

    Accepts multipart/form-data with a 'file' field.
    """
    from social_hook.filesystem import generate_id, get_base_path
    from social_hook.models import DraftChange

    # Validate extension
    ext = ""
    if file.filename and "." in file.filename:
        ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in _ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Invalid file type: .{ext}")

    # Read and validate size
    content = await file.read()
    if len(content) > _MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({len(content)} bytes). Max {_MAX_UPLOAD_SIZE} bytes.",
        )

    conn = _get_conn()
    try:
        draft = ops.get_draft(conn, draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")
        if draft.status not in EDITABLE_STATUSES:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot upload media — draft is {draft.status}",
            )

        # Save uploaded file with UUID filename
        upload_dir = get_base_path() / "media-cache" / "uploads" / draft_id
        upload_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{_uuid.uuid4()}.{ext}"
        dest = upload_dir / filename
        dest.write_bytes(content)

        file_path = str(dest)
        old_paths = draft.media_paths

        ops.update_draft(conn, draft_id, media_paths=[file_path], media_type="custom")
        ops.insert_draft_change(
            conn,
            DraftChange(
                id=generate_id("change"),
                draft_id=draft_id,
                field="media_paths",
                old_value=json.dumps(old_paths),
                new_value=json.dumps([file_path]),
                changed_by="human",
            ),
        )
        ops.emit_data_event(conn, "draft", "edited", draft_id, draft.project_id)

        return {"status": "uploaded", "file_path": file_path}
    finally:
        conn.close()


@app.post("/api/drafts/{draft_id}/generate-spec")
async def api_generate_spec(draft_id: str, body: dict[str, Any] = Body(...)):
    """Generate a media spec from draft content using LLM. Returns 202 with task_id."""
    tool_name = body.get("tool_name")
    if not tool_name:
        raise HTTPException(status_code=400, detail="tool_name is required")

    conn = _get_conn()
    try:
        draft = ops.get_draft(conn, draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")

        # Duplicate-task guard
        existing = conn.execute(
            "SELECT id FROM background_tasks"
            " WHERE type='generate_spec' AND ref_id=? AND status='running'",
            (draft_id,),
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Spec generation already running")

        from social_hook.adapters.registry import get_tool_spec_schema

        schema = get_tool_spec_schema(tool_name)

        # Capture values for the closure (conn can't be shared across threads)
        draft_content = draft.content
        draft_project_id = draft.project_id
        old_spec = draft.media_spec
    finally:
        conn.close()

    def _blocking_generate_spec() -> dict:
        from social_hook.config.yaml import load_full_config
        from social_hook.filesystem import generate_id
        from social_hook.llm.base import extract_tool_call
        from social_hook.llm.factory import create_client
        from social_hook.llm.prompts import (
            assemble_spec_generation_prompt,
            build_spec_generation_tool,
        )
        from social_hook.models import DraftChange

        config = load_full_config()
        prompt = assemble_spec_generation_prompt(
            tool_name=tool_name,
            schema=schema,
            draft_content=draft_content,
        )
        spec_tool = build_spec_generation_tool(tool_name, schema)
        client = create_client(config.models.drafter, config)
        response = client.complete(
            messages=[{"role": "user", "content": prompt}],
            tools=[spec_tool],
        )
        spec = extract_tool_call(response, "generate_media_spec")

        # Persist to DB
        conn2 = _get_conn()
        try:
            ops.update_draft(conn2, draft_id, media_spec=spec, media_type=tool_name)
            ops.insert_draft_change(
                conn2,
                DraftChange(
                    id=generate_id("change"),
                    draft_id=draft_id,
                    field="media_spec",
                    old_value=json.dumps(old_spec)[:200] if old_spec else "null",
                    new_value=json.dumps(spec)[:200],
                    changed_by="human",
                ),
            )
            ops.emit_data_event(conn2, "draft", "updated", draft_id, draft_project_id)
        finally:
            conn2.close()

        return {"spec": spec, "tool_name": tool_name}

    task_id = _run_background_task(
        "generate_spec",
        ref_id=draft_id,
        project_id=draft_project_id,
        fn=_blocking_generate_spec,
    )
    return JSONResponse(status_code=202, content={"task_id": task_id, "status": "processing"})


@app.post("/api/drafts/{draft_id}/resend-notification")
async def api_resend_draft_notification(draft_id: str):
    """Re-send a draft's review notification to all configured channels."""
    from social_hook.bot.process import is_running
    from social_hook.config.yaml import load_full_config
    from social_hook.notifications import resend_draft_notification

    if not is_running():
        raise HTTPException(status_code=409, detail="Bot daemon is not running")

    conn = _get_conn()
    try:
        draft = ops.get_draft(conn, draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")
    finally:
        conn.close()

    try:
        config = load_full_config()
        resend_draft_notification(config, draft_id)
        return {"success": True, "message": "Notification resent"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from None


@app.post("/api/drafts/{draft_id}/connect")
async def api_connect_draft(draft_id: str, body: dict[str, Any] = Body(...)):
    """Connect a preview-mode draft to an account.

    Clears preview_mode and optionally persists the target-to-account link.

    Body:
        account: Account name to connect
    """
    from social_hook.config.yaml import load_full_config
    from social_hook.errors import ConfigError
    from social_hook.parsing import check_unknown_keys

    try:
        check_unknown_keys(body, {"account"}, "connect_draft", strict=True)
    except ConfigError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None

    account_name = body.get("account")
    if not account_name:
        raise HTTPException(status_code=400, detail="Missing 'account' in body")

    conn = _get_conn()
    try:
        draft = ops.get_draft(conn, draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")
        if not draft.preview_mode:
            raise HTTPException(status_code=400, detail="Draft is not in preview mode")
        if draft.status in TERMINAL_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot connect draft with status '{draft.status}'",
            )

        config = load_full_config()
        acct = config.accounts.get(account_name)
        if not acct:
            raise HTTPException(status_code=400, detail=f"Account '{account_name}' not found")
        if acct.platform != draft.platform:
            raise HTTPException(
                status_code=400,
                detail=f"Account platform '{acct.platform}' does not match draft platform '{draft.platform}'",
            )

        ops.clear_draft_preview_mode(conn, draft_id)

        # Persist target -> account link
        target_name = draft.target_id
        if target_name and target_name in config.targets:
            from social_hook.config.yaml import save_config

            save_config(
                {"targets": {target_name: {"account": account_name}}},
                config_path=get_config_path(),
                deep_merge=True,
            )

        ops.emit_data_event(conn, "draft", "connected", draft_id, draft.project_id)
        return {
            "status": "connected",
            "draft_id": draft_id,
            "account": account_name,
            "platform": draft.platform,
        }
    finally:
        conn.close()


@app.post("/api/drafts/{draft_id}/promote")
async def api_promote_draft(draft_id: str, body: dict[str, Any] = Body(...)):
    """Promote a preview draft to a real platform.

    Creates a new draft for the target platform using the LLM drafter,
    then marks the preview draft as superseded.

    Body:
        platform: Target platform name (e.g. "x", "linkedin")
    """
    platform = body.get("platform")
    if not platform:
        raise HTTPException(status_code=400, detail="Missing 'platform' in body")

    conn = _get_conn()
    try:
        draft = ops.get_draft(conn, draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")
        if not draft.preview_mode:
            raise HTTPException(status_code=400, detail="Only preview-mode drafts can be promoted")
        if draft.status in TERMINAL_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot promote draft with status '{draft.status}'",
            )

        decision = ops.get_decision(conn, draft.decision_id)
        if not decision:
            raise HTTPException(status_code=404, detail="Decision not found")

        project = ops.get_project(conn, decision.project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
    finally:
        conn.close()

    config = _get_config()

    pcfg = config.platforms.get(platform)
    if not pcfg or not pcfg.enabled:
        raise HTTPException(status_code=400, detail=f"Platform '{platform}' is not enabled")

    from social_hook.compat import evaluation_from_decision
    from social_hook.config.project import ProjectConfig, load_project_config
    from social_hook.models import CommitInfo

    try:
        project_config = load_project_config(project.repo_path)
    except ConfigError:
        project_config = ProjectConfig(repo_path=project.repo_path)

    from social_hook.trigger import parse_commit_info

    try:
        commit = parse_commit_info(decision.commit_hash, project.repo_path)
    except Exception:
        commit = CommitInfo(
            hash=decision.commit_hash,
            message=decision.commit_message or "",
            diff="",
            files_changed=[],
        )

    evaluation = evaluation_from_decision(decision, "draft")

    def _blocking_promote():
        import sqlite3 as _sqlite3

        from social_hook.drafting import draft_for_platforms
        from social_hook.llm.dry_run import DryRunContext
        from social_hook.llm.prompts import assemble_evaluator_context

        conn2 = _sqlite3.connect(str(get_db_path()))
        conn2.row_factory = _sqlite3.Row
        db = DryRunContext(conn2, dry_run=False)
        try:
            context = assemble_evaluator_context(
                db,
                project.id,
                project_config,
                commit_timestamp=getattr(commit, "timestamp", None),
                parent_timestamp=getattr(commit, "parent_timestamp", None),
            )
            db.emit_data_event("pipeline", PipelineStage.PROMOTING, draft_id[:8], project.id)
            results = draft_for_platforms(
                config,
                conn2,
                db,
                project,
                decision_id=decision.id,
                evaluation=evaluation,
                context=context,
                commit=commit,
                project_config=project_config,
                target_platform_names=[platform],
            )
            return {"draft_ids": [r.draft.id for r in results], "count": len(results)}
        finally:
            conn2.close()

    def _on_promote_done(result: dict) -> None:
        conn2 = _get_conn()
        try:
            new_draft_ids = result.get("draft_ids", [])
            if new_draft_ids:
                ops.supersede_draft(conn2, draft_id, new_draft_ids[0])
                ops.emit_data_event(conn2, "draft", "updated", draft_id, project.id)

            from social_hook.drafting import DraftResult
            from social_hook.scheduling import calculate_optimal_time

            draft_results = []
            for did in new_draft_ids:
                d = ops.get_draft(conn2, did)
                if d:
                    sched = calculate_optimal_time(conn2, d.project_id, platform=d.platform)
                    draft_results.append(DraftResult(draft=d, schedule=sched, thread_tweets=[]))
            if draft_results:
                from social_hook.notifications import notify_draft_review

                notify_draft_review(
                    config,
                    project_name=project.name,
                    project_id=project.id,
                    commit_hash=commit.hash,
                    commit_message=commit.message,
                    draft_results=draft_results,
                )
        except Exception:
            logger.debug("Promote notification failed", exc_info=True)
        finally:
            conn2.close()

    task_id = _run_background_task(
        "promote_draft",
        ref_id=draft_id,
        project_id=project.id,
        fn=_blocking_promote,
        on_success=_on_promote_done,
    )
    return JSONResponse(status_code=202, content={"task_id": task_id, "status": "processing"})


@app.get("/api/projects")
async def api_projects():
    """List all registered projects with lifecycle phase."""
    from social_hook.setup.install import check_git_hook_installed

    conn = _get_conn()
    try:
        rows = conn.execute("""
            SELECT p.*, l.phase, l.confidence
            FROM projects p
            LEFT JOIN lifecycles l ON l.project_id = p.id
            ORDER BY p.created_at DESC
        """).fetchall()
        projects = []
        for row in rows:
            p = dict(row)
            p["git_hook_installed"] = check_git_hook_installed(p["repo_path"])
            projects.append(p)
        return {"projects": projects}
    finally:
        conn.close()


def _get_project_or_404(conn: sqlite3.Connection, project_id: str) -> sqlite3.Row:
    """Fetch a project row or raise 404."""
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    return row  # type: ignore[no-any-return]


@app.get("/api/projects/{project_id}")
async def api_project_detail(project_id: str):
    """Get project detail with lifecycle, arcs, narrative debt, summary, and stats."""
    conn = _get_conn()
    try:
        project_row = _get_project_or_404(conn, project_id)
        project = dict(project_row)

        # Lifecycle
        lc_row = conn.execute(
            "SELECT * FROM lifecycles WHERE project_id = ?", (project_id,)
        ).fetchone()
        project["lifecycle"] = dict(lc_row) if lc_row else None

        # Arcs
        arc_rows = conn.execute(
            "SELECT * FROM arcs WHERE project_id = ? ORDER BY started_at DESC",
            (project_id,),
        ).fetchall()
        project["arcs"] = [dict(a) for a in arc_rows]

        # Narrative debt
        nd_row = conn.execute(
            "SELECT * FROM narrative_debt WHERE project_id = ?", (project_id,)
        ).fetchone()
        project["narrative_debt"] = dict(nd_row) if nd_row else None

        # Stats: decision counts by type
        decision_stats = conn.execute(
            """
            SELECT decision, COUNT(*) as count
            FROM decisions WHERE project_id = ?
            GROUP BY decision
        """,
            (project_id,),
        ).fetchall()
        project["decision_counts"] = {row["decision"]: row["count"] for row in decision_stats}

        # Stats: draft and post counts
        draft_count = conn.execute(
            "SELECT COUNT(*) FROM drafts WHERE project_id = ?", (project_id,)
        ).fetchone()[0]
        post_count = conn.execute(
            "SELECT COUNT(*) FROM posts WHERE project_id = ?", (project_id,)
        ).fetchone()[0]
        project["draft_count"] = draft_count
        project["post_count"] = post_count

        # Journey capture fire count from narratives JSONL file
        narratives_file = get_narratives_path() / f"{project_id}.jsonl"
        narrative_count = 0
        if narratives_file.exists():
            with open(narratives_file) as f:
                narrative_count = sum(1 for _ in f)
        project["narrative_count"] = narrative_count

        # Journey capture enabled flag
        try:
            config = _get_config()
            project["journey_capture_enabled"] = config.journey_capture.enabled
        except Exception:
            project["journey_capture_enabled"] = False

        return project
    finally:
        conn.close()


@app.get("/api/projects/{project_id}/decisions")
async def api_project_decisions(
    project_id: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    branch: str | None = Query(None),
):
    """Get decision history for a project with pagination."""
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)

        if branch is not None:
            rows = conn.execute(
                """
                SELECT d.*, COUNT(dr.id) as draft_count
                FROM decisions d
                LEFT JOIN drafts dr ON dr.decision_id = d.id
                WHERE d.project_id = ? AND d.branch = ?
                GROUP BY d.id
                ORDER BY d.created_at DESC
                LIMIT ? OFFSET ?
            """,
                (project_id, branch, limit, offset),
            ).fetchall()

            total = conn.execute(
                "SELECT COUNT(*) FROM decisions WHERE project_id = ? AND branch = ?",
                (project_id, branch),
            ).fetchone()[0]
        else:
            rows = conn.execute(
                """
                SELECT d.*, COUNT(dr.id) as draft_count
                FROM decisions d
                LEFT JOIN drafts dr ON dr.decision_id = d.id
                WHERE d.project_id = ?
                GROUP BY d.id
                ORDER BY d.created_at DESC
                LIMIT ? OFFSET ?
            """,
                (project_id, limit, offset),
            ).fetchall()

            total = conn.execute(
                "SELECT COUNT(*) FROM decisions WHERE project_id = ?", (project_id,)
            ).fetchone()[0]

        decisions_list = [dict(r) for r in rows]

        # Enrich with draft IDs
        decision_ids = [d["id"] for d in decisions_list]
        if decision_ids:
            placeholders = ",".join("?" * len(decision_ids))
            draft_rows = conn.execute(
                f"SELECT id, decision_id FROM drafts WHERE decision_id IN ({placeholders})",
                decision_ids,
            ).fetchall()
            drafts_by_decision: dict[str, list[str]] = {}
            for dr in draft_rows:
                drafts_by_decision.setdefault(dr["decision_id"], []).append(dr["id"])
            for d in decisions_list:
                d["draft_ids"] = drafts_by_decision.get(d["id"], [])

        # Enrich with classification from stage 1 analyzer (via evaluation_cycles)
        commit_hashes = [d["commit_hash"] for d in decisions_list if d.get("commit_hash")]
        if commit_hashes:
            ch_placeholders = ",".join("?" * len(commit_hashes))
            cycle_rows = conn.execute(
                f"""SELECT trigger_ref, commit_analysis_json
                    FROM evaluation_cycles
                    WHERE project_id = ? AND trigger_type = 'commit'
                    AND trigger_ref IN ({ch_placeholders})
                    AND commit_analysis_json IS NOT NULL""",
                [project_id, *commit_hashes],
            ).fetchall()
            classification_by_hash: dict[str, str] = {}
            for cr in cycle_rows:
                analysis_data = safe_json_loads(
                    cr["commit_analysis_json"],
                    "cycle_commit_analysis_json",
                    default={},
                )
                ca = analysis_data.get("commit_analysis", {})
                cls_val = ca.get("classification")
                if cls_val:
                    classification_by_hash[cr["trigger_ref"]] = cls_val
            for d in decisions_list:
                d["classification"] = classification_by_hash.get(d.get("commit_hash", ""))

        return {"decisions": decisions_list, "total": total}
    finally:
        conn.close()


@app.get("/api/projects/{project_id}/decision-branches")
async def api_decision_branches(project_id: str):
    """Get distinct branch names from decisions for a project."""
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)
        branches = ops.get_distinct_branches(conn, project_id)
        return {"branches": branches}
    finally:
        conn.close()


@app.get("/api/projects/{project_id}/import-preview")
async def api_import_preview(project_id: str, branch: str | None = Query(None)):
    """Preview how many commits can be imported for a project."""
    conn = _get_conn()
    try:
        project = _get_project_or_404(conn, project_id)
        from social_hook.import_commits import get_import_preview

        preview = get_import_preview(conn, project["id"], project["repo_path"], branch)

        # Include git repo branches so the import modal can show them
        # (decisionBranches is empty on a fresh project)
        import subprocess

        try:
            result = subprocess.run(
                ["git", "-C", project["repo_path"], "branch", "--format=%(refname:short)"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            git_branches = [b.strip() for b in result.stdout.strip().split("\n") if b.strip()]
        except Exception:
            git_branches = []

        preview["branches"] = git_branches
        return preview
    finally:
        conn.close()


@app.post("/api/projects/{project_id}/import-commits")
async def api_import_commits(project_id: str, body: dict[str, Any] = Body(default={})):
    """Import historical commits for a project as decisions.

    Body:
        branch: Target branch name (optional — omit to import from default branch)
    """
    branch = body.get("branch")

    conn = _get_conn()
    try:
        project = _get_project_or_404(conn, project_id)

        # Check for already-running import
        running = conn.execute(
            "SELECT id FROM background_tasks WHERE type = 'import_commits' AND project_id = ? AND status = 'running'",
            (project_id,),
        ).fetchone()
        if running:
            raise HTTPException(status_code=409, detail="Import already in progress")
    finally:
        conn.close()

    repo_path = project["repo_path"]
    pid = project["id"]

    def _blocking_import():
        from social_hook.import_commits import import_project_commits

        conn2 = _get_conn()
        try:
            return import_project_commits(conn2, pid, repo_path, branch)
        finally:
            conn2.close()

    task_id = _run_background_task(
        "import_commits",
        ref_id="__import__",
        project_id=pid,
        fn=_blocking_import,
    )

    return JSONResponse(
        status_code=202,
        content={"task_id": task_id, "status": "started"},
    )


@app.post("/api/projects/{project_id}/summary-draft")
async def api_summary_draft(project_id: str):
    """Generate an introductory first draft from the project summary.

    Creates a Decision with trigger_source="manual" and drafts for all
    enabled platforms.  Uses the background-task pattern so the frontend
    can track progress via WebSocket.
    """
    conn = _get_conn()
    try:
        project = _get_project_or_404(conn, project_id)
        repo_path = project["repo_path"]
        pid = project["id"]
        pname = project["name"]

        # Prevent duplicate runs
        running = conn.execute(
            "SELECT id FROM background_tasks WHERE type = 'summary_draft'"
            " AND project_id = ? AND status = 'running'",
            (project_id,),
        ).fetchone()
        if running:
            raise HTTPException(status_code=409, detail="Summary draft already in progress")
    finally:
        conn.close()

    config = _get_config()

    def _blocking_summary_draft():
        import sqlite3 as _sqlite3

        from social_hook.llm.dry_run import DryRunContext
        from social_hook.trigger import run_summary_trigger

        conn2 = _sqlite3.connect(str(get_db_path()))
        conn2.execute("PRAGMA busy_timeout = 5000")
        conn2.row_factory = _sqlite3.Row
        db = DryRunContext(conn2, dry_run=False)
        try:
            # Run discovery first if no summary exists
            proj = ops.get_project(conn2, pid)
            proj_summary = proj.summary if proj else None
            if not proj_summary:
                from social_hook.config.project import load_project_config
                from social_hook.llm.discovery import discover_project
                from social_hook.llm.factory import create_client

                project_config = load_project_config(repo_path)
                client = create_client(config.models.evaluator, config)
                ops.emit_data_event(conn2, "pipeline", PipelineStage.DISCOVERING, pid, pid)
                disc_summary, disc_files, disc_file_summaries, disc_prompt_docs = discover_project(
                    client=client,
                    repo_path=repo_path,
                    project_docs=project_config.context.project_docs,
                    max_discovery_tokens=project_config.context.max_discovery_tokens,
                    max_file_size=project_config.context.max_file_size,
                    db=conn2,
                    project_id=pid,
                )
                if disc_summary:
                    ops.update_project_summary(conn2, pid, disc_summary)
                    if disc_files:
                        ops.update_discovery_files(conn2, pid, disc_files)
                    if disc_file_summaries:
                        ops.upsert_file_summaries(conn2, pid, disc_file_summaries)
                    if disc_prompt_docs:
                        ops.update_prompt_docs(conn2, pid, disc_prompt_docs)
                    ops.emit_data_event(conn2, "project", "updated", pid, pid)
                    proj_summary = disc_summary
                    # Re-fetch project with updated summary
                    proj = ops.get_project(conn2, pid)

            if not proj_summary:
                return {"draft_ids": [], "count": 0, "error": "Discovery produced no summary"}

            result = run_summary_trigger(
                config=config,
                conn=conn2,
                db=db,
                project=proj,
                summary=proj_summary,
                repo_path=repo_path,
            )
            return result or {"draft_ids": [], "count": 0}
        finally:
            conn2.close()

    def _on_summary_drafted(result: dict) -> None:
        draft_id = result.get("draft_id")
        if not draft_id:
            return
        conn2 = _get_conn()
        try:
            from social_hook.drafting import DraftResult
            from social_hook.scheduling import calculate_optimal_time

            d = ops.get_draft(conn2, draft_id)
            if d:
                sched = calculate_optimal_time(conn2, d.project_id, platform=d.platform)
                from social_hook.notifications import notify_draft_review

                notify_draft_review(
                    config,
                    project_name=pname,
                    project_id=pid,
                    commit_hash="summary",
                    commit_message="Project introduction",
                    draft_results=[DraftResult(draft=d, schedule=sched, thread_tweets=[])],
                )
        except Exception:
            logger.debug("Summary draft notification failed", exc_info=True)
        finally:
            conn2.close()

    task_id = _run_background_task(
        "summary_draft",
        ref_id=f"summary:{project_id}",
        project_id=pid,
        fn=_blocking_summary_draft,
        on_success=_on_summary_drafted,
    )

    return JSONResponse(
        status_code=202,
        content={"task_id": task_id, "status": "processing"},
    )


@app.get("/api/projects/{project_id}/posts")
async def api_project_posts(
    project_id: str,
    limit: int = Query(50, ge=1, le=500),
):
    """Get published posts for a project."""
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)

        rows = conn.execute(
            """
            SELECT * FROM posts
            WHERE project_id = ?
            ORDER BY posted_at DESC
            LIMIT ?
        """,
            (project_id, limit),
        ).fetchall()
        return {"posts": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.get("/api/projects/{project_id}/usage")
async def api_project_usage(
    project_id: str,
    days: int = Query(30, ge=1, le=365),
):
    """Get usage analytics for a project."""
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)

        rows = conn.execute(
            """
            SELECT
                model,
                operation_type,
                SUM(input_tokens) as total_input,
                SUM(output_tokens) as total_output,
                SUM(cache_read_tokens) as total_cache_read,
                SUM(cache_creation_tokens) as total_cache_creation,
                SUM(cost_cents) as total_cost_cents,
                COUNT(*) as call_count
            FROM usage_log
            WHERE project_id = ?
              AND created_at >= datetime('now', '-' || ? || ' days')
            GROUP BY model, operation_type
            ORDER BY total_cost_cents DESC
        """,
            (project_id, days),
        ).fetchall()

        rows_list = [dict(r) for r in rows]
        return {
            "total_input_tokens": sum(r["total_input"] for r in rows_list),
            "total_output_tokens": sum(r["total_output"] for r in rows_list),
            "total_cost_cents": sum(r["total_cost_cents"] for r in rows_list),
            "entries": rows_list,
        }
    finally:
        conn.close()


@app.post("/api/decisions/{decision_id}/create-draft")
async def api_create_draft_from_decision(decision_id: str, body: dict[str, Any] = Body(...)):
    """Create a draft from an existing decision (decision override).

    Allows manually triggering draft creation for a decision that was
    originally marked as skip or hold.
    Uses the shared drafting pipeline for real LLM-generated content.

    Body:
        platform: Target platform name (optional — omit to draft for all enabled)
    """
    platform = body.get("platform")

    conn = _get_conn()
    try:
        decision = ops.get_decision(conn, decision_id)
        if not decision:
            raise HTTPException(status_code=404, detail="Decision not found")

        project = ops.get_project(conn, decision.project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
    finally:
        conn.close()

    config = _get_config()

    from social_hook.config.project import ProjectConfig, load_project_config

    try:
        project_config = load_project_config(project.repo_path)
    except ConfigError:
        project_config = ProjectConfig(repo_path=project.repo_path)

    from social_hook.compat import evaluation_from_decision
    from social_hook.trigger import parse_commit_info

    commit = parse_commit_info(decision.commit_hash, project.repo_path)

    evaluation = evaluation_from_decision(decision, "draft")

    def _blocking_create_draft():
        import sqlite3 as _sqlite3

        from social_hook.drafting import draft_for_platforms
        from social_hook.llm.dry_run import DryRunContext
        from social_hook.llm.prompts import assemble_evaluator_context

        conn2 = _sqlite3.connect(str(get_db_path()))
        conn2.execute("PRAGMA busy_timeout = 5000")
        conn2.row_factory = _sqlite3.Row
        db = DryRunContext(conn2, dry_run=False)
        try:
            context = assemble_evaluator_context(
                db,
                project.id,
                project_config,
                commit_timestamp=commit.timestamp,
                parent_timestamp=commit.parent_timestamp,
            )
            db.emit_data_event(
                "pipeline", PipelineStage.DRAFTING, decision.commit_hash[:8], project.id
            )
            results = draft_for_platforms(
                config,
                conn2,
                db,
                project,
                decision_id=decision_id,
                evaluation=evaluation,
                context=context,
                commit=commit,
                project_config=project_config,
                target_platform_names=[platform] if platform else None,
            )
            return {"draft_ids": [r.draft.id for r in results], "count": len(results)}
        finally:
            conn2.close()

    def _on_drafts_created(result: dict) -> None:
        from social_hook.drafting import DraftResult

        # Re-fetch drafts from DB for notification (thread-safe)
        conn2 = _get_conn()
        try:
            from social_hook.scheduling import calculate_optimal_time

            draft_results = []
            for did in result["draft_ids"]:
                d = ops.get_draft(conn2, did)
                if d:
                    sched = calculate_optimal_time(conn2, d.project_id, platform=d.platform)
                    draft_results.append(DraftResult(draft=d, schedule=sched, thread_tweets=[]))
            if draft_results:
                from social_hook.notifications import notify_draft_review

                notify_draft_review(
                    config,
                    project_name=project.name,
                    project_id=project.id,
                    commit_hash=commit.hash,
                    commit_message=commit.message,
                    draft_results=draft_results,
                )
        except Exception:
            logger.debug("Draft notification failed", exc_info=True)
        finally:
            conn2.close()

    task_id = _run_background_task(
        "create_draft",
        ref_id=decision_id,
        project_id=project.id,
        fn=_blocking_create_draft,
        on_success=_on_drafts_created,
    )

    return JSONResponse(
        status_code=202,
        content={"task_id": task_id, "status": "processing"},
    )


@app.delete("/api/decisions/{decision_id}")
async def api_delete_decision(decision_id: str):
    """Delete a decision and all associated drafts/data."""
    conn = _get_conn()
    try:
        decision = ops.get_decision(conn, decision_id)
        if not decision:
            raise HTTPException(status_code=404, detail="Decision not found")

        project_id = decision.project_id
        result = ops.delete_decision(conn, decision_id)
        if not result:
            raise HTTPException(status_code=500, detail="Failed to delete decision")

        ops.emit_data_event(conn, "decision", "deleted", decision_id, project_id)
        return {"status": "deleted", "decision_id": decision_id}
    finally:
        conn.close()


@app.post("/api/decisions/{decision_id}/retrigger")
async def api_retrigger_decision(decision_id: str):
    """Re-evaluate a commit in-place, reusing the same decision ID.

    Cleans up old drafts, marks the decision as 'evaluating', then re-runs
    the full evaluator pipeline via background task. The decision row stays
    visible in the UI throughout (no delete/re-create gap).
    Returns 202 with task_id for frontend tracking via useBackgroundTasks.
    """
    conn = _get_conn()
    try:
        decision = ops.get_decision(conn, decision_id)
        if not decision:
            raise HTTPException(status_code=404, detail="Decision not found")

        project = ops.get_project(conn, decision.project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        commit_hash = decision.commit_hash
        repo_path = project.repo_path
        project_id = decision.project_id

        # Clean up old drafts (no-op for imported commits with no drafts)
        conn.execute(
            "DELETE FROM draft_changes WHERE draft_id IN (SELECT id FROM drafts WHERE decision_id = ?)",
            (decision_id,),
        )
        conn.execute(
            "DELETE FROM draft_tweets WHERE draft_id IN (SELECT id FROM drafts WHERE decision_id = ?)",
            (decision_id,),
        )
        conn.execute("DELETE FROM drafts WHERE decision_id = ?", (decision_id,))
        # Mark as processing — row stays visible in the UI.
        # The pipeline will update to the appropriate status (deferred_eval, draft, skip, etc.)
        conn.execute(
            "UPDATE decisions SET decision = 'processing' WHERE id = ?",
            (decision_id,),
        )
        conn.commit()
        ops.emit_data_event(conn, "decision", "updated", decision_id, project_id)
    finally:
        conn.close()

    def _blocking_retrigger():
        from social_hook.trigger import run_trigger

        exit_code = run_trigger(
            commit_hash=commit_hash,
            repo_path=repo_path,
            trigger_source="manual",
            existing_decision_id=decision_id,
        )
        return {"status": "retriggered" if exit_code == 0 else "failed", "exit_code": exit_code}

    task_id = _run_background_task(
        "retrigger",
        ref_id=f"retrigger-{decision_id}",
        project_id=project_id,
        fn=_blocking_retrigger,
    )
    return JSONResponse(
        status_code=202,
        content={"task_id": task_id, "status": "processing"},
    )


@app.post("/api/decisions/{decision_id}/rewind")
async def api_rewind_decision(decision_id: str, body: dict[str, Any] = Body(default={})):
    """Rewind a decision: keep the evaluation but delete all downstream artifacts.

    Body:
        force: bool (default false) - allow rewind even if drafts are posted
    """
    import shutil
    import sqlite3 as sqlite3_mod

    force = body.get("force", False)
    conn = _get_conn()
    try:
        decision = ops.get_decision(conn, decision_id)
        if not decision:
            raise HTTPException(status_code=404, detail="Decision not found")

        # Auto-snapshot before rewind (safety net)
        backup_name: str | None = "_pre_rewind"
        try:
            from social_hook.filesystem import get_base_path, get_db_path

            db_path = get_db_path()
            snap_dir = get_base_path() / "snapshots"
            snap_dir.mkdir(parents=True, exist_ok=True)
            snap_conn = sqlite3_mod.connect(str(db_path))
            snap_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            snap_conn.close()
            shutil.copy2(str(db_path), str(snap_dir / f"{backup_name}.db"))
        except Exception:
            backup_name = None

        try:
            result = ops.rewind_decision(conn, decision_id, force=force)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None

        if result is None:
            raise HTTPException(status_code=500, detail="Rewind failed")

        ops.emit_data_event(conn, "decision", "rewound", decision_id, decision.project_id)
        resp = {"status": "rewound", **result}
        if backup_name:
            resp["backup"] = backup_name
        return resp
    finally:
        conn.close()


@app.get("/api/platforms/enabled")
async def api_enabled_platforms():
    """Return all enabled platforms with their config."""
    config = _get_config()
    enabled = {}
    for name, pcfg in config.platforms.items():
        if pcfg.enabled:
            enabled[name] = {"priority": pcfg.priority, "type": pcfg.type}
    real_count = len(enabled)
    return {"platforms": enabled, "count": len(enabled), "real_count": real_count}


@app.post("/api/decisions/consolidate")
async def api_consolidate_decisions(body: dict[str, Any] = Body(...)):
    """Manually consolidate multiple decisions into a single draft.

    Body:
        decision_ids: List of decision IDs (at least 2)
    """
    decision_ids = body.get("decision_ids", [])
    if len(decision_ids) < 2:
        raise HTTPException(status_code=400, detail="At least 2 decisions required")

    conn = _get_conn()
    try:
        decisions = []
        for did in decision_ids:
            d = ops.get_decision(conn, did)
            if not d:
                raise HTTPException(status_code=404, detail=f"Decision not found: {did}")
            decisions.append(d)

        project_ids = {d.project_id for d in decisions}
        if len(project_ids) > 1:
            raise HTTPException(
                status_code=400, detail="All decisions must belong to the same project"
            )

        project = ops.get_project(conn, decisions[0].project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
    finally:
        conn.close()

    config = _get_config()

    from social_hook.config.project import ProjectConfig, load_project_config

    try:
        project_config = load_project_config(project.repo_path)
    except ConfigError:
        project_config = ProjectConfig(repo_path=project.repo_path)

    from social_hook.models import CommitInfo

    combined_summary = "\n".join(f"- {d.commit_message or d.commit_hash[:8]}" for d in decisions)
    commit = CommitInfo(
        hash=f"batch-{decisions[-1].id[:8]}",
        message=f"Combined {len(decisions)} commits:\n{combined_summary}",
        diff="",
        files_changed=[],
    )

    from social_hook.compat import evaluation_from_decision

    anchor = decisions[-1]
    evaluation = evaluation_from_decision(anchor, "draft")

    def _blocking_consolidate():
        import sqlite3 as _sqlite3

        from social_hook.drafting import draft_for_platforms
        from social_hook.llm.dry_run import DryRunContext
        from social_hook.llm.prompts import assemble_evaluator_context

        conn2 = _sqlite3.connect(str(get_db_path()))
        conn2.execute("PRAGMA busy_timeout = 5000")
        conn2.row_factory = _sqlite3.Row
        db = DryRunContext(conn2, dry_run=False)
        try:
            context = assemble_evaluator_context(
                db,
                project.id,
                project_config,
            )
            db.emit_data_event(
                "pipeline", PipelineStage.DRAFTING, anchor.commit_hash[:8], project.id
            )
            results = draft_for_platforms(
                config,
                conn2,
                db,
                project,
                decision_id=anchor.id,
                evaluation=evaluation,
                context=context,
                commit=commit,
                project_config=project_config,
            )
            return {"draft_ids": [r.draft.id for r in results], "count": len(results)}
        finally:
            conn2.close()

    def _on_consolidated(result: dict) -> None:
        from social_hook.drafting import DraftResult

        conn2 = _get_conn()
        try:
            from social_hook.scheduling import calculate_optimal_time

            draft_results = []
            for did in result["draft_ids"]:
                d = ops.get_draft(conn2, did)
                if d:
                    sched = calculate_optimal_time(conn2, d.project_id, platform=d.platform)
                    draft_results.append(DraftResult(draft=d, schedule=sched, thread_tweets=[]))
            if draft_results:
                from social_hook.notifications import notify_draft_review

                notify_draft_review(
                    config,
                    project_name=project.name,
                    project_id=project.id,
                    commit_hash=commit.hash,
                    commit_message=commit.message,
                    draft_results=draft_results,
                )
        except Exception:
            logger.debug("Consolidation notification failed", exc_info=True)
        finally:
            conn2.close()

    task_id = _run_background_task(
        "consolidate",
        ref_id=anchor.id,
        project_id=project.id,
        fn=_blocking_consolidate,
        on_success=_on_consolidated,
    )

    return JSONResponse(
        status_code=202,
        content={"task_id": task_id, "status": "processing"},
    )


# ---------------------------------------------------------------------------
# Rate Limits
# ---------------------------------------------------------------------------


@app.post("/api/snapshot/restore")
async def api_snapshot_restore(body: dict[str, Any] = Body(default={})):
    """Restore a snapshot while the server is running.

    Uses SQLite's backup API to copy pages directly between connections,
    avoiding file replacement and SHM corruption. Safe with concurrent
    readers (bridge loop, background threads, other endpoints).
    """
    name = body.get("name")
    if not name:
        raise HTTPException(400, "Missing 'name' field")

    if _restore_lock.locked():
        raise HTTPException(409, "Another restore is already in progress")

    snap_dir = get_db_path().parent / "snapshots"
    src = snap_dir / f"{name}.db"
    if not src.exists():
        raise HTTPException(404, f"Snapshot not found: {name}")

    db_path = get_db_path()
    backup_path = snap_dir / "_pre_restore.db"

    def _do_restore():
        """Run the blocking backup operations in a thread."""
        from social_hook.db.connection import get_connection, init_database

        # 1. Pre-restore backup using backup API (consistent even with open connections)
        if db_path.exists():
            pre_src = sqlite3.connect(str(db_path))
            pre_src.execute("PRAGMA busy_timeout = 5000")
            pre_dst = sqlite3.connect(str(backup_path))
            try:
                pre_src.backup(pre_dst)
            finally:
                pre_src.close()
                pre_dst.close()

        # 2. Restore: copy snapshot pages into live DB
        src_conn = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
        dst_conn = get_connection(db_path)  # WAL mode + busy_timeout
        try:
            dst_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            src_conn.backup(dst_conn)
        finally:
            src_conn.close()
            dst_conn.close()

        # 3. Apply migrations (snapshot may predate schema changes)
        new_conn = init_database(db_path)
        try:
            new_conn.execute(
                "INSERT INTO web_events (type, data) VALUES (?, ?)",
                ("data_change", json.dumps({"entity": "system", "action": "db_restored"})),
            )
            new_conn.commit()
            # 4. Checkpoint WAL to flush to main file — updates mtime so
            #    bridge's ResilientConnection detects the change and resets last_id
            new_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            new_conn.close()

    async with _restore_lock:
        try:
            await asyncio.to_thread(_do_restore)
        except Exception as e:
            raise HTTPException(500, f"Restore failed: {e}") from e

    return {"restored": True, "name": name, "backup": str(backup_path)}


@app.get("/api/rate-limits/status")
async def api_rate_limits_status():
    """Return current rate limit state for the dashboard."""
    from social_hook.rate_limits import get_rate_limit_status

    config = _get_config()
    conn = _get_conn()
    try:
        return get_rate_limit_status(conn, config.rate_limits)
    finally:
        conn.close()


@app.get("/api/tasks")
async def api_tasks(
    type: str | None = Query(None),
    ref_id: str | None = Query(None),
    project_id: str | None = Query(None),
    status: str | None = Query(None),
):
    """Query background tasks, e.g. to restore spinners on page refresh."""
    conn = _get_conn()
    try:
        clauses = []
        params: list[str] = []
        if type:
            clauses.append("type = ?")
            params.append(type)
        if ref_id:
            clauses.append("ref_id = ?")
            params.append(ref_id)
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = " AND ".join(clauses) if clauses else "1=1"
        rows = conn.execute(
            f"SELECT id, type, ref_id, project_id, status, result, error,"
            f" created_at, updated_at FROM background_tasks WHERE {where}"
            f" ORDER BY created_at DESC LIMIT 50",
            params,
        ).fetchall()
        return {
            "tasks": [
                {
                    "id": r["id"],
                    "type": r["type"],
                    "ref_id": r["ref_id"],
                    "project_id": r["project_id"],
                    "status": r["status"],
                    "result": safe_json_loads(r["result"], "background_tasks.result")
                    if r["result"]
                    else None,
                    "error": r["error"],
                    "created_at": (r["created_at"] + "Z")
                    if r["created_at"] and not r["created_at"].endswith("Z")
                    else r["created_at"],
                    "updated_at": (r["updated_at"] + "Z")
                    if r["updated_at"] and not r["updated_at"].endswith("Z")
                    else r["updated_at"],
                }
                for r in rows
            ]
        }
    finally:
        conn.close()


@app.get("/api/projects/{project_id}/arcs")
async def api_project_arcs(project_id: str):
    """Get all arcs for a project."""
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)

        rows = conn.execute(
            """
            SELECT * FROM arcs
            WHERE project_id = ?
            ORDER BY started_at DESC
        """,
            (project_id,),
        ).fetchall()
        return {"arcs": [dict(r) for r in rows]}
    finally:
        conn.close()


class ArcCreate(BaseModel):
    theme: str
    notes: str | None = None


class ArcUpdate(BaseModel):
    status: str | None = None
    notes: str | None = None


@app.post("/api/projects/{project_id}/arcs")
async def api_create_arc(project_id: str, body: ArcCreate):
    """Create a narrative arc for a project."""
    from social_hook.errors import MaxArcsError
    from social_hook.narrative.arcs import create_arc, update_arc

    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)

        try:
            arc_id = create_arc(conn, project_id, body.theme)
        except MaxArcsError:
            raise HTTPException(
                status_code=409,
                detail="Maximum 3 active arcs. Complete or abandon one first.",
            ) from None

        if body.notes:
            update_arc(conn, arc_id, notes=body.notes)

        ops.emit_data_event(conn, "arc", "created", arc_id, project_id)
        return {"arc_id": arc_id, "status": "created"}
    finally:
        conn.close()


@app.put("/api/projects/{project_id}/arcs/{arc_id}")
async def api_update_arc(project_id: str, arc_id: str, body: ArcUpdate):
    """Update a narrative arc (status, notes)."""
    from social_hook.errors import MaxArcsError
    from social_hook.models import ArcStatus
    from social_hook.narrative.arcs import resume_arc, update_arc

    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)

        arc = ops.get_arc(conn, arc_id)
        if not arc or arc.project_id != project_id:
            raise HTTPException(status_code=404, detail="Arc not found")

        if body.status is not None:
            valid = [s.value for s in ArcStatus]
            if body.status not in valid:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status '{body.status}'. Must be one of: {valid}",
                )
            # Resuming requires max-3 check
            if body.status == "active" and arc.status != "active":
                try:
                    resume_arc(conn, arc_id, project_id)
                except MaxArcsError:
                    raise HTTPException(
                        status_code=409,
                        detail="Maximum 3 active arcs. Complete or abandon one first.",
                    ) from None
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e)) from None
                # resume_arc already did the update, just update notes if provided
                if body.notes is not None:
                    update_arc(conn, arc_id, notes=body.notes)
                ops.emit_data_event(conn, "arc", "updated", arc_id, project_id)
                return {"status": "ok"}

        update_arc(conn, arc_id, status=body.status, notes=body.notes)
        ops.emit_data_event(conn, "arc", "updated", arc_id, project_id)
        return {"status": "ok"}
    finally:
        conn.close()


@app.get("/api/media/{file_path:path}")
async def api_media(file_path: str):
    """Serve a media file from the media cache directory."""
    media_dir = get_db_path().parent / "media-cache"
    requested = (media_dir / file_path).resolve()

    # Path traversal protection
    if not str(requested).startswith(str(media_dir.resolve())):
        raise HTTPException(status_code=403, detail="Access denied")

    if not requested.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(str(requested))


# ---------------------------------------------------------------------------
# Settings endpoints
# ---------------------------------------------------------------------------


@app.get("/api/wizard/templates")
async def api_get_wizard_templates():
    """Return content strategy templates for the setup wizard."""
    from social_hook.setup.templates import templates_to_dicts

    return {"templates": templates_to_dicts()}


@app.get("/api/wizard/detect-providers")
async def api_detect_providers():
    """Detect available LLM providers for the setup wizard."""
    import os

    from social_hook.setup.wizard import discover_providers

    providers = await asyncio.to_thread(discover_providers, dict(os.environ))
    return {"providers": providers}


@app.get("/api/settings/config")
async def api_get_config():
    """Return current config as JSON."""
    yaml_path = get_config_path()
    if yaml_path.exists():
        try:
            raw = yaml.safe_load(yaml_path.read_text()) or {}
        except yaml.YAMLError:
            raw = {}
    else:
        from social_hook.config.yaml import DEFAULT_CONFIG

        raw = DEFAULT_CONFIG.copy()

    # Mask any keys that look like API keys in the config
    return {"config": raw}


@app.put("/api/settings/config")
async def api_update_config(body: dict[str, Any]):
    """Update config sections (merge + validate before writing)."""
    from social_hook.config.yaml import save_config

    try:
        _merged, hook_warning = save_config(body, config_path=get_config_path())
    except ConfigError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    _invalidate_config()
    return {"status": "ok", **({"hook_warning": hook_warning} if hook_warning else {})}


@app.get("/api/settings/env")
async def api_get_env():
    """Return env var names with masked values."""
    env_path = get_env_path()
    env_vars: dict[str, str] = {}

    if env_path.exists():
        from dotenv import dotenv_values

        raw = dotenv_values(env_path)
        for key, value in raw.items():
            if value is not None:
                env_vars[key] = _mask_key(value)

    return {"env": env_vars, "known_keys": KNOWN_KEYS, "key_groups": KEY_GROUPS}


@app.put("/api/settings/env")
async def api_update_env(body: EnvUpdate):
    """Update a single .env key (or delete if value is None)."""
    if body.key not in KNOWN_KEYS:
        raise HTTPException(
            status_code=400, detail=f"Unknown key '{body.key}'. Allowed: {KNOWN_KEYS}"
        )

    env_path = get_env_path()
    lines: list[str] = []

    if env_path.exists():
        lines = env_path.read_text().splitlines()

    # Remove existing line for this key
    lines = [ln for ln in lines if not ln.startswith(f"{body.key}=")]

    # Add new line if value provided
    if body.value is not None:
        sanitized = _sanitize_value(body.value)
        lines.append(f'{body.key}="{sanitized}"')

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(lines) + "\n" if lines else "")

    _invalidate_config()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# OAuth 2.0 PKCE endpoints — multi-platform
# ---------------------------------------------------------------------------
# NOTE: The callback URL (http://localhost:<port>/api/oauth/{platform}/callback)
# must be registered in the platform's developer portal as a Redirect URI.


def _cleanup_expired_oauth_states() -> None:
    """Remove PKCE state entries older than _OAUTH_STATE_TTL_SECONDS."""
    now = time.time()
    expired = [k for k, (_, _, t) in _oauth_pending.items() if now - t > _OAUTH_STATE_TTL_SECONDS]
    for k in expired:
        del _oauth_pending[k]


def _get_oauth_credentials(platform: str) -> tuple[str, str]:
    """Read {PLATFORM}_CLIENT_ID and {PLATFORM}_CLIENT_SECRET from .env / environment.

    Returns:
        (client_id, client_secret)

    Raises:
        HTTPException 400 if client_id is missing.
    """
    from social_hook.config.env import load_env

    env = load_env()
    prefix = platform.upper()
    client_id = env.get(f"{prefix}_CLIENT_ID", "")
    client_secret = env.get(f"{prefix}_CLIENT_SECRET", "")
    if not client_id:
        raise HTTPException(
            status_code=400,
            detail=f"{prefix}_CLIENT_ID is not configured. Set it in Settings > API Keys first.",
        )
    return client_id, client_secret


def _validate_oauth_platform(platform: str) -> None:
    """Raise HTTPException 400 if platform is not in OAUTH_PLATFORMS."""
    from social_hook.setup.oauth import OAUTH_PLATFORMS

    if platform not in OAUTH_PLATFORMS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown OAuth platform: '{platform}'. Supported: {', '.join(sorted(OAUTH_PLATFORMS))}",
        )


@app.get("/api/oauth/{platform}/authorize")
async def api_oauth_authorize(platform: str, request: Request):
    """Initiate OAuth 2.0 PKCE flow for any supported platform.

    Generates a PKCE verifier/challenge and state, stores them server-side,
    builds the authorization URL, and returns it as JSON.
    """
    import secrets as _secrets

    from social_hook.setup.oauth import _build_auth_url, _generate_pkce

    _validate_oauth_platform(platform)
    _cleanup_expired_oauth_states()

    client_id, _client_secret = _get_oauth_credentials(platform)
    code_verifier, code_challenge = _generate_pkce()
    state = _secrets.token_urlsafe(32)

    # Determine redirect_uri from the current request so the port is correct.
    # Normalize 127.0.0.1 to localhost — OAuth providers treat them as different
    # redirect URIs, and developers typically register localhost.
    base_url = str(request.base_url).rstrip("/").replace("://127.0.0.1", "://localhost")
    redirect_uri = f"{base_url}/api/oauth/{platform}/callback"

    _oauth_pending[(platform, state)] = (code_verifier, redirect_uri, time.time())

    auth_url = _build_auth_url(client_id, state, code_challenge, redirect_uri, platform=platform)

    return {
        "auth_url": auth_url,
        "state": state,
        "callback_url": redirect_uri,
        "note": f"Ensure {redirect_uri} is registered as a Redirect URI in your {platform} developer portal.",
    }


@app.get("/api/oauth/{platform}/callback")
async def api_oauth_callback(platform: str, code: str = Query(...), state: str = Query(...)):
    """Handle the OAuth 2.0 callback after user authorizes.

    Exchanges the authorization code for tokens, saves them to the DB,
    validates with the platform's user-info endpoint, and returns a success HTML page.
    """
    from social_hook.setup.oauth import _exchange_code, _save_tokens, validate_token

    _validate_oauth_platform(platform)

    # Look up PKCE verifier from stored state (keyed by platform + state)
    pending = _oauth_pending.pop((platform, state), None)
    if pending is None:
        return HTMLResponse(
            "<h1>Authorization failed</h1>"
            "<p>Invalid or expired state parameter. Please try again.</p>",
            status_code=400,
        )

    code_verifier, redirect_uri, _ = pending

    client_id, client_secret = _get_oauth_credentials(platform)

    # Exchange authorization code for tokens
    resp = _exchange_code(
        code,
        code_verifier,
        client_id,
        client_secret,
        redirect_uri,
        platform=platform,
    )
    if resp.status_code != 200:
        return HTMLResponse(
            f"<h1>Token exchange failed</h1><p>HTTP {resp.status_code}: {resp.text[:300]}</p>",
            status_code=502,
        )

    tokens = resp.json()
    access_token = tokens.get("access_token", "")
    refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in", 7200)

    # Save tokens to DB
    _save_tokens(access_token, refresh_token, expires_in, platform=platform)

    # Validate token
    username = validate_token(platform, access_token)
    greeting = f" as <strong>@{username}</strong>" if username else ""

    return HTMLResponse(
        f"<html><body style='font-family:system-ui,sans-serif;text-align:center;padding:60px 20px'>"
        f"<h1>Authorization successful{greeting}!</h1>"
        f"<p>You can close this tab and return to the dashboard.</p>"
        f"<script>window.opener && window.opener.postMessage('oauth_complete','*');</script>"
        f"</body></html>"
    )


@app.get("/api/oauth/{platform}/status")
async def api_oauth_status(platform: str, request: Request):
    """Check if OAuth tokens exist in the DB for this platform.

    Returns:
        JSON with connected (bool), username (str), and callback_url (str).
    """
    from social_hook.adapters.auth import get_tokens
    from social_hook.setup.oauth import validate_token

    _validate_oauth_platform(platform)

    # Always include the correct callback URL (derived from server, not frontend)
    base_url = str(request.base_url).rstrip("/").replace("://127.0.0.1", "://localhost")
    callback_url = f"{base_url}/api/oauth/{platform}/callback"

    db_path = str(get_db_path())
    tokens = get_tokens(db_path, platform)
    if not tokens or not tokens.get("access_token"):
        return {"connected": False, "username": "", "callback_url": callback_url}

    # Validate and get username
    username = validate_token(platform, tokens["access_token"])

    return {"connected": True, "username": username, "callback_url": callback_url}


@app.delete("/api/oauth/{platform}/disconnect")
async def api_oauth_disconnect(platform: str):
    """Remove OAuth tokens from the DB for this platform."""
    from social_hook.adapters.auth import delete_tokens

    _validate_oauth_platform(platform)

    db_path = str(get_db_path())
    deleted = delete_tokens(db_path, platform)
    if deleted:
        # Clear cached adapter so next creation picks up the missing token
        from social_hook.scheduler import _registry

        _registry.invalidate(platform)
        return {"disconnected": True}
    return {"disconnected": False, "error": "No tokens found"}


@app.get("/api/settings/social-context")
async def api_get_social_context(project_path: str | None = None):
    """Read social-context.md content."""
    if project_path:
        sc_path = Path(project_path) / CONFIG_DIR_NAME / "social-context.md"
        if not sc_path.exists():
            # Fallback to global
            sc_path = get_db_path().parent / "social-context.md"
    else:
        sc_path = get_db_path().parent / "social-context.md"

    if not sc_path.exists():
        return {"content": "", "path": str(sc_path)}

    return {"content": sc_path.read_text(), "path": str(sc_path)}


@app.put("/api/settings/social-context")
async def api_update_social_context(body: SocialContextUpdate):
    """Write social-context.md content."""
    if body.project_path:
        project_dir = Path(body.project_path)
        if not project_dir.is_dir():
            raise HTTPException(
                status_code=400, detail=f"Project path not found: {body.project_path}"
            )
        sc_path = project_dir / CONFIG_DIR_NAME / "social-context.md"
    else:
        sc_path = get_db_path().parent / "social-context.md"

    sc_path.parent.mkdir(parents=True, exist_ok=True)
    sc_path.write_text(body.content)
    return {"status": "ok", "path": str(sc_path)}


@app.get("/api/settings/content-config")
async def api_get_content_config(project_path: str | None = None):
    """Read content-config.yaml content."""
    if project_path:
        cc_path = Path(project_path) / CONFIG_DIR_NAME / "content-config.yaml"
        if not cc_path.exists():
            cc_path = get_db_path().parent / "content-config.yaml"
    else:
        cc_path = get_db_path().parent / "content-config.yaml"

    if not cc_path.exists():
        return {"content": "", "path": str(cc_path)}

    return {"content": cc_path.read_text(), "path": str(cc_path)}


@app.put("/api/settings/content-config")
async def api_update_content_config(body: ContentConfigUpdate):
    """Write content-config.yaml (validates YAML first)."""
    # Validate YAML
    try:
        yaml.safe_load(body.content)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}") from None

    if body.project_path:
        project_dir = Path(body.project_path)
        if not project_dir.is_dir():
            raise HTTPException(
                status_code=400, detail=f"Project path not found: {body.project_path}"
            )
        cc_path = project_dir / CONFIG_DIR_NAME / "content-config.yaml"
    else:
        cc_path = get_db_path().parent / "content-config.yaml"

    cc_path.parent.mkdir(parents=True, exist_ok=True)
    cc_path.write_text(body.content)
    return {"status": "ok", "path": str(cc_path)}


@app.get("/api/settings/content-config/parsed")
async def api_get_content_config_parsed(project_path: str | None = None):
    """Return parsed content-config sections as structured JSON."""
    if project_path:
        cc_path = Path(project_path) / CONFIG_DIR_NAME / "content-config.yaml"
        if not cc_path.exists():
            cc_path = get_db_path().parent / "content-config.yaml"
    else:
        cc_path = get_db_path().parent / "content-config.yaml"

    if not cc_path.exists():
        return {"media_tools": {}, "strategy": {}, "context": {}, "summary": {}}

    try:
        raw = yaml.safe_load(cc_path.read_text()) or {}
    except yaml.YAMLError:
        raw = {}

    # Merge structural defaults so the UI always shows all tool slots,
    # even if the YAML doesn't mention them yet
    yaml_tools = raw.get("media_tools", {})
    merged_tools: dict[str, dict[str, object]] = {name: {} for name in DEFAULT_MEDIA_GUIDANCE}
    merged_tools.update(yaml_tools)

    return {
        "media_tools": merged_tools,
        "strategy": raw.get("strategy", {}),
        "context": raw.get("context", {}),
        "summary": raw.get("summary", {}),
    }


@app.put("/api/settings/content-config/parsed")
async def api_update_content_config_parsed(
    body: dict[str, Any] = Body(...), project_path: str | None = None
):
    """Update specific content-config sections (merge + write)."""
    if project_path:
        project_dir = Path(project_path)
        if not project_dir.is_dir():
            raise HTTPException(status_code=400, detail=f"Project path not found: {project_path}")
        cc_path = project_dir / CONFIG_DIR_NAME / "content-config.yaml"
    else:
        cc_path = get_db_path().parent / "content-config.yaml"

    # Read existing
    if cc_path.exists():
        try:
            current = yaml.safe_load(cc_path.read_text()) or {}
        except yaml.YAMLError:
            current = {}
    else:
        current = {}

    # Merge only recognized sections
    for section in ("media_tools", "strategy", "context", "summary"):
        if section in body:
            if isinstance(body[section], dict) and isinstance(current.get(section), dict):
                current[section].update(body[section])
            else:
                current[section] = body[section]

    # Write back
    cc_path.parent.mkdir(parents=True, exist_ok=True)
    cc_path.write_text(yaml.dump(current, default_flow_style=False, sort_keys=False))

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Memory endpoints (per-project voice memories)
# ---------------------------------------------------------------------------


@app.get("/api/settings/memories")
async def api_get_memories(project_path: str):
    """List all memories for a project."""
    from social_hook.config.project import list_memories

    if not Path(project_path).is_dir():
        raise HTTPException(status_code=400, detail=f"Project path not found: {project_path}")
    memories = list_memories(project_path)
    return {"memories": memories, "count": len(memories)}


@app.post("/api/settings/memories")
async def api_add_memory(body: MemoryCreate):
    """Add a new memory entry."""
    from social_hook.config.project import save_memory

    if not Path(body.project_path).is_dir():
        raise HTTPException(status_code=400, detail=f"Project path not found: {body.project_path}")
    save_memory(body.project_path, body.context, body.feedback, body.draft_id)
    return {"status": "ok"}


@app.delete("/api/settings/memories/{index}")
async def api_delete_memory(index: int, project_path: str):
    """Delete a memory by 0-based index."""
    from social_hook.config.project import delete_memory

    if not Path(project_path).is_dir():
        raise HTTPException(status_code=400, detail=f"Project path not found: {project_path}")
    try:
        delete_memory(project_path, index)
    except (IndexError, FileNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    return {"status": "ok"}


@app.post("/api/settings/memories/clear")
async def api_clear_memories(project_path: str):
    """Clear all memories for a project."""
    from social_hook.config.project import clear_memories

    if not Path(project_path).is_dir():
        raise HTTPException(status_code=400, detail=f"Project path not found: {project_path}")
    count = clear_memories(project_path)
    return {"status": "ok", "count": count}


@app.put("/api/projects/{project_id}/pause")
async def api_toggle_pause(project_id: str):
    """Toggle a project's paused state."""
    conn = _get_conn()
    try:
        project = ops.get_project(conn, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        new_paused = not project.paused
        ops.set_project_paused(conn, project_id, new_paused)
        ops.emit_data_event(conn, "project", "updated", project_id, project_id)
        return {"status": "ok", "paused": new_paused}
    finally:
        conn.close()


@app.get("/api/projects/{project_id}/branches")
async def api_get_branches(project_id: str):
    """List available local git branches for a project."""
    conn = _get_conn()
    try:
        project = ops.get_project(conn, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
    finally:
        conn.close()

    import subprocess

    repo_path = project.repo_path

    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "branch", "--format=%(refname:short)"],
            capture_output=True,
            text=True,
            check=True,
        )
        branches = [b.strip() for b in result.stdout.strip().split("\n") if b.strip()]
    except (subprocess.CalledProcessError, OSError):
        return {"branches": [], "current": None, "error": "Repository not accessible"}

    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        current: str | None = result.stdout.strip()
        if current == "HEAD":
            current = None
    except (subprocess.CalledProcessError, OSError):
        current = None

    return {"branches": branches, "current": current}


@app.put("/api/projects/{project_id}/trigger-branch")
async def api_set_trigger_branch(project_id: str, body: dict = Body(...)):
    """Set the trigger branch filter for a project."""
    conn = _get_conn()
    try:
        project = ops.get_project(conn, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        branch = body.get("branch")
        ops.set_project_trigger_branch(conn, project_id, branch)
        ops.emit_data_event(conn, "project", "updated", project_id, project_id)
        return {"status": "ok", "trigger_branch": branch}
    finally:
        conn.close()


class SummaryUpdate(BaseModel):
    summary: str


@app.put("/api/projects/{project_id}/summary")
async def api_update_summary(project_id: str, body: SummaryUpdate):
    """Update a project's summary text."""
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)
        ops.update_project_summary(conn, project_id, body.summary)
        ops.emit_data_event(conn, "project", "updated", project_id, project_id)
        return {"status": "ok"}
    finally:
        conn.close()


@app.post("/api/projects/{project_id}/regenerate-summary")
async def api_regenerate_summary(project_id: str):
    """Regenerate a project's summary using LLM discovery."""
    conn = _get_conn()
    try:
        project = ops.get_project(conn, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        config = _get_config()
        evaluator_model = config.models.evaluator

        from social_hook.llm.discovery import discover_project
        from social_hook.llm.factory import create_client

        client = create_client(evaluator_model, config)

        from social_hook.config.project import load_project_config

        project_config = load_project_config(project.repo_path)
        max_discovery_tokens = (
            project_config.context.max_discovery_tokens if project_config else 60000
        )
        max_file_size = project_config.context.max_file_size if project_config else 256000
        project_docs = project_config.context.project_docs if project_config else None

        summary, files, file_summaries, prompt_docs = await asyncio.to_thread(
            discover_project,
            client,
            project.repo_path,
            project_docs=project_docs,
            max_discovery_tokens=max_discovery_tokens,
            max_file_size=max_file_size,
            db=conn,
            project_id=project_id,
            on_progress=lambda stage: ops.emit_data_event(
                conn, "pipeline", stage, project_id, project_id
            ),
        )

        if summary:
            ops.update_project_summary(conn, project_id, summary)
            if files:
                ops.update_discovery_files(conn, project_id, files)
            if file_summaries:
                ops.upsert_file_summaries(conn, project_id, file_summaries)
            if prompt_docs:
                ops.update_prompt_docs(conn, project_id, prompt_docs)
            ops.emit_data_event(conn, "project", "updated", project_id, project_id)

        return {"summary": summary or ""}
    finally:
        conn.close()


@app.post("/api/settings/validate-key")
async def api_validate_key(body: ValidateKeyRequest):
    """Validate an API key by attempting a lightweight API call."""
    provider = body.provider.lower()

    if provider == "anthropic":
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=body.key)
            # Lightweight call to validate key
            client.models.list(limit=1)
            return {"valid": True, "provider": provider}
        except Exception as e:
            return {"valid": False, "provider": provider, "error": str(e)}

    elif provider == "openai":
        try:
            import openai

            oai_client = openai.OpenAI(api_key=body.key)
            oai_client.models.list()
            return {"valid": True, "provider": provider}
        except Exception as e:
            return {"valid": False, "provider": provider, "error": str(e)}

    else:
        return {"valid": False, "provider": provider, "error": f"Unknown provider: {provider}"}


# ---------------------------------------------------------------------------
# Installation endpoints
# ---------------------------------------------------------------------------


@app.get("/api/installations/status")
async def api_installations_status():
    from social_hook.bot.process import is_running
    from social_hook.setup.install import (
        check_cron_installed,
        check_hook_installed,
        check_narrative_hook_installed,
    )

    # Reap zombie if needed before checking
    if _bot_proc is not None:
        _bot_proc.poll()

    return {
        "commit_hook": check_hook_installed(),
        "narrative_hook": check_narrative_hook_installed(),
        "scheduler_cron": check_cron_installed(),
        "bot_daemon": is_running(),
    }


@app.post("/api/installations/{component}/install")
async def api_install_component(component: str):
    from social_hook.setup.install import install_cron, install_hook, install_narrative_hook

    install_fns = {
        "commit_hook": install_hook,
        "narrative_hook": install_narrative_hook,
        "scheduler_cron": install_cron,
    }
    fn = install_fns.get(component)
    if not fn:
        raise HTTPException(status_code=400, detail=f"Unknown component: {component}")

    if component == "commit_hook":
        # Pass registered project repo paths for mutual exclusion check
        conn = _get_conn()
        try:
            rows = conn.execute("SELECT repo_path FROM projects").fetchall()
            repo_paths = [r["repo_path"] for r in rows]
        finally:
            conn.close()
        success, message = fn(git_hook_repo_paths=repo_paths)  # type: ignore[operator]
    else:
        success, message = fn()  # type: ignore[operator]
    return {"success": success, "message": message}


@app.post("/api/installations/{component}/uninstall")
async def api_uninstall_component(component: str):
    from social_hook.setup.install import uninstall_cron, uninstall_hook, uninstall_narrative_hook

    uninstall_fns = {
        "commit_hook": uninstall_hook,
        "narrative_hook": uninstall_narrative_hook,
        "scheduler_cron": uninstall_cron,
    }
    fn = uninstall_fns.get(component)
    if not fn:
        raise HTTPException(status_code=400, detail=f"Unknown component: {component}")
    success, message = fn()  # type: ignore[operator]
    return {"success": success, "message": message}


_bot_proc: "subprocess.Popen | None" = None  # Single-worker: safe as module state


@app.post("/api/installations/bot_daemon/start")
async def api_start_bot_daemon():
    import shutil
    import subprocess as sp
    import sys

    from social_hook.bot.process import get_pid_file, is_running, stop_bot
    from social_hook.filesystem import get_base_path

    global _bot_proc
    # Reap any previous zombie
    if _bot_proc is not None:
        _bot_proc.poll()
        _bot_proc = None

    # Stop any existing daemon first — only one can poll a Telegram token.
    # This handles the case where a daemon was started from a different
    # worktree or the main branch and is now stale.
    if is_running():
        await asyncio.to_thread(stop_bot)
        await asyncio.sleep(0.5)
    try:
        # Launch directly in foreground mode (no --daemon) with detached session.
        # Avoids the double-Popen problem where --daemon spawns another child,
        # leaving a gap where is_running() returns false.
        binary = shutil.which(PROJECT_SLUG) or PROJECT_SLUG
        log_path = get_base_path() / "logs" / "bot.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fd = open(log_path, "a")  # noqa: SIM115

        kwargs: dict = {"stdout": log_fd, "stderr": log_fd, "stdin": sp.DEVNULL}
        if sys.platform == "win32":
            kwargs["creationflags"] = sp.DETACHED_PROCESS | sp.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True

        proc = sp.Popen([binary, "bot", "start"], **kwargs)
        log_fd.close()  # Child inherited the FD; parent doesn't need it
        _bot_proc = proc

        # Write PID eagerly so is_running() returns true immediately,
        # preventing duplicate daemons from concurrent start requests.
        pid_file = get_pid_file()
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(proc.pid))

        return {"success": True, "message": "Bot daemon starting"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.post("/api/installations/bot_daemon/stop")
async def api_stop_bot_daemon():
    from social_hook.bot.process import is_running, stop_bot

    global _bot_proc
    if not is_running():
        return {"success": True, "message": "Bot daemon is not running"}
    if await asyncio.to_thread(stop_bot):
        # Reap after stopping
        if _bot_proc is not None:
            _bot_proc.poll()
            _bot_proc = None
        return {"success": True, "message": "Bot daemon stopped"}
    return {"success": False, "message": "Failed to stop bot daemon"}


# ---------------------------------------------------------------------------
# Channels endpoints
# ---------------------------------------------------------------------------

_CHANNEL_CREDENTIALS = {
    "telegram": "TELEGRAM_BOT_TOKEN",
}


@app.get("/api/channels/status")
async def api_channels_status():
    """Return status of all known channels and daemon running state."""
    from social_hook.bot.process import is_running

    # Reap zombie if needed before checking
    if _bot_proc is not None:
        _bot_proc.poll()

    config = _get_config()
    channels_status = {}
    for name in sorted(KNOWN_CHANNELS):
        if name == "web":
            web_ch = config.channels.get("web")
            channels_status[name] = {
                "enabled": web_ch.enabled if web_ch else True,
                "credentials_configured": True,
                "allowed_chat_ids": [],
            }
            continue
        ch_cfg = config.channels.get(name)
        cred_key = _CHANNEL_CREDENTIALS.get(name)
        channels_status[name] = {
            "enabled": ch_cfg.enabled if ch_cfg else False,
            "credentials_configured": bool(config.env.get(cred_key)) if cred_key else False,
            "allowed_chat_ids": ch_cfg.allowed_chat_ids if ch_cfg else [],
        }
    return {"channels": channels_status, "daemon_running": is_running()}


@app.post("/api/channels/{channel}/test")
async def api_test_channel(channel: str):
    """Test channel connectivity."""
    if channel not in KNOWN_CHANNELS:
        raise HTTPException(status_code=400, detail=f"Unknown channel: {channel}")

    if channel == "web":
        return {"success": True, "info": {"status": "Built-in, always available"}}

    if channel == "slack":
        return {"success": False, "error": "Slack support coming soon"}

    if channel == "telegram":
        config = _get_config()
        tg_token = config.env.get("TELEGRAM_BOT_TOKEN")
        if not tg_token:
            return {"success": False, "error": "TELEGRAM_BOT_TOKEN not configured"}
        try:
            import requests

            resp = await asyncio.to_thread(
                requests.get,
                f"https://api.telegram.org/bot{tg_token}/getMe",
                timeout=5,
            )
            data = resp.json()
            if data.get("ok") and data.get("result", {}).get("username"):
                return {"success": True, "info": {"username": data["result"]["username"]}}
            return {"success": False, "error": "Failed to connect to Telegram API"}
        except Exception:
            return {"success": False, "error": "Failed to connect to Telegram API"}

    return {"success": False, "error": f"Testing not supported for {channel}"}


# ---------------------------------------------------------------------------
# Filesystem browser
# ---------------------------------------------------------------------------


@app.get("/api/filesystem/browse")
async def api_browse_directory(path: str = Query(default="~")):
    """List subdirectories for folder picker UI. Local-mode only."""
    resolved = Path(path).expanduser().resolve()

    home = Path.home().resolve()
    if not resolved.is_relative_to(home):
        raise HTTPException(status_code=403, detail="Access restricted to home directory")

    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail="Not a directory")

    dirs = []
    try:
        for d in sorted(resolved.iterdir(), key=lambda x: x.name.lower()):
            if d.is_dir() and not d.name.startswith("."):
                dirs.append(
                    {
                        "name": d.name,
                        "path": str(d),
                        "is_git": (d / ".git").exists(),
                    }
                )
    except PermissionError:
        pass

    return {
        "current": str(resolved),
        "parent": str(resolved.parent) if resolved != home else str(home),
        "is_git": (resolved / ".git").exists(),
        "directories": dirs,
    }


# ---------------------------------------------------------------------------
# Per-project git hook endpoints
# ---------------------------------------------------------------------------


@app.get("/api/projects/{project_id}/git-hook/status")
async def api_git_hook_status(project_id: str):
    """Check if git post-commit hook is installed for a project."""
    from social_hook.setup.install import check_git_hook_installed

    conn = _get_conn()
    try:
        row = _get_project_or_404(conn, project_id)
        return {"installed": check_git_hook_installed(row["repo_path"])}
    finally:
        conn.close()


@app.post("/api/projects/{project_id}/git-hook/install")
async def api_git_hook_install(project_id: str):
    """Install git post-commit hook for a project."""
    from social_hook.setup.install import install_git_hook

    conn = _get_conn()
    try:
        row = _get_project_or_404(conn, project_id)
        success, message = install_git_hook(row["repo_path"])
        if success:
            ops.emit_data_event(conn, "project", "updated", project_id, project_id)
        return {"success": success, "message": message}
    finally:
        conn.close()


@app.post("/api/projects/{project_id}/git-hook/uninstall")
async def api_git_hook_uninstall(project_id: str):
    """Remove git post-commit hook from a project."""
    from social_hook.setup.install import uninstall_git_hook

    conn = _get_conn()
    try:
        row = _get_project_or_404(conn, project_id)
        success, message = uninstall_git_hook(row["repo_path"])
        if success:
            ops.emit_data_event(conn, "project", "updated", project_id, project_id)
        return {"success": success, "message": message}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Project registration / deletion
# ---------------------------------------------------------------------------


class RegisterProjectBody(BaseModel):
    repo_path: str
    name: str | None = None
    install_git_hook: bool = True


@app.post("/api/projects/register")
async def api_register_project(body: RegisterProjectBody):
    """Register a new project from the web UI."""
    from social_hook.db.operations import register_project
    from social_hook.setup.install import install_git_hook as do_install_git_hook

    conn = _get_conn()
    try:
        project, repo_origin = register_project(conn, body.repo_path, body.name)

        hook_message = None
        if body.install_git_hook:
            _success, hook_message = do_install_git_hook(project.repo_path)

        ops.emit_data_event(conn, "project", "created", project.id, project.id)
        return {
            "status": "created",
            "project": {
                "id": project.id,
                "name": project.name,
                "repo_path": project.repo_path,
                "repo_origin": repo_origin,
            },
            "git_hook": hook_message,
        }
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    finally:
        conn.close()


@app.delete("/api/projects/{project_id}")
async def api_delete_project(project_id: str):
    """Unregister a project and delete all its data."""
    from social_hook.setup.install import uninstall_git_hook

    conn = _get_conn()
    try:
        project = ops.get_project(conn, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        uninstall_git_hook(project.repo_path)
        ops.delete_project(conn, project_id)
        ops.emit_data_event(conn, "project", "deleted", project_id, project_id)
        return {"status": "deleted", "project_id": project_id}
    finally:
        conn.close()


# =============================================================================
# Platform Introduced (per-platform introduction tracking)
# =============================================================================


@app.get("/api/projects/{project_id}/introduced")
async def api_project_introduced(project_id: str):
    """Get per-platform introduction status for a project."""
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)
        rows = conn.execute(
            "SELECT platform, introduced, introduced_at FROM platform_introduced WHERE project_id = ?",
            (project_id,),
        ).fetchall()
        platforms = {}
        for row in rows:
            platforms[row[0]] = {
                "introduced": bool(row[1]),
                "introduced_at": row[2],
            }
        return {"platforms": platforms}
    finally:
        conn.close()


class IntroducedResetBody(BaseModel):
    platform: str | None = None


@app.post("/api/projects/{project_id}/introduced/reset")
async def api_project_introduced_reset(project_id: str, body: IntroducedResetBody):
    """Reset introduction status for a platform or all platforms."""
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)
        count = ops.reset_platform_introduced(conn, project_id, body.platform)
        ops.emit_data_event(conn, "project", "updated", project_id, project_id)
        return {"reset": count, "platform": body.platform or "all"}
    finally:
        conn.close()


class IntroducedSetBody(BaseModel):
    platform: str
    value: bool = True


@app.post("/api/projects/{project_id}/introduced/set")
async def api_project_introduced_set(project_id: str, body: IntroducedSetBody):
    """Set introduction status for a specific platform."""
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)
        ops.set_platform_introduced(conn, project_id, body.platform, body.value)
        ops.emit_data_event(conn, "project", "updated", project_id, project_id)
        return {"platform": body.platform, "introduced": body.value}
    finally:
        conn.close()


# =============================================================================
# Platform Credentials
# =============================================================================


@app.get("/api/platform-credentials")
async def api_list_platform_credentials():
    """List platform credential entries from config."""
    config = _get_config()
    entries = {}
    for name, cred in config.platform_credentials.items():
        entries[name] = {
            "platform": cred.platform,
            "client_id_set": bool(cred.client_id),
            "client_secret_set": bool(cred.client_secret),
        }
    return {"platform_credentials": entries}


@app.post("/api/platform-credentials")
async def api_add_platform_credential(body: dict[str, Any] = Body(...)):
    """Add a platform credential entry to config."""
    from social_hook.config.yaml import save_config

    try:
        check_unknown_keys(
            body,
            {"name", "platform", "client_id", "client_secret"},
            "platform-credentials",
            strict=True,
        )
    except ConfigError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None

    name = body.get("name")
    platform = body.get("platform")
    if not name or not platform:
        raise HTTPException(status_code=400, detail="'name' and 'platform' are required")

    cred_data = {"platform": platform}
    if body.get("client_id"):
        cred_data["client_id"] = body["client_id"]
    if body.get("client_secret"):
        cred_data["client_secret"] = body["client_secret"]

    try:
        save_config(
            {"platform_credentials": {name: cred_data}},
            config_path=get_config_path(),
        )
    except ConfigError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    _invalidate_config()
    ops.emit_data_event(_get_conn(), "config", "updated", "platform_credentials")
    return {"status": "created", "name": name}


@app.put("/api/platform-credentials/{name}")
async def api_update_platform_credential(name: str, body: dict[str, Any] = Body(...)):
    """Update a platform credential entry."""
    from social_hook.config.yaml import save_config

    config = _get_config()
    if name not in config.platform_credentials:
        raise HTTPException(status_code=404, detail=f"Credential '{name}' not found")

    try:
        check_unknown_keys(
            body,
            {"platform", "client_id", "client_secret"},
            "platform-credentials",
            strict=True,
        )
    except ConfigError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None

    try:
        save_config(
            {"platform_credentials": {name: body}},
            config_path=get_config_path(),
            deep_merge=True,
        )
    except ConfigError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    _invalidate_config()
    ops.emit_data_event(_get_conn(), "config", "updated", "platform_credentials")
    return {"status": "updated", "name": name}


@app.delete("/api/platform-credentials/{name}")
async def api_delete_platform_credential(name: str):
    """Remove a platform credential entry. 409 if accounts reference it."""
    config = _get_config()
    if name not in config.platform_credentials:
        raise HTTPException(status_code=404, detail=f"Credential '{name}' not found")

    # Check if any accounts reference this credential
    for acct_name, acct in config.accounts.items():
        if acct.app == name:
            raise HTTPException(
                status_code=409,
                detail=f"Account '{acct_name}' references credential '{name}'",
            )

    # Remove from config by loading raw YAML
    yaml_path = get_config_path()
    try:
        raw = yaml.safe_load(yaml_path.read_text()) or {}
    except yaml.YAMLError:
        raw = {}
    pc = raw.get("platform_credentials", {})
    pc.pop(name, None)
    raw["platform_credentials"] = pc
    yaml_path.write_text(yaml.dump(raw, default_flow_style=False, sort_keys=False))
    _invalidate_config()
    ops.emit_data_event(_get_conn(), "config", "updated", "platform_credentials")
    return {"status": "deleted", "name": name}


@app.post("/api/platform-credentials/{name}/validate")
async def api_validate_platform_credential(name: str):
    """Validate a platform credential entry."""
    config = _get_config()
    if name not in config.platform_credentials:
        raise HTTPException(status_code=404, detail=f"Credential '{name}' not found")

    cred = config.platform_credentials[name]
    issues = []
    if not cred.client_id:
        issues.append("client_id is empty")
    if not cred.client_secret:
        issues.append("client_secret is empty")

    if issues:
        return {"valid": False, "issues": issues}
    return {"valid": True, "issues": []}


# =============================================================================
# Accounts
# =============================================================================


@app.get("/api/accounts")
async def api_list_accounts():
    """List accounts from config."""
    config = _get_config()
    accounts = {}
    for name, acct in config.accounts.items():
        accounts[name] = {
            "platform": acct.platform,
            "app": acct.app,
            "tier": acct.tier,
            "identity": acct.identity,
            "entity": acct.entity,
        }
    return {"accounts": accounts}


@app.post("/api/accounts")
async def api_add_account(body: dict[str, Any] = Body(...)):
    """Initiate account add. Returns auth_url for PKCE redirect."""
    from social_hook.config.yaml import save_config

    try:
        check_unknown_keys(
            body,
            {"name", "platform", "app", "tier", "identity", "entity"},
            "accounts",
            strict=True,
        )
    except ConfigError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None

    name = body.get("name")
    platform = body.get("platform")
    if not name or not platform:
        raise HTTPException(status_code=400, detail="'name' and 'platform' are required")

    acct_data: dict[str, Any] = {"platform": platform}
    for field in ("app", "tier", "identity", "entity"):
        if body.get(field) is not None:
            acct_data[field] = body[field]

    try:
        save_config(
            {"accounts": {name: acct_data}},
            config_path=get_config_path(),
        )
    except ConfigError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    _invalidate_config()

    # Return auth URL if PKCE auth module is available
    # Note: PKCE auth flow (build_auth_url) is not yet implemented in adapters/auth.py
    auth_url = None

    ops.emit_data_event(_get_conn(), "config", "updated", "accounts")
    result: dict[str, Any] = {"status": "created", "name": name}
    if auth_url:
        result["auth_url"] = auth_url
    return result


@app.delete("/api/accounts/{name}")
async def api_delete_account(name: str):
    """Remove an account. 409 if targets reference it."""
    config = _get_config()
    if name not in config.accounts:
        raise HTTPException(status_code=404, detail=f"Account '{name}' not found")

    # Check if any targets reference this account
    for tgt_name, tgt in config.targets.items():
        if tgt.account == name:
            raise HTTPException(
                status_code=409,
                detail=f"Target '{tgt_name}' references account '{name}'",
            )

    # Remove from config
    yaml_path = get_config_path()
    try:
        raw = yaml.safe_load(yaml_path.read_text()) or {}
    except yaml.YAMLError:
        raw = {}
    accts = raw.get("accounts", {})
    accts.pop(name, None)
    raw["accounts"] = accts
    yaml_path.write_text(yaml.dump(raw, default_flow_style=False, sort_keys=False))
    _invalidate_config()

    # Also delete OAuth token if present
    conn = _get_conn()
    try:
        ops.delete_oauth_token(conn, name)
        ops.emit_data_event(conn, "config", "updated", "accounts")
    finally:
        conn.close()

    return {"status": "deleted", "name": name}


@app.post("/api/accounts/validate")
async def api_validate_accounts():
    """Validate all account credentials."""
    config = _get_config()
    results: dict[str, dict] = {}
    conn = _get_conn()
    try:
        for name, _acct in config.accounts.items():
            token = ops.get_oauth_token(conn, name)
            if token:
                results[name] = {"valid": True, "has_token": True}
            else:
                results[name] = {"valid": False, "has_token": False, "issue": "No OAuth token"}
    finally:
        conn.close()
    return {"accounts": results}


# =============================================================================
# Targets (per-project)
# =============================================================================


@app.get("/api/projects/{project_id}/targets")
async def api_list_targets(project_id: str):
    """List targets for a project."""
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)
    finally:
        conn.close()

    config = _get_config()
    targets_list = []
    for name, tgt in config.targets.items():
        account = config.accounts.get(tgt.account)
        targets_list.append(
            {
                "id": name,
                "project_id": project_id,
                "account_name": tgt.account,
                "destination": tgt.destination,
                "strategy": tgt.strategy,
                "primary": tgt.primary,
                "source": tgt.source,
                "community_id": tgt.community_id,
                "share_with_followers": tgt.share_with_followers,
                "frequency": tgt.frequency,
                "enabled": True,  # All config-defined targets are enabled
                "platform": account.platform if account else "unknown",
                "created_at": None,
            }
        )
    return {"targets": targets_list, "project_id": project_id}


@app.post("/api/projects/{project_id}/targets")
async def api_add_target(project_id: str, body: dict[str, Any] = Body(...)):
    """Add a target."""
    from social_hook.config.yaml import save_config

    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)
    finally:
        conn.close()

    try:
        check_unknown_keys(
            body,
            {
                "name",
                "account",
                "destination",
                "strategy",
                "primary",
                "source",
                "community_id",
                "share_with_followers",
                "frequency",
                "scheduling",
            },
            "targets",
            strict=True,
        )
    except ConfigError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None

    account = body.get("account")
    if not account:
        raise HTTPException(status_code=400, detail="'account' is required")
    name = body.get("name")
    if not name:
        # Auto-generate name from account + destination
        destination = body.get("destination", "timeline")
        name = f"{account}-{destination}"

    tgt_data: dict[str, Any] = {"account": account}
    for field in (
        "destination",
        "strategy",
        "primary",
        "source",
        "community_id",
        "share_with_followers",
        "frequency",
        "scheduling",
    ):
        if body.get(field) is not None:
            tgt_data[field] = body[field]

    try:
        save_config(
            {"targets": {name: tgt_data}},
            config_path=get_config_path(),
        )
    except ConfigError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    _invalidate_config()
    conn = _get_conn()
    try:
        ops.emit_data_event(conn, "config", "updated", "targets", project_id)
    finally:
        conn.close()
    return {"status": "created", "name": name}


@app.put("/api/projects/{project_id}/targets/{name}")
async def api_update_target(project_id: str, name: str, body: dict[str, Any] = Body(...)):
    """Update a target."""
    from social_hook.config.yaml import save_config

    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)
    finally:
        conn.close()

    config = _get_config()
    if name not in config.targets:
        raise HTTPException(status_code=404, detail=f"Target '{name}' not found")

    try:
        check_unknown_keys(
            body,
            {
                "account",
                "destination",
                "strategy",
                "primary",
                "source",
                "community_id",
                "share_with_followers",
                "frequency",
                "scheduling",
            },
            "targets",
            strict=True,
        )
    except ConfigError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None

    try:
        save_config(
            {"targets": {name: body}},
            config_path=get_config_path(),
            deep_merge=True,
        )
    except ConfigError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    _invalidate_config()
    conn = _get_conn()
    try:
        ops.emit_data_event(conn, "config", "updated", "targets", project_id)
    finally:
        conn.close()
    return {"status": "updated", "name": name}


@app.put("/api/projects/{project_id}/targets/{name}/disable")
async def api_disable_target(project_id: str, name: str):
    """Disable a target and archive pending drafts."""
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)

        # Cancel pending drafts for this target
        pending = conn.execute(
            "SELECT id FROM drafts WHERE project_id = ? AND target_id = ? AND status IN ('draft', 'approved', 'scheduled', 'deferred')",
            (project_id, name),
        ).fetchall()
        for row in pending:
            ops.update_draft(conn, row["id"], status="cancelled")
            ops.emit_data_event(conn, "draft", "updated", row["id"], project_id)

        ops.emit_data_event(conn, "config", "updated", "targets", project_id)
    finally:
        conn.close()

    # Note: targets live in config.yaml, not DB. The web UI tracks disabled state separately.
    return {"status": "disabled", "name": name, "cancelled_drafts": len(pending)}


@app.put("/api/projects/{project_id}/targets/{name}/enable")
async def api_enable_target(project_id: str, name: str):
    """Re-enable a target."""
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)
        ops.emit_data_event(conn, "config", "updated", "targets", project_id)
    finally:
        conn.close()
    return {"status": "enabled", "name": name}


@app.delete("/api/projects/{project_id}/targets/{name}")
async def api_delete_target(project_id: str, name: str):
    """Remove a target from config and cancel its pending drafts."""
    cancelled_count = 0
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)

        config = _get_config()
        if name not in config.targets:
            raise HTTPException(status_code=404, detail=f"Target '{name}' not found")

        # Cancel pending drafts for this target
        _placeholders = ",".join("?" for _ in PENDING_STATUSES)
        pending = conn.execute(
            f"SELECT id FROM drafts WHERE project_id = ? AND target_id = ? AND status IN ({_placeholders})",
            (project_id, name, *PENDING_STATUSES),
        ).fetchall()
        for row in pending:
            ops.update_draft(conn, row["id"], status="cancelled")
            ops.emit_data_event(conn, "draft", "updated", row["id"], project_id)
        cancelled_count = len(pending)

        ops.emit_data_event(conn, "config", "updated", "targets", project_id)
    finally:
        conn.close()

    # Remove from config.yaml
    from social_hook.config.yaml import delete_config_key

    delete_config_key(get_config_path(), "targets", name)
    _invalidate_config()

    return {"status": "deleted", "name": name, "cancelled_drafts": cancelled_count}


# =============================================================================
# Strategies (per-project)
# =============================================================================


@app.get("/api/projects/{project_id}/strategies")
async def api_list_strategies(project_id: str):
    """List strategies: built-in templates merged with project overrides."""
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)
    finally:
        conn.close()

    config = _get_config()
    strategies = {}
    for name, strat in config.content_strategies.items():
        strategies[name] = {
            "audience": strat.audience,
            "voice": strat.voice,
            "angle": strat.angle,
            "post_when": strat.post_when,
            "avoid": strat.avoid,
            "format_preference": strat.format_preference,
            "media_preference": strat.media_preference,
            "min_length": strat.min_length,
            "requires": strat.requires,
        }
    return {"strategies": strategies, "project_id": project_id}


@app.get("/api/projects/{project_id}/strategies/{name}")
async def api_get_strategy(project_id: str, name: str):
    """Get strategy definition (merged view)."""
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)
    finally:
        conn.close()

    config = _get_config()
    if name not in config.content_strategies:
        raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found")

    strat = config.content_strategies[name]
    return {
        "name": name,
        "audience": strat.audience,
        "voice": strat.voice,
        "angle": strat.angle,
        "post_when": strat.post_when,
        "avoid": strat.avoid,
        "format_preference": strat.format_preference,
        "media_preference": strat.media_preference,
        "min_length": strat.min_length,
        "requires": strat.requires,
    }


@app.put("/api/projects/{project_id}/strategies/{name}")
async def api_update_strategy(project_id: str, name: str, body: dict[str, Any] = Body(...)):
    """Update strategy fields in config."""
    from social_hook.config.yaml import save_config

    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)
    finally:
        conn.close()

    try:
        check_unknown_keys(
            body,
            {
                "audience",
                "voice",
                "angle",
                "post_when",
                "avoid",
                "format_preference",
                "media_preference",
                "min_length",
                "requires",
            },
            "strategies",
            strict=True,
        )
    except ConfigError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None

    try:
        save_config(
            {"content_strategies": {name: body}},
            config_path=get_config_path(),
            deep_merge=True,
        )
    except ConfigError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    _invalidate_config()
    conn = _get_conn()
    try:
        ops.emit_data_event(conn, "config", "updated", "strategies", project_id)
    finally:
        conn.close()
    return {"status": "updated", "name": name}


@app.post("/api/projects/{project_id}/strategies/{name}/reset")
async def api_reset_strategy(project_id: str, name: str):
    """Reset strategy to built-in template defaults."""
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)
    finally:
        conn.close()

    # Remove the strategy override from config
    yaml_path = get_config_path()
    try:
        raw = yaml.safe_load(yaml_path.read_text()) or {}
    except yaml.YAMLError:
        raw = {}
    strategies = raw.get("content_strategies", {})
    strategies.pop(name, None)
    raw["content_strategies"] = strategies
    yaml_path.write_text(yaml.dump(raw, default_flow_style=False, sort_keys=False))
    _invalidate_config()
    conn = _get_conn()
    try:
        ops.emit_data_event(conn, "config", "updated", "strategies", project_id)
    finally:
        conn.close()
    return {"status": "reset", "name": name}


@app.post("/api/projects/{project_id}/strategies")
async def api_create_strategy(project_id: str, body: dict[str, Any] = Body(...)):
    """Create a new custom strategy."""
    from social_hook.config.yaml import save_config

    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)
    finally:
        conn.close()

    known_keys = {
        "name",
        "audience",
        "voice",
        "angle",
        "post_when",
        "avoid",
        "format_preference",
        "media_preference",
        "min_length",
        "requires",
    }
    try:
        check_unknown_keys(body, known_keys, "create_strategy", strict=True)
    except ConfigError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None

    name = body.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="'name' is required")

    config = _get_config()
    if name in config.content_strategies:
        raise HTTPException(status_code=409, detail=f"Strategy '{name}' already exists")

    fields = {k: v for k, v in body.items() if k != "name" and v is not None}

    try:
        save_config(
            {"content_strategies": {name: fields}},
            config_path=get_config_path(),
            deep_merge=True,
        )
    except ConfigError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    _invalidate_config()
    conn = _get_conn()
    try:
        ops.emit_data_event(conn, "config", "updated", "strategies", project_id)
    finally:
        conn.close()
    return JSONResponse(status_code=201, content={"status": "created", "name": name})


@app.delete("/api/projects/{project_id}/strategies/{name}")
async def api_delete_strategy(project_id: str, name: str):
    """Delete a strategy. Returns 409 if any targets reference it."""
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)
    finally:
        conn.close()

    config = _get_config()
    if name not in config.content_strategies:
        raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found")

    # Check if any targets reference this strategy
    referencing = [tgt_name for tgt_name, tgt in config.targets.items() if tgt.strategy == name]
    if referencing:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete strategy '{name}': referenced by targets {referencing}",
        )

    # Remove from config.yaml
    from social_hook.config.yaml import delete_config_key

    delete_config_key(get_config_path(), "content_strategies", name)
    _invalidate_config()
    conn = _get_conn()
    try:
        # Dismiss orphaned topics for the deleted strategy
        dismissed_count = conn.execute(
            "UPDATE content_topics SET status = 'dismissed' WHERE project_id = ? AND strategy = ? AND status != 'dismissed'",
            (project_id, name),
        ).rowcount
        if dismissed_count:
            conn.commit()
            logger.info(
                "Dismissed %d orphaned topics for deleted strategy '%s'", dismissed_count, name
            )
        ops.emit_data_event(conn, "config", "updated", "strategies", project_id)
    finally:
        conn.close()
    return {"status": "deleted", "name": name, "topics_dismissed": dismissed_count}


# =============================================================================
# Topics (per-project)
# =============================================================================


@app.get("/api/projects/{project_id}/topics")
async def api_list_topics(project_id: str, strategy: str | None = Query(None)):
    """List topics, optionally filtered by strategy."""
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)
        if strategy:
            topics = ops.get_topics_by_strategy(conn, project_id, strategy)
        else:
            from social_hook.models import ContentTopic

            rows = conn.execute(
                "SELECT * FROM content_topics WHERE project_id = ? ORDER BY strategy, priority_rank DESC, created_at ASC",
                (project_id,),
            ).fetchall()
            topics = [ContentTopic.from_dict(dict(row)) for row in rows]
        return {"topics": [t.to_dict() for t in topics]}
    finally:
        conn.close()


@app.post("/api/projects/{project_id}/topics")
async def api_add_topic(project_id: str, body: dict[str, Any] = Body(...)):
    """Add a topic."""
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)

        try:
            check_unknown_keys(
                body,
                {"strategy", "topic", "description", "priority_rank"},
                "topics",
                strict=True,
            )
        except ConfigError as e:
            raise HTTPException(status_code=422, detail=str(e)) from None

        strategy = body.get("strategy")
        topic_name = body.get("topic")
        if not strategy or not topic_name:
            raise HTTPException(status_code=400, detail="'strategy' and 'topic' are required")

        from social_hook.filesystem import generate_id
        from social_hook.models import ContentTopic
        from social_hook.parsing import safe_int

        topic = ContentTopic(
            id=generate_id("topic"),
            project_id=project_id,
            strategy=strategy,
            topic=topic_name,
            description=body.get("description"),
            priority_rank=safe_int(body.get("priority_rank", 0), 0, "topic.priority_rank"),
            created_by="operator",
        )
        ops.insert_content_topic(conn, topic)
        ops.emit_data_event(conn, "topic", "created", topic.id, project_id)
        return {"status": "created", "topic": topic.to_dict()}
    finally:
        conn.close()


# NOTE: reorder must be declared before {topic_id} to avoid path conflict
@app.put("/api/projects/{project_id}/topics/reorder")
async def api_reorder_topics(project_id: str, body: dict[str, Any] = Body(...)):
    """Batch reorder topics. Accepts {"topic_ids": [...]} in display order."""
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)
        topic_ids = body.get("topic_ids", [])
        if not isinstance(topic_ids, list):
            raise HTTPException(status_code=400, detail="'topic_ids' must be a list")

        # Assign descending priority (first in list = highest rank)
        for i, tid in enumerate(topic_ids):
            rank = len(topic_ids) - i
            ops.update_topic_priority(conn, tid, rank)

        ops.emit_data_event(conn, "topic", "reordered", project_id, project_id)
        return {"status": "reordered", "count": len(topic_ids)}
    finally:
        conn.close()


@app.put("/api/projects/{project_id}/topics/{topic_id}")
async def api_update_topic(project_id: str, topic_id: str, body: dict[str, Any] = Body(...)):
    """Update topic (priority, description)."""
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)

        try:
            check_unknown_keys(
                body,
                {"priority_rank", "description"},
                "topics",
                strict=True,
            )
        except ConfigError as e:
            raise HTTPException(status_code=422, detail=str(e)) from None

        topic = ops.get_topic(conn, topic_id)
        if not topic:
            raise HTTPException(status_code=404, detail="Topic not found")
        if topic.project_id != project_id:
            raise HTTPException(status_code=404, detail="Topic not found in this project")

        from social_hook.parsing import safe_int

        if "priority_rank" in body:
            rank = safe_int(body["priority_rank"], 0, "topic.priority_rank")
            ops.update_topic_priority(conn, topic_id, rank)
        if "description" in body:
            conn.execute(
                "UPDATE content_topics SET description = ? WHERE id = ?",
                (body["description"], topic_id),
            )
            conn.commit()

        ops.emit_data_event(conn, "topic", "updated", topic_id, project_id)
        updated = ops.get_topic(conn, topic_id)
        return {"status": "updated", "topic": updated.to_dict() if updated else None}
    finally:
        conn.close()


@app.put("/api/projects/{project_id}/topics/{topic_id}/status")
async def api_set_topic_status(project_id: str, topic_id: str, body: dict[str, Any] = Body(...)):
    """Set topic status."""
    from social_hook.models import TOPIC_STATUSES

    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)
        status = body.get("status")
        if not status or status not in TOPIC_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {sorted(TOPIC_STATUSES)}",
            )
        topic = ops.get_topic(conn, topic_id)
        if not topic:
            raise HTTPException(status_code=404, detail="Topic not found")
        if topic.project_id != project_id:
            raise HTTPException(status_code=404, detail="Topic not found in this project")

        ops.update_topic_status(conn, topic_id, status)
        ops.emit_data_event(conn, "topic", "updated", topic_id, project_id)
        return {"status": "updated", "topic_id": topic_id, "new_status": status}
    finally:
        conn.close()


@app.post("/api/projects/{project_id}/topics/{topic_id}/draft-now")
async def api_draft_now_topic(project_id: str, topic_id: str):
    """Force draft on a topic. 202 — LLM call."""
    conn = _get_conn()
    try:
        project = _get_project_or_404(conn, project_id)
        topic = ops.get_topic(conn, topic_id)
        if not topic:
            raise HTTPException(status_code=404, detail="Topic not found")
        if topic.project_id != project_id:
            raise HTTPException(status_code=404, detail="Topic not found in this project")

        # Check for already-running task
        existing = conn.execute(
            "SELECT id FROM background_tasks WHERE type='draft_topic' AND ref_id=? AND status='running'",
            (topic_id,),
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Draft already in progress for this topic")

        pid = project["id"]
    finally:
        conn.close()

    strategy = topic.strategy
    t_id = topic_id

    def _blocking_draft_topic():
        from social_hook.config.yaml import load_full_config
        from social_hook.topics import force_draft_topic

        config = load_full_config()
        c = _get_conn()
        try:
            cycle_id = force_draft_topic(c, config, pid, t_id, strategy)
            return {"topic_id": t_id, "cycle_id": cycle_id, "status": "completed"}
        finally:
            c.close()

    task_id = _run_background_task(
        "draft_topic",
        ref_id=topic_id,
        project_id=pid,
        fn=_blocking_draft_topic,
    )
    return JSONResponse(status_code=202, content={"task_id": task_id, "status": "processing"})


# =============================================================================
# Brief (per-project)
# =============================================================================


@app.get("/api/projects/{project_id}/brief")
async def api_get_brief(project_id: str):
    """Get structured brief for a project."""
    from social_hook.llm.brief import get_brief_sections

    conn = _get_conn()
    try:
        project = _get_project_or_404(conn, project_id)
        summary = project["summary"] or ""
        sections = get_brief_sections(summary)
        return {
            "brief": summary,
            "sections": sections,
            "project_id": project_id,
        }
    finally:
        conn.close()


@app.put("/api/projects/{project_id}/brief")
async def api_update_brief(project_id: str, body: dict[str, Any] = Body(...)):
    """Update brief sections."""
    from social_hook.llm.brief import BRIEF_SECTIONS, _sections_to_markdown

    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)

        try:
            check_unknown_keys(
                body,
                set(BRIEF_SECTIONS.keys()) | {"brief"},
                "brief",
                strict=True,
            )
        except ConfigError as e:
            raise HTTPException(status_code=422, detail=str(e)) from None

        # If raw "brief" string is provided, use it directly
        if "brief" in body:
            new_brief = body["brief"]
        else:
            # Build from individual sections
            sections = {key: body.get(key, "") for key in BRIEF_SECTIONS}
            new_brief = _sections_to_markdown(sections)

        ops.update_project_summary(conn, project_id, new_brief)
        ops.emit_data_event(conn, "project", "updated", project_id, project_id)
        return {"status": "updated", "project_id": project_id}
    finally:
        conn.close()


# =============================================================================
# Content Suggestions (per-project)
# =============================================================================


@app.get("/api/projects/{project_id}/suggestions")
async def api_list_suggestions(project_id: str):
    """List content suggestions for a project, enriched with cycle IDs."""
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)
        suggestions = ops.get_suggestions_by_project(conn, project_id)

        # Look up evaluation_cycle_id for suggestions that have been evaluated
        sug_ids = [s.id for s in suggestions]
        cycle_map: dict[str, str] = {}
        if sug_ids:
            placeholders = ",".join("?" for _ in sug_ids)
            rows = conn.execute(
                f"SELECT suggestion_id, evaluation_cycle_id FROM drafts WHERE suggestion_id IN ({placeholders}) AND evaluation_cycle_id IS NOT NULL",
                sug_ids,
            ).fetchall()
            for row in rows:
                cycle_map[row["suggestion_id"]] = row["evaluation_cycle_id"]

        result = []
        for s in suggestions:
            d = s.to_dict()
            d["evaluation_cycle_id"] = cycle_map.get(s.id)
            result.append(d)

        return {"suggestions": result}
    finally:
        conn.close()


@app.post("/api/projects/{project_id}/suggestions")
async def api_create_suggestion(project_id: str, body: dict[str, Any] = Body(...)):
    """Create a content suggestion. Returns 202 if auto-evaluate."""
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)

        try:
            check_unknown_keys(
                body,
                {"idea", "strategy", "media_refs"},
                "suggestions",
                strict=True,
            )
        except ConfigError as e:
            raise HTTPException(status_code=422, detail=str(e)) from None

        idea = body.get("idea")
        if not idea:
            raise HTTPException(status_code=400, detail="'idea' is required")

        from social_hook.filesystem import generate_id
        from social_hook.models import ContentSuggestion

        suggestion = ContentSuggestion(
            id=generate_id("suggestion"),
            project_id=project_id,
            idea=idea,
            strategy=body.get("strategy"),
            media_refs=body.get("media_refs"),
            source="operator",
        )
        ops.insert_content_suggestion(conn, suggestion)
        ops.emit_data_event(conn, "suggestion", "created", suggestion.id, project_id)

        # If strategy is not specified, auto-evaluate (LLM picks the strategy)
        if not suggestion.strategy:
            pid = project_id
            sid = suggestion.id

            def _blocking_evaluate():
                from social_hook.trigger import run_suggestion_trigger

                return {"exit_code": run_suggestion_trigger(sid, pid)}

            task_id = _run_background_task(
                "evaluate_suggestion",
                ref_id=sid,
                project_id=pid,
                fn=_blocking_evaluate,
            )
            return JSONResponse(
                status_code=202,
                content={
                    "task_id": task_id,
                    "status": "processing",
                    "suggestion": suggestion.to_dict(),
                },
            )

        return {"status": "created", "suggestion": suggestion.to_dict()}
    finally:
        conn.close()


@app.put("/api/projects/{project_id}/suggestions/{suggestion_id}/dismiss")
async def api_dismiss_suggestion(project_id: str, suggestion_id: str):
    """Dismiss a suggestion."""
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)
        suggestions = ops.get_suggestions_by_project(conn, project_id)
        found = any(s.id == suggestion_id for s in suggestions)
        if not found:
            raise HTTPException(status_code=404, detail="Suggestion not found")

        ops.update_suggestion_status(conn, suggestion_id, "dismissed")
        ops.emit_data_event(conn, "suggestion", "updated", suggestion_id, project_id)
        return {"status": "dismissed", "suggestion_id": suggestion_id}
    finally:
        conn.close()


@app.post("/api/projects/{project_id}/suggestions/{suggestion_id}/accept")
async def api_accept_suggestion(project_id: str, suggestion_id: str):
    """Accept a pending suggestion and trigger evaluation. 202 — LLM call."""
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)
        suggestion = ops.get_suggestion(conn, suggestion_id)
        if not suggestion:
            raise HTTPException(status_code=404, detail="Suggestion not found")
        if suggestion.status != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"Suggestion has status '{suggestion.status}', only 'pending' can be accepted",
            )

        # Check for already-running task
        existing = conn.execute(
            "SELECT id FROM background_tasks WHERE type='evaluate_suggestion' AND ref_id=? AND status='running'",
            (suggestion_id,),
        ).fetchone()
        if existing:
            raise HTTPException(
                status_code=409, detail="Evaluation already in progress for this suggestion"
            )

        ops.update_suggestion_status(conn, suggestion_id, "evaluated")
        ops.emit_data_event(conn, "suggestion", "updated", suggestion_id, project_id)
        pid = project_id
    finally:
        conn.close()

    sid = suggestion_id

    def _blocking_evaluate():
        from social_hook.trigger import run_suggestion_trigger

        return {"exit_code": run_suggestion_trigger(sid, pid)}

    task_id = _run_background_task(
        "evaluate_suggestion",
        ref_id=sid,
        project_id=pid,
        fn=_blocking_evaluate,
    )
    return JSONResponse(status_code=202, content={"task_id": task_id, "status": "evaluating"})


@app.post("/api/projects/{project_id}/content/combine")
async def api_combine_topics(project_id: str, body: dict[str, Any] = Body(...)):
    """Combine 2+ held topics into one draft. 202 — LLM call."""
    conn = _get_conn()
    try:
        project = _get_project_or_404(conn, project_id)
        topic_ids = body.get("topic_ids", [])
        if not isinstance(topic_ids, list) or len(topic_ids) < 2:
            raise HTTPException(status_code=400, detail="At least 2 topic_ids required")

        # Validate all topics exist and belong to this project
        for tid in topic_ids:
            topic = ops.get_topic(conn, tid)
            if not topic:
                raise HTTPException(status_code=404, detail=f"Topic not found: {tid}")
            if topic.project_id != project_id:
                raise HTTPException(status_code=404, detail=f"Topic {tid} not in this project")

        pid = project["id"]
    finally:
        conn.close()

    t_ids = topic_ids

    def _blocking_combine():
        from social_hook.config.yaml import load_full_config
        from social_hook.content.operations import combine_candidates

        config = load_full_config()
        c = _get_conn()
        try:
            draft_id = combine_candidates(c, config, t_ids, pid)
            return {"topic_ids": t_ids, "draft_id": draft_id, "status": "completed"}
        finally:
            c.close()

    task_id = _run_background_task(
        "combine_topics",
        ref_id=f"combine:{topic_ids[0]}",
        project_id=pid,
        fn=_blocking_combine,
    )
    return JSONResponse(status_code=202, content={"task_id": task_id, "status": "processing"})


@app.post("/api/projects/{project_id}/content/hero-launch")
async def api_hero_launch(project_id: str):
    """Trigger hero launch draft. 202 — LLM call."""
    conn = _get_conn()
    try:
        project = _get_project_or_404(conn, project_id)

        # Check for already-running task
        existing = conn.execute(
            "SELECT id FROM background_tasks WHERE type='hero_launch' AND ref_id=? AND status='running'",
            (project_id,),
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Hero launch already in progress")

        pid = project["id"]
        project_path = project["repo_path"]
    finally:
        conn.close()

    def _blocking_hero_launch():
        from social_hook.config.yaml import load_full_config
        from social_hook.content.operations import trigger_hero_launch

        config = load_full_config()
        c = _get_conn()
        try:
            draft_id = trigger_hero_launch(c, config, pid, project_path)
            return {"project_id": pid, "draft_id": draft_id, "status": "completed"}
        finally:
            c.close()

    task_id = _run_background_task(
        "hero_launch",
        ref_id=project_id,
        project_id=pid,
        fn=_blocking_hero_launch,
    )
    return JSONResponse(status_code=202, content={"task_id": task_id, "status": "processing"})


# =============================================================================
# Evaluation Cycles (per-project)
# =============================================================================


@app.get("/api/projects/{project_id}/cycles")
async def api_list_cycles(project_id: str, limit: int = Query(20, ge=1, le=100)):
    """List recent evaluation cycles with enriched trigger, strategies, and status."""
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)
        cycles = ops.get_recent_cycles(conn, project_id, limit=limit)
        enriched = []
        for c in cycles:
            cd = c.to_dict()

            # Get drafts for this cycle to derive strategies and status
            drafts = ops.get_drafts_by_cycle(conn, c.id)

            # Get the decision for strategy info
            # Try via drafts first, then fall back to cycle's trigger_ref (commit hash)
            decision = None
            if drafts:
                decision_id = drafts[0].decision_id
                decision = ops.get_decision(conn, decision_id)
            if not decision and c.trigger_ref:
                # No drafts — look up decision by commit hash directly
                from social_hook.models import Decision

                row = conn.execute(
                    "SELECT * FROM decisions WHERE project_id = ? AND commit_hash = ? "
                    "ORDER BY created_at DESC LIMIT 1",
                    (project_id, c.trigger_ref),
                ).fetchone()
                if row:
                    decision = Decision.from_dict(dict(row))

            # --- 2.3: Richer trigger descriptions ---
            cd["trigger"] = _enrich_cycle_trigger(conn, c, decision)

            # --- Strategy outcomes ---
            strategies: dict[str, dict] = {}
            if decision and decision.targets:
                # targets is a dict of {strategy_name: {action, reason, ...}}
                from social_hook.parsing import safe_json_loads

                targets_data = decision.targets
                if isinstance(targets_data, str):
                    targets_data = safe_json_loads(targets_data, "cycle.targets", default={})

                # Build strategy_to_draft map: draft.target_id → config target → strategy name
                config = _get_config()
                strategy_to_draft: dict[str, object] = {}
                for d in drafts:
                    if d.target_id and config.targets.get(d.target_id):
                        target_strategy = config.targets[d.target_id].strategy
                        if target_strategy and target_strategy not in strategy_to_draft:
                            strategy_to_draft[target_strategy] = d
                    else:
                        # Legacy drafts without target_id → assign to "default"
                        if "default" not in strategy_to_draft:
                            strategy_to_draft["default"] = d

                ep_tags = _parse_episode_tags(decision)

                for strat_name, strat_data in (targets_data or {}).items():
                    action = (
                        strat_data.get("action", "skip") if isinstance(strat_data, dict) else "skip"
                    )
                    if hasattr(action, "value"):
                        action = action.value
                    reasoning = strat_data.get("reason", "") if isinstance(strat_data, dict) else ""
                    topic_id = strat_data.get("topic_id") if isinstance(strat_data, dict) else None
                    # Find a draft matching this strategy via target_id → config target → strategy
                    strat_draft = strategy_to_draft.get(strat_name)
                    strategies[strat_name] = {
                        "decision": action,
                        "reasoning": reasoning,
                        "draft_id": strat_draft.id if strat_draft else None,
                        "draft_status": strat_draft.status if strat_draft else None,
                        "draft_content": strat_draft.content[:200] if strat_draft else None,
                        "draft_preview_mode": strat_draft.preview_mode if strat_draft else None,
                        "topic_id": topic_id,
                        "episode_tags": ep_tags,
                    }
            elif decision:
                ep_tags = _parse_episode_tags(decision)
                # Legacy decisions without per-strategy targets data
                label = "legacy" if decision.decision != "deferred_eval" else "deferred"
                strategies[label] = {
                    "decision": decision.decision,
                    "reasoning": decision.reasoning[:200] if decision.reasoning else "",
                    "draft_id": drafts[0].id if drafts else None,
                    "draft_status": drafts[0].status if drafts else None,
                    "draft_content": drafts[0].content[:200] if drafts else None,
                    "draft_preview_mode": drafts[0].preview_mode if drafts else None,
                    "topic_id": None,
                    "episode_tags": ep_tags,
                }

            cd["strategies"] = strategies

            # --- 2.6: Status with counts ---
            if not drafts:
                cd["status"] = "no drafts"
                cd["draft_count"] = 0
                cd["pending_count"] = 0
                cd["approved_count"] = 0
                cd["posted_count"] = 0
            else:
                statuses = {d.status for d in drafts}
                if "posted" in statuses:
                    cd["status"] = "posted"
                elif "approved" in statuses or "scheduled" in statuses:
                    cd["status"] = "pending"
                elif "draft" in statuses:
                    cd["status"] = "review"
                else:
                    cd["status"] = drafts[0].status
                cd["draft_count"] = len(drafts)
                cd["pending_count"] = sum(1 for d in drafts if d.status in ("draft", "deferred"))
                cd["approved_count"] = sum(
                    1 for d in drafts if d.status in ("approved", "scheduled")
                )
                cd["posted_count"] = sum(1 for d in drafts if d.status == "posted")

            enriched.append(cd)
        return {"cycles": enriched}
    finally:
        conn.close()


def _enrich_cycle_trigger(conn, cycle, decision) -> str:
    """Build a human-readable trigger description for a cycle."""
    trigger_type = cycle.trigger_type or "unknown"
    trigger_ref = cycle.trigger_ref

    if trigger_type == "commit":
        short_hash = trigger_ref[:7] if trigger_ref else "unknown"
        parts = [f"Commit {short_hash}"]
        if decision:
            ep_tags = _parse_episode_tags(decision)
            if ep_tags:
                parts.append(f"({', '.join(ep_tags)})")
            if decision.commit_message:
                msg = decision.commit_message[:80]
                parts.append(f"\u2014 {msg}")
        return " ".join(parts)
    elif trigger_type == "topic_maturity":
        if trigger_ref:
            topic = ops.get_topic(conn, trigger_ref)
            if topic:
                return f"Topic matured: {topic.topic}"
        return "Topic matured"
    elif trigger_type == "operator_suggestion":
        if trigger_ref:
            s = ops.get_suggestion(conn, trigger_ref)
            if s:
                idea_preview = s.idea[:60] + ("..." if len(s.idea) > 60 else "")
                return f"Suggestion: {idea_preview}"
        return "Operator suggestion"
    elif trigger_type == "batch":
        # trigger_ref is comma-separated commit hashes
        hashes = [h.strip() for h in (trigger_ref or "").split(",") if h.strip()]
        if not hashes:
            return "Batch evaluation"
        parts = [f"Batch of {len(hashes)} commits"]
        if decision:
            ep_tags = _parse_episode_tags(decision)
            if ep_tags:
                parts.append(f"({', '.join(ep_tags)})")
        # Get commit hash + first line of message for each
        commit_lines = []
        for h in hashes[:5]:  # Cap at 5 to avoid huge descriptions
            short = h[:7]
            d = conn.execute(
                "SELECT commit_message FROM decisions WHERE project_id = ? AND commit_hash = ? LIMIT 1",
                (cycle.project_id, h),
            ).fetchone()
            msg = d["commit_message"].splitlines()[0][:50] if d and d["commit_message"] else ""
            commit_lines.append(f"{short} {msg}".strip())
        parts.append("\u2014 " + "; ".join(commit_lines))
        if len(hashes) > 5:
            parts.append(f"(+{len(hashes) - 5} more)")
        return " ".join(parts)
    elif trigger_type == "hero_launch":
        return "Hero launch"
    elif trigger_type == "draft_now":
        return "Manual draft"
    else:
        logger.warning("Unknown trigger_type in cycle: %s", trigger_type)
        parts = [trigger_type]
        if trigger_ref:
            parts.append(trigger_ref[:8])
        return " ".join(parts)


@app.get("/api/projects/{project_id}/cycles/{cycle_id}")
async def api_get_cycle_detail(project_id: str, cycle_id: str):
    """Cycle detail with associated drafts."""
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)

        # Look up the cycle
        row = conn.execute(
            "SELECT * FROM evaluation_cycles WHERE id = ? AND project_id = ?",
            (cycle_id, project_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Cycle not found")

        from social_hook.models import EvaluationCycle

        cycle = EvaluationCycle.from_dict(dict(row))
        cycle_dict = cycle.to_dict()

        # Get associated drafts
        drafts = ops.get_drafts_by_cycle(conn, cycle_id)
        cycle_dict["drafts"] = [d.to_dict() for d in drafts]

        return cycle_dict
    finally:
        conn.close()


@app.post("/api/projects/{project_id}/cycles/{cycle_id}/approve-all")
async def api_approve_all_cycle_drafts(project_id: str, cycle_id: str):
    """Batch-approve all drafts in an evaluation cycle."""
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)

        # Verify cycle exists
        row = conn.execute(
            "SELECT id FROM evaluation_cycles WHERE id = ? AND project_id = ?",
            (cycle_id, project_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Cycle not found")

        # Get all drafts in this cycle that are in "draft" status
        drafts = ops.get_drafts_by_cycle(conn, cycle_id)
        approvable = [d for d in drafts if d.status == "draft"]

        if not approvable:
            return {"status": "no_drafts", "approved_count": 0}

        approved_ids = []
        for draft in approvable:
            ops.update_draft(conn, draft.id, status="approved")
            ops.emit_data_event(conn, "draft", "updated", draft.id, project_id)
            approved_ids.append(draft.id)

        return {
            "status": "approved",
            "approved_count": len(approved_ids),
            "draft_ids": approved_ids,
        }
    finally:
        conn.close()


# =============================================================================
# System (errors + health)
# =============================================================================


@app.get("/api/system/errors")
async def api_system_errors(
    limit: int = Query(50, ge=1, le=500),
    severity: str | None = Query(None),
    component: str | None = Query(None),
    source: str | None = Query(None),
):
    """Recent system errors with optional filters."""
    conn = _get_conn()
    try:
        errors = ops.get_recent_system_errors(
            conn, limit=limit, severity=severity, component=component, source=source
        )
        result = []
        for e in errors:
            d = e.to_dict()
            # Ensure timestamps have Z suffix for JS Date parsing
            if d.get("created_at") and not d["created_at"].endswith("Z"):
                d["created_at"] = d["created_at"] + "Z"
            result.append(d)
        return {"errors": result}
    finally:
        conn.close()


@app.post("/api/system/errors", status_code=201)
async def api_create_system_error(request: Request):
    """Capture a system error (e.g. from frontend)."""
    from social_hook.filesystem import generate_id
    from social_hook.models import SystemErrorRecord

    body = await request.json()
    check_unknown_keys(
        body, {"severity", "message", "source", "context"}, "system_error", strict=True
    )

    severity = body.get("severity", "error")
    if severity not in ("info", "warning", "error", "critical"):
        raise HTTPException(status_code=400, detail=f"Invalid severity: {severity}")

    message = body.get("message", "")
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    source = body.get("source", "")
    context_raw = body.get("context", "{}")
    if isinstance(context_raw, str):
        context = safe_json_loads(context_raw, "system_error.context", default={})
    else:
        context = context_raw

    error = SystemErrorRecord(
        id=generate_id("err"),
        severity=severity,
        message=message,
        context=json.dumps(context) if isinstance(context, dict) else str(context),
        source=source,
    )
    conn = _get_conn()
    try:
        error_id = ops.insert_system_error(conn, error)
        ops.emit_data_event(
            conn,
            "system_error",
            "created",
            error_id,
            extra={"severity": severity, "component": source},
        )
        return {"id": error_id, "status": "created"}
    finally:
        conn.close()


@app.delete("/api/system/errors")
async def api_clear_system_errors(
    older_than_days: int | None = None,
):
    """Clear system errors. Optional: ?older_than_days=30 to prune old entries only.

    Without the parameter, deletes all errors.
    """
    conn = _get_conn()
    try:
        count = ops.clear_system_errors(conn, older_than_days=older_than_days)
        ops.emit_data_event(conn, "system_error", "cleared", "")
        return {"deleted": count}
    finally:
        conn.close()


@app.get("/api/system/health")
async def api_system_health():
    """Health status summary."""
    conn = _get_conn()
    try:
        error_counts = ops.get_error_health_status(conn)
        total_errors = sum(error_counts.values())
        status = ops.compute_health_status(error_counts)

        return {
            "status": status,
            "error_counts_24h": error_counts,
            "total_errors_24h": total_errors,
        }
    finally:
        conn.close()


# =============================================================================
# Platform Settings
# =============================================================================


@app.get("/api/platform-settings")
async def api_get_platform_settings():
    """Get per-platform settings."""
    config = _get_config()
    settings = {}
    for name, ps in config.platform_settings.items():
        settings[name] = {"cross_account_gap_minutes": ps.cross_account_gap_minutes}
    return {"platform_settings": settings}


@app.put("/api/platform-settings/{platform}")
async def api_update_platform_settings(platform: str, body: dict[str, Any] = Body(...)):
    """Update per-platform settings."""
    from social_hook.config.yaml import save_config

    try:
        check_unknown_keys(
            body,
            {"cross_account_gap_minutes"},
            "platform_settings",
            strict=True,
        )
    except ConfigError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None

    try:
        save_config(
            {"platform_settings": {platform: body}},
            config_path=get_config_path(),
        )
    except ConfigError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    _invalidate_config()
    return {"status": "updated", "platform": platform}
