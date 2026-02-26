-- Migration 009: Add consolidation fields to decisions table
ALTER TABLE decisions ADD COLUMN commit_summary TEXT;
ALTER TABLE decisions ADD COLUMN processed INTEGER NOT NULL DEFAULT 0;
ALTER TABLE decisions ADD COLUMN processed_at TEXT;
ALTER TABLE decisions ADD COLUMN batch_id TEXT;

-- Mark existing consolidate/deferred decisions as already processed
UPDATE decisions SET processed = 1 WHERE decision IN ('consolidate', 'deferred');

-- Partial index for efficient lookup of unprocessed consolidation decisions
CREATE INDEX IF NOT EXISTS idx_decisions_unprocessed ON decisions(project_id, created_at)
    WHERE decision IN ('consolidate', 'deferred') AND processed = 0;
