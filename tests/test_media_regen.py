"""Tests for ``social_hook.media_regen`` — shared regen helper (A1#2/A2#3).

Covers the find-spec-by-id → resolve-adapter → generate → write paths/errors
→ insert DraftChange sequence consolidated across bot/web/cli surfaces.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from social_hook.adapters.models import MediaResult
from social_hook.db import (
    get_draft,
    get_draft_changes,
    insert_decision,
    insert_draft,
    insert_project,
)
from social_hook.filesystem import generate_id
from social_hook.media_regen import RegenResult, regen_media_item
from social_hook.models.core import Decision, Draft, Project


@pytest.fixture
def config():
    """Config stub with GEMINI_API_KEY set."""
    return SimpleNamespace(env={"GEMINI_API_KEY": "test_key"})


@pytest.fixture
def draft_with_media(temp_db):
    """Insert a project, decision, and draft carrying one mermaid media slot."""
    project = Project(id=generate_id("project"), name="test", repo_path="/tmp")
    insert_project(temp_db, project)

    decision = Decision(
        id=generate_id("decision"),
        project_id=project.id,
        commit_hash="abc123",
        decision="draft",
        reasoning="Test",
    )
    insert_decision(temp_db, decision)

    media_id = "media_abc123def456"
    draft = Draft(
        id=generate_id("draft"),
        project_id=project.id,
        decision_id=decision.id,
        platform="x",
        content="test content",
        media_specs=[
            {
                "id": media_id,
                "tool": "mermaid",
                "spec": {"code": "graph TD\nA-->B"},
                "user_uploaded": False,
            }
        ],
        media_paths=[""],
        media_errors=[None],
        media_specs_used=[{}],
    )
    insert_draft(temp_db, draft)
    return draft, media_id


class TestRegenResultDataclass:
    def test_success_flag_requires_path_and_no_error(self):
        assert RegenResult(media_id="m", path="/tmp/x.png").success is True
        assert RegenResult(media_id="m", error="boom").success is False
        # Both set => treat as failure (error wins).
        assert RegenResult(media_id="m", path="/tmp/x.png", error="half").success is False
        # Neither => neither.
        assert RegenResult(media_id="m").success is False


class TestRegenMediaItemHappyPath:
    def test_writes_path_and_inserts_change_on_success(
        self, temp_db, temp_base, draft_with_media, config
    ):
        draft, media_id = draft_with_media

        mock_adapter = MagicMock()
        mock_adapter.generate.return_value = MediaResult(
            success=True, file_path="/generated/file.png"
        )
        with patch(
            "social_hook.media_regen.resolve_media_adapter", return_value=mock_adapter
        ) as resolve:
            result = regen_media_item(temp_db, draft.id, media_id, config, changed_by="human")

        resolve.assert_called_once_with("mermaid", config)
        assert result.success is True
        assert result.path == "/generated/file.png"
        assert result.error is None

        # DB side effects
        reloaded = get_draft(temp_db, draft.id)
        assert reloaded.media_paths == ["/generated/file.png"]
        assert reloaded.media_specs_used[0]["id"] == media_id

        changes = get_draft_changes(temp_db, draft.id)
        assert len(changes) == 1
        assert changes[0].field == f"media_spec:{media_id}"
        assert changes[0].new_value == "/generated/file.png"
        assert changes[0].changed_by == "human"


class TestRegenMediaItemAdapterFailure:
    def test_adapter_returns_failure_writes_error(
        self, temp_db, temp_base, draft_with_media, config
    ):
        draft, media_id = draft_with_media

        mock_adapter = MagicMock()
        mock_adapter.generate.return_value = MediaResult(success=False, error="mermaid_cli_missing")
        with patch("social_hook.media_regen.resolve_media_adapter", return_value=mock_adapter):
            result = regen_media_item(temp_db, draft.id, media_id, config)

        assert result.success is False
        assert result.error == "mermaid_cli_missing"
        reloaded = get_draft(temp_db, draft.id)
        assert reloaded.media_errors[0] == "mermaid_cli_missing"
        # Path unchanged on failure
        assert reloaded.media_paths == [""]

    def test_adapter_raises_exception_captured(self, temp_db, temp_base, draft_with_media, config):
        draft, media_id = draft_with_media

        mock_adapter = MagicMock()
        mock_adapter.generate.side_effect = RuntimeError("network timeout")
        with patch("social_hook.media_regen.resolve_media_adapter", return_value=mock_adapter):
            result = regen_media_item(temp_db, draft.id, media_id, config)

        assert result.success is False
        assert result.error == "network timeout"
        reloaded = get_draft(temp_db, draft.id)
        assert reloaded.media_errors[0] == "network timeout"


class TestRegenMediaItemGuards:
    def test_user_uploaded_rejected(self, temp_db, temp_base, config):
        project = Project(id=generate_id("project"), name="t", repo_path="/tmp")
        insert_project(temp_db, project)
        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="c",
            decision="draft",
            reasoning="r",
        )
        insert_decision(temp_db, decision)
        media_id = "media_upload1"
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="c",
            media_specs=[
                {
                    "id": media_id,
                    "tool": "legacy_upload",
                    "spec": {"path": "/tmp/a.png"},
                    "user_uploaded": True,
                }
            ],
            media_paths=["/tmp/a.png"],
            media_errors=[None],
            media_specs_used=[{}],
        )
        insert_draft(temp_db, draft)

        # No patch — should short-circuit BEFORE resolve_media_adapter.
        result = regen_media_item(temp_db, draft.id, media_id, config)

        assert result.success is False
        assert result.error == "cannot_regen_user_upload"

    def test_media_id_not_found(self, temp_db, temp_base, draft_with_media, config):
        draft, _media_id = draft_with_media
        result = regen_media_item(temp_db, draft.id, "media_nonexistent", config)
        assert result.success is False
        assert "not_found" in result.error

    def test_draft_not_found(self, temp_db, temp_base, config):
        result = regen_media_item(temp_db, "draft_nonexistent", "media_x", config)
        assert result.success is False
        assert result.error == "draft_not_found"

    def test_enforce_spec_change_blocks_identical_spec(self, temp_db, temp_base, config):
        project = Project(id=generate_id("project"), name="t", repo_path="/tmp")
        insert_project(temp_db, project)
        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="c",
            decision="draft",
            reasoning="r",
        )
        insert_decision(temp_db, decision)
        media_id = "media_same_spec"
        spec_body = {"code": "graph TD\nA-->B"}
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="c",
            media_specs=[
                {"id": media_id, "tool": "mermaid", "spec": spec_body, "user_uploaded": False}
            ],
            media_paths=["/old.png"],
            media_errors=[None],
            media_specs_used=[
                {"id": media_id, "tool": "mermaid", "spec": spec_body, "user_uploaded": False}
            ],
        )
        insert_draft(temp_db, draft)

        # enforce_spec_change=True + identical spec → skip WITHOUT calling adapter
        with patch("social_hook.media_regen.resolve_media_adapter") as resolve:
            result = regen_media_item(temp_db, draft.id, media_id, config, enforce_spec_change=True)
        resolve.assert_not_called()
        assert result.success is False
        assert "unchanged" in result.error.lower()

    def test_configerror_from_resolver_written_to_draft(self, temp_db, temp_base, draft_with_media):
        """Missing GEMINI_API_KEY → ConfigError → error written + returned."""
        draft, media_id = draft_with_media
        # Swap the mermaid slot for a nano_banana_pro slot that needs the key.
        from social_hook.db import operations as ops

        ops.update_draft_media(
            temp_db,
            draft.id,
            media_id,
            spec={
                "id": media_id,
                "tool": "nano_banana_pro",
                "spec": {"prompt": "x"},
                "user_uploaded": False,
            },
        )

        empty_config = SimpleNamespace(env={})
        result = regen_media_item(temp_db, draft.id, media_id, empty_config)
        assert result.success is False
        assert "GEMINI_API_KEY" in result.error
        reloaded = get_draft(temp_db, draft.id)
        assert "GEMINI_API_KEY" in reloaded.media_errors[0]
