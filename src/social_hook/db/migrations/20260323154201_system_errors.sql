-- System error persistence — shared across all processes (scheduler, CLI, web)
CREATE TABLE IF NOT EXISTS system_errors (
    id TEXT PRIMARY KEY,
    severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'error', 'critical')),
    message TEXT NOT NULL,
    context TEXT DEFAULT '{}',
    source TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
