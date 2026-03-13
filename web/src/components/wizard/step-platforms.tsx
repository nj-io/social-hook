"use client";

import type { PlatformEntry } from "./use-wizard-state";

interface StepPlatformsProps {
  platforms: PlatformEntry[];
  onChange: (platforms: PlatformEntry[]) => void;
}

const BUILT_IN_PLATFORMS = [
  { name: "x", label: "X (Twitter)", tiers: ["free", "basic", "premium", "premium+"] },
  { name: "linkedin", label: "LinkedIn", tiers: [] },
  { name: "preview", label: "Preview", tiers: [] },
];

export function StepPlatforms({ platforms, onChange }: StepPlatformsProps) {
  function togglePlatform(name: string) {
    const next = platforms.map((p) =>
      p.name === name ? { ...p, enabled: !p.enabled } : p,
    );
    // Add platform if it doesn't exist
    if (!next.find((p) => p.name === name)) {
      next.push({
        name,
        enabled: true,
        priority: "primary",
        accountTier: "",
        introduce: true,
        identity: "",
      });
    }
    onChange(next);
  }

  function updatePlatform(name: string, updates: Partial<PlatformEntry>) {
    onChange(platforms.map((p) => (p.name === name ? { ...p, ...updates } : p)));
  }

  return (
    <div className="animate-wizard-dissolve space-y-4">
      <div>
        <h3 className="text-lg font-semibold">Platforms</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Select which platforms to generate content for. Preview lets you test without posting.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        {BUILT_IN_PLATFORMS.map((bp) => {
          const platform = platforms.find((p) => p.name === bp.name);
          const enabled = platform?.enabled ?? false;

          return (
            <div
              key={bp.name}
              className={`rounded-lg border-2 p-4 transition-colors ${
                enabled ? "border-accent bg-accent/5" : "border-border"
              }`}
            >
              <label className="flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={enabled}
                  onChange={() => togglePlatform(bp.name)}
                  className="rounded border-border"
                />
                <span className="text-sm font-medium">{bp.label}</span>
              </label>

              {enabled && platform && (
                <div className="mt-3 space-y-2">
                  <div>
                    <label className="mb-1 block text-xs text-muted-foreground">Priority</label>
                    <select
                      value={platform.priority}
                      onChange={(e) => updatePlatform(bp.name, { priority: e.target.value as "primary" | "secondary" })}
                      className="w-full rounded-md border border-border bg-background px-2 py-1 text-xs"
                    >
                      <option value="primary">Primary</option>
                      <option value="secondary">Secondary</option>
                    </select>
                  </div>

                  {bp.tiers.length > 0 && (
                    <div>
                      <label className="mb-1 block text-xs text-muted-foreground">Account tier</label>
                      <select
                        value={platform.accountTier}
                        onChange={(e) => updatePlatform(bp.name, { accountTier: e.target.value })}
                        className="w-full rounded-md border border-border bg-background px-2 py-1 text-xs"
                      >
                        {bp.tiers.map((tier) => (
                          <option key={tier} value={tier}>{tier}</option>
                        ))}
                      </select>
                    </div>
                  )}

                  {bp.name !== "preview" && (
                    <label className="flex items-center gap-2 text-xs">
                      <input
                        type="checkbox"
                        checked={platform.introduce}
                        onChange={(e) => updatePlatform(bp.name, { introduce: e.target.checked })}
                        className="rounded border-border"
                      />
                      Introduce project to this audience
                    </label>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
