"""Tests for the multi-media schema migration.

Verifies:
* Edge-case source rows migrate to well-formed parallel arrays.
* ``media_specs[0].id == media_specs_used[0].id`` for every migrated draft
  (SQLite's query flattener re-evaluates ``randomblob()`` per column
  reference unless the migration stages ids in a temp table — see
  plan done-criteria line 556).
* ``draft_parts.media_paths`` is backfilled into ``media_specs`` as
  ``legacy_upload`` stubs with matching ordering.
* Re-applying the migration is a no-op (schema_version skip).
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from social_hook.db.schema import create_schema
from social_hook.migrations import apply_sql_migrations

MIGRATIONS_DIR = "src/social_hook/db/migrations/"
MIGRATION_VERSION = 20260417122744


# Snapshot of drafts/draft_parts DDL at the pre-multi-media baseline
# (content-vehicles + advisory-status). `create_schema()` now ships the
# post-multi-media shape, so this test rolls the two tables back and clears
# the multi-media migration's schema_version row so it reapplies — exercising
# the INSERT ... SELECT path against a populated source table.
_PRE_MULTI_MEDIA_ROLLBACK = """
PRAGMA foreign_keys = OFF;
DROP TABLE IF EXISTS drafts;
CREATE TABLE drafts (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects(id),
    decision_id     TEXT NOT NULL REFERENCES decisions(id),
    platform        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'scheduled', 'posted', 'rejected', 'failed', 'superseded', 'cancelled', 'deferred', 'advisory')),
    content         TEXT NOT NULL,
    media_paths     TEXT NOT NULL DEFAULT '[]',
    media_type      TEXT,
    media_spec      TEXT DEFAULT '{}',
    media_spec_used TEXT,
    suggested_time  TEXT,
    scheduled_time  TEXT,
    reasoning       TEXT,
    superseded_by   TEXT REFERENCES drafts(id),
    retry_count     INTEGER NOT NULL DEFAULT 0,
    last_error      TEXT,
    is_intro        INTEGER NOT NULL DEFAULT 0,
    vehicle         TEXT NOT NULL DEFAULT 'single' CHECK (vehicle IN ('single', 'thread', 'article')),
    reference_type  TEXT DEFAULT NULL CHECK (reference_type IN ('quote', 'reply')),
    reference_files TEXT DEFAULT NULL,
    reference_post_id TEXT DEFAULT NULL REFERENCES posts(id),
    target_id       TEXT,
    evaluation_cycle_id TEXT,
    topic_id        TEXT,
    suggestion_id   TEXT,
    pattern_id      TEXT,
    preview_mode    INTEGER NOT NULL DEFAULT 0,
    arc_id          TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
DROP TABLE IF EXISTS draft_parts;
CREATE TABLE draft_parts (
    id          TEXT PRIMARY KEY,
    draft_id    TEXT NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    content     TEXT NOT NULL,
    media_paths TEXT NOT NULL DEFAULT '[]',
    external_id TEXT,
    posted_at   TEXT,
    error       TEXT,
    UNIQUE(draft_id, position)
);
DROP TABLE IF EXISTS pending_uploads;
-- Replace the current schema_version rows with the pre-multi-media
-- baseline (content-vehicles) so apply_sql_migrations only applies the
-- advisory + multi-media migrations, not every historical migration
-- since the initial schema.
DELETE FROM schema_version;
INSERT INTO schema_version (version, description) VALUES (20260408120000, 'content_vehicles_baseline');
PRAGMA foreign_keys = ON;
"""


def _build_pre_migration_db(path: str) -> sqlite3.Connection:
    """Build a DB at the pre-multi-media state so the migration has work
    to do on a populated source table.

    ``create_schema()`` now ships the post-multi-media shape (SCHEMA_VERSION
    bumped to 20260417122744). To exercise the migration's ``INSERT ...
    SELECT`` path we roll ``drafts``/``draft_parts`` back to the content-
    vehicles snapshot and delete the multi-media ``schema_version`` row so
    ``apply_sql_migrations`` reapplies the migration under test.
    """
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    conn.executescript(_PRE_MULTI_MEDIA_ROLLBACK)
    conn.execute("INSERT INTO projects (id, name, repo_path) VALUES ('p1', 'proj', '/tmp')")
    conn.execute(
        "INSERT INTO decisions (id, project_id, commit_hash, decision, reasoning) "
        "VALUES ('d1', 'p1', 'abc', 'draft', 'r')"
    )
    conn.commit()
    return conn


def _seed_legacy_draft(
    conn: sqlite3.Connection,
    draft_id: str,
    media_type: str | None,
    media_spec: str | None,
    media_spec_used: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO drafts (id, project_id, decision_id, platform, content,
            media_type, media_spec, media_spec_used)
        VALUES (?, 'p1', 'd1', 'x', 'c', ?, ?, ?)
        """,
        (draft_id, media_type, media_spec, media_spec_used),
    )


