import type { Config, Draft, EnvVars, Project, WebEvent } from "./types";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
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

export async function updateConfig(data: Partial<Config>): Promise<{ status: string }> {
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

export async function sendMessage(text: string): Promise<{ events: WebEvent[] }> {
  return apiFetch("/api/message", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
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

// Validate API key
export async function validateApiKey(provider: string, key: string): Promise<{ valid: boolean; provider: string; error?: string }> {
  return apiFetch("/api/settings/validate-key", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, key }),
  });
}
