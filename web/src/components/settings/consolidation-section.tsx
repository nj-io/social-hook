"use client";

import type { ConsolidationConfig } from "@/lib/types";

const DEFAULT_CONSOLIDATION: ConsolidationConfig = {
  enabled: false,
  mode: "notify_only",
  batch_size: 20,
};

interface ConsolidationSectionProps {
  consolidation: ConsolidationConfig;
  onChange: (consolidation: ConsolidationConfig) => void;
}

export function ConsolidationSection({ consolidation, onChange }: ConsolidationSectionProps) {
  const cfg = { ...DEFAULT_CONSOLIDATION, ...consolidation };

  function update(partial: Partial<ConsolidationConfig>) {
    onChange({ ...cfg, ...partial });
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Consolidation</h2>
      <p className="text-sm text-muted-foreground">
        When the Evaluator marks commits as &quot;consolidate&quot; or &quot;deferred&quot;, the consolidation
        processor batches them and either re-evaluates with LLM context or notifies you.
      </p>

      <div className="flex items-center gap-3">
        <button
          onClick={() => update({ enabled: !cfg.enabled })}
          className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
            cfg.enabled ? "bg-accent" : "bg-border"
          }`}
        >
          <span
            className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
              cfg.enabled ? "left-[22px]" : "left-0.5"
            }`}
          />
        </button>
        <span className="text-sm">{cfg.enabled ? "Enabled" : "Disabled"}</span>
      </div>

      {cfg.enabled && (
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium">Mode</label>
            <select
              value={cfg.mode}
              onChange={(e) => update({ mode: e.target.value })}
              className="rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
            >
              <option value="re_evaluate">Re-evaluate with LLM</option>
              <option value="notify_only">Notify only</option>
            </select>
            <p className="mt-1 text-xs text-muted-foreground">
              {cfg.mode === "re_evaluate"
                ? "Batched decisions are re-evaluated by the Evaluator with full context to determine if they are now post-worthy."
                : "You are notified of accumulated deferred/consolidated decisions for manual review."}
            </p>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">Batch size</label>
            <input
              type="number"
              value={cfg.batch_size}
              min={1}
              onChange={(e) => {
                const val = Number(e.target.value);
                if (val >= 1) update({ batch_size: val });
              }}
              className="w-32 rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
            />
            <p className="mt-1 text-xs text-muted-foreground">
              Maximum unprocessed decisions per project per scheduler tick.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
