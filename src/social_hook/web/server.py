"""FastAPI API server for the web dashboard."""

import asyncio
import json
import logging
import re
import sqlite3
import threading
import time
import uuid as _uuid
from collections.abc import Callable
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

import yaml
from fastapi import Body, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
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

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# WebSocket gateway
# ---------------------------------------------------------------------------

_hub = GatewayHub()


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    # Ensure DB schema exists before any endpoint or bridge loop runs.
    # Safe on existing DBs (CREATE TABLE IF NOT EXISTS), required on fresh installs.
    init_database(get_db_path())
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
    conn.row_factory = sqlite3.Row
    return conn


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
            (e.g. decision_id).
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

                conn2.execute(
                    "UPDATE background_tasks SET status='failed', error=?,"
                    " updated_at=datetime('now') WHERE id=?",
                    (traceback.format_exc()[-500:], task_id),
                )
                conn2.commit()
                ops.emit_data_event(conn2, "task", "failed", task_id, project_id)
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
        return [
            {
                "id": row["id"],
                "type": row["type"],
                "data": json.loads(row["data"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]
    except Exception:
        return []
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
    handle_command(msg, adapter, config)

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
    handle_callback(event, adapter, config)

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
    handle_message(msg, adapter, config)

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
async def api_events(lastId: int = Query(0)):
    """Server-Sent Events stream polling web_events."""

    def event_stream():
        current_id = lastId
        empty_polls = 0
        max_empty = 10  # ~10 seconds of no data -> close stream

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


async def _event_bridge_loop():
    """Poll web_events and broadcast new entries to WS clients.

    Broadcast events (session_id IS NULL) go to all connections.
    Scoped events go only to the connection with a matching session_id.
    """
    bridge_conn = sqlite3.connect(str(get_db_path()))
    bridge_conn.row_factory = sqlite3.Row
    try:
        row = bridge_conn.execute("SELECT COALESCE(MAX(id), 0) FROM web_events").fetchone()
        last_id = row[0] if row else 0
        while True:
            await asyncio.sleep(0.5)
            if _hub.connection_count == 0:
                row = bridge_conn.execute("SELECT COALESCE(MAX(id), 0) FROM web_events").fetchone()
                last_id = row[0] if row else 0
                continue
            rows = bridge_conn.execute(
                "SELECT id, type, data, session_id, created_at FROM web_events WHERE id > ? ORDER BY id ASC",
                (last_id,),
            ).fetchall()
            for r in rows:
                ev = {
                    "id": r["id"],
                    "type": r["type"],
                    "data": json.loads(r["data"]),
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
        bridge_conn.close()


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
):
    """List drafts, optionally filtered by status, project, decision, or commit."""
    from social_hook.db import operations as ops

    conn = _get_conn()
    try:
        draft_models = ops.get_drafts_filtered(
            conn,
            status=status,
            project_id=project_id,
            decision_id=decision_id,
            commit_hash=commit,
        )
        drafts = [d.to_dict() for d in draft_models]
        if pending:
            drafts = [d for d in drafts if d.get("status") in ("draft", "approved", "scheduled")]
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
    """Update media_spec on a draft."""
    media_spec = body.get("media_spec")
    if media_spec is None:
        raise HTTPException(status_code=400, detail="media_spec is required")
    conn = _get_conn()
    try:
        # Get old spec for audit trail
        draft = ops.get_draft(conn, draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")
        old_spec = draft.media_spec

        ops.update_draft(conn, draft_id, media_spec=media_spec)

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


@app.get("/api/projects")
async def api_projects():
    """List all registered projects with lifecycle phase."""
    conn = _get_conn()
    try:
        rows = conn.execute("""
            SELECT p.*, l.phase, l.confidence
            FROM projects p
            LEFT JOIN lifecycles l ON l.project_id = p.id
            ORDER BY p.created_at DESC
        """).fetchall()
        return {"projects": [dict(row) for row in rows]}
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
):
    """Get decision history for a project with pagination."""
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)

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

        return {"decisions": decisions_list, "total": total}
    finally:
        conn.close()


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

    from social_hook.trigger import parse_commit_info

    commit = parse_commit_info(decision.commit_hash, project.repo_path)

    from types import SimpleNamespace

    evaluation = SimpleNamespace(
        decision="draft",
        reasoning=decision.reasoning,
        angle=decision.angle,
        episode_type=decision.episode_type,
        post_category=decision.post_category,
        arc_id=decision.arc_id,
        new_arc_theme=None,
        media_tool=decision.media_tool,
        reference_posts=None,
        include_project_docs=True,
        commit_summary=decision.commit_summary,
    )

    def _blocking_create_draft():
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
                commit_timestamp=commit.timestamp,
                parent_timestamp=commit.parent_timestamp,
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
    """Delete a decision and re-evaluate the commit from scratch.

    Re-runs the full evaluator pipeline, which may produce a different
    decision, angle, episode type, or skip the commit entirely.
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

        ops.delete_decision(conn, decision_id)
        ops.emit_data_event(conn, "decision", "deleted", decision_id, decision.project_id)
    finally:
        conn.close()

    def _blocking_retrigger():
        from social_hook.trigger import run_trigger

        return run_trigger(
            commit_hash=commit_hash,
            repo_path=repo_path,
        )

    exit_code = await asyncio.to_thread(_blocking_retrigger)

    return {"status": "retriggered" if exit_code == 0 else "failed", "exit_code": exit_code}


@app.get("/api/platforms/enabled")
async def api_enabled_platforms():
    """Return all enabled platforms with their config."""
    config = _get_config()
    enabled = {}
    for name, pcfg in config.platforms.items():
        if pcfg.enabled:
            enabled[name] = {"priority": pcfg.priority, "type": pcfg.type}
    return {"platforms": enabled, "count": len(enabled)}


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

    from types import SimpleNamespace

    anchor = decisions[-1]
    evaluation = SimpleNamespace(
        decision="draft",
        reasoning=anchor.reasoning,
        angle=anchor.angle,
        episode_type=anchor.episode_type,
        post_category=anchor.post_category,
        arc_id=anchor.arc_id,
        media_tool=anchor.media_tool,
        include_project_docs=True,
        commit_summary=anchor.commit_summary,
    )

    def _blocking_consolidate():
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
                    "result": json.loads(r["result"]) if r["result"] else None,
                    "error": r["error"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
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
    from social_hook.models import ArcStatus
    from social_hook.narrative.arcs import update_arc

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

        # Load context settings from content-config.yaml
        cc_path = get_db_path().parent / "content-config.yaml"
        max_doc_tokens = 10000
        project_docs: list[str] | None = None
        if cc_path.exists():
            try:
                cc_raw = yaml.safe_load(cc_path.read_text()) or {}
                ctx = cc_raw.get("context", {})
                max_doc_tokens = ctx.get("max_doc_tokens", 10000)
                project_docs = ctx.get("project_docs") or None
            except yaml.YAMLError:
                pass

        summary, files = await asyncio.to_thread(
            discover_project,
            client,
            project.repo_path,
            project_docs=project_docs,
            max_doc_tokens=max_doc_tokens,
            db=conn,
            project_id=project_id,
        )

        if summary:
            ops.update_project_summary(conn, project_id, summary)
            if files:
                ops.update_discovery_files(conn, project_id, files)
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


@app.post("/api/installations/bot_daemon/start")
async def api_start_bot_daemon():
    import subprocess as sp

    from social_hook.bot.process import is_running

    if is_running():
        return {"success": True, "message": "Bot daemon is already running"}
    try:
        sp.Popen([PROJECT_SLUG, "bot", "start", "--daemon"])
        return {"success": True, "message": "Bot daemon starting"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.post("/api/installations/bot_daemon/stop")
async def api_stop_bot_daemon():
    from social_hook.bot.process import is_running, stop_bot

    if not is_running():
        return {"success": True, "message": "Bot daemon is not running"}
    if stop_bot():
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
