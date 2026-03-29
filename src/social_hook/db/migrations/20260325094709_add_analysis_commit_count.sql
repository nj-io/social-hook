-- Add analysis_commit_count to projects for commit_analysis_interval gating
ALTER TABLE projects ADD COLUMN analysis_commit_count INTEGER NOT NULL DEFAULT 0;

-- Add commit_analysis_json to evaluation_cycles for caching stage 1 results
ALTER TABLE evaluation_cycles ADD COLUMN commit_analysis_json TEXT DEFAULT NULL;
