PRAGMA foreign_keys = OFF;

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
    post_format     TEXT DEFAULT NULL CHECK (post_format IN ('single', 'thread', 'quote', 'reply')),
    reference_post_id TEXT DEFAULT NULL REFERENCES posts(id),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO drafts_new SELECT * FROM drafts;
DROP TABLE drafts;
ALTER TABLE drafts_new RENAME TO drafts;

CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(project_id, status);
CREATE INDEX IF NOT EXISTS idx_drafts_scheduled ON drafts(status, scheduled_time) WHERE status = 'scheduled';
CREATE INDEX IF NOT EXISTS idx_drafts_intro ON drafts(project_id) WHERE is_intro = 1;
CREATE INDEX IF NOT EXISTS idx_drafts_reference_post ON drafts(reference_post_id) WHERE reference_post_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_drafts_deferred ON drafts(status, created_at) WHERE status = 'deferred';

PRAGMA foreign_keys = ON;
