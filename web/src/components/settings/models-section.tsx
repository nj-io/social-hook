"use client";

import { useEffect, useState } from "react";

import { fetchModels } from "@/lib/api";
import type { ModelCatalogInfo, ModelsConfig, ProviderCatalogInfo } from "@/lib/types";

interface ModelsSectionProps {
  models: ModelsConfig;
  onChange: (models: ModelsConfig) => void;
}

const ROLE_HELP: Record<keyof ModelsConfig, string> = {
  evaluator: "Judges commits and drives most analysis — the workhorse role.",
  drafter: "Writes the actual post content.",
  gatekeeper: "Routes Telegram bot messages (Telegram flow only).",
};

function formatCost(m: ModelCatalogInfo): string {
  if (m.cost_input > 0) return `$${m.cost_input.toFixed(2)}/M in`;
  if (m.tier === "local") return "free/local";
  return "subscription";
}

function formatContext(n: number): string {
  if (n >= 1_000_000) return `${Math.round(n / 1_000_000)}M ctx`;
  if (n >= 1000) return `${Math.round(n / 1000)}K ctx`;
  return `${n} ctx`;
}

export function ModelsSection({ models, onChange }: ModelsSectionProps) {
  const [catalog, setCatalog] = useState<ModelCatalogInfo[]>([]);
  const [providers, setProviders] = useState<ProviderCatalogInfo[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetchModels()
      .then((res) => {
        if (!active) return;
        setCatalog(res.models);
        setProviders(res.providers);
      })
      .catch((e) => {
        if (active) setError(String(e));
      });
    return () => {
      active = false;
    };
  }, []);

  function handleChange(role: keyof ModelsConfig, value: string) {
    onChange({ ...models, [role]: value });
  }

  const providerName = (id: string) => providers.find((p) => p.id === id)?.name ?? id;
  const knownIds = new Set(catalog.map((m) => m.full_id));

  // Group models under their provider, preserving the provider ordering.
  const grouped = providers
    .map((p) => ({ provider: p, items: catalog.filter((m) => m.provider === p.id) }))
    .filter((g) => g.items.length > 0);

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Models</h2>
      <p className="text-sm text-muted-foreground">
        Configure which model runs each role in the pipeline. Pick from the catalog or type any{" "}
        <code>provider/model-id</code> (e.g. <code>openrouter/z-ai/glm-5.2</code>). Non-Anthropic
        providers need their API key set in the Environment section.
      </p>
      {error && (
        <p className="text-sm text-destructive">Couldn&apos;t load the model catalog: {error}</p>
      )}
      {(["evaluator", "drafter", "gatekeeper"] as const).map((role) => {
        const current = models[role];
        const isKnown = knownIds.has(current);
        return (
          <div key={role}>
            <label className="mb-1 block text-sm font-medium capitalize">{role}</label>
            <p className="mb-1 text-xs text-muted-foreground">{ROLE_HELP[role]}</p>
            <select
              value={isKnown ? current : "__custom__"}
              onChange={(e) => {
                if (e.target.value !== "__custom__") handleChange(role, e.target.value);
              }}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
            >
              {grouped.map((g) => (
                <optgroup key={g.provider.id} label={providerName(g.provider.id)}>
                  {g.items.map((m) => (
                    <option key={m.full_id} value={m.full_id}>
                      {m.name} — {formatCost(m)} · {formatContext(m.context_window)}
                    </option>
                  ))}
                </optgroup>
              ))}
              {!isKnown && <option value="__custom__">Custom: {current || "(unset)"}</option>}
            </select>
            <input
              type="text"
              value={current}
              onChange={(e) => handleChange(role, e.target.value)}
              className="mt-2 w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
              placeholder="provider/model-id"
            />
          </div>
        );
      })}
    </div>
  );
}
