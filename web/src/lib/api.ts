import type { Config, ChannelsStatusResponse, Decision, Draft, EnvVars, InstallationsStatus, Memory, PostRecord, Project, ProjectDetail, RateLimitStatus, StrategyTemplate, UsageSummary, Arc, WebEvent, PlatformCredential, Account, Target, Strategy, Topic, Brief, ContentSuggestion, EvaluationCycle, SystemError, SystemHealth, PlatformSettings } from "./types";
import { getSessionId } from "./session";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("X-Session-Id", getSessionId());
  const res = await fetch(path, { ...init, headers });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API error ${res.status}: ${body}`);
  }
  return res.json();
}

// Config
export async function fetchConfig(): Promise<{ config: Record<string, unknown> }> {
  return apiFetch("/api/settings/config");
}

export async function updateConfig(data: Partial<Config>): Promise<{ status: string; hook_warning?: string }> {
  return apiFetch("/api/settings/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

// Env
export async function fetchEnv(): Promise<EnvVars> {
  return apiFetch("/api/settings/env");
}

export async function updateEnv(key: string, value: string | null): Promise<{ status: string }> {
  return apiFetch("/api/settings/env", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, value }),
  });
}

// Drafts
export async function fetchDrafts(filters?: {
  status?: string;
  project_id?: string;
  decision_id?: string;
  commit?: string;
}): Promise<{ drafts: Draft[] }> {
  const params = new URLSearchParams();
  if (filters?.status) params.set("status", filters.status);
  if (filters?.project_id) params.set("project_id", filters.project_id);
  if (filters?.decision_id) params.set("decision_id", filters.decision_id);
  if (filters?.commit) params.set("commit", filters.commit);
  const qs = params.toString();
  return apiFetch(`/api/drafts${qs ? `?${qs}` : ""}`);
}

export async function fetchDraft(id: string): Promise<Draft> {
  return apiFetch(`/api/drafts/${encodeURIComponent(id)}`);
}

// Projects
export async function fetchProjects(): Promise<{ projects: Project[] }> {
  return apiFetch("/api/projects");
}

// Project detail
export async function fetchProjectDetail(id: string): Promise<ProjectDetail> {
  return apiFetch(`/api/projects/${encodeURIComponent(id)}`);
}

export async function fetchProjectDecisions(
  id: string,
  limit?: number,
  offset?: number,
  branch?: string | null,
): Promise<{ decisions: Decision[]; total: number }> {
  const params = new URLSearchParams();
  if (limit != null) params.set("limit", String(limit));
  if (offset != null) params.set("offset", String(offset));
  if (branch) params.set("branch", branch);
  const qs = params.toString();
  return apiFetch(`/api/projects/${encodeURIComponent(id)}/decisions${qs ? `?${qs}` : ""}`);
}

export async function fetchDecisionBranches(id: string): Promise<{ branches: string[] }> {
  return apiFetch(`/api/projects/${encodeURIComponent(id)}/decision-branches`);
}

export async function fetchImportPreview(
  id: string,
  branch?: string | null,
): Promise<{ total_commits: number; already_tracked: number; importable: number }> {
  const params = branch ? `?branch=${encodeURIComponent(branch)}` : "";
  return apiFetch(`/api/projects/${encodeURIComponent(id)}/import-preview${params}`);
}

export async function importCommits(
  id: string,
  branch?: string | null,
): Promise<{ task_id: string; status: string }> {
  return apiFetch(`/api/projects/${encodeURIComponent(id)}/import-commits`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(branch ? { branch } : {}),
  });
}

export async function fetchProjectPosts(
  id: string,
  limit?: number,
): Promise<{ posts: PostRecord[] }> {
  const params = limit != null ? `?limit=${limit}` : "";
  return apiFetch(`/api/projects/${encodeURIComponent(id)}/posts${params}`);
}

export async function fetchProjectUsage(
  id: string,
  days?: number,
): Promise<UsageSummary> {
  const params = days != null ? `?days=${days}` : "";
  return apiFetch(`/api/projects/${encodeURIComponent(id)}/usage${params}`);
}

export async function fetchProjectArcs(
  id: string,
): Promise<{ arcs: Arc[] }> {
  return apiFetch(`/api/projects/${encodeURIComponent(id)}/arcs`);
}

export async function createProjectArc(
  projectId: string,
  theme: string,
  notes?: string,
): Promise<{ arc_id: string; status: string }> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/arcs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ theme, notes: notes || undefined }),
  });
}

export async function updateProjectArc(
  projectId: string,
  arcId: string,
  updates: { status?: string; notes?: string },
): Promise<{ status: string }> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/arcs/${encodeURIComponent(arcId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
}

// Project summary
export async function updateProjectSummary(
  projectId: string,
  summary: string,
): Promise<{ status: string }> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/summary`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ summary }),
  });
}

