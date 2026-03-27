-- Replace 'evaluating' with 'processing' in decisions CHECK constraint.
-- Also update any existing 'evaluating' rows to 'processing'.
-- SQLite requires table recreation to change CHECK constraints.

UPDATE decisions SET decision = 'processing' WHERE decision = 'evaluating';

CREATE TABLE decisions_new (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES projects(id),
    commit_hash   TEXT NOT NULL,
    commit_message TEXT,
    decision      TEXT NOT NULL CHECK (decision IN ('draft', 'hold', 'skip', 'imported', 'deferred_eval', 'processing')),
    reasoning     TEXT,
    angle         TEXT,
    episode_type  TEXT,
    episode_tags  TEXT DEFAULT '[]',
    post_category TEXT,
    arc_id        TEXT,
    media_tool    TEXT,
    platforms     TEXT DEFAULT '{}',
    targets       TEXT DEFAULT '{}',
    commit_summary TEXT,
    consolidate_with TEXT,
    reference_posts TEXT,
    branch        TEXT,
    trigger_source TEXT DEFAULT 'commit',
    processed     INTEGER NOT NULL DEFAULT 0,
    processed_at  TEXT,
    batch_id      TEXT,
    created_at    TEXT DEFAULT (datetime('now'))
);

INSERT INTO decisions_new SELECT * FROM decisions;
DROP TABLE decisions;
ALTER TABLE decisions_new RENAME TO decisions;

CREATE UNIQUE INDEX IF NOT EXISTS idx_decisions_project_commit ON decisions(project_id, commit_hash);
