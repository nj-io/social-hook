ALTER TABLE system_errors ADD COLUMN component TEXT DEFAULT '';
ALTER TABLE system_errors ADD COLUMN run_id TEXT DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_system_errors_severity ON system_errors(severity, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_system_errors_component ON system_errors(component, created_at DESC);