@pytest.fixture
def pre_migration_db(tmp_path):
    return _build_pre_migration_db(str(tmp_path / "test.db"))


class TestMigrationEdgeCases:
    """Every edge case in plan line 548-557."""

    def test_null_null_becomes_empty_arrays(self, pre_migration_db):
        _seed_legacy_draft(pre_migration_db, "dr1", None, None)
        pre_migration_db.commit()
        apply_sql_migrations(pre_migration_db, MIGRATIONS_DIR)
        row = pre_migration_db.execute(
            "SELECT media_specs, media_specs_used, media_errors FROM drafts WHERE id = 'dr1'"
        ).fetchone()
        assert json.loads(row["media_specs"]) == []
        assert json.loads(row["media_specs_used"]) == []
        assert json.loads(row["media_errors"]) == []

    def test_empty_spec_dict_becomes_empty_array(self, pre_migration_db):
        _seed_legacy_draft(pre_migration_db, "dr1", "mermaid", "{}")
        pre_migration_db.commit()
        apply_sql_migrations(pre_migration_db, MIGRATIONS_DIR)
        row = pre_migration_db.execute(
            "SELECT media_specs, media_specs_used FROM drafts WHERE id = 'dr1'"
        ).fetchone()
        assert json.loads(row["media_specs"]) == []
        assert json.loads(row["media_specs_used"]) == []

    def test_media_type_none_string_becomes_empty(self, pre_migration_db):
        _seed_legacy_draft(pre_migration_db, "dr1", "none", "{}")
        pre_migration_db.commit()
        apply_sql_migrations(pre_migration_db, MIGRATIONS_DIR)
        row = pre_migration_db.execute("SELECT media_specs FROM drafts WHERE id = 'dr1'").fetchone()
        assert json.loads(row["media_specs"]) == []

    def test_blank_values_become_empty(self, pre_migration_db):
        _seed_legacy_draft(pre_migration_db, "dr1", "", "")
        pre_migration_db.commit()
        apply_sql_migrations(pre_migration_db, MIGRATIONS_DIR)
        row = pre_migration_db.execute(
            "SELECT media_specs, media_specs_used FROM drafts WHERE id = 'dr1'"
        ).fetchone()
        assert json.loads(row["media_specs"]) == []
        assert json.loads(row["media_specs_used"]) == []

    def test_malformed_spec_json_guarded(self, pre_migration_db):
        _seed_legacy_draft(pre_migration_db, "dr1", "mermaid", "malformed{")
        pre_migration_db.commit()
        apply_sql_migrations(pre_migration_db, MIGRATIONS_DIR)
        row = pre_migration_db.execute("SELECT media_specs FROM drafts WHERE id = 'dr1'").fetchone()
        # json_valid guard turns malformed JSON into empty array.
        assert json.loads(row["media_specs"]) == []

    def test_nano_banana_pro_populated(self, pre_migration_db):
        _seed_legacy_draft(pre_migration_db, "dr1", "nano_banana_pro", '{"prompt":"x"}')
        pre_migration_db.commit()
        apply_sql_migrations(pre_migration_db, MIGRATIONS_DIR)
        row = pre_migration_db.execute("SELECT media_specs FROM drafts WHERE id = 'dr1'").fetchone()
        specs = json.loads(row["media_specs"])
        assert len(specs) == 1
        s = specs[0]
        assert s["tool"] == "nano_banana_pro"
        assert s["spec"] == {"prompt": "x"}
        assert s["caption"] is None
        assert s["user_uploaded"] is False
        assert s["id"].startswith("media_")
        # 'media_' (6) + 12 lowercase hex chars
        assert len(s["id"]) == 18

    def test_mermaid_populated(self, pre_migration_db):
        _seed_legacy_draft(pre_migration_db, "dr1", "mermaid", '{"diagram":"y"}')
        pre_migration_db.commit()
        apply_sql_migrations(pre_migration_db, MIGRATIONS_DIR)
        row = pre_migration_db.execute("SELECT media_specs FROM drafts WHERE id = 'dr1'").fetchone()
        specs = json.loads(row["media_specs"])
        assert len(specs) == 1 and specs[0]["tool"] == "mermaid"
        assert specs[0]["spec"] == {"diagram": "y"}

    def test_custom_maps_to_legacy_upload(self, pre_migration_db):
        _seed_legacy_draft(pre_migration_db, "dr1", "custom", '{"path":"/tmp/a.png"}')
        pre_migration_db.commit()
        apply_sql_migrations(pre_migration_db, MIGRATIONS_DIR)
        row = pre_migration_db.execute("SELECT media_specs FROM drafts WHERE id = 'dr1'").fetchone()
        specs = json.loads(row["media_specs"])
        assert len(specs) == 1
        s = specs[0]
        assert s["tool"] == "legacy_upload"
        assert s["user_uploaded"] is True
        assert s["spec"] == {"path": "/tmp/a.png"}

    def test_spec_and_spec_used_share_id_on_same_row(self, pre_migration_db):
        """Regression guard for randomblob re-evaluation (plan line 556)."""
        _seed_legacy_draft(
            pre_migration_db,
            "dr1",
            "nano_banana_pro",
            '{"prompt":"old"}',
            '{"prompt":"used"}',
        )
        pre_migration_db.commit()
        apply_sql_migrations(pre_migration_db, MIGRATIONS_DIR)
        row = pre_migration_db.execute(
            "SELECT media_specs, media_specs_used FROM drafts WHERE id = 'dr1'"
        ).fetchone()
        s = json.loads(row["media_specs"])
        u = json.loads(row["media_specs_used"])
        assert s and u
        assert s[0]["id"] == u[0]["id"], (
            "media_specs[0].id must equal media_specs_used[0].id on the same row — "
            "otherwise the spec-unchanged guard fires on every migrated draft."
        )

    def test_id_stability_across_many_rows(self, pre_migration_db):
        """≥10 rows: every row's specs[0].id matches its own specs_used[0].id,
        AND all ids are unique across rows (no randomblob collision).
        """
        for i in range(15):
            _seed_legacy_draft(
                pre_migration_db,
                f"dr_{i}",
                "nano_banana_pro",
                '{"prompt":"p"}',
                '{"prompt":"p"}',
            )
        pre_migration_db.commit()
        apply_sql_migrations(pre_migration_db, MIGRATIONS_DIR)

        rows = pre_migration_db.execute(
            "SELECT media_specs, media_specs_used FROM drafts ORDER BY id"
        ).fetchall()
        ids = []
        for row in rows:
            s = json.loads(row["media_specs"])
            u = json.loads(row["media_specs_used"])
            assert s and u
            assert s[0]["id"] == u[0]["id"]
            ids.append(s[0]["id"])
        assert len(ids) >= 15
        assert len(set(ids)) == len(ids), "id collisions across migrated rows"


