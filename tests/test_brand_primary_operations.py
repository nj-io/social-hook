"""Tests for brand-primary candidate operations (combine, hero launch)."""

import pytest

from social_hook.content.operations import combine_candidates, trigger_hero_launch
from social_hook.db import operations as ops
from social_hook.models import ContentTopic, Project


def _seed_project(conn, project_id="proj_test", name="test-project"):
    """Insert a minimal project for testing."""
    project = Project(
        id=project_id,
        name=name,
        repo_path="/tmp/test-repo",
    )
    ops.insert_project(conn, project)
    return project


def _seed_topic(
    conn,
    topic_id,
    project_id,
    strategy="brand-primary",
    status="holding",
    topic_name="Auth rework",
    description=None,
):
    """Insert a content topic for testing."""
    t = ContentTopic(
        id=topic_id,
        project_id=project_id,
        strategy=strategy,
        topic=topic_name,
        description=description,
        status=status,
    )
    ops.insert_content_topic(conn, t)
    return t


class TestCombineCandidates:
    """Tests for combine_candidates()."""

    def test_combine_two_topics(self, temp_db):
        """Combine 2 topics creates draft and marks topics covered."""
        project = _seed_project(temp_db)
        _seed_topic(
            temp_db, "t1", project.id, topic_name="Auth rework", description="OAuth migration"
        )
        _seed_topic(
            temp_db, "t2", project.id, topic_name="Token refresh", description="Auto-refresh tokens"
        )

        draft_id = combine_candidates(temp_db, {}, ["t1", "t2"], project.id)

        assert draft_id is not None
        assert draft_id.startswith("draft_")

        # Verify draft was created
        draft = ops.get_draft(temp_db, draft_id)
        assert draft is not None
        assert draft.status == "draft"
        assert "Auth rework" in draft.content
        assert "Token refresh" in draft.content
        assert draft.evaluation_cycle_id is not None

        # Verify topics marked as covered
        t1 = ops.get_topic(temp_db, "t1")
        t2 = ops.get_topic(temp_db, "t2")
        assert t1.status == "covered"
        assert t2.status == "covered"

    def test_combine_three_topics(self, temp_db):
        """Combine 3 topics works correctly."""
        project = _seed_project(temp_db)
        _seed_topic(temp_db, "t1", project.id, topic_name="Feature A")
        _seed_topic(temp_db, "t2", project.id, topic_name="Feature B")
        _seed_topic(temp_db, "t3", project.id, topic_name="Feature C")

        draft_id = combine_candidates(temp_db, {}, ["t1", "t2", "t3"], project.id)
        draft = ops.get_draft(temp_db, draft_id)
        assert "Feature A" in draft.content
        assert "Feature B" in draft.content
        assert "Feature C" in draft.content

    def test_combine_fewer_than_two_raises(self, temp_db):
        """Combine with fewer than 2 topics raises ValueError."""
        _seed_project(temp_db)
        with pytest.raises(ValueError, match="at least 2"):
            combine_candidates(temp_db, {}, ["t1"], "proj_test")

    def test_combine_empty_list_raises(self, temp_db):
        """Combine with empty list raises ValueError."""
        _seed_project(temp_db)
        with pytest.raises(ValueError, match="at least 2"):
            combine_candidates(temp_db, {}, [], "proj_test")

    def test_combine_non_holding_topic_raises(self, temp_db):
        """Combine with non-holding topic raises ValueError."""
        project = _seed_project(temp_db)
        _seed_topic(temp_db, "t1", project.id, status="holding")
        _seed_topic(temp_db, "t2", project.id, status="uncovered", topic_name="Other")

        with pytest.raises(ValueError, match="not in 'holding' status"):
            combine_candidates(temp_db, {}, ["t1", "t2"], project.id)

    def test_combine_wrong_strategy_raises(self, temp_db):
        """Combine with non-brand-primary topic raises ValueError."""
        project = _seed_project(temp_db)
        _seed_topic(temp_db, "t1", project.id, strategy="brand-primary")
        _seed_topic(temp_db, "t2", project.id, strategy="building-public", topic_name="Other topic")

        with pytest.raises(ValueError, match="expected 'brand-primary'"):
            combine_candidates(temp_db, {}, ["t1", "t2"], project.id)

    def test_combine_missing_topic_raises(self, temp_db):
        """Combine with non-existent topic raises ValueError."""
        _seed_project(temp_db)
        with pytest.raises(ValueError, match="Topic not found"):
            combine_candidates(temp_db, {}, ["t1", "nonexistent"], "proj_test")

    def test_combine_creates_evaluation_cycle(self, temp_db):
        """Combine creates an evaluation cycle with trigger_type='combine'."""
        project = _seed_project(temp_db)
        _seed_topic(temp_db, "t1", project.id, topic_name="A")
        _seed_topic(temp_db, "t2", project.id, topic_name="B")

        draft_id = combine_candidates(temp_db, {}, ["t1", "t2"], project.id)
        draft = ops.get_draft(temp_db, draft_id)

        cycles = ops.get_recent_cycles(temp_db, project.id)
        assert len(cycles) == 1
        assert cycles[0].trigger_type == "combine"
        assert cycles[0].id == draft.evaluation_cycle_id

    def test_combine_includes_descriptions(self, temp_db):
        """Combined context includes topic descriptions when present."""
        project = _seed_project(temp_db)
        _seed_topic(temp_db, "t1", project.id, topic_name="Auth", description="OAuth2 migration")
        _seed_topic(temp_db, "t2", project.id, topic_name="Tokens", description="Auto-refresh")

        draft_id = combine_candidates(temp_db, {}, ["t1", "t2"], project.id)
        draft = ops.get_draft(temp_db, draft_id)
        assert "OAuth2 migration" in draft.content
        assert "Auto-refresh" in draft.content