export async function regenerateProjectSummary(
  projectId: string,
): Promise<{ summary: string }> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/regenerate-summary`, {
    method: "POST",
  });
}

// Bot interaction
export async function sendCommand(text: string): Promise<{ events: WebEvent[] }> {
  return apiFetch("/api/command", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

export async function sendCallback(action: string, payload: string): Promise<{ events: WebEvent[] }> {
  return apiFetch("/api/callback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, payload }),
  });
}

export async function sendCallbackExtended(
  action: string,
  payload: string,
  data: Record<string, unknown>,
): Promise<{ events: WebEvent[] }> {
  return apiFetch("/api/callback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, payload, ...data }),
  });
}

export async function sendMessage(text: string): Promise<{ events: WebEvent[] }> {
  return apiFetch("/api/message", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

export async function fetchChatHistory(): Promise<{ events: WebEvent[] }> {
  return apiFetch("/api/events/history");
}

export async function clearChatHistory(): Promise<{ ok: boolean }> {
  return apiFetch("/api/events/clear", { method: "POST" });
}

// Social context
export async function fetchSocialContext(projectPath?: string): Promise<{ content: string; path: string }> {
  const params = projectPath ? `?project_path=${encodeURIComponent(projectPath)}` : "";
  return apiFetch(`/api/settings/social-context${params}`);
}

export async function updateSocialContext(projectPath: string, content: string): Promise<{ status: string }> {
  return apiFetch("/api/settings/social-context", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_path: projectPath, content }),
  });
}

// Content config
export async function fetchContentConfig(projectPath?: string): Promise<{ content: string; path: string }> {
  const params = projectPath ? `?project_path=${encodeURIComponent(projectPath)}` : "";
  return apiFetch(`/api/settings/content-config${params}`);
}

export async function updateContentConfig(projectPath: string, content: string): Promise<{ status: string }> {
  return apiFetch("/api/settings/content-config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_path: projectPath, content }),
  });
}

// Content config (parsed/structured)
export async function fetchContentConfigParsed(projectPath?: string): Promise<Record<string, unknown>> {
  const params = projectPath ? `?project_path=${encodeURIComponent(projectPath)}` : "";
  return apiFetch(`/api/settings/content-config/parsed${params}`);
}

export async function updateContentConfigParsed(
  sections: Record<string, unknown>,
  projectPath?: string,
): Promise<{ status: string }> {
  const params = projectPath ? `?project_path=${encodeURIComponent(projectPath)}` : "";
  return apiFetch(`/api/settings/content-config/parsed${params}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(sections),
  });
}

