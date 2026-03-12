PRAGMA foreign_keys = OFF;

CREATE TABLE decisions_new (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES projects(id),
    commit_hash   TEXT NOT NULL,
    commit_message TEXT,
    decision      TEXT NOT NULL CHECK (decision IN ('draft', 'hold', 'skip')),
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
    processed     INTEGER NOT NULL DEFAULT 0,
    processed_at  TEXT,
    batch_id      TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(project_id, commit_hash)
);

INSERT INTO decisions_new (
    id, project_id, commit_hash, commit_message, decision, reasoning,
    angle, episode_type, episode_tags, post_category, arc_id, media_tool,
    platforms, targets, commit_summary, consolidate_with, processed,
    processed_at, batch_id, created_at
) SELECT
    id, project_id, commit_hash, commit_message, decision, reasoning,
    angle, episode_type, '[]', post_category, arc_id, media_tool,
    platforms, '{}', commit_summary, NULL, processed, processed_at,
    batch_id, created_at
FROM decisions;
DROP TABLE decisions;
ALTER TABLE decisions_new RENAME TO decisions;

CREATE INDEX IF NOT EXISTS idx_decisions_project_time ON decisions(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_decisions_commit ON decisions(project_id, commit_hash);
CREATE INDEX IF NOT EXISTS idx_decisions_arc ON decisions(arc_id) WHERE arc_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_decisions_unprocessed ON decisions(project_id, created_at)
    WHERE decision = 'hold' AND processed = 0;

ALTER TABLE drafts ADD COLUMN is_intro INTEGER NOT NULL DEFAULT 0;
ALTER TABLE drafts ADD COLUMN post_format TEXT DEFAULT NULL
    CHECK (post_format IN ('single', 'thread', 'quote', 'reply'));
ALTER TABLE drafts ADD COLUMN reference_post_id TEXT DEFAULT NULL
    REFERENCES posts(id);

CREATE INDEX IF NOT EXISTS idx_drafts_intro ON drafts(project_id) WHERE is_intro = 1;
CREATE INDEX IF NOT EXISTS idx_drafts_reference_post ON drafts(reference_post_id) WHERE reference_post_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_posts_draft_id ON posts(draft_id);

PRAGMA foreign_keys = ON;
