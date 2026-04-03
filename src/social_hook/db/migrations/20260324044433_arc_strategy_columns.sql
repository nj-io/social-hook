-- Add strategy and reasoning columns to arcs, update CHECK constraint to include 'proposed'.
-- SQLite cannot ALTER existing CHECK constraints, so the table must be recreated.

PRAGMA foreign_keys = OFF;

CREATE TABLE arcs_new (
    id           TEXT PRIMARY KEY,
    project_id   TEXT NOT NULL REFERENCES projects(id),
    theme        TEXT NOT NULL,
    strategy     TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('proposed', 'active', 'completed', 'abandoned')),
    reasoning    TEXT,
    post_count   INTEGER NOT NULL DEFAULT 0,
    last_post_at TEXT,
    notes        TEXT,
    started_at   TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at     TEXT,
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO arcs_new (id, project_id, theme, status, post_count, last_post_at, notes, started_at, ended_at, updated_at)
    SELECT id, project_id, theme, status, post_count, last_post_at, notes, started_at, ended_at, updated_at FROM arcs;

DROP TABLE arcs;
ALTER TABLE arcs_new RENAME TO arcs;

-- Recreate indexes (DROP TABLE removes them)
CREATE INDEX IF NOT EXISTS idx_arcs_project_status ON arcs(project_id, status);

PRAGMA foreign_keys = ON;
