-- New columns on drafts
ALTER TABLE drafts ADD COLUMN target_id TEXT;
ALTER TABLE drafts ADD COLUMN evaluation_cycle_id TEXT;
ALTER TABLE drafts ADD COLUMN topic_id TEXT;
ALTER TABLE drafts ADD COLUMN suggestion_id TEXT;
ALTER TABLE drafts ADD COLUMN pattern_id TEXT;

-- New columns on posts
ALTER TABLE posts ADD COLUMN target_id TEXT;
ALTER TABLE posts ADD COLUMN topic_tags TEXT DEFAULT '[]';
ALTER TABLE posts ADD COLUMN feature_tags TEXT DEFAULT '[]';
ALTER TABLE posts ADD COLUMN is_thread_head INTEGER DEFAULT 0;

-- Brief section edit metadata on projects
ALTER TABLE projects ADD COLUMN brief_section_metadata TEXT DEFAULT '{}';

-- Indexes for Phase 2 queries (filter drafts/posts by target)
CREATE INDEX IF NOT EXISTS idx_drafts_target ON drafts(target_id) WHERE target_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_posts_target ON posts(target_id) WHERE target_id IS NOT NULL;
