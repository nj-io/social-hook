-- Migration 010: Add session_id column to web_events for per-tab session isolation
ALTER TABLE web_events ADD COLUMN session_id TEXT DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_web_events_session ON web_events(session_id);
