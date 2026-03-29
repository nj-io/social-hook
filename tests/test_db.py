"""Tests for database functionality (T1, T8, T10)."""

import sqlite3
import threading

import pytest

from social_hook.db import (
    delete_project,
    execute_queue_action,
    get_active_arcs,
    get_all_recent_decisions,
    get_all_recent_posts,
    get_arc_posts,
    get_connection,
    get_deferred_drafts,
    get_deferred_eval_decisions,
    get_distinct_branches,
    get_draft,
    get_draft_changes,
    get_draft_tweets,
    get_due_drafts,
    get_last_auto_evaluation_time,
    get_lifecycle,
    get_milestone_summaries,
    get_narrative_debt,
    get_pending_drafts,
    get_posts_by_ids,
    get_project,
    get_project_by_origin,
    get_project_by_path,
    get_project_summary,
    get_recent_decisions,
    get_recent_decisions_for_llm,
    get_recent_posts,
    get_recent_posts_for_context,
    get_schema_version,
    get_summary_freshness,
    get_today_auto_evaluation_count,
    get_usage_summary,
    increment_narrative_debt,
    init_database,
    insert_arc,
    insert_decision,
    insert_decisions_batch,
    insert_draft,
    insert_draft_change,
    insert_draft_tweet,
    insert_lifecycle,
    insert_milestone_summary,
    insert_narrative_debt,
    insert_post,
    insert_project,
    insert_usage,
    reset_narrative_debt,
    set_project_trigger_branch,
    supersede_draft,
    update_arc,
    update_draft,
    update_lifecycle,
    update_project_summary,
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
        """Verify all 23 tables exist."""
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
            "milestone_summaries",
            "web_events",
            "chat_messages",
            "background_tasks",
            "file_summaries",
            "platform_introduced",
            "oauth_tokens",
            "content_topics",
            "content_suggestions",
            "evaluation_cycles",
            "draft_patterns",
            "system_errors",
            "topic_commits",
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
        """Check schema version is a timestamp (>= 20260209131940)."""
        version = get_schema_version(temp_db)
        assert version >= 20260209131940

    def test_init_twice_idempotent(self, temp_dir):
        """Running init twice is idempotent.

        Note: version checked is the max after both inits. When SCHEMA_VERSION
        is lower than available migrations, the second init may apply them.
        The key invariant is that a third init should not change anything.
        """
        db_path = temp_dir / "test.db"
        conn1 = init_database(db_path)
        conn1.close()

        conn2 = init_database(db_path)
        version2 = get_schema_version(conn2)
        conn2.close()

        conn3 = init_database(db_path)
        version3 = get_schema_version(conn3)
        conn3.close()

        assert version3 == version2


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
            decision="draft",
            reasoning="Test decision",
        )
        insert_decision(temp_db, decision)

        decisions = get_recent_decisions(temp_db, project.id)
        assert len(decisions) == 1
        assert decisions[0].decision == "draft"

    def test_commit_message_round_trip(self, temp_db):
        """commit_message persists through insert → get."""
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
            decision="draft",
            reasoning="Test decision",
            commit_message="Add user authentication module",
        )
        insert_decision(temp_db, decision)

        decisions = get_recent_decisions(temp_db, project.id)
        assert len(decisions) == 1
        assert decisions[0].commit_message == "Add user authentication module"

    def test_commit_message_null_for_legacy(self, temp_db):
        """commit_message defaults to None when not provided."""
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
            decision="draft",
            reasoning="Test decision",
        )
        insert_decision(temp_db, decision)

        decisions = get_recent_decisions(temp_db, project.id)
        assert len(decisions) == 1
        assert decisions[0].commit_message is None

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
            decision="draft",
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
            decision="draft",
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
            decision="draft",
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
            decision="draft",
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
            decision="draft",
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

    def test_get_recent_posts_for_context(self, temp_db):
        """get_recent_posts_for_context returns last N posts for LLM context."""
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp")
        insert_project(temp_db, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc",
            decision="draft",
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

        # Test count-based retrieval
        posts = get_recent_posts_for_context(temp_db, project.id, limit=15)
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
            decision="draft",
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
            decision="draft",
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


# =============================================================================
# T10a: Project Summary Operations
# =============================================================================


class TestProjectSummary:
    """Tests for project summary operations."""

    def test_update_and_get_project_summary(self, temp_db):
        """update_project_summary and get_project_summary work correctly."""
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp")
        insert_project(temp_db, project)

        # Initially no summary
        assert get_project_summary(temp_db, project.id) is None

        # Update summary
        summary_text = "# Project: Test\n\nA test project for unit tests."
        result = update_project_summary(temp_db, project.id, summary_text)
        assert result is True

        # Get summary
        retrieved = get_project_summary(temp_db, project.id)
        assert retrieved == summary_text

    def test_get_summary_freshness(self, temp_db):
        """get_summary_freshness returns correct indicators."""
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp")
        insert_project(temp_db, project)

        # Initially no summary
        freshness = get_summary_freshness(temp_db, project.id)
        assert freshness["summary_updated_at"] is None
        assert freshness["commits_since_summary"] == 0
        assert freshness["days_since_summary"] is None

        # Update summary
        update_project_summary(temp_db, project.id, "Test summary")

        # Add a decision after summary
        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc",
            decision="draft",
            reasoning="test",
        )
        insert_decision(temp_db, decision)

        # Check freshness
        freshness = get_summary_freshness(temp_db, project.id)
        assert freshness["summary_updated_at"] is not None
        assert freshness["commits_since_summary"] == 1
        assert freshness["days_since_summary"] == 0  # Same day


