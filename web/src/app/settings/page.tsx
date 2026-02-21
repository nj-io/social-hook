"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchConfig, fetchContentConfig, fetchEnv, fetchSocialContext, updateConfig, updateContentConfig, updateSocialContext } from "@/lib/api";
import type { Config, EnvVars, ImageGenerationConfig, JourneyCaptureConfig, ModelsConfig, PlatformConfig, SchedulingConfig, WebDashboardConfig } from "@/lib/types";
import { SettingsSidebar } from "@/components/settings/settings-sidebar";
import { ModelsSection } from "@/components/settings/models-section";
import { ApiKeysSection } from "@/components/settings/api-keys-section";
import { PlatformsSection } from "@/components/settings/platforms-section";
import { SchedulingSection } from "@/components/settings/scheduling-section";
import { TextEditorSection } from "@/components/settings/text-editor-section";

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
  const [envData, setEnvData] = useState<EnvVars | null>(null);
  const [socialCtx, setSocialCtx] = useState<{ content: string; path: string } | null>(null);
  const [contentCfg, setContentCfg] = useState<{ content: string; path: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState("");

  const loadAll = useCallback(async () => {
    try {
      const [cfgRes, envRes, scRes, ccRes] = await Promise.all([
        fetchConfig(),
        fetchEnv(),
        fetchSocialContext(),
        fetchContentConfig(),
      ]);
      setConfig(cfgRes.config);
      setEnvData(envRes);
      setSocialCtx(scRes);
      setContentCfg(ccRes);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  async function saveConfig(updates: Partial<Config>) {
    setSaving(true);
    setSaveStatus("");
    try {
      await updateConfig(updates);
      setSaveStatus("Saved");
      setTimeout(() => setSaveStatus(""), 2000);
      // Reload to get the merged config
      const cfgRes = await fetchConfig();
      setConfig(cfgRes.config);
    } catch (e) {
      setSaveStatus(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
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
  const imageGen: ImageGenerationConfig = (config?.image_generation as ImageGenerationConfig) ?? { enabled: true, service: "nano_banana_pro" };
  const journeyCapture: JourneyCaptureConfig = (config?.journey_capture as JourneyCaptureConfig) ?? { enabled: false };
  const webCfg: WebDashboardConfig = (config?.web as WebDashboardConfig) ?? { enabled: false, port: 3000 };

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
              onRefresh={loadAll}
            />
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

          {section === "image-generation" && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold">Image Generation</h2>
              <p className="text-sm text-muted-foreground">
                Automatically generate images for social media posts.
              </p>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => saveConfig({ image_generation: { ...imageGen, enabled: !imageGen.enabled } })}
                  className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
                    imageGen.enabled ? "bg-accent" : "bg-border"
                  }`}
                  disabled={saving}
                >
                  <span
                    className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
                      imageGen.enabled ? "left-[22px]" : "left-0.5"
                    }`}
                  />
                </button>
                <span className="text-sm">{imageGen.enabled ? "Enabled" : "Disabled"}</span>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Service</label>
                <input
                  type="text"
                  value={imageGen.service}
                  onChange={(e) => saveConfig({ image_generation: { ...imageGen, service: e.target.value } })}
                  className="rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
                />
              </div>
            </div>
          )}

          {section === "journey-capture" && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold">Journey Capture</h2>
              <p className="text-sm text-muted-foreground">
                Capture development journey narratives from Claude Code sessions.
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

          {section === "web-dashboard" && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold">Web Dashboard</h2>
              <p className="text-sm text-muted-foreground">
                Configure the web dashboard server.
              </p>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => saveConfig({ web: { ...webCfg, enabled: !webCfg.enabled } })}
                  className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
                    webCfg.enabled ? "bg-accent" : "bg-border"
                  }`}
                  disabled={saving}
                >
                  <span
                    className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
                      webCfg.enabled ? "left-[22px]" : "left-0.5"
                    }`}
                  />
                </button>
                <span className="text-sm">{webCfg.enabled ? "Enabled" : "Disabled"}</span>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Port</label>
                <input
                  type="number"
                  value={webCfg.port}
                  onChange={(e) => saveConfig({ web: { ...webCfg, port: Number(e.target.value) } })}
                  className="rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
                />
              </div>
            </div>
          )}

          {section === "voice-style" && socialCtx && (
            <TextEditorSection
              title="Voice & Style"
              description="Edit your social-context.md file that defines your writing voice and style."
              content={socialCtx.content}
              filePath={socialCtx.path}
              onSave={async (content) => {
                await updateSocialContext("", content);
                const res = await fetchSocialContext();
                setSocialCtx(res);
              }}
              language="markdown"
            />
          )}

          {section === "content-config" && contentCfg && (
            <TextEditorSection
              title="Content Config"
              description="Edit your content-config.yaml file that defines content generation rules."
              content={contentCfg.content}
              filePath={contentCfg.path}
              onSave={async (content) => {
                await updateContentConfig("", content);
                const res = await fetchContentConfig();
                setContentCfg(res);
              }}
              language="yaml"
            />
          )}
        </div>
      </div>
    </div>
  );
}
