-- Add hold_reason to content_topics for tracking why a topic is held
ALTER TABLE content_topics ADD COLUMN hold_reason TEXT;

-- Add arc_id to drafts for determining partial vs covered at posting time
ALTER TABLE drafts ADD COLUMN arc_id TEXT;

-- Index for joining drafts by topic_id (used by get_posts_by_topic_id)
CREATE INDEX IF NOT EXISTS idx_drafts_topic_id ON drafts(topic_id) WHERE topic_id IS NOT NULL;
