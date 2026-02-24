"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchConfig, fetchContentConfig, fetchEnv, fetchProjects, fetchSocialContext, updateConfig, updateContentConfig, updateSocialContext } from "@/lib/api";
import type { Config, JourneyCaptureConfig, MediaGenerationConfig, ModelsConfig, PlatformConfig, Project, SchedulingConfig, WebDashboardConfig } from "@/lib/types";
import { SettingsSidebar } from "@/components/settings/settings-sidebar";
import { ModelsSection } from "@/components/settings/models-section";
import { ApiKeysSection } from "@/components/settings/api-keys-section";
import { PlatformsSection } from "@/components/settings/platforms-section";
import { SchedulingSection } from "@/components/settings/scheduling-section";
import { TextEditorSection } from "@/components/settings/text-editor-section";
import { MediaGenerationSection } from "@/components/settings/media-generation-section";
import { NotificationsSection } from "@/components/settings/notifications-section";
import { ProjectsSection } from "@/components/settings/projects-section";

const DEFAULT_MODELS: ModelsConfig = {
  evaluator: "anthropic/claude-opus-4-5",
  drafter: "anthropic/claude-opus-4-5",
  gatekeeper: "anthropic/claude-haiku-4-5",
};

const DEFAULT_SCHEDULING: SchedulingConfig = {
  timezone: "UTC",
  max_posts_per_day: 3,
  min_gap_minutes: 30,
  optimal_days: ["Tue", "Wed", "Thu"],
  optimal_hours: [9, 12, 17],
};

