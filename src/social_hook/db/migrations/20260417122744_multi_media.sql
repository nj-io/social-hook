PRAGMA foreign_keys = OFF;

-- =============================================================================
-- Multi-media per draft.
--
-- Replaces singular-media columns on `drafts` (media_type, media_spec,
-- media_spec_used) with parallel-array columns (media_specs, media_errors,
-- media_specs_used). Adds the same three parallel arrays to `draft_parts`
-- (media_paths already exists). Creates pending_uploads table for upload
-- staging.
--
-- Migration semantics:
--   * Index i references the same media item across all four arrays
--     (media_specs, media_paths, media_errors, media_specs_used).
--   * Each spec embeds its own `tool` field — no parallel media_types column.
--   * media_type='custom' rows migrate to tool='legacy_upload' with
--     user_uploaded=true.
--   * media_specs[i].id and media_specs_used[i].id share the same stable id
--     for every migrated row (CTE-generated, one id per source row).
-- =============================================================================

-- -----------------------------------------------------------------------------
-- drafts rebuild
--
-- Preserves the existing CHECK constraints on status/vehicle/reference_type
-- and the existing FK targets (drafts(id), projects(id), decisions(id),
-- posts(id)) verbatim from the content-vehicles schema + advisory-status
-- patch. Indexes recreated verbatim from PRAGMA index_list(drafts)
-- enumeration at migration time.
-- -----------------------------------------------------------------------------

DROP TABLE IF EXISTS drafts_new;

CREATE TABLE drafts_new (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects(id),
    decision_id     TEXT NOT NULL REFERENCES decisions(id),
    platform        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'scheduled', 'posted', 'rejected', 'failed', 'superseded', 'cancelled', 'deferred', 'advisory')),
    content         TEXT NOT NULL,
    media_paths     TEXT NOT NULL DEFAULT '[]',
    media_specs     TEXT NOT NULL DEFAULT '[]',
    media_errors    TEXT NOT NULL DEFAULT '[]',
    media_specs_used TEXT NOT NULL DEFAULT '[]',
    suggested_time  TEXT,
    scheduled_time  TEXT,
    reasoning       TEXT,
    superseded_by   TEXT REFERENCES drafts_new(id),
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

-- Stage source rows + per-row new_id in a temp table so the id is materialized
-- once per row, then referenced twice in the SELECT below (once for
-- media_specs, once for media_specs_used). Without the temp table, SQLite's
-- query flattener re-evaluates randomblob(6) per column reference, yielding
-- mismatched ids and permanently tripping the spec-unchanged guard on every
-- migrated draft (see plan done-criteria ≥10-row randomblob test).
DROP TABLE IF EXISTS drafts_migration_tmp;
CREATE TEMP TABLE drafts_migration_tmp AS
    SELECT *, 'media_' || lower(substr(hex(randomblob(6)), 1, 12)) AS new_id
    FROM drafts;

INSERT INTO drafts_new (
    id, project_id, decision_id, platform, status, content,
    media_paths, media_specs, media_errors, media_specs_used,
    suggested_time, scheduled_time, reasoning, superseded_by,
    retry_count, last_error, is_intro, vehicle,
    reference_type, reference_files, reference_post_id,
    target_id, evaluation_cycle_id, topic_id, suggestion_id, pattern_id,
    preview_mode, arc_id, created_at, updated_at
)
SELECT
    d.id, d.project_id, d.decision_id, d.platform, d.status, d.content,
    COALESCE(d.media_paths, '[]'),
    CASE
      WHEN d.media_type IS NULL OR d.media_type IN ('', 'none') THEN '[]'
      WHEN d.media_spec IS NULL OR d.media_spec IN ('', '{}') THEN '[]'
      WHEN NOT json_valid(d.media_spec) THEN '[]'
      ELSE json_array(json_object(
        'id', d.new_id,
        'tool', CASE WHEN d.media_type = 'custom' THEN 'legacy_upload' ELSE d.media_type END,
        'spec', json(d.media_spec),
        'caption', NULL,
        'user_uploaded', CASE WHEN d.media_type = 'custom' THEN json('true') ELSE json('false') END
      ))
    END,
    '[]',
    CASE
      WHEN d.media_type IS NULL OR d.media_type IN ('', 'none') THEN '[]'
      WHEN d.media_spec_used IS NULL OR d.media_spec_used IN ('', '{}') THEN '[]'
      WHEN NOT json_valid(d.media_spec_used) THEN '[]'
      ELSE json_array(json_object(
        'id', d.new_id,
        'tool', CASE WHEN d.media_type = 'custom' THEN 'legacy_upload' ELSE d.media_type END,
        'spec', json(d.media_spec_used),
        'caption', NULL,
        'user_uploaded', CASE WHEN d.media_type = 'custom' THEN json('true') ELSE json('false') END
      ))
    END,
    d.suggested_time, d.scheduled_time, d.reasoning, d.superseded_by,
    d.retry_count, d.last_error, d.is_intro, d.vehicle,
    d.reference_type, d.reference_files, d.reference_post_id,
    d.target_id, d.evaluation_cycle_id, d.topic_id, d.suggestion_id, d.pattern_id,
    d.preview_mode, d.arc_id, d.created_at, d.updated_at
FROM drafts_migration_tmp d;

DROP TABLE drafts_migration_tmp;

DROP TABLE drafts;
ALTER TABLE drafts_new RENAME TO drafts;

-- Recreate every index enumerated from PRAGMA index_list(drafts) on the
-- content-vehicles + advisory-status DB (see pre-flight verification).
CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(project_id, status);
CREATE INDEX IF NOT EXISTS idx_drafts_scheduled ON drafts(status, scheduled_time) WHERE status = 'scheduled';
CREATE INDEX IF NOT EXISTS idx_drafts_intro ON drafts(project_id) WHERE is_intro = 1;
CREATE INDEX IF NOT EXISTS idx_drafts_reference_post ON drafts(reference_post_id) WHERE reference_post_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_drafts_target ON drafts(target_id) WHERE target_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_drafts_topic_id ON drafts(topic_id) WHERE topic_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_drafts_deferred ON drafts(status, created_at) WHERE status = 'deferred';

-- -----------------------------------------------------------------------------
-- draft_parts additive columns + legacy media_paths backfill
--
-- draft_parts.media_paths already exists (NOT NULL DEFAULT '[]'). For every
-- pre-existing path we synthesize a legacy_upload spec so index i lines up
-- across all four arrays.
-- -----------------------------------------------------------------------------

ALTER TABLE draft_parts ADD COLUMN media_specs TEXT NOT NULL DEFAULT '[]';
ALTER TABLE draft_parts ADD COLUMN media_errors TEXT NOT NULL DEFAULT '[]';
ALTER TABLE draft_parts ADD COLUMN media_specs_used TEXT NOT NULL DEFAULT '[]';

UPDATE draft_parts
SET media_specs = (
    SELECT json_group_array(
        json_object(
            'id', 'media_' || lower(substr(hex(randomblob(6)), 1, 12)),
            'tool', 'legacy_upload',
            'spec', json_object('path', value),
            'caption', NULL,
            'user_uploaded', json('true')
        )
    )
    FROM json_each(media_paths)
)
WHERE json_array_length(media_paths) > 0;

-- -----------------------------------------------------------------------------
-- pending_uploads table — staging for operator-uploaded reference images
-- before a draft is created. Pruned by the scheduler on a 24h TTL; see
-- Agent 3 task 5 for the hook.
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS pending_uploads (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    path TEXT NOT NULL,
    context TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pending_uploads_project ON pending_uploads(project_id, created_at);

PRAGMA foreign_keys = ON;
