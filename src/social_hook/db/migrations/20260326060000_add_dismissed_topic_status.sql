-- Add 'dismissed' to content_topics status CHECK constraint.
-- SQLite does not support ALTER TABLE ... ALTER CONSTRAINT, so recreate the table.

CREATE TABLE content_topics_new (
    id           TEXT PRIMARY KEY,
    project_id   TEXT NOT NULL,
    strategy     TEXT NOT NULL DEFAULT '',
    topic        TEXT NOT NULL,
    description  TEXT,
    priority_rank INTEGER NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'uncovered'
        CHECK (status IN ('uncovered', 'holding', 'partial', 'covered', 'dismissed')),
    commit_count INTEGER NOT NULL DEFAULT 0,
    last_commit_at TEXT,
    last_posted_at TEXT,
    created_by   TEXT NOT NULL DEFAULT 'user',
    created_at   TEXT DEFAULT (datetime('now'))
);

INSERT INTO content_topics_new SELECT * FROM content_topics;
DROP TABLE content_topics;
ALTER TABLE content_topics_new RENAME TO content_topics;
