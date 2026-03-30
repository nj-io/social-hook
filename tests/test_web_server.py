"""Tests for the FastAPI web dashboard API server."""

import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest
import yaml

from social_hook.constants import DB_FILENAME

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_env(tmp_path):
    """Set up isolated filesystem for tests."""
    db_path = tmp_path / DB_FILENAME
    config_path = tmp_path / "config.yaml"
    env_path = tmp_path / ".env"
    media_dir = tmp_path / "media-cache"
    media_dir.mkdir()

    # Create minimal DB with required tables
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
        CREATE INDEX IF NOT EXISTS idx_web_events_session
            ON web_events(session_id);
        CREATE TABLE IF NOT EXISTS drafts (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            decision_id TEXT,
            platform TEXT,
            content TEXT,
            status TEXT DEFAULT 'draft',
            media_paths TEXT DEFAULT '[]',
            media_type TEXT,
            media_spec TEXT,
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
            trigger_branch TEXT DEFAULT NULL,
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
            trigger_source TEXT DEFAULT 'commit',
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
            strategy TEXT NOT NULL DEFAULT '',
            status TEXT DEFAULT 'active' CHECK (status IN ('proposed', 'active', 'completed', 'abandoned')),
            reasoning TEXT,
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
            trigger_source TEXT DEFAULT 'auto',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT,
            description TEXT
        );
        CREATE TABLE IF NOT EXISTS background_tasks (
            id         TEXT PRIMARY KEY,
            type       TEXT NOT NULL,
            ref_id     TEXT NOT NULL DEFAULT '',
            project_id TEXT NOT NULL DEFAULT '',
            status     TEXT NOT NULL DEFAULT 'running',
            result     TEXT,
            error      TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS milestone_summaries (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            milestone_type TEXT NOT NULL,
            summary TEXT NOT NULL,
            items_covered TEXT NOT NULL DEFAULT '[]',
            token_count INTEGER NOT NULL DEFAULT 0,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
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
        # Reset module-level state
        import social_hook.web.server as srv

        srv._config = None
        srv._adapter = None

        yield TestClient(app)


# ---------------------------------------------------------------------------
# Bot interaction tests
# ---------------------------------------------------------------------------


class TestBotEndpoints:
    def test_command_endpoint(self, client, tmp_env):
        """POST /api/command calls handle_command and returns events."""
        with patch("social_hook.bot.commands.handle_command") as mock_cmd:

            def side_effect(msg, adapter, config):
                # Simulate handler writing an event
                conn = sqlite3.connect(str(tmp_env["db_path"]))
                conn.execute(
                    "INSERT INTO web_events (type, data) VALUES (?, ?)",
                    ("message", json.dumps({"text": "Help text here"})),
                )
                conn.commit()
                conn.close()

            mock_cmd.side_effect = side_effect

            resp = client.post("/api/command", json={"text": "/help"})
            assert resp.status_code == 200
            data = resp.json()
            assert "events" in data
            assert len(data["events"]) >= 1
            mock_cmd.assert_called_once()

    def test_callback_endpoint(self, client, tmp_env):
        """POST /api/callback calls handle_callback and returns events."""
        with patch("social_hook.bot.buttons.handle_callback") as mock_cb:

            def side_effect(event, adapter, config):
                conn = sqlite3.connect(str(tmp_env["db_path"]))
                conn.execute(
                    "INSERT INTO web_events (type, data) VALUES (?, ?)",
                    ("message", json.dumps({"text": "Approved!"})),
                )
                conn.commit()
                conn.close()

            mock_cb.side_effect = side_effect

            resp = client.post("/api/callback", json={"action": "approve", "payload": "draft_1"})
            assert resp.status_code == 200
            data = resp.json()
            assert "events" in data
            mock_cb.assert_called_once()

    def test_message_endpoint(self, client, tmp_env):
        """POST /api/message calls handle_message and returns events."""
        with patch("social_hook.bot.commands.handle_message") as mock_msg:
            mock_msg.return_value = None

            resp = client.post("/api/message", json={"text": "hello"})
            assert resp.status_code == 200
            data = resp.json()
            assert "events" in data
            mock_msg.assert_called_once()

    def test_events_endpoint_sse(self, client, tmp_env):
        """GET /api/events returns text/event-stream."""
        # Insert an event first
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.execute(
            "INSERT INTO web_events (type, data) VALUES (?, ?)",
            ("message", json.dumps({"text": "test"})),
        )
        conn.commit()
        conn.close()

        resp = client.get("/api/events?lastId=0&max_empty=1")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")


# ---------------------------------------------------------------------------
# Data query tests
# ---------------------------------------------------------------------------


class TestDataEndpoints:
    def test_drafts_endpoint(self, client, tmp_env):
        """GET /api/drafts returns all drafts."""
        # Insert test draft
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.execute(
            "INSERT INTO drafts (id, project_id, decision_id, platform, content, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("draft_1", "proj_1", "dec_1", "x", "Hello world", "draft"),
        )
        conn.commit()
        conn.close()

        resp = client.get("/api/drafts")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["drafts"]) == 1
        assert data["drafts"][0]["id"] == "draft_1"

    def test_drafts_status_filter(self, client, tmp_env):
        """GET /api/drafts?status=scheduled filters correctly."""
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.execute(
            "INSERT INTO drafts (id, project_id, decision_id, platform, content, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("draft_1", "proj_1", "dec_1", "x", "Hello", "draft"),
        )
        conn.execute(
            "INSERT INTO drafts (id, project_id, decision_id, platform, content, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("draft_2", "proj_1", "dec_1", "x", "Scheduled", "scheduled"),
        )
        conn.commit()
        conn.close()

        resp = client.get("/api/drafts?status=scheduled")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["drafts"]) == 1
        assert data["drafts"][0]["id"] == "draft_2"

    def test_draft_detail_endpoint(self, client, tmp_env):
        """GET /api/drafts/{id} returns draft with tweets and changes."""
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.execute(
            "INSERT INTO drafts (id, project_id, decision_id, platform, content, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("draft_1", "proj_1", "dec_1", "x", "Hello", "draft"),
        )
        conn.execute(
            "INSERT INTO draft_tweets (id, draft_id, position, content) VALUES (?, ?, ?, ?)",
            ("tweet_1", "draft_1", 0, "First tweet"),
        )
        conn.execute(
            "INSERT INTO draft_changes (id, draft_id, field, old_value, new_value, changed_by) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("change_1", "draft_1", "content", "old", "new", "human"),
        )
        conn.commit()
        conn.close()

        resp = client.get("/api/drafts/draft_1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "draft_1"
        assert len(data["tweets"]) == 1
        assert len(data["changes"]) == 1

    def test_draft_detail_not_found(self, client, tmp_env):
        """GET /api/drafts/{id} returns 404 for unknown draft."""
        resp = client.get("/api/drafts/nonexistent")
        assert resp.status_code == 404

    def test_projects_endpoint(self, client, tmp_env):
        """GET /api/projects returns all projects."""
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj_1", "My Project", "/path/to/repo"),
        )
        conn.commit()
        conn.close()

        resp = client.get("/api/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["projects"]) == 1
        assert data["projects"][0]["name"] == "My Project"

    def test_media_endpoint(self, client, tmp_env):
        """GET /api/media/{path} serves files from media cache."""
        media_dir = tmp_env["media_dir"]
        test_file = media_dir / "test.png"
        test_file.write_bytes(b"\x89PNG fake image data")

        resp = client.get("/api/media/test.png")
        assert resp.status_code == 200

    def test_media_path_traversal(self, client, tmp_env):
        """GET /api/media with path traversal is rejected."""
        resp = client.get("/api/media/../../../etc/passwd")
        assert resp.status_code in (403, 404)


# ---------------------------------------------------------------------------
# Settings tests
# ---------------------------------------------------------------------------


class TestSettingsEndpoints:
    def test_get_config_defaults(self, client, tmp_env):
        """GET /api/settings/config returns defaults when no file exists."""
        resp = client.get("/api/settings/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "config" in data
        # Should have the default config structure
        assert "models" in data["config"]

    def test_get_config_existing(self, client, tmp_env):
        """GET /api/settings/config returns existing config."""
        config = {
            "models": {"evaluator": "anthropic/claude-opus-4-5"},
            "platforms": {"x": {"enabled": True, "priority": "primary", "account_tier": "free"}},
        }
        tmp_env["config_path"].write_text(yaml.dump(config))

        resp = client.get("/api/settings/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["config"]["models"]["evaluator"] == "anthropic/claude-opus-4-5"

    def test_update_config_models(self, client, tmp_env):
        """PUT /api/settings/config updates model config."""
        # Write initial config
        config = {
            "models": {
                "evaluator": "anthropic/claude-opus-4-5",
                "drafter": "anthropic/claude-opus-4-5",
                "gatekeeper": "anthropic/claude-haiku-4-5",
            },
            "platforms": {"x": {"enabled": True, "priority": "primary", "account_tier": "free"}},
        }
        tmp_env["config_path"].write_text(yaml.dump(config))

        resp = client.put(
            "/api/settings/config",
            json={"models": {"gatekeeper": "claude-cli/haiku"}},
        )
        assert resp.status_code == 200

        # Verify file was updated
        updated = yaml.safe_load(tmp_env["config_path"].read_text())
        assert updated["models"]["gatekeeper"] == "claude-cli/haiku"

    def test_update_config_invalid(self, client, tmp_env):
        """PUT /api/settings/config rejects invalid config."""
        config = {
            "models": {
                "evaluator": "anthropic/claude-opus-4-5",
                "drafter": "anthropic/claude-opus-4-5",
                "gatekeeper": "anthropic/claude-haiku-4-5",
            },
            "platforms": {"x": {"enabled": True, "priority": "primary", "account_tier": "free"}},
        }
        tmp_env["config_path"].write_text(yaml.dump(config))

        resp = client.put(
            "/api/settings/config",
            json={"models": {"evaluator": "invalid_no_slash"}},
        )
        assert resp.status_code == 400

    def test_get_env_masked(self, client, tmp_env):
        """GET /api/settings/env returns masked values."""
        tmp_env["env_path"].write_text("ANTHROPIC_API_KEY=sk-ant-1234567890abcdef\n")

        resp = client.get("/api/settings/env")
        assert resp.status_code == 200
        data = resp.json()
        assert "env" in data
        assert data["env"]["ANTHROPIC_API_KEY"] == "****cdef"

    def test_update_env_add_key(self, client, tmp_env):
        """PUT /api/settings/env adds a new key."""
        tmp_env["env_path"].write_text("")

        resp = client.put(
            "/api/settings/env",
            json={"key": "ANTHROPIC_API_KEY", "value": "sk-ant-test"},
        )
        assert resp.status_code == 200

        content = tmp_env["env_path"].read_text()
        assert 'ANTHROPIC_API_KEY="sk-ant-test"' in content

    def test_update_env_delete_key(self, client, tmp_env):
        """PUT /api/settings/env deletes a key when value is null."""
        tmp_env["env_path"].write_text("ANTHROPIC_API_KEY=sk-ant-test\nTELEGRAM_BOT_TOKEN=abc\n")

        resp = client.put(
            "/api/settings/env",
            json={"key": "ANTHROPIC_API_KEY", "value": None},
        )
        assert resp.status_code == 200

        content = tmp_env["env_path"].read_text()
        assert "ANTHROPIC_API_KEY" not in content
        assert "TELEGRAM_BOT_TOKEN" in content

    def test_env_rejects_unknown_key(self, client, tmp_env):
        """PUT /api/settings/env rejects unknown keys."""
        resp = client.put(
            "/api/settings/env",
            json={"key": "UNKNOWN_KEY_123", "value": "test"},
        )
        assert resp.status_code == 400

    def test_get_social_context(self, client, tmp_env):
        """GET /api/settings/social-context reads file."""
        sc_path = tmp_env["tmp_path"] / "social-context.md"
        sc_path.write_text("# My Voice\nTechnical but casual.")

        resp = client.get("/api/settings/social-context")
        assert resp.status_code == 200
        data = resp.json()
        assert "My Voice" in data["content"]

    def test_update_social_context(self, client, tmp_env):
        """PUT /api/settings/social-context writes file."""
        resp = client.put(
            "/api/settings/social-context",
            json={"project_path": "", "content": "# Updated voice"},
        )
        assert resp.status_code == 200

        sc_path = tmp_env["tmp_path"] / "social-context.md"
        assert sc_path.exists()
        assert "Updated voice" in sc_path.read_text()

    def test_social_context_rejects_unknown_project(self, client, tmp_env):
        """PUT /api/settings/social-context rejects non-existent project path."""
        resp = client.put(
            "/api/settings/social-context",
            json={"project_path": "/nonexistent/path/to/project", "content": "test"},
        )
        assert resp.status_code == 400

    def test_update_content_config_invalid_yaml(self, client, tmp_env):
        """PUT /api/settings/content-config rejects invalid YAML."""
        resp = client.put(
            "/api/settings/content-config",
            json={"project_path": "", "content": "key: [invalid\nyaml"},
        )
        assert resp.status_code == 400

    def test_validate_key_anthropic(self, client, tmp_env):
        """POST /api/settings/validate-key attempts anthropic validation."""
        mock_anthropic = MagicMock()
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        import sys

        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            resp = client.post(
                "/api/settings/validate-key",
                json={"provider": "anthropic", "key": "sk-ant-test"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["valid"] is True

    def test_validate_key_unknown(self, client, tmp_env):
        """POST /api/settings/validate-key returns error for unknown provider."""
        resp = client.post(
            "/api/settings/validate-key",
            json={"provider": "gemini", "key": "test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert "Unknown provider" in data["error"]

    def test_get_env_returns_key_groups(self, client, tmp_env):
        """GET /api/settings/env returns key_groups in response."""
        resp = client.get("/api/settings/env")
        assert resp.status_code == 200
        data = resp.json()
        assert "key_groups" in data
        assert "Core" in data["key_groups"]
        assert "ANTHROPIC_API_KEY" in data["key_groups"]["Core"]
        assert "Telegram" not in data["key_groups"]  # Managed in Channels section
        assert "X / Twitter" not in data["key_groups"]  # Managed in Platforms section
        assert "LinkedIn" not in data["key_groups"]  # Managed in Platforms section
        assert "Media Generation" not in data["key_groups"]  # Managed in Media Generation section
        assert "LLM Providers" in data["key_groups"]

    def test_get_content_config_parsed_empty(self, client, tmp_env):
        """GET /api/settings/content-config/parsed returns empty sections when no file."""
        resp = client.get("/api/settings/content-config/parsed")
        assert resp.status_code == 200
        data = resp.json()
        assert data == {"media_tools": {}, "strategy": {}, "context": {}, "summary": {}}

    def test_get_content_config_parsed_with_data(self, client, tmp_env):
        """GET /api/settings/content-config/parsed returns structured sections."""
        cc_path = tmp_env["tmp_path"] / "content-config.yaml"
        cc_data = {
            "media_tools": {"mermaid": {"enabled": True}},
            "strategy": {"narrative_debt_threshold": 5},
            "context": {"recent_decisions": 20},
            "summary": {"refresh_after_commits": 10},
        }
        cc_path.write_text(yaml.dump(cc_data))

        resp = client.get("/api/settings/content-config/parsed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["media_tools"]["mermaid"]["enabled"] is True
        assert data["strategy"]["narrative_debt_threshold"] == 5
        assert data["context"]["recent_decisions"] == 20
        assert data["summary"]["refresh_after_commits"] == 10

    def test_update_content_config_parsed_merge(self, client, tmp_env):
        """PUT /api/settings/content-config/parsed merges and writes correctly."""
        cc_path = tmp_env["tmp_path"] / "content-config.yaml"
        cc_data = {
            "media_tools": {"mermaid": {"enabled": True}},
            "strategy": {"narrative_debt_threshold": 3},
        }
        cc_path.write_text(yaml.dump(cc_data))

        # Update only strategy section
        resp = client.put(
            "/api/settings/content-config/parsed",
            json={"strategy": {"narrative_debt_threshold": 7}},
        )
        assert resp.status_code == 200

        # Verify file: strategy updated, media_tools preserved
        updated = yaml.safe_load(cc_path.read_text())
        assert updated["strategy"]["narrative_debt_threshold"] == 7
        assert updated["media_tools"]["mermaid"]["enabled"] is True

    def test_content_config_parsed_round_trip(self, client, tmp_env):
        """Write via parsed API, read back -> consistent."""
        # Write initial data
        resp = client.put(
            "/api/settings/content-config/parsed",
            json={
                "media_tools": {"ray_so": {"enabled": False}},
                "context": {"max_tokens": 100000},
            },
        )
        assert resp.status_code == 200

        # Read back
        resp = client.get("/api/settings/content-config/parsed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["media_tools"]["ray_so"]["enabled"] is False
        assert data["context"]["max_tokens"] == 100000
        # Non-provided sections should be empty
        assert data["strategy"] == {}
        assert data["summary"] == {}

    def test_toggle_pause(self, client, tmp_env):
        """PUT /api/projects/{id}/pause toggles paused state."""
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.execute(
            "INSERT INTO projects (id, name, repo_path, paused) VALUES (?, ?, ?, ?)",
            ("proj_1", "Test Project", "/tmp/repo", 0),
        )
        conn.commit()
        conn.close()

        # Toggle on
        resp = client.put("/api/projects/proj_1/pause")
        assert resp.status_code == 200
        data = resp.json()
        assert data["paused"] == 1

        # Toggle off
        resp = client.put("/api/projects/proj_1/pause")
        assert resp.status_code == 200
        data = resp.json()
        assert data["paused"] == 0

    def test_toggle_pause_not_found(self, client, tmp_env):
        """PUT /api/projects/{id}/pause returns 404 for unknown project."""
        resp = client.put("/api/projects/nonexistent/pause")
        assert resp.status_code == 404

    def test_get_project_branches(self, client, tmp_env):
        """GET /api/projects/{id}/branches returns branches."""
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj_br", "Branch Project", "/tmp/repo"),
        )
        conn.commit()
        conn.close()

        def run_side_effect(cmd, **kwargs):
            result = MagicMock()
            if "branch" in cmd:
                result.stdout = "main\ndevelop\nfeature/x\n"
                result.returncode = 0
            elif "rev-parse" in cmd:
                result.stdout = "main\n"
                result.returncode = 0
            return result

        with patch("subprocess.run", side_effect=run_side_effect):
            resp = client.get("/api/projects/proj_br/branches")
            assert resp.status_code == 200
            data = resp.json()
            assert "branches" in data
            assert "current" in data

    def test_get_project_branches_not_found(self, client, tmp_env):
        """GET /api/projects/{id}/branches returns 404 for unknown project."""
        resp = client.get("/api/projects/nonexistent/branches")
        assert resp.status_code == 404

    def test_set_trigger_branch(self, client, tmp_env):
        """PUT /api/projects/{id}/trigger-branch sets branch."""
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj_tb", "TB Project", "/tmp/repo"),
        )
        conn.commit()
        conn.close()

        resp = client.put(
            "/api/projects/proj_tb/trigger-branch",
            json={"branch": "main"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["trigger_branch"] == "main"

    def test_clear_trigger_branch(self, client, tmp_env):
        """PUT /api/projects/{id}/trigger-branch clears with null."""
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.execute(
            "INSERT INTO projects (id, name, repo_path, trigger_branch) VALUES (?, ?, ?, ?)",
            ("proj_cl", "CL Project", "/tmp/repo", "main"),
        )
        conn.commit()
        conn.close()

        resp = client.put(
            "/api/projects/proj_cl/trigger-branch",
            json={"branch": None},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["trigger_branch"] is None


# ---------------------------------------------------------------------------
# WebSocket tests
# ---------------------------------------------------------------------------


class TestWebSocketEndpoints:
    def test_ws_connect_disconnect(self, client, tmp_env):
        """WebSocket connection lifecycle."""
        with client.websocket_connect("/ws") as ws:
            # Connection should succeed
            ws.send_json({"type": "subscribe", "payload": {"channel": "web"}})
            # Just verify no exception

    def test_ws_malformed_envelope(self, client, tmp_env):
        """Error envelope returned for invalid data."""
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"invalid": "data"})
            resp = ws.receive_json()
            assert resp["type"] == "error"
            assert "message" in resp["payload"]

    def test_ws_subscribe_replays_missed_events(self, client, tmp_env):
        """Subscribe with last_seen_id replays missed events."""
        # Insert events
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        for i in range(3):
            conn.execute(
                "INSERT INTO web_events (type, data) VALUES (?, ?)",
                ("message", json.dumps({"text": f"msg {i}"})),
            )
        conn.commit()
        conn.close()

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "subscribe", "payload": {"channel": "web", "last_seen_id": 1}})
            # Should receive events with id > 1 (i.e., events 2 and 3)
            events = []
            for _ in range(2):
                try:
                    resp = ws.receive_json(mode="binary")
                except Exception:
                    break
                events.append(resp)


# ---------------------------------------------------------------------------
# Installation endpoint tests
# ---------------------------------------------------------------------------


class TestInstallationEndpoints:
    def test_installations_status(self, client, tmp_env):
        """GET /api/installations/status returns all component statuses."""
        with (
            patch("social_hook.setup.install.check_hook_installed", return_value=True),
            patch("social_hook.setup.install.check_narrative_hook_installed", return_value=False),
            patch("social_hook.setup.install.check_cron_installed", return_value=True),
            patch("social_hook.bot.process.is_running", return_value=False),
        ):
            resp = client.get("/api/installations/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["commit_hook"] is True
            assert data["narrative_hook"] is False
            assert data["scheduler_cron"] is True
            assert data["bot_daemon"] is False

    def test_install_commit_hook(self, client, tmp_env):
        with patch(
            "social_hook.setup.install.install_hook", return_value=(True, "Installed")
        ) as mock_fn:
            resp = client.post("/api/installations/commit_hook/install")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            mock_fn.assert_called_once()

    def test_uninstall_commit_hook(self, client, tmp_env):
        with patch(
            "social_hook.setup.install.uninstall_hook", return_value=(True, "Removed")
        ) as mock_fn:
            resp = client.post("/api/installations/commit_hook/uninstall")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            mock_fn.assert_called_once()

    def test_install_invalid_component(self, client, tmp_env):
        resp = client.post("/api/installations/invalid_thing/install")
        assert resp.status_code == 400

    def test_bot_daemon_start(self, client, tmp_env):
        import social_hook.web.server as srv

        srv._bot_proc = None
        with (
            patch("social_hook.bot.process.is_running", return_value=False),
            patch("subprocess.Popen"),
        ):
            resp = client.post("/api/installations/bot_daemon/start")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
        srv._bot_proc = None

    def test_bot_daemon_stop(self, client, tmp_env):
        import social_hook.web.server as srv

        srv._bot_proc = None
        with (
            patch("social_hook.bot.process.is_running", return_value=True),
            patch("social_hook.bot.process.stop_bot", return_value=True),
        ):
            resp = client.post("/api/installations/bot_daemon/stop")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
        srv._bot_proc = None

    def test_journey_capture_toggle_installs_hook(self, client, tmp_env):
        """Toggling journey_capture.enabled to True installs narrative hook."""
        config = {
            "models": {
                "evaluator": "anthropic/claude-opus-4-5",
                "drafter": "anthropic/claude-opus-4-5",
                "gatekeeper": "anthropic/claude-haiku-4-5",
            },
            "platforms": {"x": {"enabled": True, "priority": "primary", "account_tier": "free"}},
        }
        tmp_env["config_path"].write_text(yaml.dump(config))

        with patch(
            "social_hook.setup.install.install_narrative_hook", return_value=(True, "Installed")
        ) as mock_install:
            resp = client.put("/api/settings/config", json={"journey_capture": {"enabled": True}})
            assert resp.status_code == 200
            mock_install.assert_called_once()

    def test_journey_capture_toggle_uninstalls_hook(self, client, tmp_env):
        """Toggling journey_capture.enabled to False uninstalls narrative hook."""
        config = {
            "models": {
                "evaluator": "anthropic/claude-opus-4-5",
                "drafter": "anthropic/claude-opus-4-5",
                "gatekeeper": "anthropic/claude-haiku-4-5",
            },
            "platforms": {"x": {"enabled": True, "priority": "primary", "account_tier": "free"}},
            "journey_capture": {"enabled": True},
        }
        tmp_env["config_path"].write_text(yaml.dump(config))

        with patch(
            "social_hook.setup.install.uninstall_narrative_hook", return_value=(True, "Removed")
        ) as mock_uninstall:
            resp = client.put("/api/settings/config", json={"journey_capture": {"enabled": False}})
            assert resp.status_code == 200
            mock_uninstall.assert_called_once()

    def test_bot_daemon_start_replaces_existing(self, client, tmp_env):
        """Starting bot when one is already running stops the old one first."""
        import social_hook.web.server as srv

        srv._bot_proc = None
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        with (
            patch("social_hook.bot.process.is_running", return_value=True),
            patch("social_hook.bot.process.stop_bot", return_value=True) as mock_stop,
            patch("asyncio.sleep", return_value=None),
            patch("shutil.which", return_value="/usr/bin/social-hook"),
            patch("subprocess.Popen", return_value=mock_proc),
        ):
            resp = client.post("/api/installations/bot_daemon/start")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert "starting" in data["message"].lower()
            mock_stop.assert_called_once()
        srv._bot_proc = None

    def test_bot_daemon_start_writes_pid_eagerly(self, client, tmp_env):
        """PID file is written immediately after Popen, not waiting for child."""
        import social_hook.web.server as srv

        srv._bot_proc = None
        mock_proc = MagicMock()
        mock_proc.pid = 99999
        with (
            patch("social_hook.bot.process.is_running", return_value=False),
            patch("shutil.which", return_value="/usr/bin/social-hook"),
            patch("subprocess.Popen", return_value=mock_proc),
        ):
            resp = client.post("/api/installations/bot_daemon/start")
            assert resp.status_code == 200
        # Verify PID was written
        from social_hook.bot.process import get_pid_file

        pid_file = get_pid_file()
        assert pid_file.exists()
        assert pid_file.read_text().strip() == "99999"

    def test_project_detail_includes_journey_capture(self, client, tmp_env):
        """Project detail response includes journey_capture_enabled."""
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj_1", "Test", "/tmp/repo"),
        )
        conn.execute("INSERT INTO lifecycles (project_id) VALUES (?)", ("proj_1",))
        conn.execute(
            "INSERT INTO narrative_debt (project_id, debt_counter) VALUES (?, ?)", ("proj_1", 0)
        )
        conn.commit()
        conn.close()

        narratives_path = tmp_env["tmp_path"] / "narratives"
        narratives_path.mkdir(exist_ok=True)

        with patch("social_hook.web.server.get_narratives_path", return_value=narratives_path):
            resp = client.get("/api/projects/proj_1")
            assert resp.status_code == 200
            data = resp.json()
            assert "journey_capture_enabled" in data

    def test_put_project_summary(self, client, tmp_env):
        """PUT /api/projects/{id}/summary updates the project summary."""
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj_1", "Test", "/tmp/repo"),
        )
        conn.commit()
        conn.close()

        resp = client.put(
            "/api/projects/proj_1/summary",
            json={"summary": "Updated summary text"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        # Verify summary was persisted
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        row = conn.execute("SELECT summary FROM projects WHERE id = ?", ("proj_1",)).fetchone()
        conn.close()
        assert row[0] == "Updated summary text"

    def test_put_project_summary_not_found(self, client, tmp_env):
        """PUT /api/projects/{id}/summary returns 404 for unknown project."""
        resp = client.put(
            "/api/projects/nonexistent/summary",
            json={"summary": "text"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Channels endpoint tests
# ---------------------------------------------------------------------------


class TestChannelsEndpoints:
    def test_channels_status(self, client, tmp_env):
        """GET /api/channels/status returns all channel statuses."""
        with patch("social_hook.bot.process.is_running", return_value=False):
            resp = client.get("/api/channels/status")
            assert resp.status_code == 200
            data = resp.json()
            assert "channels" in data
            assert "daemon_running" in data
            assert data["daemon_running"] is False
            # All 3 known channels present
            assert "telegram" in data["channels"]
            assert "slack" in data["channels"]
            assert "web" in data["channels"]
            # Web defaults to enabled
            assert data["channels"]["web"]["enabled"] is True
            assert data["channels"]["web"]["credentials_configured"] is True

    def test_channels_status_web_disabled(self, client, tmp_env):
        """Web channel respects channels config when explicitly disabled."""
        config = {
            "channels": {"web": {"enabled": False}},
        }
        tmp_env["config_path"].write_text(yaml.dump(config))
        import social_hook.web.server as srv

        srv._config = None

        with patch("social_hook.bot.process.is_running", return_value=False):
            resp = client.get("/api/channels/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["channels"]["web"]["enabled"] is False

    def test_channels_status_with_config(self, client, tmp_env):
        """Channels status reflects config.yaml settings."""
        config = {
            "channels": {"telegram": {"enabled": True, "allowed_chat_ids": ["123"]}},
        }
        tmp_env["config_path"].write_text(yaml.dump(config))
        import social_hook.web.server as srv

        srv._config = None

        tmp_env["env_path"].write_text('TELEGRAM_BOT_TOKEN="test_token"\n')
        srv._config = None

        with patch("social_hook.bot.process.is_running", return_value=True):
            resp = client.get("/api/channels/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["channels"]["telegram"]["enabled"] is True
            assert data["channels"]["telegram"]["credentials_configured"] is True
            assert data["channels"]["telegram"]["allowed_chat_ids"] == ["123"]
            assert data["daemon_running"] is True

    def test_test_channel_web(self, client, tmp_env):
        """POST /api/channels/web/test always succeeds."""
        resp = client.post("/api/channels/web/test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_test_channel_slack(self, client, tmp_env):
        """POST /api/channels/slack/test returns coming soon."""
        resp = client.post("/api/channels/slack/test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "coming soon" in data["error"].lower()

    def test_test_channel_unknown(self, client, tmp_env):
        """POST /api/channels/unknown/test returns 400."""
        resp = client.post("/api/channels/unknown/test")
        assert resp.status_code == 400

    def test_test_channel_telegram_no_token(self, client, tmp_env):
        """POST /api/channels/telegram/test without token returns error."""
        resp = client.post("/api/channels/telegram/test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "not configured" in data["error"]

    def test_test_channel_telegram_success(self, client, tmp_env):
        """POST /api/channels/telegram/test with valid token returns username."""
        tmp_env["env_path"].write_text('TELEGRAM_BOT_TOKEN="test_token"\n')
        import social_hook.web.server as srv

        srv._config = None

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"username": "my_test_bot"}}

        with patch("requests.get", return_value=mock_resp):
            resp = client.post("/api/channels/telegram/test")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["info"]["username"] == "my_test_bot"

    def test_test_channel_telegram_failure(self, client, tmp_env):
        """POST /api/channels/telegram/test with bad token returns sanitized error."""
        tmp_env["env_path"].write_text('TELEGRAM_BOT_TOKEN="bad_token"\n')
        import social_hook.web.server as srv

        srv._config = None

        import requests as req_lib

        with patch(
            "requests.get", side_effect=req_lib.RequestException("Connection failed with token")
        ):
            resp = client.post("/api/channels/telegram/test")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is False
            assert "Failed to connect" in data["error"]
            # Verify token is NOT in error message
            assert "bad_token" not in data["error"]


# ---------------------------------------------------------------------------
# Session isolation tests
# ---------------------------------------------------------------------------


class TestSessionIsolation:
    def test_different_sessions_produce_isolated_events(self, client, tmp_env):
        """Commands with different X-Session-Id headers create isolated event streams."""
        with patch("social_hook.bot.commands.handle_command") as mock_cmd:
            mock_cmd.return_value = None

            # Send command from session A
            resp_a = client.post(
                "/api/command",
                json={"text": "/help"},
                headers={"X-Session-Id": "session-a"},
            )
            assert resp_a.status_code == 200
            events_a = resp_a.json()["events"]

            # Send command from session B
            resp_b = client.post(
                "/api/command",
                json={"text": "/status"},
                headers={"X-Session-Id": "session-b"},
            )
            assert resp_b.status_code == 200
            events_b = resp_b.json()["events"]

            # Events from session B should NOT include events from session A
            a_ids = {e["id"] for e in events_a}
            b_ids = {e["id"] for e in events_b}
            assert a_ids.isdisjoint(b_ids), "Session events should not overlap"

    def test_session_scoped_history(self, client, tmp_env):
        """GET /api/events/history scoped to session returns only that session's events."""
        # Insert events for two sessions directly
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.execute(
            "INSERT INTO web_events (type, data, session_id) VALUES (?, ?, ?)",
            ("message", json.dumps({"text": "from A"}), "sess-1"),
        )
        conn.execute(
            "INSERT INTO web_events (type, data, session_id) VALUES (?, ?, ?)",
            ("message", json.dumps({"text": "from B"}), "sess-2"),
        )
        # Broadcast event (no session)
        conn.execute(
            "INSERT INTO web_events (type, data) VALUES (?, ?)",
            ("data_change", json.dumps({"entity": "draft"})),
        )
        conn.commit()
        conn.close()

        # Session 1 should see its event + broadcast
        resp = client.get(
            "/api/events/history",
            headers={"X-Session-Id": "sess-1"},
        )
        assert resp.status_code == 200
        events = resp.json()["events"]
        texts = [e["data"].get("text") for e in events]
        assert "from A" in texts
        assert "from B" not in texts

    def test_broadcast_events_visible_to_all_sessions(self, client, tmp_env):
        """Events with session_id=NULL (broadcast) appear for all sessions."""
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.execute(
            "INSERT INTO web_events (type, data) VALUES (?, ?)",
            ("message", json.dumps({"text": "broadcast msg"})),
        )
        conn.commit()
        conn.close()

        # Both sessions should see the broadcast event
        for session in ("alpha", "beta"):
            resp = client.get(
                "/api/events/history",
                headers={"X-Session-Id": session},
            )
            assert resp.status_code == 200
            events = resp.json()["events"]
            texts = [e["data"].get("text") for e in events]
            assert "broadcast msg" in texts

    def test_scoped_events_only_for_their_session(self, client, tmp_env):
        """Events with a session_id only appear in that session's history."""
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.execute(
            "INSERT INTO web_events (type, data, session_id) VALUES (?, ?, ?)",
            ("message", json.dumps({"text": "private"}), "only-me"),
        )
        conn.commit()
        conn.close()

        # Same session should see it
        resp = client.get(
            "/api/events/history",
            headers={"X-Session-Id": "only-me"},
        )
        events = resp.json()["events"]
        assert any(e["data"].get("text") == "private" for e in events)

        # Different session should NOT see it
        resp = client.get(
            "/api/events/history",
            headers={"X-Session-Id": "other-session"},
        )
        events = resp.json()["events"]
        assert not any(e["data"].get("text") == "private" for e in events)

    def test_clear_events_scoped_to_session(self, client, tmp_env):
        """POST /api/events/clear only clears the requesting session's events."""
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.execute(
            "INSERT INTO web_events (type, data, session_id) VALUES (?, ?, ?)",
            ("message", json.dumps({"text": "keep me"}), "session-keep"),
        )
        conn.execute(
            "INSERT INTO web_events (type, data, session_id) VALUES (?, ?, ?)",
            ("message", json.dumps({"text": "delete me"}), "session-delete"),
        )
        conn.commit()
        conn.close()

        # Clear session-delete
        resp = client.post(
            "/api/events/clear",
            headers={"X-Session-Id": "session-delete"},
        )
        assert resp.status_code == 200

        # Verify session-delete events are gone
        resp = client.get(
            "/api/events/history",
            headers={"X-Session-Id": "session-delete"},
        )
        events = resp.json()["events"]
        assert not any(e["data"].get("text") == "delete me" for e in events)

        # Verify session-keep events are still there
        resp = client.get(
            "/api/events/history",
            headers={"X-Session-Id": "session-keep"},
        )
        events = resp.json()["events"]
        assert any(e["data"].get("text") == "keep me" for e in events)

    def test_message_endpoint_session_scoped(self, client, tmp_env):
        """POST /api/message uses session-scoped adapter."""
        with patch("social_hook.bot.commands.handle_message") as mock_msg:
            mock_msg.return_value = None

            resp = client.post(
                "/api/message",
                json={"text": "hello"},
                headers={"X-Session-Id": "msg-session"},
            )
            assert resp.status_code == 200

            # Verify handler was called with scoped chat_id
            call_args = mock_msg.call_args
            msg_arg = call_args[0][0]
            assert msg_arg.chat_id == "web:msg-session"

    def test_callback_endpoint_session_scoped(self, client, tmp_env):
        """POST /api/callback uses session-scoped adapter."""
        with patch("social_hook.bot.buttons.handle_callback") as mock_cb:
            mock_cb.return_value = None

            resp = client.post(
                "/api/callback",
                json={"action": "approve", "payload": "draft_1"},
                headers={"X-Session-Id": "cb-session"},
            )
            assert resp.status_code == 200

            # Verify handler was called with scoped chat_id
            call_args = mock_cb.call_args
            event_arg = call_args[0][0]
            assert event_arg.chat_id == "web:cb-session"

    def test_default_session_without_header(self, client, tmp_env):
        """Endpoints work with default session when no X-Session-Id header sent."""
        with patch("social_hook.bot.commands.handle_command") as mock_cmd:
            mock_cmd.return_value = None

            # No X-Session-Id header — should default to "web"
            resp = client.post("/api/command", json={"text": "/help"})
            assert resp.status_code == 200

            call_args = mock_cmd.call_args
            msg_arg = call_args[0][0]
            assert msg_arg.chat_id == "web:web"


class TestMemoryAPI:
    """Tests for /api/settings/memories endpoints."""

    def test_get_memories(self, client, tmp_env):
        """GET /api/settings/memories returns entries."""
        # Create a project dir with a memory
        project_dir = tmp_env["tmp_path"] / "myproject"
        project_dir.mkdir()
        config_dir = project_dir / ".social-hook"
        config_dir.mkdir()

        from social_hook.config.project import save_memory

        save_memory(str(project_dir), "ctx", "fb", "d1")

        resp = client.get(f"/api/settings/memories?project_path={project_dir}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["memories"][0]["context"] == "ctx"

    def test_add_memory(self, client, tmp_env):
        """POST /api/settings/memories adds entry, roundtrip with GET."""
        project_dir = tmp_env["tmp_path"] / "myproject"
        project_dir.mkdir()
        config_dir = project_dir / ".social-hook"
        config_dir.mkdir()

        resp = client.post(
            "/api/settings/memories",
            json={
                "project_path": str(project_dir),
                "context": "test context",
                "feedback": "test feedback",
                "draft_id": "d42",
            },
        )
        assert resp.status_code == 200

        resp2 = client.get(f"/api/settings/memories?project_path={project_dir}")
        data = resp2.json()
        assert data["count"] == 1
        assert data["memories"][0]["feedback"] == "test feedback"

    def test_delete_memory(self, client, tmp_env):
        """DELETE /api/settings/memories/{index} removes entry."""
        project_dir = tmp_env["tmp_path"] / "myproject"
        project_dir.mkdir()
        config_dir = project_dir / ".social-hook"
        config_dir.mkdir()

        from social_hook.config.project import save_memory

        save_memory(str(project_dir), "ctx1", "fb1", "d1")
        save_memory(str(project_dir), "ctx2", "fb2", "d2")

        resp = client.delete(f"/api/settings/memories/0?project_path={project_dir}")
        assert resp.status_code == 200

        resp2 = client.get(f"/api/settings/memories?project_path={project_dir}")
        data = resp2.json()
        assert data["count"] == 1
        assert data["memories"][0]["context"] == "ctx2"

    def test_delete_memory_404(self, client, tmp_env):
        """DELETE /api/settings/memories/{index} with invalid index returns 404."""
        project_dir = tmp_env["tmp_path"] / "myproject"
        project_dir.mkdir()
        config_dir = project_dir / ".social-hook"
        config_dir.mkdir()

        resp = client.delete(f"/api/settings/memories/99?project_path={project_dir}")
        assert resp.status_code == 404

    def test_clear_memories(self, client, tmp_env):
        """POST /api/settings/memories/clear returns count, empties list."""
        project_dir = tmp_env["tmp_path"] / "myproject"
        project_dir.mkdir()
        config_dir = project_dir / ".social-hook"
        config_dir.mkdir()

        from social_hook.config.project import save_memory

        save_memory(str(project_dir), "ctx1", "fb1", "d1")
        save_memory(str(project_dir), "ctx2", "fb2", "d2")

        resp = client.post(f"/api/settings/memories/clear?project_path={project_dir}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2

        resp2 = client.get(f"/api/settings/memories?project_path={project_dir}")
        assert resp2.json()["count"] == 0


# ---------------------------------------------------------------------------
# Arc endpoint tests
# ---------------------------------------------------------------------------


class TestArcEndpoints:
    """Tests for POST/PUT /api/projects/{id}/arcs endpoints."""

    def _insert_project(self, db_path, project_id="proj_1", name="test"):
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            (project_id, name, "/tmp/test"),
        )
        conn.commit()
        conn.close()

    def _insert_arc(self, db_path, arc_id, project_id="proj_1", theme="Test", status="active"):
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO arcs (id, project_id, theme, status) VALUES (?, ?, ?, ?)",
            (arc_id, project_id, theme, status),
        )
        conn.commit()
        conn.close()

    def test_create_arc(self, client, tmp_env):
        """POST /api/projects/{id}/arcs creates a new arc."""
        self._insert_project(tmp_env["db_path"])
        resp = client.post("/api/projects/proj_1/arcs", json={"theme": "Auth system"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "created"
        assert data["arc_id"].startswith("arc_")

    def test_create_arc_with_notes(self, client, tmp_env):
        """POST /api/projects/{id}/arcs with notes saves them."""
        self._insert_project(tmp_env["db_path"])
        resp = client.post(
            "/api/projects/proj_1/arcs", json={"theme": "Auth", "notes": "Focus on JWT"}
        )
        assert resp.status_code == 200
        arc_id = resp.json()["arc_id"]

        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT notes FROM arcs WHERE id = ?", (arc_id,)).fetchone()
        conn.close()
        assert row["notes"] == "Focus on JWT"

    def test_create_arc_max_limit(self, client, tmp_env):
        """POST /api/projects/{id}/arcs returns 409 when 3 active arcs exist."""
        self._insert_project(tmp_env["db_path"])
        for i in range(3):
            self._insert_arc(tmp_env["db_path"], f"arc_{i}", theme=f"Arc {i}")

        resp = client.post("/api/projects/proj_1/arcs", json={"theme": "Fourth arc"})
        assert resp.status_code == 409
        assert "Maximum 3" in resp.json()["detail"]

    def test_create_arc_project_not_found(self, client, tmp_env):
        """POST /api/projects/{id}/arcs returns 404 for unknown project."""
        resp = client.post("/api/projects/nonexistent/arcs", json={"theme": "Test"})
        assert resp.status_code == 404

    def test_update_arc_status(self, client, tmp_env):
        """PUT /api/projects/{id}/arcs/{arc_id} updates status."""
        self._insert_project(tmp_env["db_path"])
        self._insert_arc(tmp_env["db_path"], "arc_upd")

        resp = client.put("/api/projects/proj_1/arcs/arc_upd", json={"status": "completed"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT status FROM arcs WHERE id = ?", ("arc_upd",)).fetchone()
        conn.close()
        assert row["status"] == "completed"

    def test_update_arc_notes(self, client, tmp_env):
        """PUT /api/projects/{id}/arcs/{arc_id} updates notes."""
        self._insert_project(tmp_env["db_path"])
        self._insert_arc(tmp_env["db_path"], "arc_notes")

        resp = client.put("/api/projects/proj_1/arcs/arc_notes", json={"notes": "Updated notes"})
        assert resp.status_code == 200

        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT notes FROM arcs WHERE id = ?", ("arc_notes",)).fetchone()
        conn.close()
        assert row["notes"] == "Updated notes"

    def test_update_arc_invalid_status(self, client, tmp_env):
        """PUT /api/projects/{id}/arcs/{arc_id} rejects invalid status."""
        self._insert_project(tmp_env["db_path"])
        self._insert_arc(tmp_env["db_path"], "arc_inv")

        resp = client.put("/api/projects/proj_1/arcs/arc_inv", json={"status": "invalid"})
        assert resp.status_code == 400
        assert "Invalid status" in resp.json()["detail"]

    def test_update_arc_not_found(self, client, tmp_env):
        """PUT /api/projects/{id}/arcs/{arc_id} returns 404 for missing arc."""
        self._insert_project(tmp_env["db_path"])

        resp = client.put("/api/projects/proj_1/arcs/arc_missing", json={"status": "completed"})
        assert resp.status_code == 404

    def test_update_arc_wrong_project(self, client, tmp_env):
        """PUT /api/projects/{id}/arcs/{arc_id} returns 404 if arc belongs to another project."""
        self._insert_project(tmp_env["db_path"], "proj_1")
        self._insert_project(tmp_env["db_path"], "proj_2", "other")
        self._insert_arc(tmp_env["db_path"], "arc_other", project_id="proj_2")

        resp = client.put("/api/projects/proj_1/arcs/arc_other", json={"status": "completed"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Create-draft endpoint tests
# ---------------------------------------------------------------------------


def _make_draft_result(
    draft_id="draft_test_1", decision_id="dec_1", project_id="proj_1", platform="x"
):
    """Build a mock DraftResult for testing."""
    from datetime import datetime as dt
    from datetime import timezone

    from social_hook.drafting import DraftResult
    from social_hook.models.core import Draft
    from social_hook.scheduling import ScheduleResult

    draft = Draft(
        id=draft_id,
        project_id=project_id,
        decision_id=decision_id,
        platform=platform,
        content="Test draft content",
    )
    schedule = ScheduleResult(
        datetime=dt.now(timezone.utc),
        is_optimal_day=True,
        deferred=False,
        day_reason="test",
        time_reason="test",
    )
    return DraftResult(draft=draft, schedule=schedule, thread_tweets=[])


def _mock_create_draft_patches():
    """Return context managers for mocking the create-draft pipeline."""
    from social_hook.config.project import ProjectConfig
    from social_hook.models.context import ProjectContext
    from social_hook.models.core import CommitInfo

    mock_commit = CommitInfo(hash="abc123", message="feat: test", diff="", files_changed=[])
    mock_project_config = ProjectConfig(repo_path="/tmp/test")
    mock_context = MagicMock(spec=ProjectContext)

    return (
        patch("social_hook.trigger.parse_commit_info", return_value=mock_commit),
        patch("social_hook.config.project.load_project_config", return_value=mock_project_config),
        patch("social_hook.llm.prompts.assemble_evaluator_context", return_value=mock_context),
    )


def _seed_project_and_decision(db_path, decision_id="dec_1", project_id="proj_1", decision="draft"):
    """Seed a project and a decision."""
    conn = sqlite3.connect(str(db_path))
    # Only insert project if not exists
    existing = conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            (project_id, "Test Project", "/tmp/test"),
        )
    conn.execute(
        "INSERT INTO decisions (id, project_id, commit_hash, commit_message, decision, reasoning) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            decision_id,
            project_id,
            "abc123",
            "feat: add new feature",
            decision,
            "This is a cool feature",
        ),
    )
    conn.commit()
    conn.close()


class TestCreateDraftEndpoint:
    @staticmethod
    def _wait_for_task(db_path, task_id, timeout=5):
        """Poll DB until background task completes or times out."""
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT status, result FROM background_tasks WHERE id = ?", (task_id,)
            ).fetchone()
            conn.close()
            if row and row["status"] != "running":
                return dict(row)
            time.sleep(0.1)
        return None

    def test_create_draft_with_platform(self, client, tmp_env):
        """POST /api/decisions/{id}/create-draft returns 202 and runs in background."""
        _seed_project_and_decision(tmp_env["db_path"])

        mock_result = _make_draft_result()
        p1, p2, p3 = _mock_create_draft_patches()
        with (
            p1,
            p2,
            p3,
            patch(
                "social_hook.drafting.draft_for_platforms", return_value=[mock_result]
            ) as mock_dfp,
            patch("social_hook.notifications.notify_draft_review"),
        ):
            resp = client.post("/api/decisions/dec_1/create-draft", json={"platform": "x"})
            assert resp.status_code == 202
            data = resp.json()
            assert "task_id" in data
            assert data["status"] == "processing"

            # Wait for background thread to complete
            task = self._wait_for_task(tmp_env["db_path"], data["task_id"])
            assert task is not None
            assert task["status"] == "completed"
            result = json.loads(task["result"])
            assert result["draft_ids"] == ["draft_test_1"]
            assert result["count"] == 1

        # Verify platform was passed
        call_kwargs = mock_dfp.call_args[1]
        assert call_kwargs["target_platform_names"] == ["x"]

    def test_create_draft_no_platform(self, client, tmp_env):
        """POST /api/decisions/{id}/create-draft with no platform drafts all enabled."""
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
            patch("social_hook.notifications.notify_draft_review"),
        ):
            resp = client.post("/api/decisions/dec_1/create-draft", json={})
            assert resp.status_code == 202
            data = resp.json()
            task = self._wait_for_task(tmp_env["db_path"], data["task_id"])
            assert task is not None
            result = json.loads(task["result"])
            assert result["count"] == 2
            assert result["draft_ids"] == ["d1", "d2"]

        # target_platform_names should be None for all-enabled
        call_kwargs = mock_dfp.call_args[1]
        assert call_kwargs["target_platform_names"] is None

    def test_create_draft_not_post_worthy_override(self, client, tmp_env):
        """POST /api/decisions/{id}/create-draft works for not_post_worthy decisions."""
        _seed_project_and_decision(tmp_env["db_path"], decision="skip")

        mock_result = _make_draft_result()
        p1, p2, p3 = _mock_create_draft_patches()
        with (
            p1,
            p2,
            p3,
            patch("social_hook.drafting.draft_for_platforms", return_value=[mock_result]),
            patch("social_hook.notifications.notify_draft_review"),
        ):
            resp = client.post("/api/decisions/dec_1/create-draft", json={"platform": "x"})
            assert resp.status_code == 202
            task = self._wait_for_task(tmp_env["db_path"], resp.json()["task_id"])
            assert task is not None
            assert task["status"] == "completed"

    def test_create_draft_decision_not_found(self, client, tmp_env):
        """POST /api/decisions/{id}/create-draft returns 404 for unknown decision."""
        resp = client.post("/api/decisions/nonexistent/create-draft", json={"platform": "x"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Consolidate endpoint tests
# ---------------------------------------------------------------------------


class TestConsolidateEndpoint:
    @staticmethod
    def _wait_for_task(db_path, task_id, timeout=5):
        """Poll DB until background task completes or times out."""
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT status, result FROM background_tasks WHERE id = ?", (task_id,)
            ).fetchone()
            conn.close()
            if row and row["status"] != "running":
                return dict(row)
            time.sleep(0.1)
        return None

    def test_consolidate_two_decisions(self, client, tmp_env):
        """POST /api/decisions/consolidate with 2+ decisions returns 202."""
        _seed_project_and_decision(tmp_env["db_path"], decision_id="dec_1")
        _seed_project_and_decision(tmp_env["db_path"], decision_id="dec_2")

        mock_result = _make_draft_result(draft_id="d_con")
        p1, p2, p3 = _mock_create_draft_patches()
        with (
            p1,
            p2,
            p3,
            patch("social_hook.drafting.draft_for_platforms", return_value=[mock_result]),
            patch("social_hook.notifications.notify_draft_review"),
        ):
            resp = client.post(
                "/api/decisions/consolidate",
                json={"decision_ids": ["dec_1", "dec_2"]},
            )
            assert resp.status_code == 202
            data = resp.json()
            assert "task_id" in data
            assert data["status"] == "processing"

            task = self._wait_for_task(tmp_env["db_path"], data["task_id"])
            assert task is not None
            assert task["status"] == "completed"
            result = json.loads(task["result"])
            assert result["draft_ids"] == ["d_con"]
            assert result["count"] == 1

    def test_consolidate_less_than_2(self, client, tmp_env):
        """POST /api/decisions/consolidate with < 2 decisions returns 400."""
        resp = client.post(
            "/api/decisions/consolidate",
            json={"decision_ids": ["dec_1"]},
        )
        assert resp.status_code == 400
        assert "At least 2" in resp.json()["detail"]

    def test_consolidate_different_projects(self, client, tmp_env):
        """POST /api/decisions/consolidate with decisions from different projects returns 400."""
        # Seed two decisions from different projects
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj_1", "Project 1", "/tmp/test1"),
        )
        conn.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj_2", "Project 2", "/tmp/test2"),
        )
        conn.execute(
            "INSERT INTO decisions (id, project_id, commit_hash, decision, reasoning) "
            "VALUES (?, ?, ?, ?, ?)",
            ("dec_a", "proj_1", "aaa", "draft", "reason"),
        )
        conn.execute(
            "INSERT INTO decisions (id, project_id, commit_hash, decision, reasoning) "
            "VALUES (?, ?, ?, ?, ?)",
            ("dec_b", "proj_2", "bbb", "draft", "reason"),
        )
        conn.commit()
        conn.close()

        resp = client.post(
            "/api/decisions/consolidate",
            json={"decision_ids": ["dec_a", "dec_b"]},
        )
        assert resp.status_code == 400
        assert "same project" in resp.json()["detail"]

    def test_consolidate_invalid_decision_id(self, client, tmp_env):
        """POST /api/decisions/consolidate with invalid decision ID returns 404."""
        _seed_project_and_decision(tmp_env["db_path"], decision_id="dec_1")

        resp = client.post(
            "/api/decisions/consolidate",
            json={"decision_ids": ["dec_1", "nonexistent"]},
        )
        assert resp.status_code == 404
        assert "nonexistent" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Enabled platforms endpoint tests
# ---------------------------------------------------------------------------


class TestEnabledPlatforms:
    def test_enabled_platforms(self, client, tmp_env):
        """GET /api/platforms/enabled returns enabled platforms from config."""
        # Write a config with platforms
        config_yaml = {
            "platforms": {
                "x": {"enabled": True, "priority": "primary", "type": "x"},
                "linkedin": {"enabled": False, "priority": "secondary", "type": "linkedin"},
            }
        }
        config_path = tmp_env["config_path"]
        config_path.write_text(yaml.dump(config_yaml))

        import social_hook.web.server as srv

        srv._config = None  # Force reload

        resp = client.get("/api/platforms/enabled")
        assert resp.status_code == 200
        data = resp.json()
        assert "x" in data["platforms"]
        assert "linkedin" not in data["platforms"]
        assert data["count"] == 1
        assert data["platforms"]["x"]["priority"] == "primary"


# ---------------------------------------------------------------------------
# Filesystem browse endpoint tests
# ---------------------------------------------------------------------------


class TestFilesystemBrowse:
    def test_browse_home(self, client, tmp_env):
        """GET /api/filesystem/browse returns directories list."""
        tmp = tmp_env["tmp_path"]
        (tmp / "subdir").mkdir()

        with (
            patch("social_hook.web.server.Path.home", return_value=tmp),
            patch.dict("os.environ", {"HOME": str(tmp)}),
        ):
            resp = client.get(f"/api/filesystem/browse?path={tmp}")
            assert resp.status_code == 200
            data = resp.json()
            assert data["current"] == str(tmp)
            assert isinstance(data["directories"], list)

    def test_browse_specific_path(self, client, tmp_env):
        """GET /api/filesystem/browse navigates to specific dir."""
        tmp = tmp_env["tmp_path"]
        sub = tmp / "mydir"
        sub.mkdir()
        (sub / "child").mkdir()

        with (
            patch("social_hook.web.server.Path.home", return_value=tmp),
            patch.dict("os.environ", {"HOME": str(tmp)}),
        ):
            resp = client.get(f"/api/filesystem/browse?path={sub}")
            assert resp.status_code == 200
            data = resp.json()
            assert data["current"] == str(sub)
            assert any(d["name"] == "child" for d in data["directories"])

    def test_browse_detects_git_repos(self, client, tmp_env):
        """GET /api/filesystem/browse detects git repos via is_git flag."""
        tmp = tmp_env["tmp_path"]
        git_repo = tmp / "myrepo"
        git_repo.mkdir()
        (git_repo / ".git").mkdir()

        with (
            patch("social_hook.web.server.Path.home", return_value=tmp),
            patch.dict("os.environ", {"HOME": str(tmp)}),
        ):
            resp = client.get(f"/api/filesystem/browse?path={tmp}")
            assert resp.status_code == 200
            data = resp.json()
            repo_entry = [d for d in data["directories"] if d["name"] == "myrepo"]
            assert len(repo_entry) == 1
            assert repo_entry[0]["is_git"] is True

    def test_browse_hides_dotfiles(self, client, tmp_env):
        """GET /api/filesystem/browse hides hidden directories."""
        tmp = tmp_env["tmp_path"]
        (tmp / ".hidden").mkdir()
        (tmp / "visible").mkdir()

        with (
            patch("social_hook.web.server.Path.home", return_value=tmp),
            patch.dict("os.environ", {"HOME": str(tmp)}),
        ):
            resp = client.get(f"/api/filesystem/browse?path={tmp}")
            assert resp.status_code == 200
            data = resp.json()
            names = [d["name"] for d in data["directories"]]
            assert ".hidden" not in names
            assert "visible" in names

    def test_browse_outside_home_forbidden(self, client, tmp_env):
        """GET /api/filesystem/browse returns 403 for paths outside home."""
        tmp = tmp_env["tmp_path"]

        with (
            patch("social_hook.web.server.Path.home", return_value=tmp),
            patch.dict("os.environ", {"HOME": str(tmp)}),
        ):
            resp = client.get("/api/filesystem/browse?path=/etc")
            assert resp.status_code == 403

    def test_browse_nonexistent_path(self, client, tmp_env):
        """GET /api/filesystem/browse returns 400 for nonexistent path."""
        tmp = tmp_env["tmp_path"]
        bad_path = tmp / "does_not_exist"

        with (
            patch("social_hook.web.server.Path.home", return_value=tmp),
            patch.dict("os.environ", {"HOME": str(tmp)}),
        ):
            resp = client.get(f"/api/filesystem/browse?path={bad_path}")
            assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Project registration / deletion endpoint tests
# ---------------------------------------------------------------------------


class TestProjectRegistration:
    def test_register_project(self, client, tmp_env):
        """POST /api/projects/register creates a project."""
        with (
            patch("social_hook.db.operations.subprocess.run") as mock_run,
            patch("social_hook.setup.install.subprocess.run") as mock_install_run,
        ):
            # Mock git rev-parse (valid repo)
            mock_git_dir = MagicMock()
            mock_git_dir.returncode = 0
            mock_git_dir.stdout = ".git\n"
            # Mock git remote get-url origin
            mock_origin = MagicMock()
            mock_origin.returncode = 0
            mock_origin.stdout = "git@github.com:test/repo.git\n"
            mock_run.side_effect = [mock_git_dir, mock_origin]

            # Mock install_git_hook subprocess calls
            mock_install_git_dir = MagicMock()
            mock_install_git_dir.returncode = 0
            mock_install_git_dir.stdout = ".git\n"
            mock_install_run.return_value = mock_install_git_dir

            resp = client.post(
                "/api/projects/register",
                json={
                    "repo_path": "/tmp/test-repo",
                    "name": "My Test Repo",
                    "install_git_hook": False,
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "created"
            assert data["project"]["name"] == "My Test Repo"
            assert (
                data["project"]["repo_path"] == "/private/tmp/test-repo"
                or data["project"]["repo_path"] == "/tmp/test-repo"
            )

    def test_register_duplicate_returns_409(self, client, tmp_env):
        """POST /api/projects/register returns 409 for duplicate."""
        from pathlib import Path

        # Use resolved path (macOS /tmp -> /private/tmp)
        resolved = str(Path("/tmp/dup-repo").resolve())

        # Seed a project with the resolved path
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj_dup", "Existing", resolved),
        )
        conn.commit()
        conn.close()

        with patch("social_hook.db.operations.subprocess.run") as mock_run:
            mock_git = MagicMock()
            mock_git.returncode = 0
            mock_git.stdout = ".git\n"
            mock_origin = MagicMock()
            mock_origin.returncode = 1
            mock_origin.stdout = ""
            mock_run.side_effect = [mock_git, mock_origin]

            resp = client.post(
                "/api/projects/register",
                json={
                    "repo_path": "/tmp/dup-repo",
                },
            )
            assert resp.status_code == 409

    def test_delete_project(self, client, tmp_env):
        """DELETE /api/projects/{id} deletes the project."""
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj_del", "To Delete", "/tmp/del-repo"),
        )
        conn.execute(
            "INSERT INTO lifecycles (project_id, phase) VALUES (?, ?)",
            ("proj_del", "research"),
        )
        conn.execute(
            "INSERT INTO narrative_debt (project_id, debt_counter) VALUES (?, ?)",
            ("proj_del", 0),
        )
        conn.commit()
        conn.close()

        with patch("social_hook.setup.install.subprocess.run") as mock_run:
            mock_git = MagicMock()
            mock_git.returncode = 0
            mock_git.stdout = ".git\n"
            mock_run.return_value = mock_git

            resp = client.delete("/api/projects/proj_del")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "deleted"

            # Verify project is gone
            conn = sqlite3.connect(str(tmp_env["db_path"]))
            row = conn.execute("SELECT id FROM projects WHERE id = ?", ("proj_del",)).fetchone()
            conn.close()
            assert row is None

    def test_delete_nonexistent_returns_404(self, client, tmp_env):
        """DELETE /api/projects/{id} returns 404 for unknown project."""
        resp = client.delete("/api/projects/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Per-project git hook endpoint tests
# ---------------------------------------------------------------------------


class TestGitHookEndpoints:
    def test_git_hook_status(self, client, tmp_env):
        """GET /api/projects/{id}/git-hook/status returns installed flag."""
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj_gh1", "Hook Test", "/tmp/hook-test"),
        )
        conn.commit()
        conn.close()

        with patch("social_hook.setup.install.check_git_hook_installed", return_value=False):
            resp = client.get("/api/projects/proj_gh1/git-hook/status")
            assert resp.status_code == 200
            assert resp.json()["installed"] is False

    def test_git_hook_install(self, client, tmp_env):
        """POST /api/projects/{id}/git-hook/install installs the hook."""
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj_gh2", "Hook Install", "/tmp/hook-install"),
        )
        conn.commit()
        conn.close()

        with patch(
            "social_hook.setup.install.install_git_hook", return_value=(True, "Git hook installed")
        ):
            resp = client.post("/api/projects/proj_gh2/git-hook/install")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert "installed" in data["message"].lower()

    def test_git_hook_uninstall(self, client, tmp_env):
        """POST /api/projects/{id}/git-hook/uninstall removes the hook."""
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj_gh3", "Hook Uninstall", "/tmp/hook-uninstall"),
        )
        conn.commit()
        conn.close()

        with patch(
            "social_hook.setup.install.uninstall_git_hook", return_value=(True, "Git hook removed")
        ):
            resp = client.post("/api/projects/proj_gh3/git-hook/uninstall")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True

    def test_git_hook_404_for_unknown_project(self, client, tmp_env):
        """Git hook endpoints return 404 for unknown project."""
        with patch("social_hook.setup.install.check_git_hook_installed", return_value=False):
            resp = client.get("/api/projects/unknown_proj/git-hook/status")
            assert resp.status_code == 404

        with patch("social_hook.setup.install.install_git_hook", return_value=(True, "ok")):
            resp = client.post("/api/projects/unknown_proj/git-hook/install")
            assert resp.status_code == 404

        with patch("social_hook.setup.install.uninstall_git_hook", return_value=(True, "ok")):
            resp = client.post("/api/projects/unknown_proj/git-hook/uninstall")
            assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Stale background task cleanup tests
# ---------------------------------------------------------------------------


class TestStaleTaskCleanup:
    """Tests for startup cleanup and periodic TTL expiration of background tasks."""

    def test_startup_cleanup_marks_running_as_failed(self, tmp_env):
        """On server start, all running tasks are marked failed."""
        from social_hook.web.server import _cleanup_stale_tasks

        db_path = tmp_env["db_path"]
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO background_tasks (id, type, ref_id, project_id, status, created_at)"
            " VALUES ('t1', 'create_draft', 'ref1', 'p1', 'running',"
            " datetime('now', '-1 hour'))"
        )
        conn.execute(
            "INSERT INTO background_tasks (id, type, ref_id, project_id, status, created_at)"
            " VALUES ('t2', 'consolidate', 'ref2', 'p1', 'running',"
            " datetime('now', '-5 minutes'))"
        )
        conn.execute(
            "INSERT INTO background_tasks (id, type, ref_id, project_id, status, created_at)"
            " VALUES ('t3', 'import_commits', 'ref3', 'p1', 'completed',"
            " datetime('now', '-2 hours'))"
        )
        conn.commit()
        conn.close()

        count = _cleanup_stale_tasks(db_path)

        assert count == 2
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM background_tasks")}
        conn.close()

        assert rows["t1"]["status"] == "failed"
        assert rows["t1"]["error"] == "Interrupted by server restart"
        assert rows["t1"]["updated_at"] is not None
        assert rows["t2"]["status"] == "failed"
        assert rows["t2"]["error"] == "Interrupted by server restart"
        # Completed task should be untouched
        assert rows["t3"]["status"] == "completed"

    def test_startup_cleanup_noop_when_no_running(self, tmp_env):
        """Cleanup is a no-op when no running tasks exist (including empty table)."""
        from social_hook.web.server import _cleanup_stale_tasks

        db_path = tmp_env["db_path"]

        # Empty table
        assert _cleanup_stale_tasks(db_path) == 0

        # Only completed/failed tasks
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO background_tasks (id, type, ref_id, project_id, status, created_at)"
            " VALUES ('t1', 'create_draft', 'ref1', 'p1', 'completed',"
            " datetime('now', '-1 hour'))"
        )
        conn.execute(
            "INSERT INTO background_tasks (id, type, ref_id, project_id, status, created_at)"
            " VALUES ('t2', 'consolidate', 'ref2', 'p1', 'failed',"
            " datetime('now', '-30 minutes'))"
        )
        conn.commit()
        conn.close()

        assert _cleanup_stale_tasks(db_path) == 0

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM background_tasks")}
        conn.close()
        assert rows["t1"]["status"] == "completed"
        assert rows["t2"]["status"] == "failed"

    def test_expire_hung_tasks_respects_threshold(self, tmp_env):
        """Tasks running longer than the timeout are expired; recent ones are kept."""
        from social_hook.web.server import _expire_hung_tasks

        db_path = tmp_env["db_path"]
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        # Old task: should be expired (20 min ago, well past 10 min threshold)
        conn.execute(
            "INSERT INTO background_tasks (id, type, ref_id, project_id, status, created_at)"
            " VALUES ('old', 'create_draft', 'r1', 'p1', 'running',"
            " datetime('now', '-20 minutes'))"
        )
        # Recent task: should be kept (2 min ago, within 10 min threshold)
        conn.execute(
            "INSERT INTO background_tasks (id, type, ref_id, project_id, status, created_at)"
            " VALUES ('new', 'create_draft', 'r2', 'p1', 'running',"
            " datetime('now', '-2 minutes'))"
        )
        conn.commit()

        count = _expire_hung_tasks(conn)

        assert count == 1
        rows = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM background_tasks")}
        assert rows["old"]["status"] == "failed"
        assert "Timed out" in rows["old"]["error"]
        assert rows["old"]["updated_at"] is not None
        assert rows["new"]["status"] == "running"
        conn.close()

    def test_expire_hung_tasks_emits_data_events(self, tmp_env):
        """Expired tasks emit data_change events for WebSocket broadcast."""
        from social_hook.web.server import _expire_hung_tasks

        db_path = tmp_env["db_path"]
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute(
            "INSERT INTO background_tasks (id, type, ref_id, project_id, status, created_at)"
            " VALUES ('stale1', 'consolidate', 'r1', 'proj1', 'running',"
            " datetime('now', '-1 hour'))"
        )
        conn.commit()

        _expire_hung_tasks(conn)

        events = conn.execute("SELECT * FROM web_events WHERE type = 'data_change'").fetchall()
        assert len(events) >= 1
        data = json.loads(events[-1]["data"])
        assert data["entity"] == "task"
        assert data["action"] == "failed"
        assert data["entity_id"] == "stale1"
        assert data["project_id"] == "proj1"
        conn.close()

    def test_expire_hung_tasks_does_not_overwrite_completed(self, tmp_env):
        """A completed task with old created_at is not overwritten to failed."""
        from social_hook.web.server import _expire_hung_tasks

        db_path = tmp_env["db_path"]
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        # Task has old created_at but is already completed
        conn.execute(
            "INSERT INTO background_tasks (id, type, ref_id, project_id, status, created_at,"
            " updated_at)"
            " VALUES ('done', 'create_draft', 'r1', 'p1', 'completed',"
            " datetime('now', '-1 hour'), datetime('now', '-59 minutes'))"
        )
        conn.commit()

        count = _expire_hung_tasks(conn)

        assert count == 0
        row = dict(conn.execute("SELECT * FROM background_tasks WHERE id = 'done'").fetchone())
        assert row["status"] == "completed"
        conn.close()


# ---------------------------------------------------------------------------
# Generate-spec endpoint tests
# ---------------------------------------------------------------------------


def _seed_draft_with_media_type(db_path, draft_id="draft_1", project_id="proj_1"):
    """Seed a project, decision, and draft with media_type set."""
    conn = sqlite3.connect(str(db_path))
    existing = conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            (project_id, "Test Project", "/tmp/test"),
        )
    dec_exists = conn.execute("SELECT id FROM decisions WHERE id = 'dec_spec'").fetchone()
    if not dec_exists:
        conn.execute(
            "INSERT INTO decisions (id, project_id, commit_hash, commit_message, decision, reasoning)"
            " VALUES ('dec_spec', ?, 'abc123', 'feat: test', 'draft', 'test')",
            (project_id,),
        )
    conn.execute(
        "INSERT INTO drafts (id, project_id, decision_id, platform, content, media_type)"
        " VALUES (?, ?, 'dec_spec', 'x', 'Test draft about CI pipelines', 'mermaid')",
        (draft_id, project_id),
    )
    conn.commit()
    conn.close()


def _make_tool_call_response(tool_name, input_dict):
    """Create a NormalizedResponse with a NormalizedToolCall."""
    from social_hook.llm.base import NormalizedResponse, NormalizedToolCall

    return NormalizedResponse(
        content=[NormalizedToolCall(type="tool_use", name=tool_name, input=input_dict)]
    )


class TestGenerateSpecEndpoint:
    @staticmethod
    def _wait_for_task(db_path, task_id, timeout=5):
        """Poll DB until background task completes or times out."""
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT status, result, error FROM background_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            conn.close()
            if row and row["status"] != "running":
                return dict(row)
            time.sleep(0.1)
        return None

    def test_generate_spec_returns_202(self, client, tmp_env):
        """POST /api/drafts/{id}/generate-spec returns 202 with task_id."""
        _seed_draft_with_media_type(tmp_env["db_path"])
        mock_response = _make_tool_call_response("generate_media_spec", {"diagram": "graph TD"})
        with (
            patch("social_hook.llm.factory.create_client") as mock_cc,
            patch("social_hook.config.yaml.load_full_config"),
        ):
            mock_cc.return_value.complete.return_value = mock_response
            resp = client.post("/api/drafts/draft_1/generate-spec", json={"tool_name": "mermaid"})
            assert resp.status_code == 202
            data = resp.json()
            assert "task_id" in data
            assert data["status"] == "processing"

            task = self._wait_for_task(tmp_env["db_path"], data["task_id"])
            assert task is not None
            assert task["status"] == "completed"

    def test_generate_spec_persists(self, client, tmp_env):
        """Spec is persisted to draft after background task completes."""
        _seed_draft_with_media_type(tmp_env["db_path"])
        mock_response = _make_tool_call_response("generate_media_spec", {"diagram": "graph TD"})
        with (
            patch("social_hook.llm.factory.create_client") as mock_cc,
            patch("social_hook.config.yaml.load_full_config"),
        ):
            mock_cc.return_value.complete.return_value = mock_response
            resp = client.post("/api/drafts/draft_1/generate-spec", json={"tool_name": "mermaid"})
            self._wait_for_task(tmp_env["db_path"], resp.json()["task_id"])

        # Verify draft updated
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        row = conn.execute("SELECT media_spec FROM drafts WHERE id='draft_1'").fetchone()
        conn.close()
        assert json.loads(row[0])["diagram"] == "graph TD"

    def test_generate_spec_missing_tool_name(self, client, tmp_env):
        resp = client.post("/api/drafts/draft_1/generate-spec", json={})
        assert resp.status_code == 400

    def test_generate_spec_draft_not_found(self, client, tmp_env):
        resp = client.post("/api/drafts/nonexistent/generate-spec", json={"tool_name": "mermaid"})
        assert resp.status_code == 404

    def test_generate_spec_duplicate_guard(self, client, tmp_env):
        """Returns 409 when spec generation is already running."""
        _seed_draft_with_media_type(tmp_env["db_path"])
        # Insert a fake running task
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.execute(
            "INSERT INTO background_tasks (id, type, ref_id, project_id, status, created_at)"
            " VALUES ('t1', 'generate_spec', 'draft_1', 'proj_1', 'running', datetime('now'))"
        )
        conn.commit()
        conn.close()
        resp = client.post("/api/drafts/draft_1/generate-spec", json={"tool_name": "mermaid"})
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Rate Limits tests
# ---------------------------------------------------------------------------


class TestRateLimitsEndpoint:
    def test_rate_limits_status_empty(self, client, tmp_env):
        """GET /api/rate-limits/status returns zeros with no data."""
        resp = client.get("/api/rate-limits/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["evaluations_today"] == 0
        assert data["max_evaluations_per_day"] == 15
        assert data["manual_evaluations_today"] == 0
        assert data["next_available_in_seconds"] == 0
        assert data["queued_triggers"] == 0
        assert data["cost_today_cents"] == 0.0

    def test_rate_limits_status_with_data(self, client, tmp_env):
        """GET /api/rate-limits/status returns correct counts from usage_log and decisions."""
        conn = sqlite3.connect(str(tmp_env["db_path"]))

        # Insert some auto evaluations today
        for i in range(3):
            conn.execute(
                "INSERT INTO usage_log (id, project_id, operation_type, model, cost_cents, trigger_source) "
                "VALUES (?, 'p1', 'evaluate', 'test-model', 5.5, 'auto')",
                (f"ul-auto-{i}",),
            )
        # Insert a manual evaluation
        conn.execute(
            "INSERT INTO usage_log (id, project_id, operation_type, model, cost_cents, trigger_source) "
            "VALUES ('ul-manual-1', 'p1', 'evaluate', 'test-model', 3.0, 'manual')",
        )
        # Insert a deferred_eval decision
        conn.execute(
            "INSERT INTO decisions (id, project_id, commit_hash, decision, reasoning, processed) "
            "VALUES ('d-def-1', 'p1', 'abc123', 'deferred_eval', 'rate limited', 0)",
        )
        conn.execute(
            "INSERT INTO decisions (id, project_id, commit_hash, decision, reasoning, processed) "
            "VALUES ('d-def-2', 'p1', 'abc456', 'deferred_eval', 'rate limited', 0)",
        )
        # Insert a processed deferred (should NOT count)
        conn.execute(
            "INSERT INTO decisions (id, project_id, commit_hash, decision, reasoning, processed) "
            "VALUES ('d-def-3', 'p1', 'abc789', 'deferred_eval', 'rate limited', 1)",
        )
        conn.commit()
        conn.close()

        resp = client.get("/api/rate-limits/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["evaluations_today"] == 3
        assert data["manual_evaluations_today"] == 1
        assert data["queued_triggers"] == 2
        assert data["cost_today_cents"] == 19.5  # 3 * 5.5 + 3.0

    def test_rate_limits_status_shape(self, client, tmp_env):
        """GET /api/rate-limits/status returns all expected fields."""
        resp = client.get("/api/rate-limits/status")
        assert resp.status_code == 200
        data = resp.json()
        expected_keys = {
            "evaluations_today",
            "max_evaluations_per_day",
            "manual_evaluations_today",
            "next_available_in_seconds",
            "queued_triggers",
            "cost_today_cents",
        }
        assert set(data.keys()) == expected_keys