class TestTriggerHeroLaunch:
    """Tests for trigger_hero_launch()."""

    def test_hero_launch_creates_draft(self, temp_db):
        """Hero launch creates a draft with hero context."""
        project = _seed_project(temp_db)
        _seed_topic(temp_db, "t1", project.id, topic_name="Feature A")
        _seed_topic(temp_db, "t2", project.id, topic_name="Feature B", status="covered")

        draft_id = trigger_hero_launch(temp_db, {}, project.id, "/tmp/test-repo")

        assert draft_id is not None
        draft = ops.get_draft(temp_db, draft_id)
        assert draft is not None
        assert draft.status == "draft"
        assert "Hero launch" in draft.content
        assert "Feature A" in draft.content
        assert "Feature B" in draft.content

    def test_hero_launch_includes_brief(self, temp_db):
        """Hero launch includes project summary when available."""
        project = _seed_project(temp_db)
        ops.update_project_summary(temp_db, project.id, "A tool for social media automation")

        draft_id = trigger_hero_launch(temp_db, {}, project.id, "/tmp/test-repo")
        draft = ops.get_draft(temp_db, draft_id)
        assert "social media automation" in draft.content

    def test_hero_launch_no_held_candidates(self, temp_db):
        """Hero launch works even with no held candidates."""
        project = _seed_project(temp_db)
        _seed_topic(temp_db, "t1", project.id, topic_name="Feature A", status="covered")

        draft_id = trigger_hero_launch(temp_db, {}, project.id, "/tmp/test-repo")
        draft = ops.get_draft(temp_db, draft_id)
        assert draft is not None
        assert "Feature A" in draft.content

    def test_hero_launch_no_topics_at_all(self, temp_db):
        """Hero launch works with no topics at all — uses brief + project path only."""
        project = _seed_project(temp_db)

        draft_id = trigger_hero_launch(temp_db, {}, project.id, "/tmp/test-repo")
        draft = ops.get_draft(temp_db, draft_id)
        assert draft is not None
        assert "/tmp/test-repo" in draft.content

    def test_hero_launch_creates_evaluation_cycle(self, temp_db):
        """Hero launch creates an evaluation cycle with trigger_type='hero_launch'."""
        project = _seed_project(temp_db)

        draft_id = trigger_hero_launch(temp_db, {}, project.id, "/tmp/test-repo")
        draft = ops.get_draft(temp_db, draft_id)

        cycles = ops.get_recent_cycles(temp_db, project.id)
        assert len(cycles) == 1
        assert cycles[0].trigger_type == "hero_launch"
        assert cycles[0].id == draft.evaluation_cycle_id

    def test_hero_launch_separates_held_and_covered(self, temp_db):
        """Hero launch context separates held candidates from covered topics."""
        project = _seed_project(temp_db)
        _seed_topic(temp_db, "t1", project.id, topic_name="Held Feature", status="holding")
        _seed_topic(temp_db, "t2", project.id, topic_name="Covered Feature", status="covered")

        draft_id = trigger_hero_launch(temp_db, {}, project.id, "/tmp/test-repo")
        draft = ops.get_draft(temp_db, draft_id)
        assert "Held candidates:" in draft.content
        assert "Covered topics:" in draft.content
        assert "Held Feature" in draft.content
        assert "Covered Feature" in draft.content