# =============================================================================
# T10a2: Arc Posts Query
# =============================================================================


class TestArcPosts:
    """Tests for arc posts query."""

    def test_get_arc_posts(self, temp_db):
        """get_arc_posts returns posts linked to an arc via decisions."""
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp")
        insert_project(temp_db, project)

        arc = Arc(id=generate_id("arc"), project_id=project.id, theme="Test arc")
        insert_arc(temp_db, arc)

        # Create decision linked to arc
        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc",
            decision="draft",
            reasoning="test",
            post_category="arc",
            arc_id=arc.id,
        )
        insert_decision(temp_db, decision)

        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="arc post content",
        )
        insert_draft(temp_db, draft)

        post = Post(
            id=generate_id("post"),
            draft_id=draft.id,
            project_id=project.id,
            platform="x",
            content="arc post content",
            external_id="12345",
        )
        insert_post(temp_db, post)

        # Get arc posts
        posts = get_arc_posts(temp_db, arc.id)
        assert len(posts) == 1
        assert posts[0].content == "arc post content"

    def test_get_arc_posts_empty(self, temp_db):
        """get_arc_posts returns empty list for nonexistent arc."""
        posts = get_arc_posts(temp_db, "nonexistent")
        assert posts == []


# =============================================================================
# T10b: Milestone Summary Operations
# =============================================================================


class TestMilestoneSummaries:
    """Tests for milestone summary operations."""

    def test_insert_and_get_milestone_summary(self, temp_db):
        """insert_milestone_summary and get_milestone_summaries work correctly."""
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp")
        insert_project(temp_db, project)

        summary = {
            "id": generate_id("summary"),
            "project_id": project.id,
            "milestone_type": "post",
            "summary": "Published post about feature X",
            "items_covered": ["decision_1", "decision_2"],
            "token_count": 150,
            "period_start": "2026-01-01",
            "period_end": "2026-01-15",
        }
        result = insert_milestone_summary(temp_db, summary)
        assert result == summary["id"]

        # Retrieve
        summaries = get_milestone_summaries(temp_db, project.id)
        assert len(summaries) == 1
        assert summaries[0]["milestone_type"] == "post"
        assert summaries[0]["summary"] == "Published post about feature X"

    def test_milestone_type_constraint(self, temp_db):
        """Invalid milestone_type raises IntegrityError."""
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp")
        insert_project(temp_db, project)

        summary = {
            "id": generate_id("summary"),
            "project_id": project.id,
            "milestone_type": "invalid",  # Not in CHECK constraint
            "summary": "Test",
            "items_covered": [],
            "token_count": 0,
            "period_start": "2026-01-01",
            "period_end": "2026-01-15",
        }
        with pytest.raises(sqlite3.IntegrityError):
            insert_milestone_summary(temp_db, summary)


# =============================================================================
# WS4 Phase 0: New DB Operations
# =============================================================================


class TestProjectByPath:
    """Tests for get_project_by_path."""

    def test_find_by_path(self, temp_db):
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp/my-repo")
        insert_project(temp_db, project)

        found = get_project_by_path(temp_db, "/tmp/my-repo")
        assert found is not None
        assert found.id == project.id

    def test_not_found_by_path(self, temp_db):
        assert get_project_by_path(temp_db, "/nonexistent") is None


