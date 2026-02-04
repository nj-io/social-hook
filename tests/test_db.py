"""Tests for database functionality (T1, T8, T10)."""

import sqlite3
import threading
from pathlib import Path

import pytest

from social_hook.db import (
    get_connection,
    get_schema_version,
    init_database,
    create_schema,
    get_active_arcs,
    get_all_pending_drafts,
    get_draft,
    get_draft_changes,
    get_draft_tweets,
    get_lifecycle,
    get_narrative_debt,
    get_pending_drafts,
    get_project,
    get_recent_decisions,
    get_recent_posts,
    get_usage_summary,
    increment_narrative_debt,
    insert_arc,
    insert_decision,
    insert_draft,
    insert_draft_change,
    insert_draft_tweet,
    insert_lifecycle,
    insert_narrative_debt,
    insert_post,
    insert_project,
    insert_usage,
    reset_narrative_debt,
    supersede_draft,
    update_arc,
    update_draft,
    update_lifecycle,
)
from social_hook.filesystem import generate_id
from social_hook.models import (
    Arc,
    Decision,
    Draft,
    DraftChange,
    DraftTweet,
    Lifecycle,
    NarrativeDebt,
    Post,
    Project,
    UsageLog,
)


# =============================================================================
# T1: Database Initialization
# =============================================================================


