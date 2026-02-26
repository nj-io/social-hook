"""FastAPI API server for the web dashboard."""

import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

import yaml
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from social_hook.config.env import KEY_GROUPS, KNOWN_KEYS
from social_hook.config.project import DEFAULT_MEDIA_GUIDANCE
from social_hook.config.yaml import Config, validate_config
from social_hook.errors import ConfigError
from social_hook.filesystem import get_config_path, get_db_path, get_env_path, get_narratives_path
from social_hook.messaging.base import CallbackEvent, InboundMessage

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Social Hook Dashboard API", version="0.1.0")

# CORS: localhost only
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_config: Optional[Config] = None
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


def _get_adapter():
    """Return lazy WebAdapter singleton."""
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
    value: Optional[str] = None  # None = delete


class SocialContextUpdate(BaseModel):
    project_path: str
    content: str


class ContentConfigUpdate(BaseModel):
    project_path: str
    content: str


class ValidateKeyRequest(BaseModel):
    provider: str
    key: str


# ---------------------------------------------------------------------------
# Bot interaction endpoints
# ---------------------------------------------------------------------------


def _get_events_since(last_id: int) -> list[dict]:
    """Query web_events for rows with id > last_id."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, type, data, created_at FROM web_events WHERE id > ? ORDER BY id ASC",
            (last_id,),
        ).fetchall()
        return [
            {"id": row["id"], "type": row["type"], "data": json.loads(row["data"]),
             "created_at": row["created_at"]}
            for row in rows
        ]
    except Exception:
        return []
    finally:
        conn.close()


@app.get("/api/events/history")
async def api_events_history():
    """Return all chat events for initial page load."""
    return {"events": _get_events_since(0)}


@app.post("/api/command")
async def api_command(body: CommandRequest):
    """Execute a bot command via the web adapter."""
    from social_hook.bot.commands import handle_command

    adapter = _get_adapter()
    config = _get_config()

    # Persist user event, run handler synchronously, return all events together.
    before_id = _max_event_id()
    adapter._insert_event("user", {"text": body.text})

    msg = InboundMessage(chat_id="web", text=body.text, message_id="web_0")
    handle_command(msg, adapter, config)

    events = _get_events_since(before_id)
    return {"events": events}


@app.post("/api/callback")
async def api_callback(body: CallbackRequest):
    """Execute a button callback via the web adapter."""
    from social_hook.bot.buttons import handle_callback

    adapter = _get_adapter()
    config = _get_config()

    before_id = _max_event_id()

    event = CallbackEvent(
        chat_id="web",
        callback_id="web_0",
        action=body.action,
        payload=body.payload,
    )
    handle_callback(event, adapter, config)

    events = _get_events_since(before_id)
    return {"events": events}


@app.post("/api/message")
async def api_message(body: MessageRequest):
    """Send a free-text message via the web adapter."""
    from social_hook.bot.commands import handle_message

    adapter = _get_adapter()
    config = _get_config()

    # Persist user event, run handler synchronously, return all events together.
    before_id = _max_event_id()
    adapter._insert_event("user", {"text": body.text})

    msg = InboundMessage(chat_id="web", text=body.text, message_id="web_0")
    handle_message(msg, adapter, config)

    events = _get_events_since(before_id)
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
async def api_clear_events():
    """Clear all chat history from web_events and chat_messages."""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM web_events")
        try:
            conn.execute("DELETE FROM chat_messages WHERE chat_id = 'web'")
        except sqlite3.OperationalError:
            pass  # Table may not exist yet
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
# Data query endpoints
# ---------------------------------------------------------------------------


@app.get("/api/drafts")
async def api_drafts(status: Optional[str] = None):
    """List drafts, optionally filtered by status."""
    conn = _get_conn()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM drafts WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM drafts ORDER BY created_at DESC"
            ).fetchall()
        return {"drafts": [dict(row) for row in rows]}
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
    return row


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
        decision_stats = conn.execute("""
            SELECT decision, COUNT(*) as count
            FROM decisions WHERE project_id = ?
            GROUP BY decision
        """, (project_id,)).fetchall()
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
            with open(narratives_file, "r") as f:
                narrative_count = sum(1 for _ in f)
        project["narrative_count"] = narrative_count

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

        rows = conn.execute("""
            SELECT * FROM decisions
            WHERE project_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (project_id, limit, offset)).fetchall()

        total = conn.execute(
            "SELECT COUNT(*) FROM decisions WHERE project_id = ?", (project_id,)
        ).fetchone()[0]

        return {"decisions": [dict(r) for r in rows], "total": total}
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

        rows = conn.execute("""
            SELECT * FROM posts
            WHERE project_id = ?
            ORDER BY posted_at DESC
            LIMIT ?
        """, (project_id, limit)).fetchall()
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

        rows = conn.execute("""
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
        """, (project_id, days)).fetchall()

        rows_list = [dict(r) for r in rows]
        return {
            "total_input_tokens": sum(r["total_input"] for r in rows_list),
            "total_output_tokens": sum(r["total_output"] for r in rows_list),
            "total_cost_cents": sum(r["total_cost_cents"] for r in rows_list),
            "entries": rows_list,
        }
    finally:
        conn.close()