class TestDraftPartsBackfill:
    def test_existing_media_paths_become_legacy_upload_specs(self, pre_migration_db):
        _seed_legacy_draft(pre_migration_db, "dr1", None, None)
        pre_migration_db.execute(
            "INSERT INTO draft_parts (id, draft_id, position, content, media_paths) "
            "VALUES ('pp1', 'dr1', 0, 't', '[\"a.png\",\"b.png\"]')"
        )
        pre_migration_db.commit()
        apply_sql_migrations(pre_migration_db, MIGRATIONS_DIR)
        row = pre_migration_db.execute(
            "SELECT media_paths, media_specs FROM draft_parts WHERE id = 'pp1'"
        ).fetchone()
        paths = json.loads(row["media_paths"])
        specs = json.loads(row["media_specs"])
        assert paths == ["a.png", "b.png"]
        assert len(specs) == 2
        for s, p in zip(specs, paths, strict=True):
            assert s["tool"] == "legacy_upload"
            assert s["user_uploaded"] is True
            assert s["spec"] == {"path": p}
            assert s["id"].startswith("media_")

    def test_no_media_paths_yields_empty_specs(self, pre_migration_db):
        _seed_legacy_draft(pre_migration_db, "dr1", None, None)
        pre_migration_db.execute(
            "INSERT INTO draft_parts (id, draft_id, position, content, media_paths) "
            "VALUES ('pp1', 'dr1', 0, 't', '[]')"
        )
        pre_migration_db.commit()
        apply_sql_migrations(pre_migration_db, MIGRATIONS_DIR)
        row = pre_migration_db.execute(
            "SELECT media_specs FROM draft_parts WHERE id = 'pp1'"
        ).fetchone()
        assert json.loads(row["media_specs"]) == []


