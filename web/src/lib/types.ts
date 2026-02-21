export interface SchedulingOverride {
  optimal_days?: string[];
  optimal_hours?: number[];
  max_posts_per_day?: number;
  min_gap_minutes?: number;
}

export interface PlatformConfig {
  enabled: boolean;
  priority: "primary" | "secondary";
  type: "builtin" | "custom";
  account_tier?: string;
  description?: string;
  format?: string;
  max_length?: number;
  filter?: string;
  frequency?: string;
  scheduling?: SchedulingOverride;
}

export interface ModelsConfig {
  evaluator: string;
  drafter: string;
  gatekeeper: string;
}

export interface SchedulingConfig {
  timezone: string;
  max_posts_per_day: number;
  min_gap_minutes: number;
  optimal_days: string[];
  optimal_hours: number[];
}

export interface ImageGenerationConfig {
  enabled: boolean;
  service: string;
}

export interface JourneyCaptureConfig {
  enabled: boolean;
  model?: string;
}

export interface WebDashboardConfig {
  enabled: boolean;
  port: number;
}

export interface Config {
  models: ModelsConfig;
  platforms: Record<string, PlatformConfig>;
  scheduling: SchedulingConfig;
  image_generation: ImageGenerationConfig;
  journey_capture: JourneyCaptureConfig;
  web: WebDashboardConfig;
}

export interface DraftTweet {
  id: string;
  draft_id: string;
  position: number;
  content: string;
}

export interface DraftChange {
  id: string;
  draft_id: string;
  field: string;
  old_value: string;
  new_value: string;
  changed_by: string;
  changed_at: string;
}

export interface Draft {
  id: string;
  project_id: string;
  platform: string;
  content: string;
  status: string;
  suggested_time?: string;
  media_paths?: string;
  media_type?: string;
  reasoning?: string;
  created_at: string;
  updated_at?: string;
  tweets?: DraftTweet[];
  changes?: DraftChange[];
}

export interface Project {
  id: string;
  path: string;
  name: string;
  created_at: string;
}

export interface WebEvent {
  id: number;
  type: string;
  data: Record<string, unknown>;
  created_at: string;
}

export interface EnvVars {
  env: Record<string, string>;
  known_keys: string[];
}
