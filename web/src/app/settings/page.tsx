"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { fetchConfig, fetchContentConfig, fetchContentConfigParsed, fetchEnv, fetchProjects, fetchSocialContext, updateConfig, updateContentConfig, updateContentConfigParsed, updateSocialContext } from "@/lib/api";
import { useSectionNav } from "@/lib/use-section-nav";
import type { ChannelConfig, Config, ConsolidationConfig, JourneyCaptureConfig, MediaGenerationConfig, ModelsConfig, PlatformConfig, Project, RateLimitsConfig, SchedulingConfig } from "@/lib/types";
import { SettingsSidebar, sections } from "@/components/settings/settings-sidebar";
import { ModelsSection } from "@/components/settings/models-section";
import { ApiKeysSection } from "@/components/settings/api-keys-section";
import { PlatformsSection } from "@/components/settings/platforms-section";
import { SchedulingSection } from "@/components/settings/scheduling-section";
import { TextEditorSection } from "@/components/settings/text-editor-section";
import { MediaGenerationSection } from "@/components/settings/media-generation-section";
import { ConsolidationSection } from "@/components/settings/consolidation-section";
import { RateLimitsSection } from "@/components/settings/rate-limits-section";
import { ProjectsSection } from "@/components/settings/projects-section";
import { InstallationsSection } from "@/components/settings/installations-section";
import { ChannelsSection } from "@/components/settings/channels-section";
import { CredentialsSection } from "@/components/settings/credentials-section";
import { AccountsSection } from "@/components/settings/accounts-section";
import { TargetsSection } from "@/components/settings/targets-section";
import { StrategiesSection } from "@/components/settings/strategies-section";
import { PlatformSettingsSection } from "@/components/settings/platform-settings-section";

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

