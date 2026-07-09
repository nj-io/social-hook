"""Tests for content vehicles schema and model changes (Phase 1h/1i)."""

import json
import sqlite3
from pathlib import Path

import pytest

from social_hook.db.operations import (
    get_draft,
    get_draft_parts,
    insert_decision,
    insert_draft,
    insert_draft_part,
    insert_project,
    replace_draft_parts,
    update_draft,
    update_draft_part,
)
from social_hook.db.schema import SCHEMA_DDL, SCHEMA_VERSION
from social_hook.filesystem import generate_id
from social_hook.models.core import CommitInfo, Decision, Draft, DraftPart, Project


@pytest.fixture
def temp_db():
    """Create an in-memory database with full schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_DDL)
    yield conn
    conn.close()


@pytest.fixture
def project_and_decision(temp_db):
    """Set up a project + decision for draft tests."""
    project = Project(id=generate_id("project"), name="test", repo_path="/tmp/test")
    insert_project(temp_db, project)
    decision = Decision(
        id=generate_id("decision"),
        project_id=project.id,
        commit_hash="abc123",
        decision="draft",
        reasoning="test",
    )
    insert_decision(temp_db, decision)
    return project, decision


# =============================================================================
# Draft model serialization with new fields
# =============================================================================


class TestDraftVehicleFields:
    def test_draft_default_vehicle(self):
        """Draft defaults to vehicle='single'."""
        draft = Draft(
            id="d1",
            project_id="p1",
            decision_id="dec1",
            platform="x",
            content="hello",
        )
        assert draft.vehicle == "single"
        assert draft.reference_type is None
        assert draft.reference_files is None

    def test_draft_to_dict_includes_vehicle(self):
        """to_dict() includes vehicle, reference_type, reference_files."""
        draft = Draft(
            id="d1",
            project_id="p1",
            decision_id="dec1",
            platform="x",
            content="hello",
            vehicle="thread",
            reference_type="quote",
            reference_files=["file1.md", "file2.py"],
        )
        d = draft.to_dict()
        assert d["vehicle"] == "thread"
        assert d["reference_type"] == "quote"
        assert d["reference_files"] == ["file1.md", "file2.py"]

    def test_draft_from_dict_with_vehicle(self):
        """from_dict() parses vehicle, reference_type, reference_files."""
        d = {
            "id": "d1",
            "project_id": "p1",
            "decision_id": "dec1",
            "platform": "x",
            "content": "hello",
            "vehicle": "article",
            "reference_type": "reply",
            "reference_files": '["a.md", "b.md"]',  # JSON string from DB
        }
        draft = Draft.from_dict(d)
        assert draft.vehicle == "article"
        assert draft.reference_type == "reply"
        assert draft.reference_files == ["a.md", "b.md"]

    def test_draft_from_dict_defaults(self):
        """from_dict() defaults vehicle to 'single' when missing."""
        d = {
            "id": "d1",
            "project_id": "p1",
            "decision_id": "dec1",
            "platform": "x",
            "content": "hello",
        }
        draft = Draft.from_dict(d)
        assert draft.vehicle == "single"
        assert draft.reference_type is None
        assert draft.reference_files is None

    def test_draft_to_row_column_count(self):
        """to_row() returns 28 columns matching insert_draft()."""
        draft = Draft(
            id="d1",
            project_id="p1",
            decision_id="dec1",
            platform="x",
            content="hello",
            vehicle="thread",
            reference_type="quote",
            reference_files=["f1.md"],
        )
        row = draft.to_row()
        assert len(row) == 28

    def test_draft_to_row_reference_files_json(self):
        """to_row() serializes reference_files as JSON."""
        draft = Draft(
            id="d1",
            project_id="p1",
            decision_id="dec1",
            platform="x",
            content="hello",
            reference_files=["a.md", "b.py"],
        )
        row = draft.to_row()
        # reference_files is at index 19 (after reference_type at 18)
        assert json.loads(row[19]) == ["a.md", "b.py"]

    def test_draft_to_row_reference_files_none(self):
        """to_row() produces None when reference_files is None."""
        draft = Draft(
            id="d1",
            project_id="p1",
            decision_id="dec1",
            platform="x",
            content="hello",
        )
        row = draft.to_row()
        assert row[19] is None


# =============================================================================
# DraftPart (renamed from DraftTweet)
# =============================================================================


class TestDraftPart:
    def test_draft_part_from_dict(self):
        """DraftPart.from_dict() works like old DraftTweet.from_dict()."""
        d = {
            "id": "p1",
            "draft_id": "d1",
            "position": 1,
            "content": "Part 1",
            "media_paths": "[]",
        }
        part = DraftPart.from_dict(d)
        assert part.id == "p1"
        assert part.position == 1
        assert part.media_paths == []

    def test_draft_part_to_dict(self):
        part = DraftPart(id="p1", draft_id="d1", position=1, content="hello")
        d = part.to_dict()
        assert d["id"] == "p1"
        assert d["draft_id"] == "d1"

    def test_draft_part_to_row(self):
        # Multi-media added 3 parallel-array columns to draft_parts
        # (media_specs, media_errors, media_specs_used) alongside the
        # existing media_paths — so to_row now returns 11 elements.
        part = DraftPart(id="p1", draft_id="d1", position=1, content="hello")
        row = part.to_row()
        assert len(row) == 11


# =============================================================================
# CommitInfo.from_operator_input()
# =============================================================================


class TestCommitInfoFactory:
    def test_from_operator_input_basic(self):
        """from_operator_input() creates a CommitInfo with generated hash."""
        ci = CommitInfo.from_operator_input("My idea")
        assert ci.message == "My idea"
        assert ci.diff == ""
        assert ci.hash.startswith("op_")
        assert ci.files_changed == []
        assert ci.insertions == 0
        assert ci.deletions == 0

    def test_from_operator_input_with_context(self):
        """from_operator_input() passes reference_context as diff."""
        ci = CommitInfo.from_operator_input("My idea", reference_context="some docs")
        assert ci.diff == "some docs"

    def test_from_operator_input_with_trigger_id(self):
        """from_operator_input() uses trigger_id as hash when provided."""
        ci = CommitInfo.from_operator_input("idea", trigger_id="custom_id_123")
        assert ci.hash == "custom_id_123"

    def test_from_operator_input_unique_hashes(self):
        """Each call generates a unique hash."""
        hashes = {CommitInfo.from_operator_input("idea").hash for _ in range(10)}
        assert len(hashes) == 10


# =============================================================================
# DB round-trip with new fields
# =============================================================================


class TestDBRoundTrip:
    def test_insert_and_get_draft_with_vehicle(self, temp_db, project_and_decision):
        """Draft with vehicle='thread' round-trips through DB."""
        project, decision = project_and_decision
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="thread content",
            vehicle="thread",
            reference_type="quote",
            reference_files=["doc.md"],
        )
        insert_draft(temp_db, draft)
        loaded = get_draft(temp_db, draft.id)
        assert loaded is not None
        assert loaded.vehicle == "thread"
        assert loaded.reference_type == "quote"
        assert loaded.reference_files == ["doc.md"]

    def test_insert_draft_default_vehicle(self, temp_db, project_and_decision):
        """Draft without explicit vehicle gets 'single' from DB default."""
        project, decision = project_and_decision
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="simple post",
        )
        insert_draft(temp_db, draft)
        loaded = get_draft(temp_db, draft.id)
        assert loaded.vehicle == "single"

    def test_update_draft_vehicle(self, temp_db, project_and_decision):
        """update_draft() can change vehicle."""
        project, decision = project_and_decision
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="test",
        )
        insert_draft(temp_db, draft)
        update_draft(temp_db, draft.id, vehicle="thread")
        loaded = get_draft(temp_db, draft.id)
        assert loaded.vehicle == "thread"

    def test_update_draft_reference_files(self, temp_db, project_and_decision):
        """update_draft() can set reference_files."""
        project, decision = project_and_decision
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="test",
        )
        insert_draft(temp_db, draft)
        update_draft(temp_db, draft.id, reference_files=["a.md", "b.py"])
        loaded = get_draft(temp_db, draft.id)
        assert loaded.reference_files == ["a.md", "b.py"]

    def test_draft_parts_crud(self, temp_db, project_and_decision):
        """DraftPart CRUD (insert, get, update, replace)."""
        project, decision = project_and_decision
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="thread",
            vehicle="thread",
        )
        insert_draft(temp_db, draft)

        # Insert parts
        parts = []
        for i in range(3):
            p = DraftPart(
                id=generate_id("part"),
                draft_id=draft.id,
                position=i + 1,
                content=f"Part {i + 1}",
            )
            insert_draft_part(temp_db, p)
            parts.append(p)

        loaded = get_draft_parts(temp_db, draft.id)
        assert len(loaded) == 3
        assert [p.content for p in loaded] == ["Part 1", "Part 2", "Part 3"]

        # Update a part
        update_draft_part(temp_db, parts[0].id, external_id="ext_123")
        loaded = get_draft_parts(temp_db, draft.id)
        assert loaded[0].external_id == "ext_123"

        # Replace all parts
        new_parts = [
            DraftPart(id=generate_id("part"), draft_id=draft.id, position=1, content="New 1"),
            DraftPart(id=generate_id("part"), draft_id=draft.id, position=2, content="New 2"),
        ]
        replace_draft_parts(temp_db, draft.id, new_parts)
        loaded = get_draft_parts(temp_db, draft.id)
        assert len(loaded) == 2
        assert loaded[0].content == "New 1"

    def test_vehicle_check_constraint(self, temp_db, project_and_decision):
        """Vehicle CHECK constraint rejects invalid values."""
        project, decision = project_and_decision
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="test",
            vehicle="invalid",
        )
        with pytest.raises(sqlite3.IntegrityError):
            insert_draft(temp_db, draft)

    def test_reference_type_check_constraint(self, temp_db, project_and_decision):
        """reference_type CHECK constraint only allows quote/reply."""
        project, decision = project_and_decision
        draft = Draft(
            id=generate_id("draft"),
            project_id=project.id,
            decision_id=decision.id,
            platform="x",
            content="test",
            reference_type="single",  # was valid in post_format, not in reference_type
        )
        with pytest.raises(sqlite3.IntegrityError):
            insert_draft(temp_db, draft)


# =============================================================================
# Migration SQL validity
# =============================================================================


class TestMigrationSQL:
    def test_migration_sql_parses(self):
        """Migration SQL file is valid SQLite."""
        migration_path = (
            Path(__file__).parent.parent
            / "src/social_hook/db/migrations/20260408120000_content_vehicles.sql"
        )
        sql = migration_path.read_text()
        assert "PRAGMA foreign_keys = OFF" in sql
        assert "DROP TABLE IF EXISTS drafts_new" in sql
        assert "vehicle" in sql
        assert "reference_type" in sql
        assert "reference_files" in sql
        assert "draft_parts" in sql

    def test_migration_against_old_schema(self):
        """Migration applies cleanly to pre-migration schema."""
        # Create a DB with old schema (draft_tweets, post_format)
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row

        # Minimal old schema with just the tables the migration touches
        conn.executescript("""
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                repo_path TEXT NOT NULL
            );
            CREATE TABLE decisions (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                commit_hash TEXT NOT NULL,
                decision TEXT NOT NULL,
                reasoning TEXT NOT NULL
            );
            CREATE TABLE posts (id TEXT PRIMARY KEY);
            CREATE TABLE drafts (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                decision_id TEXT NOT NULL,
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
                superseded_by TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                is_intro INTEGER NOT NULL DEFAULT 0,
                post_format TEXT DEFAULT NULL,
                reference_post_id TEXT DEFAULT NULL,
                target_id TEXT,
                evaluation_cycle_id TEXT,
                topic_id TEXT,
                suggestion_id TEXT,
                pattern_id TEXT,
                preview_mode INTEGER NOT NULL DEFAULT 0,
                arc_id TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE draft_tweets (
                id TEXT PRIMARY KEY,
                draft_id TEXT NOT NULL,
                position INTEGER NOT NULL,
                content TEXT NOT NULL,
                media_paths TEXT NOT NULL DEFAULT '[]',
                external_id TEXT,
                posted_at TEXT,
                error TEXT,
                UNIQUE(draft_id, position)
            );
        """)

        # Insert test data
        conn.execute("INSERT INTO projects VALUES ('p1', 'test', '/tmp')")
        conn.execute("INSERT INTO decisions VALUES ('dec1', 'p1', 'abc', 'draft', 'test')")
        conn.execute(
            """INSERT INTO drafts (id, project_id, decision_id, platform, content, post_format)
               VALUES ('d1', 'p1', 'dec1', 'x', 'single post', NULL)"""
        )
        conn.execute(
            """INSERT INTO drafts (id, project_id, decision_id, platform, content, post_format)
               VALUES ('d2', 'p1', 'dec1', 'x', 'thread head', 'thread')"""
        )
        conn.execute(
            """INSERT INTO drafts (id, project_id, decision_id, platform, content, post_format)
               VALUES ('d3', 'p1', 'dec1', 'x', 'quote post', 'quote')"""
        )
        conn.execute(
            "INSERT INTO draft_tweets VALUES ('t1', 'd2', 1, 'Part 1', '[]', NULL, NULL, NULL)"
        )
        conn.execute(
            "INSERT INTO draft_tweets VALUES ('t2', 'd2', 2, 'Part 2', '[]', NULL, NULL, NULL)"
        )
        conn.commit()

        # Apply migration
        migration_path = (
            Path(__file__).parent.parent
            / "src/social_hook/db/migrations/20260408120000_content_vehicles.sql"
        )
        conn.executescript(migration_path.read_text())

        # Verify: d1 (no tweets) -> vehicle='single'
        row = conn.execute("SELECT vehicle, reference_type FROM drafts WHERE id='d1'").fetchone()
        assert row[0] == "single"
        assert row[1] is None

        # Verify: d2 (has tweets) -> vehicle='thread', post_format='thread' discarded
        row = conn.execute("SELECT vehicle, reference_type FROM drafts WHERE id='d2'").fetchone()
        assert row[0] == "thread"
        assert row[1] is None  # 'thread' was not a valid reference_type

        # Verify: d3 (quote) -> reference_type='quote'
        row = conn.execute("SELECT vehicle, reference_type FROM drafts WHERE id='d3'").fetchone()
        assert row[0] == "single"
        assert row[1] == "quote"

        # Verify: draft_tweets -> draft_parts rename
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "draft_parts" in tables
        assert "draft_tweets" not in tables

        # Verify: data migrated to draft_parts
        parts = conn.execute(
            "SELECT * FROM draft_parts WHERE draft_id='d2' ORDER BY position"
        ).fetchall()
        assert len(parts) == 2

        conn.close()


# =============================================================================
# PostCapability enhancements
# =============================================================================


class TestPostCapability:
    def test_single_capability(self):
        from social_hook.adapters.models import SINGLE

        assert SINGLE.name == "single"
        assert SINGLE.auto_postable is True
        assert SINGLE.description != ""

    def test_thread_capability(self):
        from social_hook.adapters.models import THREAD

        assert THREAD.name == "thread"
        assert THREAD.auto_postable is True

    def test_article_capability(self):
        from social_hook.adapters.models import ARTICLE

        assert ARTICLE.name == "article"
        assert ARTICLE.auto_postable is False
        assert "manual" in ARTICLE.description.lower() or "long-form" in ARTICLE.description.lower()

    def test_platform_vehicle_support(self):
        # Multi-media Option 4 naming: SINGLE is the universal baseline
        # (one image, one GIF); SINGLE_X extends it with MULTI_IMAGE_X for
        # X's 4-image carousels. LinkedIn uses the baseline SINGLE.
        from social_hook.adapters.models import ARTICLE, SINGLE, SINGLE_X, THREAD
        from social_hook.config.platforms import PLATFORM_VEHICLE_SUPPORT

        assert SINGLE_X in PLATFORM_VEHICLE_SUPPORT["x"]
        assert THREAD in PLATFORM_VEHICLE_SUPPORT["x"]
        assert ARTICLE in PLATFORM_VEHICLE_SUPPORT["x"]
        assert SINGLE in PLATFORM_VEHICLE_SUPPORT["linkedin"]
        assert ARTICLE in PLATFORM_VEHICLE_SUPPORT["linkedin"]
        assert THREAD not in PLATFORM_VEHICLE_SUPPORT["linkedin"]
        # Universal baseline must not carry the X-only carousel mode.
        assert SINGLE not in PLATFORM_VEHICLE_SUPPORT["x"]


# =============================================================================
# Schema DDL includes new table/column names
# =============================================================================


class TestSchemaDDL:
    def test_schema_has_vehicle_column(self):
        assert "vehicle" in SCHEMA_DDL
        assert "reference_type" in SCHEMA_DDL
        assert "reference_files" in SCHEMA_DDL

    def test_schema_has_draft_parts_table(self):
        assert "draft_parts" in SCHEMA_DDL
        assert "draft_tweets" not in SCHEMA_DDL

    def test_schema_version_updated(self):
        # Bumped when the multi-media migration landed — schema.py now
        # ships the parallel-array drafts/draft_parts + pending_uploads
        # tables, so fresh DBs skip the multi-media migration at startup.
        assert SCHEMA_VERSION == 20260417122744