@app.get("/api/projects/{project_id}/arcs")
async def api_project_arcs(project_id: str):
    """Get all arcs for a project."""
    conn = _get_conn()
    try:
        _get_project_or_404(conn, project_id)

        rows = conn.execute("""
            SELECT * FROM arcs
            WHERE project_id = ?
            ORDER BY started_at DESC
        """, (project_id,)).fetchall()
        return {"arcs": [dict(r) for r in rows]}
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
    yaml_path = get_config_path()

    # Read existing
    if yaml_path.exists():
        try:
            current = yaml.safe_load(yaml_path.read_text()) or {}
        except yaml.YAMLError:
            current = {}
    else:
        current = {}

    # Merge updates
    for key, value in body.items():
        if isinstance(value, dict) and isinstance(current.get(key), dict):
            current[key].update(value)
        else:
            current[key] = value

    # Validate before writing
    try:
        validate_config(current)
    except ConfigError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Write back
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_path.write_text(yaml.dump(current, default_flow_style=False, sort_keys=False))

    _invalidate_config()
    return {"status": "ok"}


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
async def api_get_social_context(project_path: Optional[str] = None):
    """Read social-context.md content."""
    if project_path:
        sc_path = Path(project_path) / ".social-hook" / "social-context.md"
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
            raise HTTPException(status_code=400, detail=f"Project path not found: {body.project_path}")
        sc_path = project_dir / ".social-hook" / "social-context.md"
    else:
        sc_path = get_db_path().parent / "social-context.md"

    sc_path.parent.mkdir(parents=True, exist_ok=True)
    sc_path.write_text(body.content)
    return {"status": "ok", "path": str(sc_path)}


@app.get("/api/settings/content-config")
async def api_get_content_config(project_path: Optional[str] = None):
    """Read content-config.yaml content."""
    if project_path:
        cc_path = Path(project_path) / ".social-hook" / "content-config.yaml"
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
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}")

    if body.project_path:
        project_dir = Path(body.project_path)
        if not project_dir.is_dir():
            raise HTTPException(status_code=400, detail=f"Project path not found: {body.project_path}")
        cc_path = project_dir / ".social-hook" / "content-config.yaml"
    else:
        cc_path = get_db_path().parent / "content-config.yaml"

    cc_path.parent.mkdir(parents=True, exist_ok=True)
    cc_path.write_text(body.content)
    return {"status": "ok", "path": str(cc_path)}


@app.get("/api/settings/content-config/parsed")
async def api_get_content_config_parsed(project_path: Optional[str] = None):
    """Return parsed content-config sections as structured JSON."""
    if project_path:
        cc_path = Path(project_path) / ".social-hook" / "content-config.yaml"
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
    merged_tools = {name: {} for name in DEFAULT_MEDIA_GUIDANCE}
    merged_tools.update(yaml_tools)

    return {
        "media_tools": merged_tools,
        "strategy": raw.get("strategy", {}),
        "context": raw.get("context", {}),
        "summary": raw.get("summary", {}),
    }


@app.put("/api/settings/content-config/parsed")
async def api_update_content_config_parsed(body: dict[str, Any] = Body(...), project_path: Optional[str] = None):
    """Update specific content-config sections (merge + write)."""
    if project_path:
        project_dir = Path(project_path)
        if not project_dir.is_dir():
            raise HTTPException(status_code=400, detail=f"Project path not found: {project_path}")
        cc_path = project_dir / ".social-hook" / "content-config.yaml"
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


@app.put("/api/projects/{project_id}/pause")
async def api_toggle_pause(project_id: str):
    """Toggle a project's paused state."""
    conn = _get_conn()
    try:
        row = conn.execute("SELECT paused FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Project not found")
        new_paused = 0 if row["paused"] else 1
        conn.execute("UPDATE projects SET paused = ? WHERE id = ?", (new_paused, project_id))
        conn.commit()
        return {"status": "ok", "paused": new_paused}
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

            client = openai.OpenAI(api_key=body.key)
            client.models.list()
            return {"valid": True, "provider": provider}
        except Exception as e:
            return {"valid": False, "provider": provider, "error": str(e)}

    else:
        return {"valid": False, "provider": provider, "error": f"Unknown provider: {provider}"}
