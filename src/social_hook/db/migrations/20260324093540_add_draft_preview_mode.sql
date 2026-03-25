ALTER TABLE drafts ADD COLUMN preview_mode INTEGER NOT NULL DEFAULT 0;
UPDATE drafts SET preview_mode = 1 WHERE platform = 'preview';
