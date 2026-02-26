"use client";

import { useState } from "react";
import type { PlatformConfig, SchedulingOverride } from "@/lib/types";
import { updateEnv } from "@/lib/api";

const FILTERS = ["all", "notable", "significant"];
const FREQUENCIES = ["high", "moderate", "low", "minimal"];
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const TIERS: Record<string, string[]> = {
  x: ["free", "basic", "premium", "pro"],
  linkedin: ["free", "premium"],
};

function platformDisplayName(name: string): string {
  const names: Record<string, string> = {
    x: "X (Twitter)",
    linkedin: "LinkedIn",
  };
  return names[name] ?? name;
}

const PLATFORM_ENV_KEYS: Record<string, { key: string; label: string }[]> = {
  x: [
    { key: "X_API_KEY", label: "API Key" },
    { key: "X_API_SECRET", label: "API Secret" },
    { key: "X_ACCESS_TOKEN", label: "Access Token" },
    { key: "X_ACCESS_TOKEN_SECRET", label: "Access Token Secret" },
  ],
  linkedin: [
    { key: "LINKEDIN_CLIENT_ID", label: "Client ID" },
    { key: "LINKEDIN_CLIENT_SECRET", label: "Client Secret" },
    { key: "LINKEDIN_ACCESS_TOKEN", label: "Access Token" },
  ],
};

interface PlatformCardProps {
  name: string;
  config: PlatformConfig;
  onChange: (config: PlatformConfig) => void;
  onRemove?: () => void;
  env: Record<string, string>;
  onEnvRefresh: () => void;
}