class TestProjectByOrigin:
    """Tests for get_project_by_origin."""

    def test_find_by_origin(self, temp_db):
        project = Project(
            id=generate_id("project"),
            name="test",
            repo_path="/tmp/test",
            repo_origin="git@github.com:user/repo.git",
        )
        insert_project(temp_db, project)

        found = get_project_by_origin(temp_db, "git@github.com:user/repo.git")
        assert len(found) == 1
        assert found[0].id == project.id

    def test_multiple_worktrees_same_origin(self, temp_db):
        for i in range(2):
            p = Project(
                id=generate_id("project"),
                name=f"wt-{i}",
                repo_path=f"/tmp/wt-{i}",
                repo_origin="git@github.com:user/repo.git",
            )
            insert_project(temp_db, p)

        found = get_project_by_origin(temp_db, "git@github.com:user/repo.git")
        assert len(found) == 2

    def test_not_found_by_origin(self, temp_db):
        assert get_project_by_origin(temp_db, "nonexistent") == []


class TestDeleteProject:
    """Tests for delete_project (cascading delete)."""

    def test_delete_project_with_all_data(self, temp_db):
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp")
        insert_project(temp_db, project)

        # Create related data
        insert_lifecycle(temp_db, Lifecycle(project_id=project.id))
        insert_narrative_debt(temp_db, NarrativeDebt(project_id=project.id))

        arc = Arc(id=generate_id("arc"), project_id=project.id, theme="test")
        insert_arc(temp_db, arc)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc",
            decision="draft",
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

        tweet = DraftTweet(id=generate_id("tweet"), draft_id=draft.id, position=1, content="t1")
        insert_draft_tweet(temp_db, tweet)

        change = DraftChange(
            id=generate_id("change"),
            draft_id=draft.id,
            field="content",
            old_value="old",
            new_value="new",
            changed_by="human",
        )
        insert_draft_change(temp_db, change)

        post = Post(
            id=generate_id("post"),
            draft_id=draft.id,
            project_id=project.id,
            platform="x",
            content="posted",
        )
        insert_post(temp_db, post)

        # Delete project
        result = delete_project(temp_db, project.id)
        assert result is True

        # Verify everything is gone
        assert get_project(temp_db, project.id) is None
        assert get_lifecycle(temp_db, project.id) is None
        assert get_narrative_debt(temp_db, project.id) is None
        assert get_active_arcs(temp_db, project.id) == []
        assert get_recent_decisions(temp_db, project.id) == []
        assert get_pending_drafts(temp_db, project.id) == []

    def test_delete_nonexistent_project(self, temp_db):
        assert delete_project(temp_db, "nonexistent") is False


class TestGetDueDrafts:
    """Tests for get_due_drafts."""

    def test_returns_scheduled_due_drafts(self, temp_db):
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp")
        insert_project(temp_db, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc",
            decision="draft",
            reasoning="test",
        )
        insert_decision(temp_db, decision)

        # Create a scheduled draft with past time
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="due draft",
            status="scheduled",
        )
        insert_draft(temp_db, draft)
        # Set scheduled_time to the past
        temp_db.execute(
            "UPDATE drafts SET scheduled_time = datetime('now', '-1 hour') WHERE id = ?",
            (draft.id,),
        )
        temp_db.commit()

        due = get_due_drafts(temp_db)
        assert len(due) == 1
        assert due[0].id == draft.id

    def test_ignores_future_scheduled_drafts(self, temp_db):
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp")
        insert_project(temp_db, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc",
            decision="draft",
            reasoning="test",
        )
        insert_decision(temp_db, decision)

        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="future draft",
            status="scheduled",
        )
        insert_draft(temp_db, draft)
        temp_db.execute(
            "UPDATE drafts SET scheduled_time = datetime('now', '+1 hour') WHERE id = ?",
            (draft.id,),
        )
        temp_db.commit()

        due = get_due_drafts(temp_db)
        assert len(due) == 0

    def test_ignores_non_scheduled_drafts(self, temp_db):
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp")
        insert_project(temp_db, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc",
            decision="draft",
            reasoning="test",
        )
        insert_decision(temp_db, decision)

        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="approved draft",
            status="approved",
        )
        insert_draft(temp_db, draft)

        due = get_due_drafts(temp_db)
        assert len(due) == 0