function SettingsContent() {
  const [config, setConfig] = useState<Record<string, unknown> | null>(null);
  const [envData, setEnvData] = useState<{ env: Record<string, string>; known_keys: string[]; key_groups: Record<string, string[]> } | null>(null);
  const [socialCtx, setSocialCtx] = useState<{ content: string; path: string } | null>(null);
  const [contentCfg, setContentCfg] = useState<{ content: string; path: string } | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectPath, setSelectedProjectPath] = useState("");
  const [contextConfig, setContextConfig] = useState<{ max_doc_tokens?: number; project_docs?: string[]; commit_analysis_interval?: number; topic_granularity?: string }>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState("");
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const headerRef = useRef<HTMLDivElement>(null);
  const [contentHeight, setContentHeight] = useState("100vh");

  const { activeSection, scrollToSection } = useSectionNav({
    sections,
    defaultSection: "models",
    scrollContainerRef,
  });

  const loadAll = useCallback(async () => {
    try {
      const [cfgRes, envRes, scRes, ccRes, projRes, ccParsed] = await Promise.all([
        fetchConfig(),
        fetchEnv(),
        fetchSocialContext(),
        fetchContentConfig(),
        fetchProjects(),
        fetchContentConfigParsed(),
      ]);
      setConfig(cfgRes.config);
      setEnvData(envRes);
      setSocialCtx(scRes);
      setContentCfg(ccRes);
      setProjects(projRes.projects);
      setContextConfig(ccParsed.context || {});
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  // Dynamically measure space above the scroll area so it fills the remaining viewport
  useEffect(() => {
    function measure() {
      if (!headerRef.current) return;
      const rect = headerRef.current.getBoundingClientRect();
      setContentHeight(`calc(100vh - ${rect.bottom}px)`);
    }
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [loading]);

  // Refresh content config (called when Media Generation guidance is saved)
  const refreshContentConfig = useCallback(async () => {
    try {
      const res = await fetchContentConfig(selectedProjectPath || undefined);
      setContentCfg(res);
    } catch {
      // ignore — content config section will show stale data
    }
  }, [selectedProjectPath]);

  async function saveConfig(updates: Partial<Config>) {
    setSaving(true);
    setSaveStatus("");
    try {
      const result = await updateConfig(updates);
      if (result.hook_warning) {
        setSaveStatus(`Saved — ${result.hook_warning}`);
      } else {
        setSaveStatus("Saved");
      }
      setTimeout(() => setSaveStatus(""), 3000);
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
  const consolidation: ConsolidationConfig = (config?.consolidation as ConsolidationConfig) ?? { enabled: false, mode: "notify_only", batch_size: 20 };
  const rateLimits: RateLimitsConfig = (config?.rate_limits as RateLimitsConfig) ?? { max_evaluations_per_day: 15, min_evaluation_gap_minutes: 10, batch_throttled: false };
  const channels: Record<string, ChannelConfig> = (config?.channels as Record<string, ChannelConfig>) ?? {};

  return (
    <div>
      <div ref={headerRef} className="flex items-center justify-between pb-4">
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

      <div className="flex gap-8" style={{ height: contentHeight }}>
        <SettingsSidebar active={activeSection} onSelect={scrollToSection} />

        <div ref={scrollContainerRef} className="min-w-0 flex-1 space-y-12 overflow-y-auto scroll-smooth pb-[50vh]">
          <section id="models" className="pt-1">
            <ModelsSection
              models={models}
              onChange={(m) => saveConfig({ models: m })}
            />
          </section>

          <section id="api-keys" className="pt-1">
            {envData && (
              <ApiKeysSection
                env={envData.env}
                knownKeys={envData.known_keys}
                keyGroups={envData.key_groups}
                onRefresh={loadAll}
              />
            )}
          </section>

          <section id="projects" className="pt-1">
            <ProjectsSection />
          </section>

          <section id="installations" className="pt-1">
            <InstallationsSection />
          </section>

          <section id="channels" className="pt-1">
            <ChannelsSection
              channels={channels}
              onChange={(ch) => saveConfig({ channels: ch } as Partial<Config>)}
              env={envData?.env ?? {}}
              onEnvRefresh={loadAll}
            />
          </section>

          <section id="credentials" className="pt-1">
            <CredentialsSection />
          </section>

          <section id="accounts" className="pt-1">
            <AccountsSection />
          </section>

          <section id="targets" className="pt-1">
            <TargetsSection />
          </section>

          <section id="strategies" className="pt-1">
            <StrategiesSection />
            <div className="mt-6 border-t border-border pt-4">
              <h3 className="mb-1 text-sm font-semibold">Topic Generation</h3>
              <p className="mb-3 text-xs text-muted-foreground">
                Controls how the system auto-creates content topics for strategies.
              </p>
              <div>
                <label className="mb-1 block text-sm font-medium">Topic granularity</label>
                <select
                  value={contextConfig.topic_granularity ?? "low"}
                  onChange={async (e) => {
                    const val = e.target.value;
                    setContextConfig((prev) => ({ ...prev, topic_granularity: val }));
                    await updateContentConfigParsed({ context: { ...contextConfig, topic_granularity: val } });
                  }}
                  className="w-48 rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
                >
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                </select>
                <p className="mt-1 text-xs text-muted-foreground">
                  Low: broad themes (~3-5 per strategy). Medium: feature-level (~5-10). High: implementation-specific (~10-20).
                </p>
              </div>
            </div>
          </section>

          <section id="platforms" className="pt-1">
            <PlatformsSection
              platforms={platforms}
              onChange={(p) => saveConfig({ platforms: p } as Partial<Config>)}
              env={envData?.env ?? {}}
              onEnvRefresh={loadAll}
            />
          </section>

          <section id="platform-settings" className="pt-1">
            <PlatformSettingsSection />
          </section>

          <section id="scheduling" className="pt-1">
            <SchedulingSection
              scheduling={scheduling}
              onChange={(s) => saveConfig({ scheduling: s })}
            />
          </section>

          <section id="media-generation" className="pt-1">
            <MediaGenerationSection
              config={{ models, platforms, scheduling, media_generation: mediaGen, journey_capture: journeyCapture }}
              onConfigChange={(updates) => saveConfig(updates)}
              projects={projects}
              onGuidanceSave={refreshContentConfig}
              env={envData?.env ?? {}}
              onEnvRefresh={loadAll}
            />
          </section>

          <section id="rate-limits" className="pt-1">
            <RateLimitsSection
              rateLimits={rateLimits}
              onChange={(r) => saveConfig({ rate_limits: r } as Partial<Config>)}
            />
            <div className="mt-6 border-t border-border pt-4">
              <h3 className="mb-1 text-sm font-semibold">Per-Project Evaluation</h3>
              <p className="mb-3 text-xs text-muted-foreground">
                How often commits trigger full evaluations. Stored per-project in content-config.yaml.
              </p>
              <div>
                <label className="mb-1 block text-sm font-medium">Commit analysis interval</label>
                <input
                  type="number"
                  min={1}
                  step={1}
                  value={contextConfig.commit_analysis_interval ?? 1}
                  onChange={(e) => {
                    const val = parseInt(e.target.value, 10);
                    if (isNaN(val)) return;
                    setContextConfig((prev) => ({ ...prev, commit_analysis_interval: val }));
                  }}
                  onBlur={async () => {
                    await updateContentConfigParsed({ context: { ...contextConfig } });
                  }}
                  className="w-48 rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  How many commits to accumulate before running a full evaluation. Set to 1 to evaluate every commit.
                </p>
              </div>
            </div>
          </section>

          <section id="consolidation" className="pt-1">
            <ConsolidationSection
              consolidation={consolidation}
              onChange={(c) => saveConfig({ consolidation: c })}
            />
          </section>

          <section id="journey-capture" className="pt-1">
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
          </section>

          <section id="voice-style" className="pt-1">
            {socialCtx && (
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
          </section>

          <section id="content-config" className="pt-1">
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
                        const template = [
                          "# Content Config",
                          "# See docs/templates/content-config.example.yaml for full reference",
                          "",
                          "media_tools:",
                          "  mermaid:",
                          "    use_when:",
                          '      - "Technical architecture explanations"',
                          '      - "Flow diagrams and processes"',
                          "    constraints:",
                          '      - "Don\'t overuse - can feel dry/boring"',
                          '      - "Best for technical audience"',
                          "    prompt_example: |",
                          "      Create a Mermaid diagram showing the flow from git commit to social post.",
                          "      Keep it clean and minimal. Use graph LR (left-to-right) orientation.",
                          "      Maximum 8-10 nodes for readability.",
                          "",
                          "  nano_banana_pro:",
                          "    use_when:",
                          '      - "Marketing/announcement visuals"',
                          '      - "Polished graphics for launches"',
                          "    constraints:",
                          '      - "Always specify \'no text\' unless text is essential"',
                          "    prompt_example: |",
                          "      Create a clean, modern illustration representing [concept].",
                          "      Style: Minimal, developer-focused, no text overlays.",
                          "      Colors: Use a limited palette, prefer blues and purples.",
                          "      Avoid: Stock photo feel, corporate clipart, busy backgrounds.",
                          "",
                          "  playwright:",
                          "    use_when:",
                          '      - "Demonstrating actual UI/product"',
                          '      - "Showing working features"',
                          "    constraints:",
                          '      - "Only use when there\'s actual UI to show"',
                          '      - "Ensure no sensitive data visible"',
                          "    prompt_example: |",
                          "      Take a screenshot of the application showing [feature].",
                          "      Ensure the relevant UI element is visible and highlighted.",
                          "      Use a clean browser window (no bookmarks bar, minimal chrome).",
                          "",
                          "  ray_so:",
                          "    use_when:",
                          '      - "Highlighting interesting code snippets"',
                          '      - "Code-focused posts"',
                          "    constraints: []",
                          "    prompt_example: |",
                          "      Create a code screenshot of the following snippet.",
                          "      Highlight lines that show the key logic.",
                          "      Use dark theme, include filename if relevant.",
                          "",
                        ].join("\n");
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
          </section>

          <section id="context" className="pt-1">
            <div className="space-y-4">
              <h2 className="text-lg font-semibold">Context</h2>
              <p className="text-sm text-muted-foreground">
                Control how much project documentation the AI reads when generating summaries and drafts.
              </p>

              <div>
                <label className="mb-1 block text-sm font-medium">Max Document Tokens</label>
                <p className="mb-2 text-xs text-muted-foreground">
                  Maximum tokens to include from project documentation files (README, CLAUDE.md, discovery files)
                  when generating summaries and drafts. Higher values give the AI more project context but use
                  more of the context window. Default: 10,000.
                </p>
                <input
                  type="number"
                  min={1000}
                  max={100000}
                  step={1000}
                  value={contextConfig.max_doc_tokens ?? 10000}
                  onChange={async (e) => {
                    const val = parseInt(e.target.value, 10);
                    if (isNaN(val)) return;
                    setContextConfig((prev) => ({ ...prev, max_doc_tokens: val }));
                  }}
                  onBlur={async () => {
                    await updateContentConfigParsed({ context: { ...contextConfig } });
                  }}
                  className="w-48 rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
                />
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium">Priority Documentation Files</label>
                <p className="mb-2 text-xs text-muted-foreground">
                  Glob patterns for files to prioritize during project discovery (e.g., docs/ARCHITECTURE.md,
                  src/**/README.md). These files are loaded first when generating project summaries. One
                  pattern per line.
                </p>
                <textarea
                  rows={4}
                  value={(contextConfig.project_docs || []).join("\n")}
                  onChange={(e) => {
                    const docs = e.target.value.split("\n").filter((l) => l.trim());
                    setContextConfig((prev) => ({ ...prev, project_docs: docs }));
                  }}
                  onBlur={async () => {
                    await updateContentConfigParsed({ context: { ...contextConfig } });
                  }}
                  placeholder="docs/ARCHITECTURE.md&#10;src/**/README.md"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-sm outline-none focus:ring-2 focus:ring-accent"
                />
              </div>

            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <Suspense fallback={<p className="text-center text-muted-foreground">Loading settings...</p>}>
      <SettingsContent />
    </Suspense>
  );
}
