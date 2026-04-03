"""Tests for content topic queue management."""

import pytest

from social_hook.db import init_database
from social_hook.db import operations as ops
from social_hook.models.content import ContentTopic
from social_hook.topics import (
    get_evaluable_topics,
    is_positioning_strategy,
    match_tags_to_topics,
    process_topic_suggestions,
)


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


class _FakeSuggestion:
    """Mimics TopicSuggestion from schemas."""

    def __init__(
        self, title: str, description: str | None = None, strategy_type: str = "code-driven"
    ):
        self.title = title
        self.description = description
        self.strategy_type = strategy_type


class TestIsPositioningStrategy:
    def test_brand_primary_is_positioning(self):
        assert is_positioning_strategy("brand-primary") is True

    def test_product_news_is_positioning(self):
        assert is_positioning_strategy("product-news") is True

    def test_building_public_is_code_driven(self):
        assert is_positioning_strategy("building-public") is False

    def test_custom_defaults_to_code_driven(self):
        assert is_positioning_strategy("my-custom-strategy") is False


class TestProcessTopicSuggestions:
    def test_creates_code_driven_topic(self, db, project_id):
        suggestions = [
            _FakeSuggestion("OAuth Migration", "Journey from 1.0a to 2.0", "code-driven")
        ]
        created = process_topic_suggestions(db, project_id, suggestions, ["building-public"])
        assert len(created) == 1
        assert created[0].topic == "OAuth Migration"
        assert created[0].description == "Journey from 1.0a to 2.0"
        assert created[0].strategy == "building-public"
        assert created[0].created_by == "track1"

    def test_creates_positioning_topic(self, db, project_id):
        suggestions = [
            _FakeSuggestion("Simplified Onboarding", "Fewer steps to get started", "positioning")
        ]
        created = process_topic_suggestions(db, project_id, suggestions, ["brand-primary"])
        assert len(created) == 1
        assert created[0].strategy == "brand-primary"
        assert created[0].created_by == "discovery"

    def test_routes_to_correct_strategies(self, db, project_id):
        suggestions = [
            _FakeSuggestion("OAuth Migration", strategy_type="code-driven"),
            _FakeSuggestion("Simplified Onboarding", strategy_type="positioning"),
        ]
        created = process_topic_suggestions(
            db, project_id, suggestions, ["building-public", "brand-primary"]
        )
        assert len(created) == 2
        code = [t for t in created if t.strategy == "building-public"]
        pos = [t for t in created if t.strategy == "brand-primary"]
        assert len(code) == 1
        assert len(pos) == 1

    def test_skips_duplicates(self, db, project_id):
        suggestions = [_FakeSuggestion("OAuth Migration", strategy_type="code-driven")]
        first = process_topic_suggestions(db, project_id, suggestions, ["building-public"])
        assert len(first) == 1
        second = process_topic_suggestions(db, project_id, suggestions, ["building-public"])
        assert len(second) == 0

    def test_skips_dismissed_topics(self, db, project_id):
        # Create and dismiss a topic
        topic = ContentTopic(
            id="topic_dismissed1",
            project_id=project_id,
            strategy="building-public",
            topic="OAuth Migration",
            status="dismissed",
            created_by="track1",
        )
        ops.insert_content_topic(db, topic)

        suggestions = [_FakeSuggestion("OAuth Migration", strategy_type="code-driven")]
        created = process_topic_suggestions(db, project_id, suggestions, ["building-public"])
        assert len(created) == 0

    def test_empty_suggestions_returns_empty(self, db, project_id):
        assert process_topic_suggestions(db, project_id, [], ["building-public"]) == []

    def test_empty_strategies_returns_empty(self, db, project_id):
        suggestions = [_FakeSuggestion("Test", strategy_type="code-driven")]
        assert process_topic_suggestions(db, project_id, suggestions, []) == []

    def test_no_matching_strategy_type_skips(self, db, project_id):
        # Only positioning strategies available, but suggestion is code-driven
        suggestions = [_FakeSuggestion("OAuth Migration", strategy_type="code-driven")]
        created = process_topic_suggestions(db, project_id, suggestions, ["brand-primary"])
        assert len(created) == 0

    def test_creates_for_multiple_strategies_same_type(self, db, project_id):
        suggestions = [_FakeSuggestion("OAuth Migration", strategy_type="code-driven")]
        created = process_topic_suggestions(
            db, project_id, suggestions, ["building-public", "technical-deep-dive"]
        )
        assert len(created) == 2
        strategies = {t.strategy for t in created}
        assert strategies == {"building-public", "technical-deep-dive"}


class TestMatchTagsToTopics:
    def test_matches_case_insensitive_substring(self, db, project_id):
        topic = ContentTopic(
            id="topic_auth1",
            project_id=project_id,
            strategy="building-public",
            topic="auth system",
            status="uncovered",
        )
        ops.insert_content_topic(db, topic)
        matched = match_tags_to_topics(db, project_id, ["auth"])
        assert "topic_auth1" in matched

    def test_returns_empty_for_no_tags(self, db, project_id):
        assert match_tags_to_topics(db, project_id, []) == []

    def test_deduplicates_matches(self, db, project_id):
        topic = ContentTopic(
            id="topic_auth2",
            project_id=project_id,
            strategy="building-public",
            topic="auth and authentication",
            status="uncovered",
        )
        ops.insert_content_topic(db, topic)
        matched = match_tags_to_topics(db, project_id, ["auth", "authentication"])
        assert matched.count("topic_auth2") == 1

    def test_no_match_returns_empty(self, db, project_id):
        topic = ContentTopic(
            id="topic_x1",
            project_id=project_id,
            strategy="building-public",
            topic="scheduling",
            status="uncovered",
        )
        ops.insert_content_topic(db, topic)
        matched = match_tags_to_topics(db, project_id, ["auth"])
        assert matched == []


class TestGetEvaluableTopics:
    def test_returns_holding_with_commits(self, db, project_id):
        topic = ContentTopic(
            id="topic_eval1",
            project_id=project_id,
            strategy="building-public",
            topic="auth system",
            status="holding",
            commit_count=3,
        )
        ops.insert_content_topic(db, topic)
        result = get_evaluable_topics(db, project_id, "building-public")
        assert len(result) == 1
        assert result[0].id == "topic_eval1"

    def test_skips_uncovered(self, db, project_id):
        topic = ContentTopic(
            id="topic_eval2",
            project_id=project_id,
            strategy="building-public",
            topic="auth system",
            status="uncovered",
            commit_count=3,
        )
        ops.insert_content_topic(db, topic)
        result = get_evaluable_topics(db, project_id, "building-public")
        assert len(result) == 0

    def test_skips_zero_commits(self, db, project_id):
        topic = ContentTopic(
            id="topic_eval3",
            project_id=project_id,
            strategy="building-public",
            topic="auth system",
            status="holding",
            commit_count=0,
        )
        ops.insert_content_topic(db, topic)
        result = get_evaluable_topics(db, project_id, "building-public")
        assert len(result) == 0
