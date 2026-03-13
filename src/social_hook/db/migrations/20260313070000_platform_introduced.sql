PRAGMA foreign_keys = OFF;

CREATE TABLE IF NOT EXISTS platform_introduced (
    project_id          TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    platform            TEXT NOT NULL,
    introduced          INTEGER NOT NULL DEFAULT 0,
    introduced_at       TEXT,
    PRIMARY KEY (project_id, platform)
);

-- Seed from existing audience_introduced flag: for projects where
-- audience_introduced=1, mark platforms that have actual published posts
-- as introduced. Uses posted_at timestamp for accuracy.
INSERT INTO platform_introduced (project_id, platform, introduced, introduced_at)
SELECT p.id, po.platform, 1, MIN(po.posted_at)
FROM projects p
JOIN posts po ON po.project_id = p.id
WHERE p.audience_introduced = 1
GROUP BY p.id, po.platform;

-- Drop the old column via table rebuild
-- CRITICAL: Must include prompt_docs column (added in migration 018)
CREATE TABLE projects_new (
    id                    TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    repo_path             TEXT NOT NULL,
    repo_origin           TEXT,
    summary               TEXT,
    summary_updated_at    TEXT,
    paused                INTEGER NOT NULL DEFAULT 0,
    discovery_files       TEXT DEFAULT NULL,
    prompt_docs           TEXT DEFAULT NULL,
    trigger_branch        TEXT DEFAULT NULL,
    created_at            TEXT NOT NULL DEFAULT (datetime('now'))
);
INSERT INTO projects_new SELECT id, name, repo_path, repo_origin, summary, summary_updated_at, paused, discovery_files, prompt_docs, trigger_branch, created_at FROM projects;
DROP TABLE projects;
ALTER TABLE projects_new RENAME TO projects;

-- Re-create index dropped with the table
CREATE INDEX IF NOT EXISTS idx_projects_origin ON projects(repo_origin);

PRAGMA foreign_keys = ON;