export function PlatformCard({ name, config, onChange, onRemove, env, onEnvRefresh }: PlatformCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [keyValues, setKeyValues] = useState<Record<string, string>>({});
  const [savingKey, setSavingKey] = useState<string | null>(null);

  const envKeys = PLATFORM_ENV_KEYS[name];

  async function handleKeySave(envKey: string) {
    const value = keyValues[envKey];
    if (!value) return;
    setSavingKey(envKey);
    try {
      await updateEnv(envKey, value);
      setKeyValues((prev) => { const next = { ...prev }; delete next[envKey]; return next; });
      onEnvRefresh();
    } catch {
      // Input retains value for retry
    } finally {
      setSavingKey(null);
    }
  }

  function update(partial: Partial<PlatformConfig>) {
    onChange({ ...config, ...partial });
  }

  function updateScheduling(partial: Partial<SchedulingOverride>) {
    onChange({ ...config, scheduling: { ...config.scheduling, ...partial } });
  }

  const effectiveFilter = config.filter ?? "smart default";
  const effectiveFrequency = config.frequency ?? "smart default";

  return (
    <div className="rounded-lg border border-border">
      <div className="flex items-center gap-3 p-4">
        {/* Enable toggle */}
        <button
          onClick={() => update({ enabled: !config.enabled })}
          className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
            config.enabled ? "bg-accent" : "bg-border"
          }`}
        >
          <span
            className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
              config.enabled ? "left-[22px]" : "left-0.5"
            }`}
          />
        </button>

        {/* Name + info */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-medium">{platformDisplayName(name)}</span>
            {config.type === "custom" && (
              <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">custom</span>
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            {config.account_tier ? `${config.account_tier} tier` : ""}
            {config.account_tier && (effectiveFilter !== "smart default" || effectiveFrequency !== "smart default") ? " · " : ""}
            {effectiveFilter !== "smart default" ? effectiveFilter : ""}
            {effectiveFilter !== "smart default" && effectiveFrequency !== "smart default" ? " · " : ""}
            {effectiveFrequency !== "smart default" ? `${effectiveFrequency} frequency` : ""}
          </p>
        </div>

        {/* Tier selector */}
        {(TIERS[name] || config.type === "custom") && (
          <select
            value={config.account_tier ?? ""}
            onChange={(e) => update({ account_tier: e.target.value || undefined })}
            className="rounded-md border border-border bg-background px-2 py-1 text-xs"
          >
            <option value="">Tier</option>
            {(TIERS[name] ?? ["free", "premium"]).map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        )}

        {/* Priority badge */}
        <select
          value={config.priority}
          onChange={(e) => update({ priority: e.target.value as "primary" | "secondary" })}
          className={`rounded-full px-3 py-1 text-xs font-medium ${
            config.priority === "primary"
              ? "bg-accent text-accent-foreground"
              : "bg-muted text-muted-foreground"
          }`}
        >
          <option value="primary">Primary</option>
          <option value="secondary">Secondary</option>
        </select>
      </div>

      {/* Credentials */}
      {envKeys && (
        <div className="space-y-2 border-t border-border px-4 py-3">
          <p className="text-xs font-medium text-muted-foreground">Credentials</p>
          {envKeys.map(({ key, label }) => (
            <div key={key}>
              <label className="mb-1 block text-xs font-medium">{label}</label>
              <div className="flex gap-2">
                <input
                  type="password"
                  value={keyValues[key] ?? ""}
                  onChange={(e) => setKeyValues((prev) => ({ ...prev, [key]: e.target.value }))}
                  placeholder={env[key] ? `Current: ${env[key]}` : "Not set"}
                  className="flex-1 rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-accent"
                />
                <button
                  onClick={() => handleKeySave(key)}
                  disabled={!keyValues[key] || savingKey === key}
                  className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-foreground transition-colors hover:bg-accent/80 disabled:opacity-50"
                >
                  {savingKey === key ? "..." : "Save"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Advanced toggle */}
      <div className="border-t border-border px-4 py-2">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          <span className={`transition-transform ${expanded ? "rotate-90" : ""}`}>&#9654;</span>
          Advanced settings
        </button>
        {onRemove && (
          <button
            onClick={onRemove}
            className="float-right text-xs text-destructive hover:underline"
          >
            Remove
          </button>
        )}
      </div>

      {/* Advanced panel */}
      {expanded && (
        <div className="space-y-3 border-t border-border p-4">
          {/* Content filter */}
          <div>
            <label className="mb-1 block text-xs font-medium">Content filter</label>
            <select
              value={config.filter ?? ""}
              onChange={(e) => update({ filter: e.target.value || undefined })}
              className="rounded-md border border-border bg-background px-3 py-1.5 text-sm"
            >
              <option value="">Smart default</option>
              {FILTERS.map((f) => (
                <option key={f} value={f}>{f}</option>
              ))}
            </select>
          </div>

          {/* Frequency */}
          <div>
            <label className="mb-1 block text-xs font-medium">Frequency</label>
            <select
              value={config.frequency ?? ""}
              onChange={(e) => update({ frequency: e.target.value || undefined })}
              className="rounded-md border border-border bg-background px-3 py-1.5 text-sm"
            >
              <option value="">Smart default</option>
              {FREQUENCIES.map((f) => (
                <option key={f} value={f}>{f}</option>
              ))}
            </select>
          </div>

          {/* Custom platform fields */}
          {config.type === "custom" && (
            <>
              <div>
                <label className="mb-1 block text-xs font-medium">Format</label>
                <input
                  type="text"
                  value={config.format ?? ""}
                  onChange={(e) => update({ format: e.target.value || undefined })}
                  placeholder="tweet, post, article, email..."
                  className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-accent"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium">Max length</label>
                <input
                  type="number"
                  value={config.max_length ?? ""}
                  onChange={(e) => update({ max_length: e.target.value ? Number(e.target.value) : undefined })}
                  placeholder="No limit"
                  className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-accent"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium">Description</label>
                <textarea
                  value={config.description ?? ""}
                  onChange={(e) => update({ description: e.target.value || undefined })}
                  placeholder="Extra context for the drafter..."
                  rows={2}
                  className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-accent"
                />
              </div>
            </>
          )}

          {/* Scheduling overrides */}
          <div>
            <p className="mb-2 text-xs font-medium">Scheduling overrides</p>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="mb-0.5 block text-xs text-muted-foreground">Max posts/day</label>
                <input
                  type="number"
                  value={config.scheduling?.max_posts_per_day ?? ""}
                  onChange={(e) =>
                    updateScheduling({ max_posts_per_day: e.target.value ? Number(e.target.value) : undefined })
                  }
                  placeholder="Default"
                  className="w-full rounded-md border border-border bg-background px-2 py-1 text-sm"
                />
              </div>
              <div>
                <label className="mb-0.5 block text-xs text-muted-foreground">Min gap (min)</label>
                <input
                  type="number"
                  value={config.scheduling?.min_gap_minutes ?? ""}
                  onChange={(e) =>
                    updateScheduling({ min_gap_minutes: e.target.value ? Number(e.target.value) : undefined })
                  }
                  placeholder="Default"
                  className="w-full rounded-md border border-border bg-background px-2 py-1 text-sm"
                />
              </div>
            </div>
            <div className="mt-2">
              <label className="mb-0.5 block text-xs text-muted-foreground">Optimal days</label>
              <div className="flex flex-wrap gap-1">
                {DAYS.map((day) => {
                  const selected = config.scheduling?.optimal_days?.includes(day);
                  return (
                    <button
                      key={day}
                      onClick={() => {
                        const current = config.scheduling?.optimal_days ?? [];
                        const next = selected ? current.filter((d) => d !== day) : [...current, day];
                        updateScheduling({ optimal_days: next.length > 0 ? next : undefined });
                      }}
                      className={`rounded px-2 py-1 text-xs transition-colors ${
                        selected
                          ? "bg-accent text-accent-foreground"
                          : "bg-muted text-muted-foreground hover:bg-muted/80"
                      }`}
                    >
                      {day}
                    </button>
                  );
                })}
              </div>
            </div>
            <div className="mt-2">
              <label className="mb-0.5 block text-xs text-muted-foreground">Optimal hours</label>
              <div className="flex flex-wrap gap-1">
                {[6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21].map((h) => {
                  const selected = config.scheduling?.optimal_hours?.includes(h);
                  return (
                    <button
                      key={h}
                      onClick={() => {
                        const current = config.scheduling?.optimal_hours ?? [];
                        const next = selected ? current.filter((x) => x !== h) : [...current, h];
                        updateScheduling({ optimal_hours: next.length > 0 ? next : undefined });
                      }}
                      className={`rounded px-2 py-1 text-xs transition-colors ${
                        selected
                          ? "bg-accent text-accent-foreground"
                          : "bg-muted text-muted-foreground hover:bg-muted/80"
                      }`}
                    >
                      {h}:00
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