export default function SettingsPage() {
  const [section, setSection] = useState("models");
  const [config, setConfig] = useState<Record<string, unknown> | null>(null);
  const [envData, setEnvData] = useState<{ env: Record<string, string>; known_keys: string[]; key_groups: Record<string, string[]> } | null>(null);
  const [socialCtx, setSocialCtx] = useState<{ content: string; path: string } | null>(null);
  const [contentCfg, setContentCfg] = useState<{ content: string; path: string } | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectPath, setSelectedProjectPath] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState("");

  const loadAll = useCallback(async () => {
    try {
      const [cfgRes, envRes, scRes, ccRes, projRes] = await Promise.all([
        fetchConfig(),
        fetchEnv(),
        fetchSocialContext(),
        fetchContentConfig(),
        fetchProjects(),
      ]);
      setConfig(cfgRes.config);
      setEnvData(envRes);
      setSocialCtx(scRes);
      setContentCfg(ccRes);
      setProjects(projRes.projects);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  // Listen for navigation events from child components (e.g. Notifications → API Keys link)
  useEffect(() => {
    function handleNavigate(e: Event) {
      const detail = (e as CustomEvent<string>).detail;
      if (detail) setSection(detail);
    }
    window.addEventListener("settings-navigate", handleNavigate);
    return () => window.removeEventListener("settings-navigate", handleNavigate);
  }, []);

  async function saveConfig(updates: Partial<Config>) {
    setSaving(true);
    setSaveStatus("");
    try {
      await updateConfig(updates);
      setSaveStatus("Saved");
      setTimeout(() => setSaveStatus(""), 2000);
      const cfgRes = await fetchConfig();
      setConfig(cfgRes.config);
    } catch (e) {
      setSaveStatus(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  // Load project-specific content config/social context when project selector changes
  async function loadProjectContent(projectPath: string) {
    setSelectedProjectPath(projectPath);
    try {
      const [scRes, ccRes] = await Promise.all([
        fetchSocialContext(projectPath || undefined),
        fetchContentConfig(projectPath || undefined),
      ]);
      setSocialCtx(scRes);
      setContentCfg(ccRes);
    } catch {
      // Falls back to existing loaded content
    }
  }

  if (loading) {
    return <p className="text-center text-muted-foreground">Loading settings...</p>;
  }

  if (error) {
    return (
      <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
        {error}
      </div>
    );
  }

  const models: ModelsConfig = (config?.models as ModelsConfig) ?? DEFAULT_MODELS;
  const platforms: Record<string, PlatformConfig> = (config?.platforms as Record<string, PlatformConfig>) ?? {};
  const scheduling: SchedulingConfig = (config?.scheduling as SchedulingConfig) ?? DEFAULT_SCHEDULING;
  const mediaGen: MediaGenerationConfig = (config?.media_generation as MediaGenerationConfig) ?? { enabled: true, tools: {} };
  const journeyCapture: JourneyCaptureConfig = (config?.journey_capture as JourneyCaptureConfig) ?? { enabled: false };
  const webCfg: WebDashboardConfig = (config?.web as WebDashboardConfig) ?? { enabled: false, port: 3000 };

  const telegramConfigured = !!(envData?.env?.TELEGRAM_BOT_TOKEN && envData?.env?.TELEGRAM_ALLOWED_CHAT_IDS);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Settings</h1>
          <p className="text-muted-foreground">Configure your social media pipeline.</p>
        </div>
        {saveStatus && (
          <span className={`text-sm ${saveStatus === "Saved" ? "text-green-600 dark:text-green-400" : "text-destructive"}`}>
            {saveStatus}
          </span>
        )}
      </div>

      <div className="flex gap-8">
        <SettingsSidebar active={section} onSelect={setSection} />

        <div className="min-w-0 flex-1">
          {section === "models" && (
            <ModelsSection
              models={models}
              onChange={(m) => saveConfig({ models: m })}
            />
          )}

          {section === "api-keys" && envData && (
            <ApiKeysSection
              env={envData.env}
              knownKeys={envData.known_keys}
              keyGroups={envData.key_groups}
              onRefresh={loadAll}
            />
          )}

          {section === "projects" && (
            <ProjectsSection />
          )}

          {section === "platforms" && (
            <PlatformsSection
              platforms={platforms}
              onChange={(p) => saveConfig({ platforms: p } as Partial<Config>)}
            />
          )}

          {section === "scheduling" && (
            <SchedulingSection
              scheduling={scheduling}
              onChange={(s) => saveConfig({ scheduling: s })}
            />
          )}

          {section === "media-generation" && (
            <MediaGenerationSection
              config={{ models, platforms, scheduling, media_generation: mediaGen, journey_capture: journeyCapture, web: webCfg }}
              onConfigChange={(updates) => saveConfig(updates)}
              projects={projects}
            />
          )}

          {section === "journey-capture" && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold">Journey Capture</h2>
              <p className="text-sm text-muted-foreground">
                Requires Claude Code. Captures development session narratives as source material
                for authentic &quot;building in public&quot; content.
              </p>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => saveConfig({ journey_capture: { ...journeyCapture, enabled: !journeyCapture.enabled } })}
                  className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
                    journeyCapture.enabled ? "bg-accent" : "bg-border"
                  }`}
                  disabled={saving}
                >
                  <span
                    className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
                      journeyCapture.enabled ? "left-[22px]" : "left-0.5"
                    }`}
                  />
                </button>
                <span className="text-sm">{journeyCapture.enabled ? "Enabled" : "Disabled"}</span>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Model override (optional)</label>
                <input
                  type="text"
                  value={journeyCapture.model ?? ""}
                  onChange={(e) => saveConfig({ journey_capture: { ...journeyCapture, model: e.target.value || undefined } })}
                  placeholder="Uses evaluator model by default"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
                />
              </div>
            </div>
          )}

          {section === "notifications" && (
            <NotificationsSection
              webCfg={webCfg}
              onChange={(web) => saveConfig({ web })}
              telegramConfigured={telegramConfigured}
            />
          )}

          {section === "voice-style" && socialCtx && (
            <div className="space-y-4">
              {/* Project selector for voice/style */}
              {projects.length > 0 && (
                <div>
                  <label className="mb-1 block text-sm font-medium">Project</label>
                  <select
                    value={selectedProjectPath}
                    onChange={(e) => loadProjectContent(e.target.value)}
                    className="rounded-md border border-border bg-background px-3 py-1.5 text-sm"
                  >
                    <option value="">Global defaults</option>
                    {projects.map((p) => (
                      <option key={p.id} value={p.repo_path}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              <TextEditorSection
                title="Voice & Style"
                description="Edit your social-context.md file that defines your writing voice and style."
                content={socialCtx.content}
                filePath={socialCtx.path}
                onSave={async (content) => {
                  await updateSocialContext(selectedProjectPath, content);
                  const res = await fetchSocialContext(selectedProjectPath || undefined);
                  setSocialCtx(res);
                }}
                language="markdown"
              />
            </div>
          )}

          {section === "content-config" && (
            <div className="space-y-4">
              {/* Project selector for content config */}
              {projects.length > 0 && (
                <div>
                  <label className="mb-1 block text-sm font-medium">Project</label>
                  <select
                    value={selectedProjectPath}
                    onChange={(e) => loadProjectContent(e.target.value)}
                    className="rounded-md border border-border bg-background px-3 py-1.5 text-sm"
                  >
                    <option value="">Global defaults</option>
                    {projects.map((p) => (
                      <option key={p.id} value={p.repo_path}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              {contentCfg && contentCfg.content ? (
                <TextEditorSection
                  title="Content Config"
                  description="Edit your content-config.yaml file that defines content generation rules."
                  content={contentCfg.content}
                  filePath={contentCfg.path}
                  onSave={async (content) => {
                    await updateContentConfig(selectedProjectPath, content);
                    const res = await fetchContentConfig(selectedProjectPath || undefined);
                    setContentCfg(res);
                  }}
                  language="yaml"
                />
              ) : (
                <div className="space-y-3">
                  <h2 className="text-lg font-semibold">Content Config</h2>
                  <p className="text-sm text-muted-foreground">
                    Define content generation rules, platform-specific formatting, and media tool guidance.
                  </p>
                  <div className="rounded-lg border-2 border-dashed border-border p-6 text-center">
                    <p className="text-sm text-muted-foreground">No content config found for this project.</p>
                    <button
                      onClick={async () => {
                        const template = `# Content Config\n# See docs/templates/content-config.example.yaml for full reference\n\nmedia_tools: {}\n`;
                        await updateContentConfig(selectedProjectPath, template);
                        const res = await fetchContentConfig(selectedProjectPath || undefined);
                        setContentCfg(res);
                      }}
                      className="mt-3 rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-foreground transition-colors hover:bg-accent/80"
                    >
                      Create from template
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
