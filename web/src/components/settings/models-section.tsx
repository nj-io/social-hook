"use client";

import type { ModelsConfig } from "@/lib/types";

const MODEL_PRESETS = [
  "anthropic/claude-opus-4-5",
  "anthropic/claude-sonnet-4-5",
  "anthropic/claude-haiku-4-5",
  "claude-cli/sonnet",
  "claude-cli/opus",
  "openrouter/anthropic/claude-sonnet-4.5",
  "ollama/llama3.3",
];

interface ModelsSectionProps {
  models: ModelsConfig;
  onChange: (models: ModelsConfig) => void;
}

export function ModelsSection({ models, onChange }: ModelsSectionProps) {
  function handleChange(role: keyof ModelsConfig, value: string) {
    onChange({ ...models, [role]: value });
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Models</h2>
      <p className="text-sm text-muted-foreground">
        Configure which models are used for each role in the pipeline.
      </p>
      {(["evaluator", "drafter", "gatekeeper"] as const).map((role) => (
        <div key={role}>
          <label className="mb-1 block text-sm font-medium capitalize">{role}</label>
          <div className="flex gap-2">
            <select
              value={MODEL_PRESETS.includes(models[role]) ? models[role] : "__custom__"}
              onChange={(e) => {
                if (e.target.value !== "__custom__") {
                  handleChange(role, e.target.value);
                }
              }}
              className="rounded-md border border-border bg-background px-3 py-2 text-sm"
            >
              {MODEL_PRESETS.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
              {!MODEL_PRESETS.includes(models[role]) && (
                <option value="__custom__">Custom</option>
              )}
            </select>
            <input
              type="text"
              value={models[role]}
              onChange={(e) => handleChange(role, e.target.value)}
              className="flex-1 rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
              placeholder="provider/model-id"
            />
          </div>
        </div>
      ))}
    </div>
  );
}
