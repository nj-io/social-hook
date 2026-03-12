-- Migration 017: Add reference_posts to decisions
-- Stores JSON array of post IDs that the evaluator identified as relevant
-- for the drafter to reference when creating new content.
ALTER TABLE decisions ADD COLUMN reference_posts TEXT DEFAULT NULL;
