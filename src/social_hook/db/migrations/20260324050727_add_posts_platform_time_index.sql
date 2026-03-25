CREATE INDEX IF NOT EXISTS idx_posts_platform_time ON posts(platform, posted_at DESC);