class TestDatabaseInitialization:
    """T1: Database initialization tests."""

    def test_initialize_fresh_database(self, temp_dir):
        """Initialize fresh database creates file at path."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)
        assert db_path.exists()
        conn.close()

    def test_wal_mode_enabled(self, temp_db):
        """WAL mode is enabled."""
        result = temp_db.execute("PRAGMA journal_mode").fetchone()
        assert result[0].lower() == "wal"

    def test_foreign_keys_enabled(self, temp_db):
        """Foreign keys are enabled."""
        result = temp_db.execute("PRAGMA foreign_keys").fetchone()
        assert result[0] == 1

    def test_all_tables_exist(self, temp_db):
        """Verify all 11 tables exist."""
        tables = temp_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        table_names = {row[0] for row in tables}

        expected_tables = {
            "projects",
            "decisions",
            "drafts",
            "draft_tweets",
            "draft_changes",
            "posts",
            "lifecycles",
            "arcs",
            "narrative_debt",
            "usage_log",
            "schema_version",
        }

        assert table_names == expected_tables

    def test_foreign_key_enforcement(self, temp_db):
        """Insert draft with invalid project_id raises IntegrityError."""
        with pytest.raises(sqlite3.IntegrityError):
            temp_db.execute(
                "INSERT INTO drafts (id, project_id, decision_id, platform, content) VALUES (?, ?, ?, ?, ?)",
                ("draft-1", "nonexistent-project", "decision-1", "x", "content"),
            )

    def test_schema_version(self, temp_db):
        """Check schema version returns 1."""
        version = get_schema_version(temp_db)
        assert version == 1

    def test_init_twice_idempotent(self, temp_dir):
        """Running init twice is idempotent."""
        db_path = temp_dir / "test.db"
        conn1 = init_database(db_path)
        version1 = get_schema_version(conn1)
        conn1.close()

        conn2 = init_database(db_path)
        version2 = get_schema_version(conn2)
        conn2.close()

        assert version1 == version2 == 1


# =============================================================================
# T8: Concurrent Access
# =============================================================================


class TestConcurrentAccess:
    """T8: Concurrent access tests."""

    def test_concurrent_writes(self, temp_dir):
        """Two parallel insert_project calls both succeed."""
        db_path = temp_dir / "test.db"
        init_database(db_path)

        results = []
        errors = []

        def insert_project_thread(project_id):
            try:
                conn = get_connection(db_path)
                project = Project(
                    id=project_id,
                    name=f"project-{project_id}",
                    repo_path=f"/tmp/{project_id}",
                )
                insert_project(conn, project)
                conn.close()
                results.append(True)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=insert_project_thread, args=("project-1",))
        t2 = threading.Thread(target=insert_project_thread, args=("project-2",))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(results) == 2
        assert len(errors) == 0

    def test_concurrent_read_during_write(self, temp_dir):
        """Read while write in progress succeeds."""
        db_path = temp_dir / "test.db"
        conn = init_database(db_path)

        # Insert a project
        project = Project(
            id="project-1",
            name="test-project",
            repo_path="/tmp/test",
        )
        insert_project(conn, project)
        conn.close()

        read_results = []
        write_done = threading.Event()

        def write_thread():
            conn = get_connection(db_path)
            for i in range(10):
                p = Project(
                    id=f"project-write-{i}",
                    name=f"write-{i}",
                    repo_path=f"/tmp/write-{i}",
                )
                insert_project(conn, p)
            write_done.set()
            conn.close()

        def read_thread():
            conn = get_connection(db_path)
            result = get_project(conn, "project-1")
            read_results.append(result)
            conn.close()

        t1 = threading.Thread(target=write_thread)
        t2 = threading.Thread(target=read_thread)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(read_results) == 1
        assert read_results[0].name == "test-project"


# =============================================================================
# T10: Database Operations (CRUD)
# =============================================================================


class TestDatabaseOperations:
    """T10: CRUD operations tests."""

    def test_insert_and_get_project(self, temp_db):
        """Insert project, get project returns correct data."""
        project = Project(
            id=generate_id("project"),
            name="test-project",
            repo_path="/tmp/test",
            repo_origin="git@github.com:test/repo.git",
        )
        insert_project(temp_db, project)

        loaded = get_project(temp_db, project.id)
        assert loaded is not None
        assert loaded.name == "test-project"
        assert loaded.repo_path == "/tmp/test"
        assert loaded.repo_origin == "git@github.com:test/repo.git"

    def test_get_nonexistent_project(self, temp_db):
        """Get nonexistent project returns None."""
        result = get_project(temp_db, "nonexistent")
        assert result is None

    def test_insert_decision_with_fk(self, temp_db):
        """Insert decision with FK to project succeeds."""
        project = Project(
            id=generate_id("project"),
            name="test-project",
            repo_path="/tmp/test",
        )
        insert_project(temp_db, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc123",
            decision="post_worthy",
            reasoning="Test decision",
        )
        insert_decision(temp_db, decision)

        decisions = get_recent_decisions(temp_db, project.id)
        assert len(decisions) == 1
        assert decisions[0].decision == "post_worthy"

    def test_insert_draft_with_fk(self, temp_db):
        """Insert draft with FK to decision succeeds."""
        project = Project(
            id=generate_id("project"),
            name="test-project",
            repo_path="/tmp/test",
        )
        insert_project(temp_db, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc123",
            decision="post_worthy",
            reasoning="Test decision",
        )
        insert_decision(temp_db, decision)

        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Test content",
        )
        insert_draft(temp_db, draft)

        loaded = get_draft(temp_db, draft.id)
        assert loaded is not None
        assert loaded.content == "Test content"

    def test_update_draft_status(self, temp_db):
        """Update draft status changes status and updated_at."""
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp")
        insert_project(temp_db, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc",
            decision="post_worthy",
            reasoning="test",
        )
        insert_decision(temp_db, decision)

        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="test",
        )
        insert_draft(temp_db, draft)

        # Update status
        result = update_draft(temp_db, draft.id, status="approved")
        assert result is True

        loaded = get_draft(temp_db, draft.id)
        assert loaded.status == "approved"

    def test_supersede_draft(self, temp_db):
        """Supersede draft marks old draft superseded."""
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp")
        insert_project(temp_db, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc",
            decision="post_worthy",
            reasoning="test",
        )
        insert_decision(temp_db, decision)

        old_draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="old content",
        )
        insert_draft(temp_db, old_draft)

        new_draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="new content",
        )
        insert_draft(temp_db, new_draft)

        # Supersede
        result = supersede_draft(temp_db, old_draft.id, new_draft.id)
        assert result is True

        loaded = get_draft(temp_db, old_draft.id)
        assert loaded.status == "superseded"
        assert loaded.superseded_by == new_draft.id

    def test_get_pending_drafts(self, temp_db):
        """Get pending drafts returns draft, approved, scheduled only."""
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp")
        insert_project(temp_db, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc",
            decision="post_worthy",
            reasoning="test",
        )
        insert_decision(temp_db, decision)

        # Create drafts with different statuses
        statuses = ["draft", "approved", "scheduled", "posted", "rejected"]
        for status in statuses:
            draft = Draft(
                id=generate_id("draft"),
                project_id=project.id,
                decision_id=decision.id,
                platform="x",
                content=f"content-{status}",
                status=status,
            )
            insert_draft(temp_db, draft)

        pending = get_pending_drafts(temp_db, project.id)
        assert len(pending) == 3
        pending_statuses = {d.status for d in pending}
        assert pending_statuses == {"draft", "approved", "scheduled"}

    def test_insert_and_get_recent_posts(self, temp_db):
        """Insert post, get recent posts returns within date range."""
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp")
        insert_project(temp_db, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc",
            decision="post_worthy",
            reasoning="test",
        )
        insert_decision(temp_db, decision)

        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="test",
        )
        insert_draft(temp_db, draft)

        post = Post(
            id=generate_id("post"),
            draft_id=draft.id,
            project_id=project.id,
            platform="x",
            content="posted content",
            external_id="12345",
        )
        insert_post(temp_db, post)

        posts = get_recent_posts(temp_db, project.id, days=7)
        assert len(posts) == 1
        assert posts[0].content == "posted content"

    def test_insert_and_get_usage(self, temp_db):
        """Insert usage log, get usage summary works."""
        usage = UsageLog(
            id=generate_id("usage"),
            operation_type="evaluation",
            model="opus",
            input_tokens=1000,
            output_tokens=500,
            cost_cents=0.5,
        )
        insert_usage(temp_db, usage)

        summary = get_usage_summary(temp_db, days=30)
        assert len(summary) == 1
        assert summary[0]["model"] == "opus"
        assert summary[0]["total_input"] == 1000

    def test_narrative_debt_operations(self, temp_db):
        """Narrative debt increment and reset work correctly."""
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp")
        insert_project(temp_db, project)

        # Increment
        count = increment_narrative_debt(temp_db, project.id)
        assert count == 1

        count = increment_narrative_debt(temp_db, project.id)
        assert count == 2

        # Get
        debt = get_narrative_debt(temp_db, project.id)
        assert debt.debt_counter == 2

        # Reset
        result = reset_narrative_debt(temp_db, project.id)
        assert result is True

        debt = get_narrative_debt(temp_db, project.id)
        assert debt.debt_counter == 0

    def test_arc_operations(self, temp_db):
        """Arc insert, update, and get active arcs work."""
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp")
        insert_project(temp_db, project)

        arc = Arc(
            id=generate_id("arc"),
            project_id=project.id,
            theme="Building the content brain",
        )
        insert_arc(temp_db, arc)

        # Get active arcs
        arcs = get_active_arcs(temp_db, project.id)
        assert len(arcs) == 1
        assert arcs[0].theme == "Building the content brain"

        # Update arc
        update_arc(temp_db, arc.id, status="completed")
        arcs = get_active_arcs(temp_db, project.id)
        assert len(arcs) == 0  # No longer active

    def test_lifecycle_operations(self, temp_db):
        """Lifecycle insert, get, and update work."""
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp")
        insert_project(temp_db, project)

        lifecycle = Lifecycle(
            project_id=project.id,
            phase="research",
            confidence=0.5,
        )
        insert_lifecycle(temp_db, lifecycle)

        loaded = get_lifecycle(temp_db, project.id)
        assert loaded.phase == "research"

        # Update
        update_lifecycle(temp_db, project.id, phase="build", confidence=0.75)
        loaded = get_lifecycle(temp_db, project.id)
        assert loaded.phase == "build"
        assert loaded.confidence == 0.75

    def test_draft_tweets_operations(self, temp_db):
        """Draft tweets insert and get work for threads."""
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp")
        insert_project(temp_db, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc",
            decision="post_worthy",
            reasoning="test",
        )
        insert_decision(temp_db, decision)

        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="thread content",
        )
        insert_draft(temp_db, draft)

        # Insert tweets
        for i in range(3):
            tweet = DraftTweet(
                id=generate_id("tweet"),
                draft_id=draft.id,
                position=i + 1,
                content=f"Tweet {i + 1}",
            )
            insert_draft_tweet(temp_db, tweet)

        tweets = get_draft_tweets(temp_db, draft.id)
        assert len(tweets) == 3
        assert tweets[0].position == 1
        assert tweets[1].position == 2
        assert tweets[2].position == 3

    def test_draft_changes_audit(self, temp_db):
        """Draft changes audit trail works."""
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp")
        insert_project(temp_db, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc",
            decision="post_worthy",
            reasoning="test",
        )
        insert_decision(temp_db, decision)

        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="original",
        )
        insert_draft(temp_db, draft)

        # Record change
        change = DraftChange(
            id=generate_id("change"),
            draft_id=draft.id,
            field="content",
            old_value="original",
            new_value="updated",
            changed_by="human",
        )
        insert_draft_change(temp_db, change)

        changes = get_draft_changes(temp_db, draft.id)
        assert len(changes) == 1
        assert changes[0].field == "content"
        assert changes[0].changed_by == "human"
