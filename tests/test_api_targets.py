"""Tests for targets-related web API endpoints."""

import sqlite3
from unittest.mock import patch

import pytest
import yaml

from social_hook.constants import DB_FILENAME
from social_hook.db.connection import init_database

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_env(tmp_path):
    """Set up isolated filesystem for tests with full init_database schema."""
    db_path = tmp_path / DB_FILENAME
    config_path = tmp_path / "config.yaml"
    env_path = tmp_path / ".env"
    media_dir = tmp_path / "media-cache"
    media_dir.mkdir()

    # Use init_database to get all tables including Phase 1-4 targets tables
    conn = init_database(db_path)

    # Insert a test project
    conn.execute(
        "INSERT INTO projects (id, name, repo_path, summary) VALUES (?, ?, ?, ?)",
        ("proj-1", "test-project", str(tmp_path / "repo"), "Test summary"),
    )
    conn.commit()
    conn.close()

    # Create minimal config
    config_data = {
        "models": {
            "evaluator": "anthropic/claude-opus-4-5",
            "drafter": "anthropic/claude-sonnet-4-5",
        },
        "platform_credentials": {
            "x-main": {"platform": "x", "client_id": "test-id", "client_secret": "test-secret"},
        },
        "accounts": {
            "lead": {"platform": "x", "app": "x-main", "tier": "free"},
        },
        "targets": {
            "product-news": {
                "account": "lead",
                "destination": "timeline",
                "strategy": "brand-primary",
            },
        },
        "content_strategies": {
            "brand-primary": {
                "audience": "developers",
                "voice": "technical",
            },
        },
        "platform_settings": {
            "x": {"cross_account_gap_minutes": 5},
        },
    }
    config_path.write_text(yaml.dump(config_data, default_flow_style=False))

    # Create env file
    env_path.write_text("ANTHROPIC_API_KEY=sk-ant-test-key\n")

    return {
        "tmp_path": tmp_path,
        "db_path": db_path,
        "config_path": config_path,
        "env_path": env_path,
    }


@pytest.fixture()
def client(tmp_env):
    """Create a test client with mocked filesystem paths."""
    from fastapi.testclient import TestClient

    from social_hook.web.server import app

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


# ---------------------------------------------------------------------------
# Platform Credentials
# ---------------------------------------------------------------------------


