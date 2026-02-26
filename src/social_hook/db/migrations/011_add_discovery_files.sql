-- Migration 011: Add discovery_files column to projects table
-- Stores JSON-serialized list of file paths selected during project discovery

ALTER TABLE projects ADD COLUMN discovery_files TEXT DEFAULT NULL;