class TestGetAllRecentDecisions:
    """Tests for get_all_recent_decisions."""

    def test_cross_project_decisions(self, temp_db):
        # Create two projects
        for i in range(2):
            p = Project(id=generate_id("project"), name=f"p{i}", repo_path=f"/tmp/{i}")
            insert_project(temp_db, p)
            d = Decision(
                id=generate_id("decision"),
                project_id=p.id,
                commit_hash=f"hash{i}",
                decision="draft",
                reasoning=f"test {i}",
            )
            insert_decision(temp_db, d)

        decisions = get_all_recent_decisions(temp_db, limit=30)
        assert len(decisions) == 2

    def test_limit_respected(self, temp_db):
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp")
        insert_project(temp_db, project)

        for i in range(5):
            d = Decision(
                id=generate_id("decision"),
                project_id=project.id,
                commit_hash=f"hash{i}",
                decision="draft",
                reasoning=f"test {i}",
            )
            insert_decision(temp_db, d)

        decisions = get_all_recent_decisions(temp_db, limit=3)
        assert len(decisions) == 3


class TestGetAllRecentPosts:
    """Tests for get_all_recent_posts."""

    def test_cross_project_posts(self, temp_db):
        # Create two projects with posts
        for i in range(2):
            p = Project(id=generate_id("project"), name=f"p{i}", repo_path=f"/tmp/{i}")
            insert_project(temp_db, p)
            d = Decision(
                id=generate_id("decision"),
                project_id=p.id,
                commit_hash=f"hash{i}",
                decision="draft",
                reasoning=f"test {i}",
            )
            insert_decision(temp_db, d)
            dr = Draft(
                id=generate_id("draft"),
                project_id=p.id,
                decision_id=d.id,
                platform="x",
                content=f"content {i}",
            )
            insert_draft(temp_db, dr)
            post = Post(
                id=generate_id("post"),
                draft_id=dr.id,
                project_id=p.id,
                platform="x",
                content=f"posted {i}",
            )
            insert_post(temp_db, post)

        # Get all posts since yesterday
        posts = get_all_recent_posts(temp_db, "2020-01-01")
        assert len(posts) == 2

    def test_filters_by_datetime(self, temp_db):
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp")
        insert_project(temp_db, project)
        d = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="hash",
            decision="draft",
            reasoning="test",
        )
        insert_decision(temp_db, d)
        dr = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=d.id,
            platform="x",
            content="c",
        )
        insert_draft(temp_db, dr)
        post = Post(
            id=generate_id("post"),
            draft_id=dr.id,
            project_id=project.id,
            platform="x",
            content="posted",
        )
        insert_post(temp_db, post)

        # Query with a far-future datetime should return nothing
        posts = get_all_recent_posts(temp_db, "2099-01-01")
        assert len(posts) == 0


class TestProjectPausedField:
    """Tests for the paused field on Project model."""

    def test_default_not_paused(self, temp_db):
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp")
        insert_project(temp_db, project)
        loaded = get_project(temp_db, project.id)
        assert loaded.paused is False

    def test_insert_paused(self, temp_db):
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp", paused=True)
        insert_project(temp_db, project)
        loaded = get_project(temp_db, project.id)
        assert loaded.paused is True

    def test_paused_to_dict(self):
        project = Project(id="p1", name="test", repo_path="/tmp", paused=True)
        d = project.to_dict()
        assert d["paused"] is True

    def test_paused_from_dict(self):
        d = {"id": "p1", "name": "test", "repo_path": "/tmp", "paused": 1}
        project = Project.from_dict(d)
        assert project.paused is True


# =============================================================================
# Media Fields Tests
# =============================================================================