class TestPlatformCredentials:
    def test_list_credentials(self, client):
        resp = client.get("/api/platform-credentials")
        assert resp.status_code == 200
        data = resp.json()
        assert "platform_credentials" in data
        assert "x-main" in data["platform_credentials"]
        assert data["platform_credentials"]["x-main"]["platform"] == "x"
        assert data["platform_credentials"]["x-main"]["client_id_set"] is True

    def test_add_credential(self, client):
        resp = client.post(
            "/api/platform-credentials",
            json={"name": "linkedin-main", "platform": "linkedin"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "created"

        # Verify it shows up in list
        resp2 = client.get("/api/platform-credentials")
        assert "linkedin-main" in resp2.json()["platform_credentials"]

    def test_add_credential_missing_fields(self, client):
        resp = client.post("/api/platform-credentials", json={"name": "bad"})
        assert resp.status_code == 400

    def test_add_credential_unknown_keys(self, client):
        resp = client.post(
            "/api/platform-credentials",
            json={"name": "x2", "platform": "x", "unknown_field": "val"},
        )
        assert resp.status_code == 422

    def test_update_credential(self, client):
        resp = client.put(
            "/api/platform-credentials/x-main",
            json={"client_id": "new-id"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "updated"

    def test_update_credential_not_found(self, client):
        resp = client.put(
            "/api/platform-credentials/nonexistent",
            json={"client_id": "x"},
        )
        assert resp.status_code == 404

    def test_delete_credential(self, client):
        # First add a credential that no accounts reference
        client.post(
            "/api/platform-credentials",
            json={"name": "to-delete", "platform": "x"},
        )
        resp = client.delete("/api/platform-credentials/to-delete")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_delete_credential_referenced_by_account(self, client):
        resp = client.delete("/api/platform-credentials/x-main")
        assert resp.status_code == 409

    def test_delete_credential_not_found(self, client):
        resp = client.delete("/api/platform-credentials/nonexistent")
        assert resp.status_code == 404

    def test_validate_credential(self, client):
        resp = client.post("/api/platform-credentials/x-main/validate")
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    def test_validate_credential_not_found(self, client):
        resp = client.post("/api/platform-credentials/nonexistent/validate")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


class TestAccounts:
    def test_list_accounts(self, client):
        resp = client.get("/api/accounts")
        assert resp.status_code == 200
        data = resp.json()
        assert "lead" in data["accounts"]
        assert data["accounts"]["lead"]["platform"] == "x"

    def test_add_account(self, client):
        resp = client.post(
            "/api/accounts",
            json={"name": "secondary", "platform": "x"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "created"

    def test_add_account_missing_fields(self, client):
        resp = client.post("/api/accounts", json={"name": "bad"})
        assert resp.status_code == 400

    def test_add_account_unknown_keys(self, client):
        resp = client.post(
            "/api/accounts",
            json={"name": "test", "platform": "x", "bogus_field": 1},
        )
        assert resp.status_code == 422

    def test_delete_account(self, client):
        # Add an account that no targets reference
        client.post(
            "/api/accounts",
            json={"name": "to-delete", "platform": "linkedin"},
        )
        resp = client.delete("/api/accounts/to-delete")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_delete_account_referenced_by_target(self, client):
        resp = client.delete("/api/accounts/lead")
        assert resp.status_code == 409

    def test_delete_account_not_found(self, client):
        resp = client.delete("/api/accounts/nonexistent")
        assert resp.status_code == 404

    def test_validate_accounts(self, client):
        resp = client.post("/api/accounts/validate")
        assert resp.status_code == 200
        assert "accounts" in resp.json()

    # OAuth callback tests removed — stub endpoint replaced by generic
    # /api/oauth/{platform}/callback in oauth2-migration


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------


class TestTargets:
    def test_list_targets(self, client):
        resp = client.get("/api/projects/proj-1/targets")
        assert resp.status_code == 200
        data = resp.json()
        target_ids = [t["id"] for t in data["targets"]]
        assert "product-news" in target_ids
        assert data["project_id"] == "proj-1"
        # Verify target structure
        target = data["targets"][0]
        assert "account_name" in target
        assert "enabled" in target
        assert "platform" in target

    def test_list_targets_project_not_found(self, client):
        resp = client.get("/api/projects/nonexistent/targets")
        assert resp.status_code == 404

    def test_add_target(self, client):
        resp = client.post(
            "/api/projects/proj-1/targets",
            json={
                "name": "community",
                "account": "lead",
                "destination": "timeline",
                "strategy": "brand-primary",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "created"

    def test_add_target_missing_fields(self, client):
        resp = client.post(
            "/api/projects/proj-1/targets",
            json={"name": "bad"},
        )
        assert resp.status_code == 400

    def test_update_target(self, client):
        resp = client.put(
            "/api/projects/proj-1/targets/product-news",
            json={"destination": "timeline"},
        )
        assert resp.status_code == 200

    def test_update_target_not_found(self, client):
        resp = client.put(
            "/api/projects/proj-1/targets/nonexistent",
            json={"destination": "timeline"},
        )
        assert resp.status_code == 404

    def test_disable_target(self, client):
        resp = client.put("/api/projects/proj-1/targets/product-news/disable")
        assert resp.status_code == 200
        assert resp.json()["status"] == "disabled"

    def test_enable_target(self, client):
        resp = client.put("/api/projects/proj-1/targets/product-news/enable")
        assert resp.status_code == 200
        assert resp.json()["status"] == "enabled"


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


class TestStrategies:
    def test_list_strategies(self, client):
        resp = client.get("/api/projects/proj-1/strategies")
        assert resp.status_code == 200
        data = resp.json()
        assert "brand-primary" in data["strategies"]
        assert data["strategies"]["brand-primary"]["audience"] == "developers"

    def test_get_strategy(self, client):
        resp = client.get("/api/projects/proj-1/strategies/brand-primary")
        assert resp.status_code == 200
        assert resp.json()["name"] == "brand-primary"
        assert resp.json()["audience"] == "developers"

    def test_get_strategy_not_found(self, client):
        resp = client.get("/api/projects/proj-1/strategies/nonexistent")
        assert resp.status_code == 404

    def test_update_strategy(self, client):
        resp = client.put(
            "/api/projects/proj-1/strategies/brand-primary",
            json={"audience": "designers"},
        )
        assert resp.status_code == 200

    def test_update_strategy_unknown_keys(self, client):
        resp = client.put(
            "/api/projects/proj-1/strategies/brand-primary",
            json={"bogus": "field"},
        )
        assert resp.status_code == 422

    def test_reset_strategy(self, client):
        resp = client.post("/api/projects/proj-1/strategies/brand-primary/reset")
        assert resp.status_code == 200
        assert resp.json()["status"] == "reset"


# ---------------------------------------------------------------------------
# Topics
# ---------------------------------------------------------------------------


class TestTopics:
    def test_list_topics_empty(self, client):
        resp = client.get("/api/projects/proj-1/topics")
        assert resp.status_code == 200
        assert resp.json()["topics"] == []

    def test_add_topic(self, client):
        resp = client.post(
            "/api/projects/proj-1/topics",
            json={
                "strategy": "brand-primary",
                "topic": "evaluation pipeline",
                "description": "How the evaluator works",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "created"
        assert resp.json()["topic"]["strategy"] == "brand-primary"
        assert resp.json()["topic"]["topic"] == "evaluation pipeline"

    def test_add_topic_missing_fields(self, client):
        resp = client.post(
            "/api/projects/proj-1/topics",
            json={"strategy": "brand-primary"},
        )
        assert resp.status_code == 400

    def test_add_topic_unknown_keys(self, client):
        resp = client.post(
            "/api/projects/proj-1/topics",
            json={"strategy": "x", "topic": "y", "bogus": 1},
        )
        assert resp.status_code == 422

    def test_update_topic(self, client):
        # First add a topic
        resp = client.post(
            "/api/projects/proj-1/topics",
            json={"strategy": "brand-primary", "topic": "test-topic"},
        )
        topic_id = resp.json()["topic"]["id"]

        resp = client.put(
            f"/api/projects/proj-1/topics/{topic_id}",
            json={"description": "Updated description", "priority_rank": 5},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "updated"

    def test_update_topic_not_found(self, client):
        resp = client.put(
            "/api/projects/proj-1/topics/nonexistent",
            json={"description": "x"},
        )
        assert resp.status_code == 404

    def test_set_topic_status(self, client):
        # Add a topic first
        resp = client.post(
            "/api/projects/proj-1/topics",
            json={"strategy": "brand-primary", "topic": "status-test"},
        )
        topic_id = resp.json()["topic"]["id"]

        resp = client.put(
            f"/api/projects/proj-1/topics/{topic_id}/status",
            json={"status": "holding"},
        )
        assert resp.status_code == 200
        assert resp.json()["new_status"] == "holding"

    def test_set_topic_status_invalid(self, client):
        # Add a topic first
        resp = client.post(
            "/api/projects/proj-1/topics",
            json={"strategy": "brand-primary", "topic": "status-bad"},
        )
        topic_id = resp.json()["topic"]["id"]

        resp = client.put(
            f"/api/projects/proj-1/topics/{topic_id}/status",
            json={"status": "invalid_status"},
        )
        assert resp.status_code == 400

    def test_list_topics_with_strategy_filter(self, client):
        client.post(
            "/api/projects/proj-1/topics",
            json={"strategy": "brand-primary", "topic": "filter-test"},
        )
        resp = client.get("/api/projects/proj-1/topics?strategy=brand-primary")
        assert resp.status_code == 200
        assert len(resp.json()["topics"]) >= 1

    def test_reorder_topics(self, client):
        # Add two topics
        resp1 = client.post(
            "/api/projects/proj-1/topics",
            json={"strategy": "brand-primary", "topic": "first"},
        )
        resp2 = client.post(
            "/api/projects/proj-1/topics",
            json={"strategy": "brand-primary", "topic": "second"},
        )
        id1 = resp1.json()["topic"]["id"]
        id2 = resp2.json()["topic"]["id"]

        # Reorder: second first, then first
        resp = client.put(
            "/api/projects/proj-1/topics/reorder",
            json={"topic_ids": [id2, id1]},
        )
        assert resp.status_code == 200
        assert resp.json()["count"] == 2

    def test_draft_now_topic(self, client):
        # Add a topic
        resp = client.post(
            "/api/projects/proj-1/topics",
            json={"strategy": "brand-primary", "topic": "draft-now"},
        )
        topic_id = resp.json()["topic"]["id"]

        resp = client.post(f"/api/projects/proj-1/topics/{topic_id}/draft-now")
        assert resp.status_code == 202
        assert "task_id" in resp.json()

    def test_draft_now_topic_not_found(self, client):
        resp = client.post("/api/projects/proj-1/topics/nonexistent/draft-now")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Brief
# ---------------------------------------------------------------------------


class TestBrief:
    def test_get_brief(self, client):
        resp = client.get("/api/projects/proj-1/brief")
        assert resp.status_code == 200
        data = resp.json()
        assert "brief" in data
        assert data["project_id"] == "proj-1"

    def test_update_brief(self, client):
        resp = client.put(
            "/api/projects/proj-1/brief",
            json={"brief": "## What It Does\n\nA test project."},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "updated"

        # Verify update persisted
        resp2 = client.get("/api/projects/proj-1/brief")
        assert "test project" in resp2.json()["brief"]

    def test_update_brief_unknown_keys(self, client):
        resp = client.put(
            "/api/projects/proj-1/brief",
            json={"bogus_key": "value"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Content Suggestions
# ---------------------------------------------------------------------------


class TestSuggestions:
    def test_list_suggestions_empty(self, client):
        resp = client.get("/api/projects/proj-1/suggestions")
        assert resp.status_code == 200
        assert resp.json()["suggestions"] == []

    def test_create_suggestion_with_strategy(self, client):
        resp = client.post(
            "/api/projects/proj-1/suggestions",
            json={"idea": "Write about testing", "strategy": "brand-primary"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "created"
        assert resp.json()["suggestion"]["idea"] == "Write about testing"

    def test_create_suggestion_auto_evaluate(self, client):
        """Without strategy, should return 202 for auto-evaluation."""
        resp = client.post(
            "/api/projects/proj-1/suggestions",
            json={"idea": "Something interesting"},
        )
        assert resp.status_code == 202
        assert "task_id" in resp.json()

    def test_create_suggestion_missing_idea(self, client):
        resp = client.post(
            "/api/projects/proj-1/suggestions",
            json={"strategy": "brand-primary"},
        )
        assert resp.status_code == 400

    def test_dismiss_suggestion(self, client):
        # Create one first
        resp = client.post(
            "/api/projects/proj-1/suggestions",
            json={"idea": "To dismiss", "strategy": "brand-primary"},
        )
        suggestion_id = resp.json()["suggestion"]["id"]

        resp = client.put(f"/api/projects/proj-1/suggestions/{suggestion_id}/dismiss")
        assert resp.status_code == 200
        assert resp.json()["status"] == "dismissed"

    def test_dismiss_suggestion_not_found(self, client):
        resp = client.put("/api/projects/proj-1/suggestions/nonexistent/dismiss")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Content Operations (combine + hero-launch)
# ---------------------------------------------------------------------------


class TestContentOperations:
    def test_combine_topics_insufficient(self, client):
        resp = client.post(
            "/api/projects/proj-1/content/combine",
            json={"topic_ids": ["one"]},
        )
        assert resp.status_code == 400

    def test_combine_topics_not_found(self, client):
        resp = client.post(
            "/api/projects/proj-1/content/combine",
            json={"topic_ids": ["nonexistent1", "nonexistent2"]},
        )
        assert resp.status_code == 404

    def test_combine_topics_success(self, client):
        # Create two topics
        r1 = client.post(
            "/api/projects/proj-1/topics",
            json={"strategy": "brand-primary", "topic": "combine1"},
        )
        r2 = client.post(
            "/api/projects/proj-1/topics",
            json={"strategy": "brand-primary", "topic": "combine2"},
        )
        tid1 = r1.json()["topic"]["id"]
        tid2 = r2.json()["topic"]["id"]

        resp = client.post(
            "/api/projects/proj-1/content/combine",
            json={"topic_ids": [tid1, tid2]},
        )
        assert resp.status_code == 202
        assert "task_id" in resp.json()

    def test_hero_launch(self, client):
        resp = client.post("/api/projects/proj-1/content/hero-launch")
        assert resp.status_code == 202
        assert "task_id" in resp.json()


# ---------------------------------------------------------------------------
# Evaluation Cycles
# ---------------------------------------------------------------------------


class TestEvaluationCycles:
    def test_list_cycles_empty(self, client):
        resp = client.get("/api/projects/proj-1/cycles")
        assert resp.status_code == 200
        assert resp.json()["cycles"] == []

    def test_list_cycles_with_data(self, client, tmp_env):
        # Insert a cycle directly
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.execute(
            "INSERT INTO evaluation_cycles (id, project_id, trigger_type) VALUES (?, ?, ?)",
            ("cycle-1", "proj-1", "commit"),
        )
        conn.commit()
        conn.close()

        resp = client.get("/api/projects/proj-1/cycles")
        assert resp.status_code == 200
        assert len(resp.json()["cycles"]) == 1

    def test_get_cycle_detail(self, client, tmp_env):
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.execute(
            "INSERT INTO evaluation_cycles (id, project_id, trigger_type) VALUES (?, ?, ?)",
            ("cycle-2", "proj-1", "commit"),
        )
        conn.commit()
        conn.close()

        resp = client.get("/api/projects/proj-1/cycles/cycle-2")
        assert resp.status_code == 200
        assert resp.json()["id"] == "cycle-2"
        assert "drafts" in resp.json()

    def test_get_cycle_not_found(self, client):
        resp = client.get("/api/projects/proj-1/cycles/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------


class TestSystem:
    def test_system_errors_empty(self, client):
        resp = client.get("/api/system/errors")
        assert resp.status_code == 200
        assert resp.json()["errors"] == []

    def test_system_errors_with_data(self, client, tmp_env):
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.execute(
            "INSERT INTO system_errors (id, severity, message) VALUES (?, ?, ?)",
            ("err-1", "error", "Test error"),
        )
        conn.commit()
        conn.close()

        resp = client.get("/api/system/errors")
        assert resp.status_code == 200
        assert len(resp.json()["errors"]) == 1
        assert resp.json()["errors"][0]["severity"] == "error"

    def test_system_health(self, client):
        resp = client.get("/api/system/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "error_counts_24h" in data

    def test_system_health_degraded(self, client, tmp_env):
        conn = sqlite3.connect(str(tmp_env["db_path"]))
        conn.execute(
            "INSERT INTO system_errors (id, severity, message) VALUES (?, ?, ?)",
            ("err-2", "critical", "Critical failure"),
        )
        conn.commit()
        conn.close()

        resp = client.get("/api/system/health")
        assert resp.json()["status"] == "critical"


# ---------------------------------------------------------------------------
# Platform Settings
# ---------------------------------------------------------------------------


class TestPlatformSettings:
    def test_get_platform_settings(self, client):
        resp = client.get("/api/platform-settings")
        assert resp.status_code == 200
        data = resp.json()
        assert "x" in data["platform_settings"]
        assert data["platform_settings"]["x"]["cross_account_gap_minutes"] == 5

    def test_update_platform_settings(self, client):
        resp = client.put(
            "/api/platform-settings/x",
            json={"cross_account_gap_minutes": 10},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "updated"

    def test_update_platform_settings_unknown_key(self, client):
        resp = client.put(
            "/api/platform-settings/x",
            json={"bogus": 123},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# check_unknown_keys strict mode
# ---------------------------------------------------------------------------


class TestCheckUnknownKeysStrict:
    def test_strict_raises_on_unknown_keys(self):
        from social_hook.errors import ConfigError
        from social_hook.parsing import check_unknown_keys

        with pytest.raises(ConfigError, match="Unknown keys"):
            check_unknown_keys(
                {"known": 1, "typo": 2},
                {"known"},
                "test-section",
                strict=True,
            )

    def test_non_strict_does_not_raise(self):
        from social_hook.parsing import check_unknown_keys

        # Should not raise, just log warning
        check_unknown_keys(
            {"known": 1, "typo": 2},
            {"known"},
            "test-section",
            strict=False,
        )

    def test_no_unknown_keys_passes(self):
        from social_hook.parsing import check_unknown_keys

        # No exception for valid keys
        check_unknown_keys(
            {"known": 1},
            {"known"},
            "test-section",
            strict=True,
        )
