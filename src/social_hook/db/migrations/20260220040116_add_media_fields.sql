-- Migration 005: Add media_type and media_spec columns to drafts table
-- Supports per-draft media metadata for the media generation pipeline
ALTER TABLE drafts ADD COLUMN media_type TEXT;
ALTER TABLE drafts ADD COLUMN media_spec TEXT DEFAULT '{}';
