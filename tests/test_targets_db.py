"""Tests for targets Phase 1 DB: schema, models, CRUD operations."""

import json
import sqlite3

import pytest

from social_hook.db.operations import (
    delete_oauth_token,
    get_error_health_status,
    get_oauth_token,
    get_patterns_by_project,
    get_recent_cycles,
    get_recent_system_errors,
    get_suggestions_by_project,
    get_topic,
    get_topics_by_strategy,
    increment_topic_commit_count,
    insert_content_suggestion,
    insert_content_topic,
    insert_draft,
    insert_draft_pattern,
    insert_evaluation_cycle,
    insert_post,
    insert_system_error,
    update_suggestion_status,
    update_topic_priority,
    update_topic_status,
    upsert_oauth_token,
)
from social_hook.models import (
    SUGGESTION_STATUSES,
    TOPIC_STATUSES,
    ContentSuggestion,
    ContentTopic,
    Draft,
    DraftPattern,
    EvaluationCycle,
    OAuthToken,
    Post,
    SystemErrorRecord,
)

# =============================================================================
# Schema & Table Creation
# =============================================================================


class TestSchemaCreation:
    """Verify init_database creates all new tables."""

    def test_new_tables_exist(self, temp_db):
        tables = {
            row[0]
            for row in temp_db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for expected in [
            "oauth_tokens",
            "content_topics",
            "content_suggestions",
            "evaluation_cycles",
            "draft_patterns",
            "system_errors",
        ]:
            assert expected in tables, f"Missing table: {expected}"

    def test_drafts_has_new_columns(self, temp_db):
        info = temp_db.execute("PRAGMA table_info(drafts)").fetchall()
        col_names = {row[1] for row in info}
        for col in ["target_id", "evaluation_cycle_id", "topic_id", "suggestion_id", "pattern_id"]:
            assert col in col_names, f"Missing column on drafts: {col}"

    def test_posts_has_new_columns(self, temp_db):
        info = temp_db.execute("PRAGMA table_info(posts)").fetchall()
        col_names = {row[1] for row in info}
        for col in ["target_id", "topic_tags", "feature_tags", "is_thread_head"]:
            assert col in col_names, f"Missing column on posts: {col}"

    def test_projects_has_brief_section_metadata(self, temp_db):
        info = temp_db.execute("PRAGMA table_info(projects)").fetchall()
        col_names = {row[1] for row in info}
        assert "brief_section_metadata" in col_names


# =============================================================================
# Migrations
# =============================================================================


class TestMigrations:
    """Verify migrations apply cleanly to an existing DB."""

    def test_migrations_apply_to_existing_db(self, temp_dir):
        """Create a DB with the old schema, then apply migrations."""
        from social_hook.db.schema import apply_migrations

        db_path = temp_dir / "migrate_test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Create a minimal old schema (pre-targets)
        conn.executescript("""
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now')),
                description TEXT
            );
            INSERT INTO schema_version (version, description) VALUES (20260323142446, 'add_oauth_tokens');

            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                repo_path TEXT NOT NULL,
                repo_origin TEXT,
                summary TEXT,
                summary_updated_at TEXT,
                paused INTEGER NOT NULL DEFAULT 0,
                discovery_files TEXT DEFAULT NULL,
                prompt_docs TEXT DEFAULT NULL,
                trigger_branch TEXT DEFAULT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE decisions (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id),
                commit_hash TEXT NOT NULL,
                commit_message TEXT,
                decision TEXT NOT NULL,
                reasoning TEXT NOT NULL,
                angle TEXT,
                episode_type TEXT,
                episode_tags TEXT DEFAULT '[]',
                post_category TEXT,
                arc_id TEXT,
                media_tool TEXT,
                platforms TEXT NOT NULL DEFAULT '{}',
                targets TEXT NOT NULL DEFAULT '{}',
                commit_summary TEXT,
                consolidate_with TEXT,
                reference_posts TEXT DEFAULT NULL,
                branch TEXT DEFAULT NULL,
                trigger_source TEXT DEFAULT 'commit',
                processed INTEGER NOT NULL DEFAULT 0,
                processed_at TEXT,
                batch_id TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(project_id, commit_hash)
            );

            CREATE TABLE drafts (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id),
                decision_id TEXT NOT NULL REFERENCES decisions(id),
                platform TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                content TEXT NOT NULL,
                media_paths TEXT NOT NULL DEFAULT '[]',
                media_type TEXT,
                media_spec TEXT DEFAULT '{}',
                media_spec_used TEXT,
                suggested_time TEXT,
                scheduled_time TEXT,
                reasoning TEXT,
                superseded_by TEXT REFERENCES drafts(id),
                retry_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                is_intro INTEGER NOT NULL DEFAULT 0,
                post_format TEXT DEFAULT NULL,
                reference_post_id TEXT DEFAULT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE posts (
                id TEXT PRIMARY KEY,
                draft_id TEXT NOT NULL REFERENCES drafts(id),
                project_id TEXT NOT NULL REFERENCES projects(id),
                platform TEXT NOT NULL,
                external_id TEXT,
                external_url TEXT,
                content TEXT NOT NULL,
                posted_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE oauth_tokens (
                account_name TEXT PRIMARY KEY,
                platform TEXT NOT NULL,
                access_token TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        conn.commit()

        # Use the actual migrations dir from the worktree
        from pathlib import Path

        actual_migrations = Path(
            "/Users/neil/dev/social-media-auto-hook/.claude/worktrees/targets"
            "/src/social_hook/db/migrations"
        )
        apply_migrations(conn, actual_migrations)

        # Verify new tables exist
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "content_topics" in tables
        assert "system_errors" in tables

        # Verify new columns on drafts
        info = conn.execute("PRAGMA table_info(drafts)").fetchall()
        col_names = {row[1] for row in info}
        assert "target_id" in col_names

        # Verify new columns on posts
        info = conn.execute("PRAGMA table_info(posts)").fetchall()
        col_names = {row[1] for row in info}
        assert "topic_tags" in col_names

        # Verify brief_section_metadata on projects
        info = conn.execute("PRAGMA table_info(projects)").fetchall()
        col_names = {row[1] for row in info}
        assert "brief_section_metadata" in col_names

        conn.close()


# =============================================================================
# OAuth Token CRUD
# =============================================================================


class TestOAuthTokenCRUD:
    def test_upsert_and_get(self, temp_db):
        token = OAuthToken(
            account_name="my-x-account",
            platform="x",
            access_token="at_123",
            refresh_token="rt_456",
            expires_at="2026-04-01T00:00:00Z",
            updated_at="2026-03-23T00:00:00Z",
        )
        upsert_oauth_token(temp_db, token)
        result = get_oauth_token(temp_db, "my-x-account")
        assert result is not None
        assert result.access_token == "at_123"
        assert result.platform == "x"

    def test_upsert_updates_existing(self, temp_db):
        token1 = OAuthToken(
            account_name="acct",
            platform="x",
            access_token="old",
            refresh_token="rt",
            expires_at="2026-04-01T00:00:00Z",
            updated_at="2026-03-23T00:00:00Z",
        )
        upsert_oauth_token(temp_db, token1)
        token2 = OAuthToken(
            account_name="acct",
            platform="x",
            access_token="new",
            refresh_token="rt2",
            expires_at="2026-04-02T00:00:00Z",
            updated_at="2026-03-24T00:00:00Z",
        )
        upsert_oauth_token(temp_db, token2)
        result = get_oauth_token(temp_db, "acct")
        assert result is not None
        assert result.access_token == "new"
        assert result.refresh_token == "rt2"

    def test_get_nonexistent(self, temp_db):
        assert get_oauth_token(temp_db, "nope") is None

    def test_delete(self, temp_db):
        token = OAuthToken(
            account_name="del-me",
            platform="x",
            access_token="at",
            refresh_token="rt",
            expires_at="2026-04-01T00:00:00Z",
            updated_at="2026-03-23T00:00:00Z",
        )
        upsert_oauth_token(temp_db, token)
        assert delete_oauth_token(temp_db, "del-me") is True
        assert get_oauth_token(temp_db, "del-me") is None

    def test_delete_nonexistent(self, temp_db):
        assert delete_oauth_token(temp_db, "nope") is False

    def test_account_name_uniqueness(self, temp_db):
        """Inserting same account_name via raw INSERT should fail."""
        temp_db.execute(
            "INSERT INTO oauth_tokens VALUES (?, ?, ?, ?, ?, ?)",
            ("dup", "x", "at1", "rt1", "2026-04-01", "2026-03-23"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            temp_db.execute(
                "INSERT INTO oauth_tokens VALUES (?, ?, ?, ?, ?, ?)",
                ("dup", "x", "at2", "rt2", "2026-04-01", "2026-03-23"),
            )

    def test_round_trip_to_dict(self):
        token = OAuthToken(
            account_name="test",
            platform="linkedin",
            access_token="at",
            refresh_token="rt",
            expires_at="2026-04-01T00:00:00Z",
            updated_at="2026-03-23T00:00:00Z",
        )
        d = token.to_dict()
        restored = OAuthToken.from_dict(d)
        assert restored.account_name == "test"
        assert restored.platform == "linkedin"


# =============================================================================
# Content Topic CRUD
# =============================================================================


class TestContentTopicCRUD:
    def _make_project(self, conn):
        conn.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj-1", "test", "/tmp/test"),
        )
        conn.commit()

    def test_insert_and_get(self, temp_db):
        self._make_project(temp_db)
        topic = ContentTopic(
            id="topic-1",
            project_id="proj-1",
            strategy="building-public",
            topic="Testing framework",
            description="Our testing approach",
            priority_rank=5,
        )
        insert_content_topic(temp_db, topic)
        result = get_topic(temp_db, "topic-1")
        assert result is not None
        assert result.topic == "Testing framework"
        assert result.priority_rank == 5
        assert result.status == "uncovered"

    def test_get_by_strategy(self, temp_db):
        self._make_project(temp_db)
        for i in range(3):
            insert_content_topic(
                temp_db,
                ContentTopic(
                    id=f"t-{i}",
                    project_id="proj-1",
                    strategy="strat-a",
                    topic=f"Topic {i}",
                    priority_rank=i,
                ),
            )
        insert_content_topic(
            temp_db,
            ContentTopic(
                id="t-other",
                project_id="proj-1",
                strategy="strat-b",
                topic="Other",
            ),
        )
        results = get_topics_by_strategy(temp_db, "proj-1", "strat-a")
        assert len(results) == 3
        # Ordered by priority_rank DESC
        assert results[0].priority_rank == 2

    def test_update_status(self, temp_db):
        self._make_project(temp_db)
        insert_content_topic(
            temp_db,
            ContentTopic(id="t-s", project_id="proj-1", strategy="s", topic="T"),
        )
        assert update_topic_status(temp_db, "t-s", "covered") is True
        assert get_topic(temp_db, "t-s").status == "covered"

    def test_update_priority(self, temp_db):
        self._make_project(temp_db)
        insert_content_topic(
            temp_db,
            ContentTopic(id="t-p", project_id="proj-1", strategy="s", topic="T"),
        )
        assert update_topic_priority(temp_db, "t-p", 10) is True
        assert get_topic(temp_db, "t-p").priority_rank == 10

    def test_increment_commit_count(self, temp_db):
        self._make_project(temp_db)
        insert_content_topic(
            temp_db,
            ContentTopic(id="t-c", project_id="proj-1", strategy="s", topic="T"),
        )
        increment_topic_commit_count(temp_db, "t-c")
        increment_topic_commit_count(temp_db, "t-c")
        result = get_topic(temp_db, "t-c")
        assert result.commit_count == 2
        assert result.last_commit_at is not None

    def test_status_check_constraint(self, temp_db):
        self._make_project(temp_db)
        with pytest.raises(sqlite3.IntegrityError):
            temp_db.execute(
                """INSERT INTO content_topics (id, project_id, strategy, topic, status)
                   VALUES (?, ?, ?, ?, ?)""",
                ("bad", "proj-1", "s", "t", "invalid_status"),
            )

    def test_round_trip(self, temp_db):
        self._make_project(temp_db)
        topic = ContentTopic(
            id="rt-1",
            project_id="proj-1",
            strategy="building-public",
            topic="Round trip test",
            description="desc",
            priority_rank=3,
            status="holding",
            created_by="system",
        )
        insert_content_topic(temp_db, topic)
        restored = get_topic(temp_db, "rt-1")
        assert restored.to_dict()["strategy"] == "building-public"
        assert restored.to_dict()["created_by"] == "system"


# =============================================================================
# Content Suggestion CRUD
# =============================================================================


class TestContentSuggestionCRUD:
    def _make_project(self, conn):
        conn.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj-1", "test", "/tmp/test"),
        )
        conn.commit()

    def test_insert_and_get(self, temp_db):
        self._make_project(temp_db)
        suggestion = ContentSuggestion(
            id="sug-1",
            project_id="proj-1",
            idea="Write about testing",
            strategy="building-public",
            media_refs=["screenshot.png"],
        )
        insert_content_suggestion(temp_db, suggestion)
        results = get_suggestions_by_project(temp_db, "proj-1")
        assert len(results) == 1
        assert results[0].idea == "Write about testing"
        assert results[0].media_refs == ["screenshot.png"]

    def test_update_status(self, temp_db):
        self._make_project(temp_db)
        insert_content_suggestion(
            temp_db,
            ContentSuggestion(id="sug-2", project_id="proj-1", idea="Test idea"),
        )
        update_suggestion_status(temp_db, "sug-2", "evaluated")
        results = get_suggestions_by_project(temp_db, "proj-1")
        assert results[0].status == "evaluated"
        assert results[0].evaluated_at is not None

    def test_media_refs_json(self, temp_db):
        """media_refs stored as JSON string deserializes properly."""
        self._make_project(temp_db)
        suggestion = ContentSuggestion(
            id="sug-json",
            project_id="proj-1",
            idea="JSON test",
            media_refs=["a.png", "b.mp4"],
        )
        insert_content_suggestion(temp_db, suggestion)
        result = get_suggestions_by_project(temp_db, "proj-1")[0]
        assert result.media_refs == ["a.png", "b.mp4"]

    def test_status_check_constraint(self, temp_db):
        self._make_project(temp_db)
        with pytest.raises(sqlite3.IntegrityError):
            temp_db.execute(
                """INSERT INTO content_suggestions (id, project_id, idea, status)
                   VALUES (?, ?, ?, ?)""",
                ("bad", "proj-1", "idea", "bad_status"),
            )


# =============================================================================
# Evaluation Cycle CRUD
# =============================================================================


class TestEvaluationCycleCRUD:
    def _make_project(self, conn):
        conn.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj-1", "test", "/tmp/test"),
        )
        conn.commit()

    def test_insert_and_get_recent(self, temp_db):
        self._make_project(temp_db)
        cycle = EvaluationCycle(
            id="cycle-1",
            project_id="proj-1",
            trigger_type="commit",
            trigger_ref="abc123",
        )
        insert_evaluation_cycle(temp_db, cycle)
        results = get_recent_cycles(temp_db, "proj-1")
        assert len(results) == 1
        assert results[0].trigger_type == "commit"
        assert results[0].trigger_ref == "abc123"

    def test_round_trip(self, temp_db):
        self._make_project(temp_db)
        cycle = EvaluationCycle(
            id="cycle-rt",
            project_id="proj-1",
            trigger_type="suggestion",
            commit_analysis_id="ca-1",
        )
        insert_evaluation_cycle(temp_db, cycle)
        result = get_recent_cycles(temp_db, "proj-1")[0]
        d = result.to_dict()
        assert d["trigger_type"] == "suggestion"
        assert d["commit_analysis_id"] == "ca-1"


# =============================================================================
# Draft Pattern CRUD
# =============================================================================


class TestDraftPatternCRUD:
    def _make_project(self, conn):
        conn.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj-1", "test", "/tmp/test"),
        )
        conn.commit()

    def test_insert_and_get(self, temp_db):
        self._make_project(temp_db)
        pattern = DraftPattern(
            id="pat-1",
            project_id="proj-1",
            pattern_name="before-after",
            description="Show before/after comparison",
        )
        insert_draft_pattern(temp_db, pattern)
        results = get_patterns_by_project(temp_db, "proj-1")
        assert len(results) == 1
        assert results[0].pattern_name == "before-after"

    def test_round_trip(self, temp_db):
        self._make_project(temp_db)
        pattern = DraftPattern(
            id="pat-rt",
            project_id="proj-1",
            pattern_name="thread",
            example_draft_id="draft-123",
            created_by="system",
        )
        insert_draft_pattern(temp_db, pattern)
        result = get_patterns_by_project(temp_db, "proj-1")[0]
        d = result.to_dict()
        assert d["example_draft_id"] == "draft-123"
        assert d["created_by"] == "system"


# =============================================================================
# System Error CRUD
# =============================================================================


class TestSystemErrorCRUD:
    def test_insert_and_get(self, temp_db):
        error = SystemErrorRecord(
            id="err-1",
            severity="error",
            message="Something broke",
            context=json.dumps({"detail": "stack trace"}),
            source="scheduler",
        )
        insert_system_error(temp_db, error)
        results = get_recent_system_errors(temp_db)
        assert len(results) == 1
        assert results[0].message == "Something broke"
        assert results[0].source == "scheduler"

    def test_health_status(self, temp_db):
        entries = [
            ("err-info", "info"),
            ("err-warning", "warning"),
            ("err-error-1", "error"),
            ("err-error-2", "error"),
            ("err-critical", "critical"),
        ]
        for eid, sev in entries:
            insert_system_error(
                temp_db,
                SystemErrorRecord(id=eid, severity=sev, message=f"{sev} msg"),
            )
        status = get_error_health_status(temp_db)
        assert status["info"] == 1
        assert status["warning"] == 1
        assert status["error"] == 2
        assert status["critical"] == 1

    def test_severity_check_constraint(self, temp_db):
        with pytest.raises(sqlite3.IntegrityError):
            temp_db.execute(
                "INSERT INTO system_errors (id, severity, message) VALUES (?, ?, ?)",
                ("bad", "panic", "nope"),
            )

    def test_round_trip(self, temp_db):
        error = SystemErrorRecord(
            id="err-rt",
            severity="warning",
            message="Transient failure",
            context=json.dumps({"retry": True}),
            source="auth",
        )
        insert_system_error(temp_db, error)
        result = get_recent_system_errors(temp_db, limit=1)[0]
        d = result.to_dict()
        assert d["severity"] == "warning"
        assert json.loads(d["context"])["retry"] is True


# =============================================================================
# Draft & Post with New Fields
# =============================================================================


class TestDraftNewFields:
    def _seed(self, conn):
        conn.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj-1", "test", "/tmp/test"),
        )
        conn.execute(
            """INSERT INTO decisions (id, project_id, commit_hash, decision, reasoning)
               VALUES (?, ?, ?, ?, ?)""",
            ("dec-1", "proj-1", "abc123", "draft", "test"),
        )
        conn.commit()

    def test_insert_with_target_fields(self, temp_db):
        self._seed(temp_db)
        draft = Draft(
            id="draft-t1",
            project_id="proj-1",
            decision_id="dec-1",
            platform="x",
            content="Hello world",
            target_id="target-main",
            evaluation_cycle_id="cycle-1",
            topic_id="topic-1",
            suggestion_id="sug-1",
            pattern_id="pat-1",
        )
        insert_draft(temp_db, draft)
        row = temp_db.execute(
            "SELECT target_id, evaluation_cycle_id, topic_id, suggestion_id, pattern_id FROM drafts WHERE id = ?",
            ("draft-t1",),
        ).fetchone()
        assert row[0] == "target-main"
        assert row[1] == "cycle-1"
        assert row[2] == "topic-1"
        assert row[3] == "sug-1"
        assert row[4] == "pat-1"

    def test_insert_without_target_fields(self, temp_db):
        """Backward compat: drafts without target fields default to None."""
        self._seed(temp_db)
        draft = Draft(
            id="draft-nt",
            project_id="proj-1",
            decision_id="dec-1",
            platform="x",
            content="No targets",
        )
        insert_draft(temp_db, draft)
        from social_hook.db.operations import get_draft

        result = get_draft(temp_db, "draft-nt")
        assert result.target_id is None
        assert result.evaluation_cycle_id is None

    def test_from_dict_with_target_fields(self):
        d = {
            "id": "d1",
            "project_id": "p1",
            "decision_id": "dec1",
            "platform": "x",
            "content": "test",
            "target_id": "t1",
            "evaluation_cycle_id": "c1",
            "topic_id": "top1",
            "suggestion_id": "s1",
            "pattern_id": "pat1",
        }
        draft = Draft.from_dict(d)
        assert draft.target_id == "t1"
        assert draft.pattern_id == "pat1"


class TestPostNewFields:
    def _seed(self, conn):
        conn.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj-1", "test", "/tmp/test"),
        )
        conn.execute(
            """INSERT INTO decisions (id, project_id, commit_hash, decision, reasoning)
               VALUES (?, ?, ?, ?, ?)""",
            ("dec-1", "proj-1", "abc123", "draft", "test"),
        )
        conn.execute(
            """INSERT INTO drafts (id, project_id, decision_id, platform, content)
               VALUES (?, ?, ?, ?, ?)""",
            ("draft-1", "proj-1", "dec-1", "x", "content"),
        )
        conn.commit()

    def test_insert_with_target_fields(self, temp_db):
        self._seed(temp_db)
        post = Post(
            id="post-t1",
            draft_id="draft-1",
            project_id="proj-1",
            platform="x",
            content="Hello",
            target_id="target-main",
            topic_tags=["testing", "ci"],
            feature_tags=["auto-test"],
            is_thread_head=True,
        )
        insert_post(temp_db, post)
        row = temp_db.execute(
            "SELECT target_id, topic_tags, feature_tags, is_thread_head FROM posts WHERE id = ?",
            ("post-t1",),
        ).fetchone()
        assert row[0] == "target-main"
        assert json.loads(row[1]) == ["testing", "ci"]
        assert json.loads(row[2]) == ["auto-test"]
        assert row[3] == 1

    def test_post_from_dict_json_tags(self):
        d = {
            "id": "p1",
            "draft_id": "d1",
            "project_id": "proj1",
            "platform": "x",
            "content": "test",
            "topic_tags": '["a","b"]',
            "feature_tags": '["c"]',
            "is_thread_head": 1,
        }
        post = Post.from_dict(d)
        assert post.topic_tags == ["a", "b"]
        assert post.feature_tags == ["c"]
        assert post.is_thread_head is True

    def test_backward_compat_no_target_fields(self, temp_db):
        """Posts without target fields still work."""
        self._seed(temp_db)
        post = Post(
            id="post-nt",
            draft_id="draft-1",
            project_id="proj-1",
            platform="x",
            content="No targets",
        )
        insert_post(temp_db, post)
        from social_hook.db.operations import get_recent_posts

        results = get_recent_posts(temp_db, "proj-1")
        assert len(results) == 1
        assert results[0].target_id is None
        assert results[0].topic_tags == []


# =============================================================================
# Status Constants
# =============================================================================


class TestStatusConstants:
    def test_topic_statuses(self):
        assert "uncovered" in TOPIC_STATUSES
        assert "holding" in TOPIC_STATUSES
        assert "partial" in TOPIC_STATUSES
        assert "covered" in TOPIC_STATUSES
        assert len(TOPIC_STATUSES) == 4

    def test_suggestion_statuses(self):
        assert "pending" in SUGGESTION_STATUSES
        assert "evaluated" in SUGGESTION_STATUSES
        assert "drafted" in SUGGESTION_STATUSES
        assert "dismissed" in SUGGESTION_STATUSES
        assert len(SUGGESTION_STATUSES) == 4
