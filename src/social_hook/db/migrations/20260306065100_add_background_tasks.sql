CREATE TABLE IF NOT EXISTS background_tasks (
    id         TEXT PRIMARY KEY,
    type       TEXT NOT NULL,
    ref_id     TEXT NOT NULL DEFAULT '',
    project_id TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'running',
    result     TEXT,
    error      TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_background_tasks_status ON background_tasks(status);
CREATE INDEX IF NOT EXISTS idx_background_tasks_ref ON background_tasks(type, ref_id, status);
