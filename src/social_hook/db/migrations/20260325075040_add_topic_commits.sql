CREATE TABLE IF NOT EXISTS topic_commits (
    topic_id TEXT NOT NULL,
    commit_hash TEXT NOT NULL,
    matched_tag TEXT,
    matched_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (topic_id, commit_hash)
);
