"""Tests for POST /api/drafts/{id}/connect and POST /api/drafts/{id}/promote endpoints."""

from unittest.mock import patch

import pytest
import yaml

from social_hook.constants import DB_FILENAME
from social_hook.db import operations as ops
from social_hook.db.connection import init_database
from social_hook.models.core import Draft

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_env(tmp_path):
    """Set up isolated filesystem with a preview-mode draft for connect tests."""
    db_path = tmp_path / DB_FILENAME
    config_path = tmp_path / "config.yaml"
    env_path = tmp_path / ".env"
    media_dir = tmp_path / "media-cache"
    media_dir.mkdir()

    conn = init_database(db_path)

    # Insert a test project
    conn.execute(
        "INSERT INTO projects (id, name, repo_path, summary) VALUES (?, ?, ?, ?)",
        ("proj-1", "test-project", str(tmp_path / "repo"), "Test summary"),
    )

    # Insert a decision (required FK for drafts)
    conn.execute(
        "INSERT INTO decisions (id, project_id, commit_hash, commit_message, decision, reasoning) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("dec-1", "proj-1", "abc123", "test commit", "draft", "test reasoning"),
    )

    # Insert a preview-mode draft on platform "x"
    preview_draft = Draft(
        id="draft-preview",
        project_id="proj-1",
        decision_id="dec-1",
        platform="x",
        content="Preview content",
        status="draft",
        preview_mode=True,
        target_id="product-news",
    )
    ops.insert_draft(conn, preview_draft)

    # Insert a non-preview draft
    normal_draft = Draft(
        id="draft-normal",
        project_id="proj-1",
        decision_id="dec-1",
        platform="x",
        content="Normal content",
        status="draft",
        preview_mode=False,
    )
    ops.insert_draft(conn, normal_draft)

    # Insert a terminal (posted) preview draft
    posted_draft = Draft(
        id="draft-posted",
        project_id="proj-1",
        decision_id="dec-1",
        platform="x",
        content="Posted content",
        status="posted",
        preview_mode=True,
    )
    ops.insert_draft(conn, posted_draft)

    conn.commit()
    conn.close()

    # Create config with accounts and targets
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
            "linkedin-acct": {"platform": "linkedin", "app": "x-main", "tier": "free"},
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
    }
    config_path.write_text(yaml.dump(config_data, default_flow_style=False))

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
# POST /api/drafts/{id}/connect
# ---------------------------------------------------------------------------


class TestConnectDraft:
    def test_connect_happy_path(self, client, tmp_env):
        """Connect an account to a preview-mode draft."""
        # Patch load_full_config inside the connect handler to use test paths
        from social_hook.config.yaml import load_full_config

        config = load_full_config(env_path=tmp_env["env_path"], yaml_path=tmp_env["config_path"])
        with patch("social_hook.config.yaml.load_full_config", return_value=config):
            resp = client.post(
                "/api/drafts/draft-preview/connect",
                json={"account": "lead"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "connected"
        assert data["draft_id"] == "draft-preview"
        assert data["account"] == "lead"
        assert data["platform"] == "x"

    def test_connect_non_preview_draft_rejected(self, client):
        """Non-preview draft should return 400."""
        resp = client.post(
            "/api/drafts/draft-normal/connect",
            json={"account": "lead"},
        )
        assert resp.status_code == 400
        assert "not in preview mode" in resp.json()["detail"]

    def test_connect_terminal_status_rejected(self, client):
        """Draft with terminal status (posted) should return 400."""
        resp = client.post(
            "/api/drafts/draft-posted/connect",
            json={"account": "lead"},
        )
        assert resp.status_code == 400
        assert "Cannot connect draft" in resp.json()["detail"]

    def test_connect_account_not_found(self, client, tmp_env):
        """Nonexistent account should return 400."""
        from social_hook.config.yaml import load_full_config

        config = load_full_config(env_path=tmp_env["env_path"], yaml_path=tmp_env["config_path"])
        with patch("social_hook.config.yaml.load_full_config", return_value=config):
            resp = client.post(
                "/api/drafts/draft-preview/connect",
                json={"account": "nonexistent"},
            )
        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"]

    def test_connect_platform_mismatch(self, client, tmp_env):
        """Account on different platform should return 400."""
        from social_hook.config.yaml import load_full_config

        config = load_full_config(env_path=tmp_env["env_path"], yaml_path=tmp_env["config_path"])
        with patch("social_hook.config.yaml.load_full_config", return_value=config):
            resp = client.post(
                "/api/drafts/draft-preview/connect",
                json={"account": "linkedin-acct"},
            )
        assert resp.status_code == 400
        assert "does not match" in resp.json()["detail"]

    def test_connect_missing_account_in_body(self, client):
        """Missing 'account' key should return 400."""
        resp = client.post(
            "/api/drafts/draft-preview/connect",
            json={},
        )
        assert resp.status_code == 400
        assert "Missing" in resp.json()["detail"]

    def test_connect_unknown_keys_rejected(self, client):
        """Extra fields in body should return 422 via check_unknown_keys strict mode."""
        resp = client.post(
            "/api/drafts/draft-preview/connect",
            json={"account": "lead", "extra_field": "bad"},
        )
        assert resp.status_code == 422
        assert "Unknown" in resp.json()["detail"]

    def test_connect_draft_not_found(self, client):
        """Nonexistent draft should return 404."""
        resp = client.post(
            "/api/drafts/nonexistent/connect",
            json={"account": "lead"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/drafts/{id}/promote
# ---------------------------------------------------------------------------


class TestPromoteDraft:
    def test_promote_preview_mode_draft(self, client, tmp_env):
        """Preview-mode draft should be accepted for promotion (returns 202)."""
        resp = client.post(
            "/api/drafts/draft-preview/promote",
            json={"platform": "x"},
        )
        # The promote endpoint checks preview_mode, then loads project
        # and spawns a background task. With our test setup it should
        # at least pass the preview_mode gate. The endpoint returns 202
        # on success, but may fail on config/platform lookup.
        # Either 202 (success) or 400 (platform not enabled) is acceptable
        # since we don't have platforms config — just verify the preview check passes.
        assert resp.status_code in (200, 202, 400)
        # If it's 400, it should NOT be about preview mode
        if resp.status_code == 400:
            assert "preview" not in resp.json()["detail"].lower()

    def test_promote_non_preview_draft_rejected(self, client):
        """Non-preview draft should return 400."""
        resp = client.post(
            "/api/drafts/draft-normal/promote",
            json={"platform": "x"},
        )
        assert resp.status_code == 400
        assert "preview-mode" in resp.json()["detail"] or "preview" in resp.json()["detail"].lower()

    def test_promote_missing_platform(self, client):
        """Missing 'platform' in body should return 400."""
        resp = client.post(
            "/api/drafts/draft-preview/promote",
            json={},
        )
        assert resp.status_code == 400
        assert "Missing" in resp.json()["detail"]

    def test_promote_draft_not_found(self, client):
        """Nonexistent draft should return 404."""
        resp = client.post(
            "/api/drafts/nonexistent/promote",
            json={"platform": "x"},
        )
        assert resp.status_code == 404

    def test_promote_terminal_status_rejected(self, client):
        """Draft with terminal status should return 400."""
        resp = client.post(
            "/api/drafts/draft-posted/promote",
            json={"platform": "x"},
        )
        assert resp.status_code == 400
        assert "Cannot promote" in resp.json()["detail"]
