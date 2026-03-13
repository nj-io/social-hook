CREATE TABLE IF NOT EXISTS file_summaries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    file_path  TEXT NOT NULL,
    summary    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(project_id, file_path)
);
CREATE INDEX IF NOT EXISTS idx_file_summaries_project ON file_summaries(project_id);

ALTER TABLE projects ADD COLUMN prompt_docs TEXT DEFAULT NULL;