class TestDraftMediaFields:
    """Tests for media_type, media_spec, and media_paths update_draft support."""

    def _create_draft(self, temp_db):
        """Helper to create a project + decision + draft for media tests."""
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp")
        insert_project(temp_db, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc",
            decision="draft",
            reasoning="test",
        )
        insert_decision(temp_db, decision)

        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="test content",
        )
        insert_draft(temp_db, draft)
        return draft

    def test_update_draft_media_paths(self, temp_db):
        """update_draft with media_paths persists and round-trips."""
        draft = self._create_draft(temp_db)

        paths = ["/tmp/img1.png", "/tmp/img2.jpg"]
        result = update_draft(temp_db, draft.id, media_paths=paths)
        assert result is True

        loaded = get_draft(temp_db, draft.id)
        assert loaded.media_paths == paths

    def test_update_draft_media_type_and_spec(self, temp_db):
        """media_type and media_spec persist via update_draft."""
        draft = self._create_draft(temp_db)

        spec = {"prompt": "A diagram of the architecture", "style": "technical"}
        result = update_draft(
            temp_db,
            draft.id,
            media_type="image",
            media_spec=spec,
        )
        assert result is True

        loaded = get_draft(temp_db, draft.id)
        assert loaded.media_type == "image"
        assert loaded.media_spec == spec

    def test_draft_serialization_with_media_fields(self, temp_db):
        """Draft.to_row()/from_dict() round-trip with media fields."""
        draft = Draft(
            id="draft-media-test",
            project_id="proj-1",
            decision_id="dec-1",
            platform="x",
            content="media test",
            media_paths=["/tmp/pic.png"],
            media_type="image",
            media_spec={"prompt": "test prompt", "width": 1024},
        )

        # Verify to_row returns exactly 25 elements
        row = draft.to_row()
        assert len(row) == 25

        # Verify round-trip via to_dict/from_dict
        d = draft.to_dict()
        assert d["media_type"] == "image"
        assert d["media_spec"] == {"prompt": "test prompt", "width": 1024}

        restored = Draft.from_dict(d)
        assert restored.media_type == "image"
        assert restored.media_spec == {"prompt": "test prompt", "width": 1024}
        assert restored.media_paths == ["/tmp/pic.png"]

    def test_draft_from_dict_media_spec_string(self):
        """from_dict handles media_spec as a JSON string (from DB row)."""
        d = {
            "id": "d1",
            "project_id": "p1",
            "decision_id": "dec1",
            "platform": "x",
            "content": "test",
            "media_spec": '{"prompt": "hello"}',
            "media_type": "image",
        }
        draft = Draft.from_dict(d)
        assert draft.media_spec == {"prompt": "hello"}
        assert draft.media_type == "image"

    def test_draft_defaults_media_fields_none(self, temp_db):
        """Drafts without media fields default to None."""
        draft = self._create_draft(temp_db)
        loaded = get_draft(temp_db, draft.id)
        assert loaded.media_type is None
        assert loaded.media_spec is None


class TestTriggerBranch:
    """Tests for trigger branch operations."""

    def test_set_and_get_trigger_branch(self, temp_db):
        """Set and retrieve trigger branch."""
        project = Project(
            id=generate_id("project"),
            name="Branch Test",
            repo_path="/tmp/branch-test",
        )
        insert_project(temp_db, project)

        # Default is None
        p = get_project(temp_db, project.id)
        assert p.trigger_branch is None

        # Set to "main"
        set_project_trigger_branch(temp_db, project.id, "main")
        p = get_project(temp_db, project.id)
        assert p.trigger_branch == "main"

        # Clear (set to None)
        set_project_trigger_branch(temp_db, project.id, None)
        p = get_project(temp_db, project.id)
        assert p.trigger_branch is None


class TestGetDeferredDrafts:
    """Tests for get_deferred_drafts."""

    def _create_draft(self, temp_db, project, decision, status="draft", content="test"):
        """Helper to create a draft with a given status."""
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content=content,
            status=status,
        )
        insert_draft(temp_db, draft)
        return draft

    def test_returns_only_deferred_drafts(self, temp_db):
        """get_deferred_drafts returns only drafts with status='deferred'."""
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp")
        insert_project(temp_db, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc",
            decision="draft",
            reasoning="test",
        )
        insert_decision(temp_db, decision)

        # Create drafts with various statuses
        self._create_draft(temp_db, project, decision, status="draft", content="draft one")
        deferred1 = self._create_draft(
            temp_db, project, decision, status="deferred", content="deferred one"
        )
        self._create_draft(temp_db, project, decision, status="approved", content="approved one")
        deferred2 = self._create_draft(
            temp_db, project, decision, status="deferred", content="deferred two"
        )
        self._create_draft(temp_db, project, decision, status="scheduled", content="scheduled one")

        results = get_deferred_drafts(temp_db)
        assert len(results) == 2
        result_ids = {r.id for r in results}
        assert deferred1.id in result_ids
        assert deferred2.id in result_ids

    def test_ordered_by_created_at_asc(self, temp_db):
        """Deferred drafts are returned in FIFO order (oldest first)."""
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp")
        insert_project(temp_db, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc",
            decision="draft",
            reasoning="test",
        )
        insert_decision(temp_db, decision)

        # Create three deferred drafts and set explicit timestamps
        d1 = self._create_draft(temp_db, project, decision, status="deferred", content="first")
        d2 = self._create_draft(temp_db, project, decision, status="deferred", content="second")
        d3 = self._create_draft(temp_db, project, decision, status="deferred", content="third")

        # Force specific ordering via created_at
        temp_db.execute(
            "UPDATE drafts SET created_at = datetime('now', '-3 hours') WHERE id = ?", (d1.id,)
        )
        temp_db.execute(
            "UPDATE drafts SET created_at = datetime('now', '-1 hour') WHERE id = ?", (d2.id,)
        )
        temp_db.execute("UPDATE drafts SET created_at = datetime('now') WHERE id = ?", (d3.id,))
        temp_db.commit()

        results = get_deferred_drafts(temp_db)
        assert len(results) == 3
        assert results[0].id == d1.id
        assert results[1].id == d2.id
        assert results[2].id == d3.id

    def test_returns_empty_when_no_deferred(self, temp_db):
        """get_deferred_drafts returns empty list when no deferred drafts exist."""
        project = Project(id=generate_id("project"), name="test", repo_path="/tmp")
        insert_project(temp_db, project)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc",
            decision="draft",
            reasoning="test",
        )
        insert_decision(temp_db, decision)

        self._create_draft(temp_db, project, decision, status="draft")
        self._create_draft(temp_db, project, decision, status="approved")

        results = get_deferred_drafts(temp_db)
        assert results == []


