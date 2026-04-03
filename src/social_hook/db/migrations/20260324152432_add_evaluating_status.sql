-- Add 'evaluating' to the decision CHECK constraint.
-- SQLite requires table rebuild to alter CHECK constraints.
PRAGMA foreign_keys=OFF;

DROP TABLE IF EXISTS decisions_new;

CREATE TABLE decisions_new (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES projects(id),
    commit_hash   TEXT NOT NULL,
    commit_message TEXT,
    decision      TEXT NOT NULL CHECK (decision IN ('draft', 'hold', 'skip', 'imported', 'deferred_eval', 'evaluating')),
    reasoning     TEXT NOT NULL,
    angle         TEXT,
    episode_type  TEXT,
    episode_tags  TEXT DEFAULT '[]',
    post_category TEXT,
    arc_id        TEXT,
    media_tool    TEXT,
    platforms     TEXT NOT NULL DEFAULT '{}',
    targets       TEXT NOT NULL DEFAULT '{}',
    commit_summary TEXT,
    consolidate_with TEXT,
    reference_posts TEXT DEFAULT NULL,
    branch        TEXT DEFAULT NULL,
    trigger_source TEXT DEFAULT 'commit',
    processed     INTEGER NOT NULL DEFAULT 0,
    processed_at  TEXT,
    batch_id      TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(project_id, commit_hash)
);

INSERT INTO decisions_new SELECT * FROM decisions;
DROP TABLE decisions;
ALTER TABLE decisions_new RENAME TO decisions;

PRAGMA foreign_keys=ON;
