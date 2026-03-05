"use client";

import type { ConsolidationConfig } from "@/lib/types";

const DEFAULT_CONSOLIDATION: ConsolidationConfig = {
  enabled: false,
  mode: "notify_only",
  batch_size: 20,
  auto_consolidate_drafts: true,
  consolidate_approved: false,
  time_window_hours: 4,
  time_window_max_drafts: 3,
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

          <h3 className="pt-2 text-sm font-semibold">Auto-Consolidation (Phase 2)</h3>
          <p className="text-xs text-muted-foreground">
            Automatically groups pending drafts within a time window as a safety net against duplicate posts.
          </p>

          <div className="flex items-center gap-3">
            <button
              onClick={() => update({ auto_consolidate_drafts: !cfg.auto_consolidate_drafts })}
              className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
                cfg.auto_consolidate_drafts ? "bg-accent" : "bg-border"
              }`}
            >
              <span
                className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
                  cfg.auto_consolidate_drafts ? "left-[22px]" : "left-0.5"
                }`}
              />
            </button>
            <span className="text-sm">Auto-consolidate drafts</span>
          </div>

          {cfg.auto_consolidate_drafts && (
            <div className="space-y-4 pl-4 border-l-2 border-border">
              <div className="flex items-center gap-3">
                <button
                  onClick={() => update({ consolidate_approved: !cfg.consolidate_approved })}
                  className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
                    cfg.consolidate_approved ? "bg-accent" : "bg-border"
                  }`}
                >
                  <span
                    className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
                      cfg.consolidate_approved ? "left-[22px]" : "left-0.5"
                    }`}
                  />
                </button>
                <span className="text-sm">Include approved drafts</span>
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium">Time window (hours)</label>
                <input
                  type="number"
                  value={cfg.time_window_hours}
                  min={0.5}
                  step={0.5}
                  onChange={(e) => {
                    const val = Number(e.target.value);
                    if (val >= 0.5) update({ time_window_hours: val });
                  }}
                  className="w-32 rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  Drafts within this window are candidates for grouping.
                </p>
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium">Max drafts before auto-consolidation</label>
                <input
                  type="number"
                  value={cfg.time_window_max_drafts}
                  min={2}
                  onChange={(e) => {
                    const val = Number(e.target.value);
                    if (val >= 2) update({ time_window_max_drafts: val });
                  }}
                  className="w-32 rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  Number of drafts in the window that triggers auto-consolidation.
                </p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