# =============================================================================
# Import / Branch operations
# =============================================================================


class TestImportOperations:
    """Tests for imported decision operations."""

    def _make_project(self, temp_db):
        project = Project(
            id=generate_id("project"),
            name="test-import",
            repo_path="/tmp/test",
        )
        insert_project(temp_db, project)
        return project

    def test_get_recent_decisions_for_llm_excludes_imported(self, temp_db):
        """get_recent_decisions_for_llm excludes imported decisions."""
        project = self._make_project(temp_db)

        # Insert a normal decision
        d1 = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc123",
            decision="draft",
            reasoning="Good commit",
            branch="main",
        )
        insert_decision(temp_db, d1)

        # Insert an imported decision
        d2 = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="def456",
            decision="imported",
            reasoning="Historical commit",
            branch="main",
        )
        insert_decision(temp_db, d2)

        # get_recent_decisions includes both
        all_decisions = get_recent_decisions(temp_db, project.id)
        assert len(all_decisions) == 2

        # get_recent_decisions_for_llm excludes imported
        llm_decisions = get_recent_decisions_for_llm(temp_db, project.id)
        assert len(llm_decisions) == 1
        assert llm_decisions[0].decision == "draft"

    def test_insert_decisions_batch_and_duplicates(self, temp_db):
        """insert_decisions_batch handles duplicates via INSERT OR IGNORE."""
        project = self._make_project(temp_db)

        # Insert a decision normally first
        d_existing = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc123",
            decision="draft",
            reasoning="Existing",
        )
        insert_decision(temp_db, d_existing)

        # Now batch insert, including a duplicate commit_hash
        batch = [
            (
                Decision(
                    id=generate_id("decision"),
                    project_id=project.id,
                    commit_hash="abc123",  # duplicate
                    decision="imported",
                    reasoning="Historical commit",
                ),
                "2024-01-01T00:00:00+00:00",
            ),
            (
                Decision(
                    id=generate_id("decision"),
                    project_id=project.id,
                    commit_hash="def456",  # new
                    decision="imported",
                    reasoning="Historical commit",
                ),
                "2024-01-02T00:00:00+00:00",
            ),
        ]

        inserted = insert_decisions_batch(temp_db, batch)
        assert inserted == 1  # only def456 inserted

        all_decisions = get_recent_decisions(temp_db, project.id)
        assert len(all_decisions) == 2

    def test_insert_decisions_batch_respects_created_at(self, temp_db):
        """Batch insert uses the provided created_at timestamp."""
        project = self._make_project(temp_db)

        batch = [
            (
                Decision(
                    id=generate_id("decision"),
                    project_id=project.id,
                    commit_hash="aaa111",
                    decision="imported",
                    reasoning="Historical commit",
                ),
                "2023-06-15T12:00:00+00:00",
            ),
        ]

        insert_decisions_batch(temp_db, batch)
        row = temp_db.execute(
            "SELECT created_at FROM decisions WHERE commit_hash = 'aaa111'"
        ).fetchone()
        assert row[0] == "2023-06-15T12:00:00+00:00"

    def test_get_distinct_branches(self, temp_db):
        """get_distinct_branches returns sorted unique non-null branches."""
        project = self._make_project(temp_db)

        for branch, commit_hash in [
            ("main", "a1"),
            ("develop", "a2"),
            ("main", "a3"),
            (None, "a4"),
        ]:
            d = Decision(
                id=generate_id("decision"),
                project_id=project.id,
                commit_hash=commit_hash,
                decision="imported",
                reasoning="Historical",
                branch=branch,
            )
            insert_decision(temp_db, d)

        branches = get_distinct_branches(temp_db, project.id)
        assert branches == ["develop", "main"]

    def test_insert_decisions_batch_empty(self, temp_db):
        """insert_decisions_batch with empty list returns 0."""
        assert insert_decisions_batch(temp_db, []) == 0


