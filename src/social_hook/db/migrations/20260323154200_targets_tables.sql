-- Content topic queue
CREATE TABLE IF NOT EXISTS content_topics (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    strategy TEXT NOT NULL,
    topic TEXT NOT NULL,
    description TEXT,
    priority_rank INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'uncovered'
        CHECK (status IN ('uncovered', 'holding', 'partial', 'covered')),
    commit_count INTEGER NOT NULL DEFAULT 0,
    last_commit_at TEXT,
    last_posted_at TEXT,
    created_by TEXT NOT NULL DEFAULT 'user',
    created_at TEXT DEFAULT (datetime('now'))
);

-- Operator content suggestions
CREATE TABLE IF NOT EXISTS content_suggestions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    strategy TEXT,
    idea TEXT NOT NULL,
    media_refs TEXT DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'evaluated', 'drafted', 'dismissed')),
    source TEXT NOT NULL DEFAULT 'operator',
    created_at TEXT DEFAULT (datetime('now')),
    evaluated_at TEXT
);

-- Evaluation cycle grouping
CREATE TABLE IF NOT EXISTS evaluation_cycles (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    trigger_type TEXT NOT NULL,
    trigger_ref TEXT,
    commit_analysis_id TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Observational content format patterns
CREATE TABLE IF NOT EXISTS draft_patterns (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    pattern_name TEXT NOT NULL,
    description TEXT,
    example_draft_id TEXT,
    created_by TEXT NOT NULL DEFAULT 'operator',
    created_at TEXT DEFAULT (datetime('now'))
);
