import type { Config, ChannelsStatusResponse, Decision, Draft, EnvVars, InstallationsStatus, Memory, PostRecord, Project, ProjectDetail, UsageSummary, Arc, WebEvent } from "./types";
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
export async function fetchDrafts(status?: string): Promise<{ drafts: Draft[] }> {
  const params = status ? `?status=${encodeURIComponent(status)}` : "";
  return apiFetch(`/api/drafts${params}`);
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
): Promise<{ decisions: Decision[] }> {
  const params = new URLSearchParams();
  if (limit != null) params.set("limit", String(limit));
  if (offset != null) params.set("offset", String(offset));
  const qs = params.toString();
  return apiFetch(`/api/projects/${encodeURIComponent(id)}/decisions${qs ? `?${qs}` : ""}`);
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
): Promise<{ status: string }> {
  return apiFetch(`/api/drafts/${encodeURIComponent(draftId)}/media-spec`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ media_spec: mediaSpec }),
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

// Platforms
export async function fetchEnabledPlatforms(): Promise<{ platforms: Record<string, { priority: string; type: string }>; count: number }> {
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
