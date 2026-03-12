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
  max_per_week?: number;
  thread_min_tweets?: number;
}

export interface MediaToolGuidance {
  enabled?: boolean | null;  // null = inherit global
  use_when?: string[];
  constraints?: string[];
  prompt_example?: string;
}

export interface MediaGenerationConfig {
  enabled: boolean;
  tools: Record<string, boolean>;
}

export interface JourneyCaptureConfig {
  enabled: boolean;
  model?: string;
}

export interface ConsolidationConfig {
  enabled: boolean;
  mode: string;
  batch_size: number;
  auto_consolidate_drafts: boolean;
  consolidate_approved: boolean;
  time_window_hours: number;
  time_window_max_drafts: number;
}

export interface Config {
  models: ModelsConfig;
  platforms: Record<string, PlatformConfig>;
  scheduling: SchedulingConfig;
  media_generation: MediaGenerationConfig;
  journey_capture: JourneyCaptureConfig;
  consolidation?: ConsolidationConfig;
  channels?: Record<string, ChannelConfig>;
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
  media_spec?: string;
  media_spec_used?: string;
  reasoning?: string;
  last_error?: string;
  retry_count?: number;
  is_intro: boolean;
  post_format: string | null;
  reference_post_id: string | null;
  created_at: string;
  updated_at?: string;
  tweets?: DraftTweet[];
  changes?: DraftChange[];
  decision_id?: string;
  decision?: Decision;
}

export interface Project {
  id: string;
  repo_path: string;
  name: string;
  created_at: string;
  paused: number;
  summary?: string;
  phase?: string;
  trigger_branch?: string | null;
  confidence?: number;
  git_hook_installed?: boolean;
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
  key_groups: Record<string, string[]>;
}

export interface Decision {
  id: string;
  project_id: string;
  commit_hash: string;
  commit_message: string;
  decision: string;
  reasoning: string;
  angle: string;
  episode_type: string;
  episode_tags: string[];
  post_category: string;
  arc_id?: string;
  media_tool?: string;
  platforms: string;
  targets: Record<string, unknown>;
  consolidate_with: string[] | null;
  draft_count: number;
  draft_ids?: string[];
  branch?: string | null;
  created_at: string;
}

export interface PostRecord {
  id: string;
  draft_id: string;
  project_id: string;
  platform: string;
  external_id?: string;
  external_url?: string;
  content: string;
  posted_at: string;
}

export interface Lifecycle {
  project_id: string;
  phase: string;
  confidence: number;
  evidence: string;
  updated_at: string;
}

export interface Arc {
  id: string;
  project_id: string;
  theme: string;
  status: string;
  post_count: number;
  notes?: string;
  last_post_at?: string;
  started_at: string;
  ended_at?: string;
  updated_at?: string;
}

export interface NarrativeDebt {
  project_id: string;
  debt_counter: number;
  last_synthesis_at?: string;
}

export interface UsageEntry {
  id: string;
  operation_type: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cost_cents: number;
  created_at: string;
}

export interface UsageSummary {
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_cents: number;
  entries: UsageEntry[];
}

export interface InstallationsStatus {
  commit_hook: boolean;
  narrative_hook: boolean;
  scheduler_cron: boolean;
  bot_daemon: boolean;
}

export interface ChannelConfig {
  enabled: boolean;
  allowed_chat_ids: string[];
}

export interface ChannelStatus {
  enabled: boolean;
  credentials_configured: boolean;
  allowed_chat_ids: string[];
}

export interface ChannelsStatusResponse {
  channels: Record<string, ChannelStatus>;
  daemon_running: boolean;
}

export interface DataChangeEvent {
  entity: string;
  action: string;
  entity_id: string;
  project_id: string;
  content?: string;
  platform?: string;
}

export interface Memory {
  date: string;
  context: string;
  feedback: string;
  draft_id: string;
}

export interface ProjectDetail extends Project {
  lifecycle?: Lifecycle;
  arcs: Arc[];
  narrative_debt?: NarrativeDebt;
  decision_counts: Record<string, number>;
  draft_count: number;
  post_count: number;
  narrative_count: number;
  journey_capture_enabled?: boolean;
}
