-- Migration 007: Add commit_message to decisions for history-rewrite resilience
ALTER TABLE decisions ADD COLUMN commit_message TEXT;
