"""Tests for advisory items — CRUD, API, scheduler creation, notifications."""

import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from social_hook.db import operations as ops
from social_hook.db.schema import SCHEMA_DDL
from social_hook.filesystem import generate_id
from social_hook.models.core import Project
from social_hook.models.infra import AdvisoryItem
from social_hook.models.narrative import Lifecycle, NarrativeDebt


@pytest.fixture
def temp_db():
    """Create an in-memory database with full schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_DDL)
    yield conn
    conn.close()


@pytest.fixture
def project(temp_db):
    """Insert a test project."""
    proj = Project(
        id=generate_id("project"),
        name="test-project",
        repo_path="/tmp/test-project",
    )
    ops.insert_project(temp_db, proj)
    lc = Lifecycle(project_id=proj.id, phase="research", confidence=0.3)
    ops.insert_lifecycle(temp_db, lc)
    debt = NarrativeDebt(project_id=proj.id, debt_counter=0)
    ops.insert_narrative_debt(temp_db, debt)
    return proj


@pytest.fixture
def advisory_item(temp_db, project):
    """Insert a test advisory item."""
    item = AdvisoryItem(
        id=generate_id("advisory"),
        project_id=project.id,
        category="content_asset",
        title="Post article manually",
        description="Article draft is ready for manual posting.",
        urgency="normal",
        created_by="system",
        linked_entity_type="draft",
        linked_entity_id="draft_test123",
    )
    ops.insert_advisory_item(temp_db, item)
    return item


# =============================================================================
# Model tests
# =============================================================================


class TestAdvisoryItemModel:
    def test_to_dict(self):
        item = AdvisoryItem(
            id="adv_1",
            project_id="proj_1",
            category="content_asset",
            title="Test",
            created_by="system",
        )
        d = item.to_dict()
        assert d["id"] == "adv_1"
        assert d["category"] == "content_asset"
        assert d["status"] == "pending"
        assert d["urgency"] == "normal"
        assert d["automation_level"] == "manual"

    def test_from_dict(self):
        d = {
            "id": "adv_2",
            "project_id": "proj_2",
            "category": "platform_presence",
            "title": "Set up LinkedIn",
            "created_by": "operator",
            "status": "completed",
            "urgency": "blocking",
        }
        item = AdvisoryItem.from_dict(d)
        assert item.id == "adv_2"
        assert item.status == "completed"
        assert item.urgency == "blocking"

    def test_to_row(self):
        item = AdvisoryItem(
            id="adv_3",
            project_id="proj_3",
            category="code_change",
            title="Fix CI",
            created_by="system",
        )
        row = item.to_row()
        assert row[0] == "adv_3"
        assert row[1] == "proj_3"
        assert row[2] == "code_change"
        assert row[3] == "Fix CI"
        assert len(row) == 16


# =============================================================================
# CRUD tests
# =============================================================================


class TestAdvisoryCRUD:
    def test_insert_and_get(self, temp_db, project):
        item = AdvisoryItem(
            id=generate_id("advisory"),
            project_id=project.id,
            category="platform_presence",
            title="Set up X account",
            created_by="operator",
        )
        item_id = ops.insert_advisory_item(temp_db, item)
        assert item_id == item.id

        fetched = ops.get_advisory_item(temp_db, item.id)
        assert fetched is not None
        assert fetched.title == "Set up X account"
        assert fetched.category == "platform_presence"
        assert fetched.status == "pending"

    def test_get_nonexistent(self, temp_db):
        assert ops.get_advisory_item(temp_db, "nonexistent") is None

    def test_list_all(self, temp_db, project):
        for i in range(3):
            item = AdvisoryItem(
                id=generate_id("advisory"),
                project_id=project.id,
                category="content_asset",
                title=f"Item {i}",
                created_by="system",
            )
            ops.insert_advisory_item(temp_db, item)

        items = ops.get_advisory_items(temp_db, project_id=project.id)
        assert len(items) == 3

    def test_filter_by_status(self, temp_db, project):
        item1 = AdvisoryItem(
            id=generate_id("advisory"),
            project_id=project.id,
            category="content_asset",
            title="Pending item",
            created_by="system",
            status="pending",
        )
        item2 = AdvisoryItem(
            id=generate_id("advisory"),
            project_id=project.id,
            category="content_asset",
            title="Completed item",
            created_by="system",
            status="completed",
        )
        ops.insert_advisory_item(temp_db, item1)
        ops.insert_advisory_item(temp_db, item2)

        pending = ops.get_advisory_items(temp_db, project_id=project.id, status="pending")
        assert len(pending) == 1
        assert pending[0].title == "Pending item"

    def test_filter_by_category(self, temp_db, project):
        ops.insert_advisory_item(
            temp_db,
            AdvisoryItem(
                id=generate_id("advisory"),
                project_id=project.id,
                category="content_asset",
                title="Content",
                created_by="system",
            ),
        )
        ops.insert_advisory_item(
            temp_db,
            AdvisoryItem(
                id=generate_id("advisory"),
                project_id=project.id,
                category="outreach",
                title="Outreach",
                created_by="system",
            ),
        )
        content = ops.get_advisory_items(temp_db, category="content_asset")
        assert len(content) == 1

    def test_filter_by_linked_entity(self, temp_db, advisory_item):
        items = ops.get_advisory_items(
            temp_db,
            linked_entity_type="draft",
            linked_entity_id="draft_test123",
        )
        assert len(items) == 1
        assert items[0].id == advisory_item.id

    def test_update(self, temp_db, advisory_item):
        result = ops.update_advisory_item(
            temp_db, advisory_item.id, status="completed", completed_at="2026-04-09 00:00:00"
        )
        assert result is True

        updated = ops.get_advisory_item(temp_db, advisory_item.id)
        assert updated.status == "completed"
        assert updated.completed_at == "2026-04-09 00:00:00"

    def test_update_nonexistent(self, temp_db):
        result = ops.update_advisory_item(temp_db, "nonexistent", status="completed")
        assert result is False

    def test_update_no_kwargs(self, temp_db, advisory_item):
        result = ops.update_advisory_item(temp_db, advisory_item.id)
        assert result is False

    def test_delete(self, temp_db, advisory_item):
        result = ops.delete_advisory_item(temp_db, advisory_item.id)
        assert result is True
        assert ops.get_advisory_item(temp_db, advisory_item.id) is None

    def test_delete_nonexistent(self, temp_db):
        result = ops.delete_advisory_item(temp_db, "nonexistent")
        assert result is False

    def test_count(self, temp_db, project):
        for status in ("pending", "pending", "completed"):
            ops.insert_advisory_item(
                temp_db,
                AdvisoryItem(
                    id=generate_id("advisory"),
                    project_id=project.id,
                    category="content_asset",
                    title=f"Item {status}",
                    created_by="system",
                    status=status,
                ),
            )
        assert ops.count_advisory_items(temp_db) == 3
        assert ops.count_advisory_items(temp_db, status="pending") == 2
        assert ops.count_advisory_items(temp_db, project_id=project.id, status="completed") == 1

    def test_delete_project_cascades_advisory(self, temp_db, project, advisory_item):
        """Deleting a project should also delete its advisory items."""
        ops.delete_project(temp_db, project.id)
        assert ops.get_advisory_item(temp_db, advisory_item.id) is None


# =============================================================================
# Scheduler article advisory creation
# =============================================================================


class TestArticleAdvisory:
    def test_create_article_advisory(self, temp_db, project):
        """_create_article_advisory creates an advisory and sends notification."""
        from social_hook.scheduler import _create_article_advisory

        # Create a minimal draft-like object
        draft = MagicMock()
        draft.id = generate_id("draft")
        draft.project_id = project.id
        draft.platform = "x"

        config = MagicMock()

        with patch("social_hook.notifications.broadcast_notification") as mock_notify:
            _create_article_advisory(draft, temp_db, config)

        # Advisory was created
        items = ops.get_advisory_items(temp_db, project_id=project.id)
        assert len(items) == 1
        item = items[0]
        assert item.category == "content_asset"
        assert item.linked_entity_type == "draft"
        assert item.linked_entity_id == draft.id
        assert item.created_by == "system"
        assert "article" in item.title.lower() or "post manually" in item.title.lower()

        # Notification was sent
        mock_notify.assert_called_once()


# =============================================================================
# API tests
# =============================================================================


class TestAdvisoryAPI:
    """Test advisory API endpoint response shapes."""

    def test_advisory_to_api_appends_z(self):
        """_advisory_to_api appends Z to datetime fields."""
        from social_hook.web.server import _advisory_to_api

        item = AdvisoryItem(
            id="adv_1",
            project_id="proj_1",
            category="content_asset",
            title="Test",
            created_by="system",
            created_at="2026-04-09 12:00:00",
            completed_at=None,
        )
        d = _advisory_to_api(item)
        assert d["created_at"] == "2026-04-09 12:00:00Z"
        assert d["completed_at"] is None

    def test_advisory_to_api_no_double_z(self):
        """Don't double-append Z."""
        from social_hook.web.server import _advisory_to_api

        item = AdvisoryItem(
            id="adv_1",
            project_id="proj_1",
            category="content_asset",
            title="Test",
            created_by="system",
            created_at="2026-04-09 12:00:00Z",
        )
        d = _advisory_to_api(item)
        assert d["created_at"] == "2026-04-09 12:00:00Z"
