"""Tests for content topic queue management."""

import pytest

from social_hook.db import init_database
from social_hook.db import operations as ops
from social_hook.models import ContentTopic
from social_hook.topics import (
    _parse_key_capabilities,
    force_draft_topic,
    get_evaluable_topics,
    match_tags_to_topics,
    seed_topics_from_brief,
)

SAMPLE_BRIEF = """\
## What It Does

A tool that does things.

## Key Capabilities

- Authentication system
- Real-time notifications
- Plugin architecture

## Technical Architecture

Built with Python.

## Current State

In active development.
"""

BRIEF_NO_CAPABILITIES = """\
## What It Does

A tool that does things.

## Technical Architecture

Built with Python.
"""


@pytest.fixture
def db():
    """Create an in-memory database with schema."""
    conn = init_database(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def project_id(db):
    """Register a test project."""
    pid = "proj_test123"
    db.execute(
        "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
        (pid, "test-project", "/tmp/test"),
    )
    db.commit()
    return pid


class TestParseKeyCapabilities:
    def test_extracts_bullet_points(self):
        caps = _parse_key_capabilities(SAMPLE_BRIEF)
        assert caps == [
            "Authentication system",
            "Real-time notifications",
            "Plugin architecture",
        ]

    def test_returns_empty_when_no_section(self):
        caps = _parse_key_capabilities(BRIEF_NO_CAPABILITIES)
        assert caps == []

    def test_returns_empty_for_empty_brief(self):
        assert _parse_key_capabilities("") == []
        assert _parse_key_capabilities(None) == []

    def test_handles_asterisk_bullets(self):
        brief = "## Key Capabilities\n\n* Feature one\n* Feature two\n"
        caps = _parse_key_capabilities(brief)
        assert caps == ["Feature one", "Feature two"]

    def test_stops_at_next_heading(self):
        brief = "## Key Capabilities\n\n- Cap one\n\n## Next Section\n\n- Not a cap\n"
        caps = _parse_key_capabilities(brief)
        assert caps == ["Cap one"]


class TestSeedTopicsFromBrief:
    def test_creates_topics_from_brief(self, db, project_id):
        created = seed_topics_from_brief(db, project_id, SAMPLE_BRIEF, ["brand-primary"])
        assert len(created) == 3
        assert created[0].topic == "Authentication system"
        assert created[0].strategy == "brand-primary"
        assert created[0].status == "uncovered"
        assert created[0].created_by == "discovery"

    def test_creates_per_strategy_topics(self, db, project_id):
        created = seed_topics_from_brief(
            db, project_id, SAMPLE_BRIEF, ["brand-primary", "product-news"]
        )
        assert len(created) == 6  # 3 capabilities x 2 strategies
        brand_topics = [t for t in created if t.strategy == "brand-primary"]
        product_topics = [t for t in created if t.strategy == "product-news"]
        assert len(brand_topics) == 3
        assert len(product_topics) == 3

    def test_skips_duplicates_on_reseed(self, db, project_id):
        first = seed_topics_from_brief(db, project_id, SAMPLE_BRIEF, ["brand-primary"])
        assert len(first) == 3
        second = seed_topics_from_brief(db, project_id, SAMPLE_BRIEF, ["brand-primary"])
        assert len(second) == 0

    def test_warns_when_no_capabilities(self, db, project_id, caplog):
        created = seed_topics_from_brief(db, project_id, BRIEF_NO_CAPABILITIES, ["brand-primary"])
        assert len(created) == 0
        assert "No topics extracted for strategy" in caplog.text

    def test_empty_strategies_creates_zero(self, db, project_id):
        created = seed_topics_from_brief(db, project_id, SAMPLE_BRIEF, [])
        assert len(created) == 0

    def test_idempotent_different_strategies(self, db, project_id):
        first = seed_topics_from_brief(db, project_id, SAMPLE_BRIEF, ["brand-primary"])
        assert len(first) == 3
        second = seed_topics_from_brief(db, project_id, SAMPLE_BRIEF, ["product-news"])
        assert len(second) == 3  # New strategy gets its own topics


class TestMatchTagsToTopics:
    def test_matches_case_insensitive_substring(self, db, project_id):
        topic = ContentTopic(
            id="topic_auth1",
            project_id=project_id,
            strategy="brand-primary",
            topic="Authentication system",
        )
        ops.insert_content_topic(db, topic)

        result = match_tags_to_topics(db, project_id, ["auth"])
        assert result == ["topic_auth1"]

    def test_returns_empty_when_no_matches(self, db, project_id):
        topic = ContentTopic(
            id="topic_auth1",
            project_id=project_id,
            strategy="brand-primary",
            topic="Authentication system",
        )
        ops.insert_content_topic(db, topic)

        result = match_tags_to_topics(db, project_id, ["database"])
        assert result == []

    def test_returns_empty_for_empty_tags(self, db, project_id):
        result = match_tags_to_topics(db, project_id, [])
        assert result == []

    def test_deduplicates_matches(self, db, project_id):
        topic = ContentTopic(
            id="topic_auth1",
            project_id=project_id,
            strategy="brand-primary",
            topic="Authentication and auth tokens",
        )
        ops.insert_content_topic(db, topic)

        # Both tags match the same topic
        result = match_tags_to_topics(db, project_id, ["auth", "token"])
        assert result == ["topic_auth1"]

    def test_multiple_topics_matched(self, db, project_id):
        t1 = ContentTopic(
            id="topic_auth1",
            project_id=project_id,
            strategy="brand-primary",
            topic="Authentication system",
        )
        t2 = ContentTopic(
            id="topic_notif1",
            project_id=project_id,
            strategy="brand-primary",
            topic="Notification service",
        )
        ops.insert_content_topic(db, t1)
        ops.insert_content_topic(db, t2)

        result = match_tags_to_topics(db, project_id, ["auth", "notif"])
        assert set(result) == {"topic_auth1", "topic_notif1"}


class TestGetEvaluableTopics:
    def test_returns_holding_topics_with_commits(self, db, project_id):
        topic = ContentTopic(
            id="topic_eval1",
            project_id=project_id,
            strategy="brand-primary",
            topic="Auth system",
            status="holding",
            commit_count=3,
        )
        ops.insert_content_topic(db, topic)

        result = get_evaluable_topics(db, project_id, "brand-primary")
        assert len(result) == 1
        assert result[0].id == "topic_eval1"

    def test_excludes_uncovered_topics(self, db, project_id):
        topic = ContentTopic(
            id="topic_unc1",
            project_id=project_id,
            strategy="brand-primary",
            topic="Uncovered thing",
            status="uncovered",
            commit_count=5,
        )
        ops.insert_content_topic(db, topic)

        result = get_evaluable_topics(db, project_id, "brand-primary")
        assert len(result) == 0

    def test_excludes_holding_with_zero_commits(self, db, project_id):
        topic = ContentTopic(
            id="topic_zero1",
            project_id=project_id,
            strategy="brand-primary",
            topic="No commits yet",
            status="holding",
            commit_count=0,
        )
        ops.insert_content_topic(db, topic)

        result = get_evaluable_topics(db, project_id, "brand-primary")
        assert len(result) == 0

    def test_excludes_covered_topics(self, db, project_id):
        topic = ContentTopic(
            id="topic_cov1",
            project_id=project_id,
            strategy="brand-primary",
            topic="Already covered",
            status="covered",
            commit_count=10,
        )
        ops.insert_content_topic(db, topic)

        result = get_evaluable_topics(db, project_id, "brand-primary")
        assert len(result) == 0

    def test_includes_global_strategy_topics(self, db, project_id):
        topic = ContentTopic(
            id="topic_glob1",
            project_id=project_id,
            strategy="_global",
            topic="Global topic",
            status="holding",
            commit_count=2,
        )
        ops.insert_content_topic(db, topic)

        result = get_evaluable_topics(db, project_id, "brand-primary")
        assert len(result) == 1
        assert result[0].id == "topic_glob1"

    def test_combines_strategy_and_global(self, db, project_id):
        t1 = ContentTopic(
            id="topic_strat1",
            project_id=project_id,
            strategy="brand-primary",
            topic="Strategy topic",
            status="holding",
            commit_count=1,
        )
        t2 = ContentTopic(
            id="topic_glob1",
            project_id=project_id,
            strategy="_global",
            topic="Global topic",
            status="holding",
            commit_count=2,
        )
        ops.insert_content_topic(db, t1)
        ops.insert_content_topic(db, t2)

        result = get_evaluable_topics(db, project_id, "brand-primary")
        assert len(result) == 2
        result_ids = {t.id for t in result}
        assert result_ids == {"topic_strat1", "topic_glob1"}


class TestForceDraftTopic:
    def test_creates_evaluation_cycle(self, db, project_id):
        topic = ContentTopic(
            id="topic_force1",
            project_id=project_id,
            strategy="brand-primary",
            topic="Auth system",
            status="holding",
            commit_count=5,
        )
        ops.insert_content_topic(db, topic)

        cycle_id = force_draft_topic(db, None, project_id, "topic_force1", "brand-primary")
        assert cycle_id is not None
        assert cycle_id.startswith("cycle_")

        # Verify cycle was inserted
        cycles = ops.get_recent_cycles(db, project_id)
        assert len(cycles) == 1
        assert cycles[0].trigger_type == "topic_maturity"
        assert cycles[0].trigger_ref == "topic_force1"

    def test_returns_none_for_missing_topic(self, db, project_id):
        from social_hook.errors import ConfigError

        with pytest.raises(ConfigError, match="Topic not found"):
            force_draft_topic(db, None, project_id, "topic_nonexistent", "brand-primary")

    def test_allows_uncovered_topic(self, db, project_id):
        topic = ContentTopic(
            id="topic_unc1",
            project_id=project_id,
            strategy="brand-primary",
            topic="Uncovered thing",
            status="uncovered",
        )
        ops.insert_content_topic(db, topic)

        cycle_id = force_draft_topic(db, None, project_id, "topic_unc1", "brand-primary")
        assert cycle_id is not None  # uncovered topics can be force-drafted

    def test_returns_none_for_covered_topic(self, db, project_id):
        topic = ContentTopic(
            id="topic_cov1",
            project_id=project_id,
            strategy="brand-primary",
            topic="Covered thing",
            status="covered",
        )
        ops.insert_content_topic(db, topic)

        cycle_id = force_draft_topic(db, None, project_id, "topic_cov1", "brand-primary")
        assert cycle_id is None

    def test_dry_run_does_not_insert(self, db, project_id):
        topic = ContentTopic(
            id="topic_dry1",
            project_id=project_id,
            strategy="brand-primary",
            topic="Auth system",
            status="holding",
            commit_count=3,
        )
        ops.insert_content_topic(db, topic)

        cycle_id = force_draft_topic(
            db, None, project_id, "topic_dry1", "brand-primary", dry_run=True
        )
        assert cycle_id is not None

        # Verify no cycle was actually inserted
        cycles = ops.get_recent_cycles(db, project_id)
        assert len(cycles) == 0


class TestStatusTransitions:
    def test_uncovered_to_holding(self, db, project_id):
        topic = ContentTopic(
            id="topic_trans1",
            project_id=project_id,
            strategy="brand-primary",
            topic="Auth system",
            status="uncovered",
        )
        ops.insert_content_topic(db, topic)

        result = ops.update_topic_status(db, "topic_trans1", "holding")
        assert result is True

        updated = ops.get_topic(db, "topic_trans1")
        assert updated.status == "holding"

    def test_holding_to_partial(self, db, project_id):
        topic = ContentTopic(
            id="topic_trans2",
            project_id=project_id,
            strategy="brand-primary",
            topic="Auth system",
            status="holding",
        )
        ops.insert_content_topic(db, topic)

        result = ops.update_topic_status(db, "topic_trans2", "partial")
        assert result is True

        updated = ops.get_topic(db, "topic_trans2")
        assert updated.status == "partial"

    def test_partial_to_covered(self, db, project_id):
        topic = ContentTopic(
            id="topic_trans3",
            project_id=project_id,
            strategy="brand-primary",
            topic="Auth system",
            status="partial",
        )
        ops.insert_content_topic(db, topic)

        result = ops.update_topic_status(db, "topic_trans3", "covered")
        assert result is True

        updated = ops.get_topic(db, "topic_trans3")
        assert updated.status == "covered"