class TestDecisionReferencePosts:
    """Tests for reference_posts field on decisions."""

    def test_insert_decision_with_reference_posts(self, temp_db):
        """Decision with reference_posts persists through insert → get."""
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
            decision="draft",
            reasoning="References previous posts",
            reference_posts=["post_abc", "post_def"],
        )
        insert_decision(temp_db, decision)

        decisions = get_recent_decisions(temp_db, project.id)
        assert len(decisions) == 1
        assert decisions[0].reference_posts == ["post_abc", "post_def"]

    def test_insert_decision_without_reference_posts(self, temp_db):
        """Decision without reference_posts stores None."""
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
            decision="draft",
            reasoning="No references",
        )
        insert_decision(temp_db, decision)

        decisions = get_recent_decisions(temp_db, project.id)
        assert len(decisions) == 1
        assert decisions[0].reference_posts is None


class TestGetPostsByIds:
    """Tests for get_posts_by_ids helper."""

    def test_get_posts_by_ids_empty(self, temp_db):
        """get_posts_by_ids with empty list returns empty list."""
        assert get_posts_by_ids(temp_db, []) == []

    def test_get_posts_by_ids_found(self, temp_db):
        """get_posts_by_ids returns matching posts."""
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
            decision="draft",
            reasoning="Test",
        )
        insert_decision(temp_db, decision)

        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Test post",
        )
        insert_draft(temp_db, draft)

        post1 = Post(
            id="post_aaa",
            draft_id=draft.id,
            project_id=project.id,
            platform="x",
            content="First post",
        )
        post2 = Post(
            id="post_bbb",
            draft_id=draft.id,
            project_id=project.id,
            platform="x",
            content="Second post",
        )
        insert_post(temp_db, post1)
        insert_post(temp_db, post2)

        results = get_posts_by_ids(temp_db, ["post_aaa", "post_bbb"])
        assert len(results) == 2
        ids = {p.id for p in results}
        assert ids == {"post_aaa", "post_bbb"}

    def test_get_posts_by_ids_partial_match(self, temp_db):
        """get_posts_by_ids returns only existing posts."""
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
            decision="draft",
            reasoning="Test",
        )
        insert_decision(temp_db, decision)

        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="Test post",
        )
        insert_draft(temp_db, draft)

        post = Post(
            id="post_ccc",
            draft_id=draft.id,
            project_id=project.id,
            platform="x",
            content="Only post",
        )
        insert_post(temp_db, post)

        results = get_posts_by_ids(temp_db, ["post_ccc", "post_nonexistent"])
        assert len(results) == 1
        assert results[0].id == "post_ccc"


