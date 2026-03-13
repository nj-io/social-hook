-- Migration 003: Add paused column to projects table
-- Needed by /pause and /resume Telegram commands (T26)
ALTER TABLE projects ADD COLUMN paused INTEGER NOT NULL DEFAULT 0;