// Projects (actions)
export async function toggleProjectPause(projectId: string): Promise<{ status: string; paused: number }> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/pause`, {
    method: "PUT",
  });
}

// Project branches
export async function fetchProjectBranches(id: string): Promise<{ branches: string[]; current: string | null; error?: string }> {
  return apiFetch(`/api/projects/${encodeURIComponent(id)}/branches`);
}

export async function updateProjectTriggerBranch(id: string, branch: string | null): Promise<{ status: string; trigger_branch: string | null }> {
  return apiFetch(`/api/projects/${encodeURIComponent(id)}/trigger-branch`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ branch }),
  });
}

// Validate API key
export async function validateApiKey(provider: string, key: string): Promise<{ valid: boolean; provider: string; error?: string }> {
  return apiFetch("/api/settings/validate-key", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, key }),
  });
}

// Branding
export async function fetchBranding(): Promise<{ name: string; slug: string; description: string }> {
  return apiFetch("/api/branding");
}

// Installations
export async function fetchInstallationsStatus(): Promise<InstallationsStatus> {
  return apiFetch("/api/installations/status");
}

export async function installComponent(component: string): Promise<{ success: boolean; message: string }> {
  return apiFetch(`/api/installations/${encodeURIComponent(component)}/install`, { method: "POST" });
}

export async function uninstallComponent(component: string): Promise<{ success: boolean; message: string }> {
  return apiFetch(`/api/installations/${encodeURIComponent(component)}/uninstall`, { method: "POST" });
}

export async function startBotDaemon(): Promise<{ success: boolean; message: string }> {
  return apiFetch("/api/installations/bot_daemon/start", { method: "POST" });
}

export async function stopBotDaemon(): Promise<{ success: boolean; message: string }> {
  return apiFetch("/api/installations/bot_daemon/stop", { method: "POST" });
}

// Channels
export async function fetchChannelsStatus(): Promise<ChannelsStatusResponse> {
  return apiFetch("/api/channels/status");
}

export async function testChannel(channel: string): Promise<{ success: boolean; error?: string; info?: Record<string, string> }> {
  return apiFetch(`/api/channels/${encodeURIComponent(channel)}/test`, { method: "POST" });
}

// Draft media spec
export async function updateDraftMediaSpec(
  draftId: string,
  mediaSpec: Record<string, unknown>,
  mediaType?: string,
): Promise<{ status: string }> {
  const body: Record<string, unknown> = { media_spec: mediaSpec };
  if (mediaType) body.media_type = mediaType;
  return apiFetch(`/api/drafts/${encodeURIComponent(draftId)}/media-spec`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function uploadDraftMedia(
  draftId: string,
  file: File,
): Promise<{ status: string; media_paths: string[] }> {
  const form = new FormData();
  form.append("file", file);
  const headers = new Headers();
  headers.set("X-Session-Id", getSessionId());
  const res = await fetch(`/api/drafts/${encodeURIComponent(draftId)}/media-upload`, {
    method: "POST",
    headers,
    body: form,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Upload failed ${res.status}: ${body}`);
  }
  return res.json();
}

export async function generateMediaSpec(
  draftId: string,
  mediaType: string,
): Promise<{ task_id: string; status: string }> {
  return apiFetch(`/api/drafts/${encodeURIComponent(draftId)}/generate-spec`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tool_name: mediaType }),
  });
}

export async function resendDraftNotification(
  draftId: string,
): Promise<{ success: boolean; message: string }> {
  return apiFetch(`/api/drafts/${encodeURIComponent(draftId)}/resend-notification`, {
    method: "POST",
  });
}

// Decisions
export async function createDraftFromDecision(
  decisionId: string,
  platform?: string,
): Promise<{ task_id: string; status: string }> {
  return apiFetch(`/api/decisions/${encodeURIComponent(decisionId)}/create-draft`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(platform ? { platform } : {}),
  });
}

export async function deleteDecision(
  decisionId: string,
): Promise<{ status: string; decision_id: string }> {
  return apiFetch(`/api/decisions/${encodeURIComponent(decisionId)}`, {
    method: "DELETE",
  });
}

export async function retriggerDecision(
  decisionId: string,
): Promise<{ status: string; exit_code: number }> {
  return apiFetch(`/api/decisions/${encodeURIComponent(decisionId)}/retrigger`, {
    method: "POST",
  });
}

// Promote
export async function promoteDraft(
  draftId: string,
  platform: string,
): Promise<{ task_id: string; status: string }> {
  return apiFetch(`/api/drafts/${encodeURIComponent(draftId)}/promote`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ platform }),
  });
}

// Platforms
export async function fetchEnabledPlatforms(): Promise<{ platforms: Record<string, { priority: string; type: string }>; count: number; real_count: number }> {
  return apiFetch("/api/platforms/enabled");
}

// Consolidation
export async function consolidateDecisions(
  decisionIds: string[],
): Promise<{ task_id: string; status: string }> {
  return apiFetch("/api/decisions/consolidate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision_ids: decisionIds }),
  });
}

// Background tasks
export interface BackgroundTask {
  id: string;
  type: string;
  ref_id: string;
  project_id: string;
  status: "running" | "completed" | "failed";
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  updated_at: string | null;
}

export async function fetchTasks(params: {
  type?: string;
  ref_id?: string;
  project_id?: string;
  status?: string;
}): Promise<{ tasks: BackgroundTask[] }> {
  const qs = new URLSearchParams();
  if (params.type) qs.set("type", params.type);
  if (params.ref_id) qs.set("ref_id", params.ref_id);
  if (params.project_id) qs.set("project_id", params.project_id);
  if (params.status) qs.set("status", params.status);
  return apiFetch(`/api/tasks?${qs.toString()}`);
}

