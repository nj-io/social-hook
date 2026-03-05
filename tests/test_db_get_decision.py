"""Tests for get_decision DB operation (Phase A)."""

import pytest

from social_hook.db import get_decision, insert_decision, insert_project, init_database
from social_hook.filesystem import generate_id
from social_hook.models import Decision, Project


class TestGetDecision:
    """Tests for get_decision single-row fetch."""

    def test_get_existing_decision(self, temp_db):
        project = Project(id=generate_id("project"), name="t", repo_path="/t")
        insert_project(temp_db, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc123",
            decision="draft",
            reasoning="Great commit",
            episode_type="milestone",
        )
        insert_decision(temp_db, decision)

        fetched = get_decision(temp_db, decision.id)
        assert fetched is not None
        assert fetched.id == decision.id
        assert fetched.reasoning == "Great commit"
        assert fetched.episode_type == "milestone"

    def test_get_nonexistent_decision_returns_none(self, temp_db):
        result = get_decision(temp_db, "decision_nonexistent")
        assert result is None
