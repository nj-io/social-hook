PRAGMA foreign_keys = OFF;

-- =============================================================================
-- Drafts table rebuild: add vehicle, rename post_format -> reference_type,
-- add reference_files, narrow reference_type CHECK to quote/reply only
-- =============================================================================

DROP TABLE IF EXISTS drafts_new;

CREATE TABLE drafts_new (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects(id),
    decision_id     TEXT NOT NULL REFERENCES decisions(id),
    platform        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'scheduled', 'posted', 'rejected', 'failed', 'superseded', 'cancelled', 'deferred')),
    content         TEXT NOT NULL,
    media_paths     TEXT NOT NULL DEFAULT '[]',
    media_type      TEXT,
    media_spec      TEXT DEFAULT '{}',
    media_spec_used TEXT,
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

-- Backfill: drafts with draft_tweets rows get vehicle='thread', rest get 'single'.
-- post_format 'quote'/'reply' map to reference_type; 'single'/'thread' values are discarded.
INSERT INTO drafts_new (
    id, project_id, decision_id, platform, status, content,
    media_paths, media_type, media_spec, media_spec_used,
    suggested_time, scheduled_time, reasoning, superseded_by,
    retry_count, last_error, is_intro,
    vehicle,
    reference_type,
    reference_files,
    reference_post_id, target_id, evaluation_cycle_id, topic_id,
    suggestion_id, pattern_id, preview_mode, arc_id,
    created_at, updated_at
) SELECT
    d.id, d.project_id, d.decision_id, d.platform, d.status, d.content,
    d.media_paths, d.media_type, d.media_spec, d.media_spec_used,
    d.suggested_time, d.scheduled_time, d.reasoning, d.superseded_by,
    d.retry_count, d.last_error, d.is_intro,
    CASE WHEN EXISTS (SELECT 1 FROM draft_tweets dt WHERE dt.draft_id = d.id)
         THEN 'thread' ELSE 'single' END,
    CASE WHEN d.post_format IN ('quote', 'reply') THEN d.post_format ELSE NULL END,
    NULL,
    d.reference_post_id, d.target_id, d.evaluation_cycle_id, d.topic_id,
    d.suggestion_id, d.pattern_id, d.preview_mode, d.arc_id,
    d.created_at, d.updated_at
FROM drafts d;

DROP TABLE drafts;
ALTER TABLE drafts_new RENAME TO drafts;

CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(project_id, status);
CREATE INDEX IF NOT EXISTS idx_drafts_scheduled ON drafts(status, scheduled_time) WHERE status = 'scheduled';
CREATE INDEX IF NOT EXISTS idx_drafts_intro ON drafts(project_id) WHERE is_intro = 1;
CREATE INDEX IF NOT EXISTS idx_drafts_reference_post ON drafts(reference_post_id) WHERE reference_post_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_drafts_target ON drafts(target_id) WHERE target_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_drafts_topic_id ON drafts(topic_id) WHERE topic_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_drafts_deferred ON drafts(status, created_at) WHERE status = 'deferred';

-- =============================================================================
-- Rename draft_tweets table -> draft_parts, rename indexes
-- =============================================================================

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

INSERT INTO draft_parts (id, draft_id, position, content, media_paths, external_id, posted_at, error)
SELECT id, draft_id, position, content, media_paths, external_id, posted_at, error
FROM draft_tweets;

DROP TABLE IF EXISTS draft_tweets;

CREATE INDEX IF NOT EXISTS idx_draft_parts_draft ON draft_parts(draft_id, position);
CREATE INDEX IF NOT EXISTS idx_draft_parts_external ON draft_parts(external_id) WHERE external_id IS NOT NULL;

PRAGMA foreign_keys = ON;
