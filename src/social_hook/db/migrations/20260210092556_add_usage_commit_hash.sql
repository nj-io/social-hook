-- Migration 004: Add commit_hash column to usage_log table
-- Enables per-operation tracking of which commit triggered the API call
ALTER TABLE usage_log ADD COLUMN commit_hash TEXT;