class TestIdempotency:
    def test_reapplying_is_noop(self, pre_migration_db):
        _seed_legacy_draft(pre_migration_db, "dr1", "mermaid", '{"diagram":"y"}')
        pre_migration_db.commit()
        first = apply_sql_migrations(pre_migration_db, MIGRATIONS_DIR)
        second = apply_sql_migrations(pre_migration_db, MIGRATIONS_DIR)
        assert first >= 1
        assert second == 0

    def test_fresh_db_ends_up_with_multi_media_schema(self, tmp_path):
        from social_hook.db.schema import apply_migrations

        conn = sqlite3.connect(str(tmp_path / "fresh.db"))
        create_schema(conn)
        apply_migrations(conn, MIGRATIONS_DIR)
        draft_cols = [r[1] for r in conn.execute("PRAGMA table_info(drafts)").fetchall()]
        assert {"media_specs", "media_errors", "media_specs_used"}.issubset(draft_cols)
        # Singular columns dropped
        assert "media_type" not in draft_cols
        assert "media_spec" not in draft_cols
        assert "media_spec_used" not in draft_cols

        part_cols = [r[1] for r in conn.execute("PRAGMA table_info(draft_parts)").fetchall()]
        assert {"media_specs", "media_errors", "media_specs_used"}.issubset(part_cols)

        pu_cols = [r[1] for r in conn.execute("PRAGMA table_info(pending_uploads)").fetchall()]
        assert {"id", "project_id", "path", "context", "created_at"}.issubset(pu_cols)


class TestPendingUploadsTable:
    def test_table_created(self, pre_migration_db):
        apply_sql_migrations(pre_migration_db, MIGRATIONS_DIR)
        cols = [
            r[1] for r in pre_migration_db.execute("PRAGMA table_info(pending_uploads)").fetchall()
        ]
        assert {"id", "project_id", "path", "context", "created_at"}.issubset(cols)

    def test_project_index_created(self, pre_migration_db):
        apply_sql_migrations(pre_migration_db, MIGRATIONS_DIR)
        idx = [
            r[1] for r in pre_migration_db.execute("PRAGMA index_list(pending_uploads)").fetchall()
        ]
        assert "idx_pending_uploads_project" in idx
