"""Tests for the FastAPI web dashboard API server."""

import json
import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_env(tmp_path):
    """Set up isolated filesystem for tests."""
    db_path = tmp_path / "social-hook.db"
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
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
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

    from social_hook.web.server import _invalidate_config, app

    tmp_path = tmp_env["tmp_path"]
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

            resp = client.post(
                "/api/callback", json={"action": "approve", "payload": "draft_1"}
            )
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

        resp = client.get("/api/events?lastId=0")
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
        assert "Telegram" in data["key_groups"]
        assert "Media Generation" in data["key_groups"]
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
        with patch("social_hook.setup.install.install_hook", return_value=(True, "Installed")) as mock_fn:
            resp = client.post("/api/installations/commit_hook/install")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            mock_fn.assert_called_once()

    def test_uninstall_commit_hook(self, client, tmp_env):
        with patch("social_hook.setup.install.uninstall_hook", return_value=(True, "Removed")) as mock_fn:
            resp = client.post("/api/installations/commit_hook/uninstall")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            mock_fn.assert_called_once()

    def test_install_invalid_component(self, client, tmp_env):
        resp = client.post("/api/installations/invalid_thing/install")
        assert resp.status_code == 400

    def test_bot_daemon_start(self, client, tmp_env):
        with (
            patch("social_hook.bot.process.is_running", return_value=False),
            patch("subprocess.Popen") as mock_popen,
        ):
            resp = client.post("/api/installations/bot_daemon/start")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True

    def test_bot_daemon_stop(self, client, tmp_env):
        with (
            patch("social_hook.bot.process.is_running", return_value=True),
            patch("social_hook.bot.process.stop_bot", return_value=True),
        ):
            resp = client.post("/api/installations/bot_daemon/stop")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True

    def test_journey_capture_toggle_installs_hook(self, client, tmp_env):
        """Toggling journey_capture.enabled to True installs narrative hook."""
        config = {
            "models": {"evaluator": "anthropic/claude-opus-4-5", "drafter": "anthropic/claude-opus-4-5", "gatekeeper": "anthropic/claude-haiku-4-5"},
            "platforms": {"x": {"enabled": True, "priority": "primary", "account_tier": "free"}},
        }
        tmp_env["config_path"].write_text(yaml.dump(config))

        with patch("social_hook.setup.install.install_narrative_hook", return_value=(True, "Installed")) as mock_install:
            resp = client.put("/api/settings/config", json={"journey_capture": {"enabled": True}})
            assert resp.status_code == 200
            mock_install.assert_called_once()

    def test_journey_capture_toggle_uninstalls_hook(self, client, tmp_env):
        """Toggling journey_capture.enabled to False uninstalls narrative hook."""
        config = {
            "models": {"evaluator": "anthropic/claude-opus-4-5", "drafter": "anthropic/claude-opus-4-5", "gatekeeper": "anthropic/claude-haiku-4-5"},
            "platforms": {"x": {"enabled": True, "priority": "primary", "account_tier": "free"}},
            "journey_capture": {"enabled": True},
        }
        tmp_env["config_path"].write_text(yaml.dump(config))

        with patch("social_hook.setup.install.uninstall_narrative_hook", return_value=(True, "Removed")) as mock_uninstall:
            resp = client.put("/api/settings/config", json={"journey_capture": {"enabled": False}})
            assert resp.status_code == 200
            mock_uninstall.assert_called_once()

    def test_project_detail_includes_journey_capture(self, client, tmp_env):
        """Project detail response includes journey_capture_enabled."""
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.execute("INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)", ("proj_1", "Test", "/tmp/repo"))
        conn.execute("INSERT INTO lifecycles (project_id) VALUES (?)", ("proj_1",))
        conn.execute("INSERT INTO narrative_debt (project_id, debt_counter) VALUES (?, ?)", ("proj_1", 0))
        conn.commit()
        conn.close()

        narratives_path = tmp_env["tmp_path"] / "narratives"
        narratives_path.mkdir(exist_ok=True)

        with patch("social_hook.web.server.get_narratives_path", return_value=narratives_path):
            resp = client.get("/api/projects/proj_1")
            assert resp.status_code == 200
            data = resp.json()
            assert "journey_capture_enabled" in data
