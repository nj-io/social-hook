PRAGMA foreign_keys = OFF;

CREATE TABLE IF NOT EXISTS advisory_items (
    id                  TEXT PRIMARY KEY,
    project_id          TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    category            TEXT NOT NULL CHECK (category IN (
                            'platform_presence', 'product_infrastructure',
                            'content_asset', 'code_change',
                            'external_action', 'outreach')),
    title               TEXT NOT NULL,
    description         TEXT,
    status              TEXT NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'completed', 'dismissed')),
    urgency             TEXT NOT NULL DEFAULT 'normal'
                            CHECK (urgency IN ('blocking', 'normal')),
    created_by          TEXT NOT NULL,
    linked_entity_type  TEXT,
    linked_entity_id    TEXT,
    handler_type        TEXT,
    automation_level    TEXT NOT NULL DEFAULT 'manual'
                            CHECK (automation_level IN (
                                'manual', 'assisted', 'semi_automated', 'automated')),
    verification_method TEXT,
    due_date            TEXT,
    dismissed_reason    TEXT,
    completed_at        TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_advisory_project_status
    ON advisory_items(project_id, status);

CREATE INDEX IF NOT EXISTS idx_advisory_linked
    ON advisory_items(linked_entity_type, linked_entity_id)
    WHERE linked_entity_type IS NOT NULL;

PRAGMA foreign_keys = ON;