// Memories
export async function fetchMemories(projectPath: string): Promise<{ memories: Memory[]; count: number }> {
  return apiFetch(`/api/settings/memories?project_path=${encodeURIComponent(projectPath)}`);
}

export async function addMemory(projectPath: string, context: string, feedback: string, draftId?: string): Promise<{ status: string }> {
  return apiFetch("/api/settings/memories", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_path: projectPath, context, feedback, draft_id: draftId ?? "" }),
  });
}

export async function deleteMemory(projectPath: string, index: number): Promise<{ status: string }> {
  return apiFetch(`/api/settings/memories/${index}?project_path=${encodeURIComponent(projectPath)}`, {
    method: "DELETE",
  });
}

export async function clearMemories(projectPath: string): Promise<{ status: string; count: number }> {
  return apiFetch(`/api/settings/memories/clear?project_path=${encodeURIComponent(projectPath)}`, {
    method: "POST",
  });
}

// Filesystem browser
export async function browseDirectory(path?: string): Promise<{
  current: string;
  parent: string;
  is_git: boolean;
  directories: { name: string; path: string; is_git: boolean }[];
}> {
  const params = path ? `?path=${encodeURIComponent(path)}` : "";
  return apiFetch(`/api/filesystem/browse${params}`);
}

// Git hook
export async function fetchGitHookStatus(projectId: string): Promise<{ installed: boolean }> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/git-hook/status`);
}

export async function installGitHook(projectId: string): Promise<{ success: boolean; message: string }> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/git-hook/install`, { method: "POST" });
}

export async function uninstallGitHook(projectId: string): Promise<{ success: boolean; message: string }> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/git-hook/uninstall`, { method: "POST" });
}

// Project registration
export async function registerProject(
  repoPath: string,
  name?: string,
  installHook: boolean = true,
): Promise<{
  status: string;
  project: { id: string; name: string; repo_path: string; repo_origin: string | null };
  git_hook: string | null;
}> {
  return apiFetch("/api/projects/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      repo_path: repoPath,
      name: name || undefined,
      install_git_hook: installHook,
    }),
  });
}

export async function deleteProject(projectId: string): Promise<{ status: string; project_id: string }> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}`, { method: "DELETE" });
}

// Rate limits
export async function fetchRateLimits(): Promise<RateLimitStatus> {
  return apiFetch("/api/rate-limits/status");
}

// Wizard templates
export async function fetchWizardTemplates(): Promise<{ templates: StrategyTemplate[] }> {
  return apiFetch("/api/wizard/templates");
}

// Summary draft
export async function createSummaryDraft(
  projectId: string,
): Promise<{ task_id: string; status: string }> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/summary-draft`, {
    method: "POST",
  });
}

// --- Targets API ---

// Platform Credentials
export async function fetchPlatformCredentials(): Promise<{ credentials: PlatformCredential[] }> {
  return apiFetch("/api/platform-credentials");
}

export async function addPlatformCredential(data: { platform: string; name: string; credentials?: Record<string, string> }): Promise<{ status: string }> {
  return apiFetch("/api/platform-credentials", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function deletePlatformCredential(name: string): Promise<{ status: string }> {
  return apiFetch(`/api/platform-credentials/${encodeURIComponent(name)}`, { method: "DELETE" });
}

export async function validatePlatformCredential(name: string): Promise<{ valid: boolean; error?: string }> {
  return apiFetch(`/api/platform-credentials/${encodeURIComponent(name)}/validate`, { method: "POST" });
}

// Accounts
export async function fetchAccounts(): Promise<{ accounts: Account[] }> {
  return apiFetch("/api/accounts");
}

export async function addAccount(data: { platform: string; name: string }): Promise<{ auth_url?: string; status: string }> {
  return apiFetch("/api/accounts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function deleteAccount(name: string): Promise<{ status: string }> {
  return apiFetch(`/api/accounts/${encodeURIComponent(name)}`, { method: "DELETE" });
}

export async function validateAccounts(): Promise<{ results: Record<string, { valid: boolean; error?: string }> }> {
  return apiFetch("/api/accounts/validate", { method: "POST" });
}

// Targets
export async function fetchTargets(projectId: string): Promise<{ targets: Target[] }> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/targets`);
}