class TestRateLimitsOperations:
    """Tests for rate limiting DB operations."""

    def _make_project(self, temp_db):
        project = Project(
            id=generate_id("project"),
            name="test-rate-limits",
            repo_path="/tmp/test",
        )
        insert_project(temp_db, project)
        return project

    def test_insert_decision_deferred_eval(self, temp_db):
        """Insert decision with deferred_eval type succeeds."""
        project = self._make_project(temp_db)
        d = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc123",
            decision="deferred_eval",
            reasoning="Rate limited",
            trigger_source="auto",
        )
        insert_decision(temp_db, d)

        decisions = get_recent_decisions(temp_db, project.id)
        assert len(decisions) == 1
        assert decisions[0].decision == "deferred_eval"
        assert decisions[0].trigger_source == "auto"

    def test_get_recent_decisions_for_llm_excludes_deferred(self, temp_db):
        """get_recent_decisions_for_llm excludes deferred_eval decisions."""
        project = self._make_project(temp_db)

        d1 = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc123",
            decision="draft",
            reasoning="Good commit",
        )
        insert_decision(temp_db, d1)

        d2 = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="def456",
            decision="deferred_eval",
            reasoning="Rate limited",
        )
        insert_decision(temp_db, d2)

        llm_decisions = get_recent_decisions_for_llm(temp_db, project.id)
        assert len(llm_decisions) == 1
        assert llm_decisions[0].decision == "draft"

    def test_get_deferred_eval_decisions(self, temp_db):
        """get_deferred_eval_decisions returns only unprocessed deferred_eval."""
        project = self._make_project(temp_db)

        # Unprocessed deferred_eval
        d1 = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc123",
            decision="deferred_eval",
            reasoning="Rate limited",
        )
        insert_decision(temp_db, d1)

        # Processed deferred_eval (mark it processed)
        d2 = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="def456",
            decision="deferred_eval",
            reasoning="Rate limited",
        )
        insert_decision(temp_db, d2)
        temp_db.execute("UPDATE decisions SET processed = 1 WHERE id = ?", (d2.id,))
        temp_db.commit()

        # Normal decision (should not appear)
        d3 = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="ghi789",
            decision="draft",
            reasoning="Good commit",
        )
        insert_decision(temp_db, d3)

        deferred = get_deferred_eval_decisions(temp_db, project.id)
        assert len(deferred) == 1
        assert deferred[0].id == d1.id

    def test_get_today_auto_evaluation_count(self, temp_db):
        """get_today_auto_evaluation_count counts only auto evaluations today."""
        # Auto evaluation (should count)
        u1 = UsageLog(
            id=generate_id("usage"),
            operation_type="evaluate",
            model="opus",
            trigger_source="auto",
        )
        insert_usage(temp_db, u1)

        # Manual evaluation (should NOT count)
        u2 = UsageLog(
            id=generate_id("usage"),
            operation_type="evaluate",
            model="opus",
            trigger_source="manual",
        )
        insert_usage(temp_db, u2)

        # Auto drafting (should NOT count - wrong operation type)
        u3 = UsageLog(
            id=generate_id("usage"),
            operation_type="draft",
            model="opus",
            trigger_source="auto",
        )
        insert_usage(temp_db, u3)

        count = get_today_auto_evaluation_count(temp_db)
        assert count == 1

    def test_get_last_auto_evaluation_time(self, temp_db):
        """get_last_auto_evaluation_time returns most recent auto eval time."""
        # No evaluations yet
        assert get_last_auto_evaluation_time(temp_db) is None

        # Insert auto evaluation
        u1 = UsageLog(
            id=generate_id("usage"),
            operation_type="evaluate",
            model="opus",
            trigger_source="auto",
        )
        insert_usage(temp_db, u1)

        result = get_last_auto_evaluation_time(temp_db)
        assert result is not None

    def test_insert_usage_with_trigger_source(self, temp_db):
        """insert_usage persists trigger_source field."""
        u = UsageLog(
            id=generate_id("usage"),
            operation_type="evaluate",
            model="opus",
            trigger_source="manual",
        )
        insert_usage(temp_db, u)

        row = temp_db.execute(
            "SELECT trigger_source FROM usage_log WHERE id = ?", (u.id,)
        ).fetchone()
        assert row[0] == "manual"

    def test_execute_queue_action_merge(self, temp_db):
        """execute_queue_action handles merge action (marks draft as superseded)."""
        project = self._make_project(temp_db)

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc123",
            decision="draft",
            reasoning="Test",
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

        execute_queue_action(temp_db, "merge", draft.id, "merged into new draft")

        updated = get_draft(temp_db, draft.id)
        assert updated.status == "superseded"

    def test_execute_queue_action_invalid_raises(self, temp_db):
        """execute_queue_action raises ValueError for unknown action type."""
        project = self._make_project(temp_db)
        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc123",
            decision="draft",
            reasoning="Test",
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

        with pytest.raises(ValueError, match="Unknown queue action"):
            execute_queue_action(temp_db, "invalid_action", draft.id, "bad action")

    def test_decision_trigger_source_persists(self, temp_db):
        """Decision trigger_source persists through insert -> get."""
        project = self._make_project(temp_db)
        d = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc123",
            decision="draft",
            reasoning="test",
            trigger_source="scheduler",
        )
        insert_decision(temp_db, d)

        decisions = get_recent_decisions(temp_db, project.id)
        assert len(decisions) == 1
        assert decisions[0].trigger_source == "scheduler"
