"""Tests for Chunk 6: Decision Override, Media Spec Editing, Reasoning Display, Tier Selector."""

import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from social_hook.constants import DB_FILENAME

# ---------------------------------------------------------------------------
# Fixtures (mirror test_web_server.py pattern)
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_env(tmp_path):
    """Set up isolated filesystem for tests."""
    db_path = tmp_path / DB_FILENAME
    config_path = tmp_path / "config.yaml"
    env_path = tmp_path / ".env"
    media_dir = tmp_path / "media-cache"
    media_dir.mkdir()

    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS web_events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            type       TEXT NOT NULL,
            data       TEXT NOT NULL,
            session_id TEXT DEFAULT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_web_events_session ON web_events(session_id);
        CREATE TABLE IF NOT EXISTS drafts (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            decision_id TEXT,
            platform TEXT,
            content TEXT,
            status TEXT DEFAULT 'draft',
            media_paths TEXT DEFAULT '[]',
            media_type TEXT,
            media_spec TEXT DEFAULT '{}',
            suggested_time TEXT,
            scheduled_time TEXT,
            reasoning TEXT,
            superseded_by TEXT,
            retry_count INTEGER DEFAULT 0,
            last_error TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS draft_tweets (
            id TEXT PRIMARY KEY,
            draft_id TEXT,
            position INTEGER,
            content TEXT,
            media_paths TEXT DEFAULT '[]',
            external_id TEXT,
            posted_at TEXT,
            error TEXT
        );
        CREATE TABLE IF NOT EXISTS draft_changes (
            id TEXT PRIMARY KEY,
            draft_id TEXT,
            field TEXT,
            old_value TEXT,
            new_value TEXT,
            changed_by TEXT,
            changed_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT,
            repo_path TEXT,
            repo_origin TEXT,
            summary TEXT,
            summary_updated_at TEXT,
            audience_introduced INTEGER DEFAULT 0,
            paused INTEGER DEFAULT 0,
            discovery_files TEXT DEFAULT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS decisions (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            commit_hash TEXT,
            commit_message TEXT,
            decision TEXT,
            reasoning TEXT,
            angle TEXT,
            episode_type TEXT,
            post_category TEXT,
            arc_id TEXT,
            media_tool TEXT,
            platforms TEXT DEFAULT '{}',
            commit_summary TEXT,
            processed INTEGER NOT NULL DEFAULT 0,
            processed_at TEXT,
            batch_id TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS lifecycles (
            project_id TEXT PRIMARY KEY,
            phase TEXT DEFAULT 'research',
            confidence REAL DEFAULT 0.5,
            evidence TEXT DEFAULT '[]',
            last_strategy_moment TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS arcs (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            theme TEXT,
            status TEXT DEFAULT 'active',
            post_count INTEGER DEFAULT 0,
            last_post_at TEXT,
            notes TEXT,
            started_at TEXT DEFAULT (datetime('now')),
            ended_at TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS narrative_debt (
            project_id TEXT PRIMARY KEY,
            debt_counter INTEGER DEFAULT 0,
            last_synthesis_at TEXT
        );
        CREATE TABLE IF NOT EXISTS posts (
            id TEXT PRIMARY KEY,
            draft_id TEXT,
            project_id TEXT,
            platform TEXT,
            external_id TEXT,
            external_url TEXT,
            content TEXT,
            posted_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS usage_log (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            operation_type TEXT,
            model TEXT,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            cache_read_tokens INTEGER DEFAULT 0,
            cache_creation_tokens INTEGER DEFAULT 0,
            cost_cents REAL DEFAULT 0.0,
            commit_hash TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT,
            description TEXT
        );
        """
    )
    conn.commit()
    conn.close()

    return {
        "tmp_path": tmp_path,
        "db_path": db_path,
        "config_path": config_path,
        "env_path": env_path,
        "media_dir": media_dir,
    }


@pytest.fixture()
def client(tmp_env):
    """Create a test client with mocked filesystem paths."""
    from fastapi.testclient import TestClient

    from social_hook.web.server import app

    tmp_env["tmp_path"]
    db_path = tmp_env["db_path"]
    config_path = tmp_env["config_path"]
    env_path = tmp_env["env_path"]

    with (
        patch("social_hook.web.server.get_db_path", return_value=db_path),
        patch("social_hook.web.server.get_config_path", return_value=config_path),
        patch("social_hook.web.server.get_env_path", return_value=env_path),
    ):
        import social_hook.web.server as srv

        srv._config = None
        srv._adapter = None

        yield TestClient(app)


def _seed_project_and_decision(db_path, decision="draft"):
    """Seed a project and a decision."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
        ("proj_1", "Test Project", "/tmp/test"),
    )
    conn.execute(
        "INSERT INTO decisions (id, project_id, commit_hash, commit_message, decision, reasoning) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("dec_1", "proj_1", "abc123", "feat: add new feature", decision, "This is a cool feature"),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Decision override: POST /api/decisions/{id}/create-draft
# ---------------------------------------------------------------------------


def _make_draft_result(
    draft_id="draft_test_1", decision_id="dec_1", project_id="proj_1", platform="x"
):
    """Build a mock DraftResult for testing."""
    from datetime import datetime, timezone

    from social_hook.drafting import DraftResult
    from social_hook.models import Draft
    from social_hook.scheduling import ScheduleResult

    draft = Draft(
        id=draft_id,
        project_id=project_id,
        decision_id=decision_id,
        platform=platform,
        content="Test draft content",
    )
    schedule = ScheduleResult(
        datetime=datetime.now(timezone.utc),
        is_optimal_day=True,
        deferred=False,
        day_reason="test",
        time_reason="test",
    )
    return DraftResult(draft=draft, schedule=schedule, thread_tweets=[])


def _mock_create_draft_patches():
    """Return context managers for mocking the create-draft pipeline."""
    from social_hook.config.project import ProjectConfig
    from social_hook.models import CommitInfo, ProjectContext

    mock_commit = CommitInfo(hash="abc123", message="feat: test", diff="", files_changed=[])
    mock_project_config = ProjectConfig(repo_path="/tmp/test")
    mock_context = MagicMock(spec=ProjectContext)

    return (
        patch("social_hook.trigger.parse_commit_info", return_value=mock_commit),
        patch("social_hook.config.project.load_project_config", return_value=mock_project_config),
        patch("social_hook.llm.prompts.assemble_evaluator_context", return_value=mock_context),
    )


class TestCreateDraftFromDecision:
    def test_creates_draft_from_decision(self, client, tmp_env):
        """POST /api/decisions/{id}/create-draft creates drafts via the pipeline."""
        _seed_project_and_decision(tmp_env["db_path"])

        mock_result = _make_draft_result()
        p1, p2, p3 = _mock_create_draft_patches()
        with (
            p1,
            p2,
            p3,
            patch("social_hook.drafting.draft_for_platforms", return_value=[mock_result]),
        ):
            resp = client.post("/api/decisions/dec_1/create-draft", json={"platform": "x"})

        assert resp.status_code == 200
        data = resp.json()
        assert "draft_ids" in data
        assert data["count"] == 1
        assert data["status"] == "created"

    def test_create_draft_no_platform_drafts_all(self, client, tmp_env):
        """POST /api/decisions/{id}/create-draft with no platform drafts for all enabled."""
        _seed_project_and_decision(tmp_env["db_path"])

        mock_results = [
            _make_draft_result(draft_id="d1", platform="x"),
            _make_draft_result(draft_id="d2", platform="linkedin"),
        ]
        p1, p2, p3 = _mock_create_draft_patches()
        with (
            p1,
            p2,
            p3,
            patch(
                "social_hook.drafting.draft_for_platforms", return_value=mock_results
            ) as mock_dfp,
        ):
            resp = client.post("/api/decisions/dec_1/create-draft", json={})

        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        # Verify target_platform_names was None (all platforms)
        call_kwargs = mock_dfp.call_args[1]
        assert call_kwargs.get("target_platform_names") is None

    def test_create_draft_decision_not_found(self, client, tmp_env):
        """POST /api/decisions/{id}/create-draft returns 404 for unknown decision."""
        resp = client.post("/api/decisions/nonexistent/create-draft", json={"platform": "x"})
        assert resp.status_code == 404

    def test_create_draft_links_to_decision(self, client, tmp_env):
        """Created draft IDs are returned with correct response shape."""
        _seed_project_and_decision(tmp_env["db_path"])

        mock_result = _make_draft_result(draft_id="draft_linked", platform="linkedin")
        p1, p2, p3 = _mock_create_draft_patches()
        with (
            p1,
            p2,
            p3,
            patch("social_hook.drafting.draft_for_platforms", return_value=[mock_result]),
        ):
            resp = client.post("/api/decisions/dec_1/create-draft", json={"platform": "linkedin"})

        data = resp.json()
        assert data["draft_ids"] == ["draft_linked"]
        assert data["status"] == "created"


# ---------------------------------------------------------------------------
# Media spec editing: PUT /api/drafts/{id}/media-spec
# ---------------------------------------------------------------------------


class TestUpdateDraftMediaSpec:
    def test_update_media_spec(self, client, tmp_env):
        """PUT /api/drafts/{id}/media-spec updates the media_spec field."""
        # Seed a draft
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.execute(
            "INSERT INTO drafts (id, project_id, decision_id, platform, content, media_spec) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("draft_1", "proj_1", "dec_1", "x", "Hello", "{}"),
        )
        conn.commit()
        conn.close()

        new_spec = {"tool": "nano_banana_pro", "prompt": "A developer coding"}
        resp = client.put("/api/drafts/draft_1/media-spec", json={"media_spec": new_spec})
        assert resp.status_code == 200
        assert resp.json()["status"] == "updated"

        # Verify in DB
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        row = conn.execute("SELECT media_spec FROM drafts WHERE id = 'draft_1'").fetchone()
        conn.close()
        assert json.loads(row[0]) == new_spec

    def test_update_media_spec_not_found(self, client, tmp_env):
        """PUT /api/drafts/{id}/media-spec returns 404 for unknown draft."""
        resp = client.put("/api/drafts/nonexistent/media-spec", json={"media_spec": {}})
        assert resp.status_code == 404

    def test_update_media_spec_missing_field(self, client, tmp_env):
        """PUT /api/drafts/{id}/media-spec rejects missing media_spec."""
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.execute(
            "INSERT INTO drafts (id, project_id, decision_id, platform, content) "
            "VALUES (?, ?, ?, ?, ?)",
            ("draft_1", "proj_1", "dec_1", "x", "Hello"),
        )
        conn.commit()
        conn.close()

        resp = client.put("/api/drafts/draft_1/media-spec", json={"wrong_field": {}})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Button kwargs forward-compat
# ---------------------------------------------------------------------------


class TestButtonKwargsForwardCompat:
    """Verify that btn_* functions accept **kwargs without error."""

    def test_handle_callback_with_kwargs(self):
        """handle_callback passes kwargs through to handler."""
        from social_hook.bot.buttons import handle_callback
        from social_hook.messaging.base import CallbackEvent, MessagingAdapter, SendResult

        adapter = MagicMock(spec=MessagingAdapter)
        adapter.send_message.return_value = SendResult(success=True, message_id="1")
        adapter.answer_callback.return_value = True

        event = CallbackEvent(
            chat_id="123",
            callback_id="cb1",
            action="approve",
            payload="draft_xyz",
        )

        # Should not raise even with extra kwargs
        with patch("social_hook.bot.buttons.btn_approve") as mock_btn:
            handle_callback(event, adapter, config=None, extra_param="test")
            mock_btn.assert_called_once()
            # Verify kwargs were forwarded
            call_kwargs = mock_btn.call_args[1]
            assert call_kwargs.get("extra_param") == "test"

    def test_btn_approve_accepts_kwargs(self):
        """btn_approve function signature accepts **kwargs."""
        from social_hook.bot.buttons import btn_approve

        adapter = MagicMock()
        adapter.send_message.return_value = MagicMock(success=True)
        adapter.answer_callback.return_value = True

        mock_conn = MagicMock()
        # Should not raise TypeError for unexpected keyword args
        with (
            patch("social_hook.bot.buttons._get_conn", return_value=mock_conn),
            patch("social_hook.db.get_draft", return_value=None),
        ):
            btn_approve(adapter, "123", "cb1", "draft_1", None, future_param="value")

    def test_btn_reject_accepts_kwargs(self):
        """btn_reject (reject_submenu) accepts **kwargs."""
        from social_hook.bot.buttons import btn_reject_submenu

        adapter = MagicMock()
        adapter.send_message.return_value = MagicMock(success=True)
        adapter.answer_callback.return_value = True

        mock_conn = MagicMock()
        with (
            patch("social_hook.bot.buttons._get_conn", return_value=mock_conn),
            patch("social_hook.db.get_draft", return_value=None),
        ):
            btn_reject_submenu(adapter, "123", "cb1", "draft_1", None, future_param="value")