export async function addTarget(projectId: string, data: { account: string; destination: string; strategy: string; frequency?: string }): Promise<{ status: string; name: string }> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/targets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function disableTarget(projectId: string, name: string): Promise<{ status: string }> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/targets/${encodeURIComponent(name)}/disable`, { method: "PUT" });
}

export async function enableTarget(projectId: string, name: string): Promise<{ status: string }> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/targets/${encodeURIComponent(name)}/enable`, { method: "PUT" });
}

// Strategies
export async function fetchStrategies(projectId: string): Promise<{ strategies: Strategy[] }> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/strategies`);
}

export async function fetchStrategy(projectId: string, name: string): Promise<Strategy> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/strategies/${encodeURIComponent(name)}`);
}

export async function updateStrategy(projectId: string, name: string, data: Partial<Strategy>): Promise<{ status: string }> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/strategies/${encodeURIComponent(name)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function resetStrategy(projectId: string, name: string): Promise<{ status: string }> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/strategies/${encodeURIComponent(name)}/reset`, { method: "POST" });
}

// Topics
export async function fetchTopics(projectId: string, strategy?: string): Promise<{ topics: Topic[] }> {
  const params = strategy ? `?strategy=${encodeURIComponent(strategy)}` : "";
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/topics${params}`);
}

export async function addTopic(projectId: string, data: { strategy: string; topic: string; description?: string }): Promise<{ status: string; topic: Topic }> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/topics`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function updateTopic(projectId: string, topicId: string, data: { description?: string; priority_rank?: number }): Promise<{ status: string }> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/topics/${encodeURIComponent(topicId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function setTopicStatus(projectId: string, topicId: string, status: string): Promise<{ status: string }> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/topics/${encodeURIComponent(topicId)}/status`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
}

export async function reorderTopics(projectId: string, topicIds: string[]): Promise<{ status: string }> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/topics/reorder`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic_ids: topicIds }),
  });
}

export async function draftNowTopic(projectId: string, topicId: string): Promise<{ task_id: string; status: string }> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/topics/${encodeURIComponent(topicId)}/draft-now`, { method: "POST" });
}

// Brief
export async function fetchBrief(projectId: string): Promise<Brief> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/brief`);
}

export async function updateBrief(projectId: string, sections: Record<string, string>): Promise<{ status: string }> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/brief`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sections }),
  });
}

// Content Suggestions
export async function fetchSuggestions(projectId: string): Promise<{ suggestions: ContentSuggestion[] }> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/suggestions`);
}

export async function createSuggestion(projectId: string, data: { idea: string; strategy?: string }): Promise<{ status: string; task_id?: string }> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/suggestions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function dismissSuggestion(projectId: string, suggestionId: string): Promise<{ status: string }> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/suggestions/${encodeURIComponent(suggestionId)}/dismiss`, { method: "PUT" });
}

export async function combineTopics(projectId: string, topicIds: string[]): Promise<{ task_id: string; status: string }> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/content/combine`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic_ids: topicIds }),
  });
}

export async function heroLaunch(projectId: string): Promise<{ task_id: string; status: string }> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/content/hero-launch`, { method: "POST" });
}

// Evaluation Cycles
export async function fetchCycles(projectId: string): Promise<{ cycles: EvaluationCycle[] }> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/cycles`);
}

export async function fetchCycleDetail(projectId: string, cycleId: string): Promise<EvaluationCycle> {
  return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/cycles/${encodeURIComponent(cycleId)}`);
}

export async function approveAllCycleDrafts(
  projectId: string,
  cycleId: string,
): Promise<{ status: string; approved_count: number; draft_ids?: string[] }> {
  return apiFetch(
    `/api/projects/${encodeURIComponent(projectId)}/cycles/${encodeURIComponent(cycleId)}/approve-all`,
    { method: "POST" },
  );
}

// System
export async function fetchSystemErrors(): Promise<{ errors: SystemError[] }> {
  return apiFetch("/api/system/errors");
}

export async function fetchSystemHealth(): Promise<SystemHealth> {
  return apiFetch("/api/system/health");
}

// Platform Settings
export async function fetchPlatformSettings(): Promise<{ settings: PlatformSettings[] }> {
  return apiFetch("/api/platform-settings");
}

export async function updatePlatformSettings(platform: string, data: { cross_account_gap_minutes: number }): Promise<{ status: string }> {
  return apiFetch(`/api/platform-settings/${encodeURIComponent(platform)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}
