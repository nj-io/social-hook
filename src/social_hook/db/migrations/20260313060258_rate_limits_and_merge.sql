PRAGMA foreign_keys = OFF;

-- Rebuild decisions table with expanded CHECK constraint and trigger_source column
CREATE TABLE decisions_new (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES projects(id),
    commit_hash   TEXT NOT NULL,
    commit_message TEXT,
    decision      TEXT NOT NULL CHECK (decision IN ('draft', 'hold', 'skip', 'imported', 'deferred_eval')),
    reasoning     TEXT NOT NULL,
    angle         TEXT,
    episode_type  TEXT CHECK (episode_type IN
        ('decision','before_after','demo_proof','milestone','postmortem','launch','synthesis')),
    episode_tags  TEXT DEFAULT '[]',
    post_category TEXT CHECK (post_category IN ('arc', 'opportunistic', 'experiment')),
    arc_id        TEXT REFERENCES arcs(id),
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

INSERT INTO decisions_new (
    id, project_id, commit_hash, commit_message, decision, reasoning,
    angle, episode_type, episode_tags, post_category, arc_id, media_tool,
    platforms, targets, commit_summary, consolidate_with, reference_posts,
    branch, trigger_source, processed, processed_at, batch_id, created_at
) SELECT
    id, project_id, commit_hash, commit_message, decision, reasoning,
    angle, episode_type, episode_tags, post_category, arc_id, media_tool,
    platforms, targets, commit_summary, consolidate_with, reference_posts,
    branch, 'commit', processed, processed_at, batch_id, created_at
FROM decisions;

DROP TABLE decisions;
ALTER TABLE decisions_new RENAME TO decisions;

-- Recreate all existing indexes
CREATE INDEX IF NOT EXISTS idx_decisions_project_time ON decisions(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_decisions_commit ON decisions(project_id, commit_hash);
CREATE INDEX IF NOT EXISTS idx_decisions_arc ON decisions(arc_id) WHERE arc_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_decisions_unprocessed ON decisions(project_id, created_at)
    WHERE decision = 'hold' AND processed = 0;
CREATE INDEX IF NOT EXISTS idx_decisions_branch ON decisions(project_id, branch)
    WHERE branch IS NOT NULL;

-- New partial index for deferred evaluations
CREATE INDEX IF NOT EXISTS idx_decisions_deferred ON decisions(project_id, created_at)
    WHERE decision = 'deferred_eval' AND processed = 0;

-- Add trigger_source to usage_log
ALTER TABLE usage_log ADD COLUMN trigger_source TEXT DEFAULT 'auto';

PRAGMA foreign_keys = ON;
