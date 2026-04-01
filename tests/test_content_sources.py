"""Tests for ContentSource registry and built-in resolvers."""

import sqlite3

from social_hook.content_sources import (
    ContentSourceRegistry,
    content_sources,
    resolve_brief,
    resolve_commits,
    resolve_operator_suggestion,
    resolve_topic,
)
from social_hook.db import operations as ops
from social_hook.filesystem import generate_id
from social_hook.models.content import ContentTopic
from social_hook.models.core import Project


class TestContentSourceRegistry:
    """Tests for the registry itself."""

    def test_register_and_resolve(self):
        """Register a resolver and resolve it."""
        registry = ContentSourceRegistry()
        registry.register("test", lambda **kw: "hello")

        result = registry.resolve(["test"])
        assert result == {"test": "hello"}

    def test_resolve_multiple_types(self):
        """Resolve multiple source types in one call."""
        registry = ContentSourceRegistry()
        registry.register("a", lambda **kw: "alpha")
        registry.register("b", lambda **kw: "beta")

        result = registry.resolve(["a", "b"])
        assert result == {"a": "alpha", "b": "beta"}

    def test_unknown_type_skipped(self):
        """Unknown source type logs warning and skips."""
        registry = ContentSourceRegistry()
        registry.register("known", lambda **kw: "ok")

        result = registry.resolve(["known", "unknown"])
        assert result == {"known": "ok"}

    def test_empty_result_skipped(self):
        """Resolver returning empty string is not included."""
        registry = ContentSourceRegistry()
        registry.register("empty", lambda **kw: "")
        registry.register("full", lambda **kw: "content")

        result = registry.resolve(["empty", "full"])
        assert result == {"full": "content"}

    def test_resolver_exception_handled(self):
        """Resolver that raises is caught and skipped."""
        registry = ContentSourceRegistry()
        registry.register("bad", lambda **kw: 1 / 0)
        registry.register("good", lambda **kw: "ok")

        result = registry.resolve(["bad", "good"])
        assert result == {"good": "ok"}

    def test_kwargs_passed_to_resolver(self):
        """Keyword arguments are passed through to resolvers."""
        registry = ContentSourceRegistry()
        captured = {}

        def capture(**kw):
            captured.update(kw)
            return "ok"

        registry.register("test", capture)
        registry.resolve(["test"], foo="bar", baz=42)
        assert captured["foo"] == "bar"
        assert captured["baz"] == 42


class TestBuiltInResolvers:
    """Tests for built-in resolver functions."""

    def _seed_project(self, conn: sqlite3.Connection) -> str:
        """Insert a test project and return its ID."""
        project = Project(
            id=generate_id("proj"),
            name="test-project",
            repo_path="/tmp/test",
        )
        ops.insert_project(conn, project)
        return project.id

    def test_resolve_brief_with_summary(self, temp_db):
        """resolve_brief returns project summary when no brief module."""
        project_id = self._seed_project(temp_db)
        # Set summary directly
        temp_db.execute(
            "UPDATE projects SET summary = ? WHERE id = ?",
            ("This is a test project.", project_id),
        )
        temp_db.commit()

        result = resolve_brief(conn=temp_db, project_id=project_id)
        assert "test project" in result

    def test_resolve_brief_no_summary(self, temp_db):
        """resolve_brief returns empty when no summary exists."""
        project_id = self._seed_project(temp_db)
        result = resolve_brief(conn=temp_db, project_id=project_id)
        assert result == ""

    def test_resolve_commits_no_decisions(self, temp_db):
        """resolve_commits returns empty when no decisions exist."""
        project_id = self._seed_project(temp_db)
        result = resolve_commits(conn=temp_db, project_id=project_id)
        assert result == ""

    def test_resolve_topic_found(self, temp_db):
        """resolve_topic returns topic description."""
        project_id = self._seed_project(temp_db)
        topic = ContentTopic(
            id=generate_id("topic"),
            project_id=project_id,
            strategy="bip",
            topic="OAuth migration",
            description="Migrating from OAuth 1.0a to 2.0",
        )
        ops.insert_content_topic(temp_db, topic)

        result = resolve_topic(conn=temp_db, project_id=project_id, topic_id=topic.id)
        assert "OAuth migration" in result
        assert "Migrating" in result

    def test_resolve_topic_not_found(self, temp_db):
        """resolve_topic returns empty when topic doesn't exist."""
        project_id = self._seed_project(temp_db)
        result = resolve_topic(conn=temp_db, project_id=project_id, topic_id="nonexistent")
        assert result == ""

    def test_resolve_topic_no_id(self, temp_db):
        """resolve_topic returns empty when no topic_id provided."""
        result = resolve_topic(conn=temp_db, project_id="proj-1")
        assert result == ""

    def test_resolve_operator_suggestion_no_id(self, temp_db):
        """resolve_operator_suggestion returns empty when no suggestion_id."""
        result = resolve_operator_suggestion(conn=temp_db, project_id="proj-1")
        assert result == ""

    def test_resolve_operator_suggestion_not_found(self, temp_db):
        """resolve_operator_suggestion returns empty for missing suggestion."""
        project_id = self._seed_project(temp_db)
        result = resolve_operator_suggestion(
            conn=temp_db, project_id=project_id, suggestion_id="missing"
        )
        assert result == ""


class TestModuleSingleton:
    """Test the module-level singleton registration."""

    def test_default_registry_has_all_resolvers(self):
        """Module singleton has all 5 built-in resolvers registered."""
        assert "brief" in content_sources._resolvers
        assert "commits" in content_sources._resolvers
        assert "topic" in content_sources._resolvers
        assert "topic_commits" in content_sources._resolvers
        assert "operator_suggestion" in content_sources._resolvers
