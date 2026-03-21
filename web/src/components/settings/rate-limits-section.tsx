"use client";

import type { RateLimitsConfig } from "@/lib/types";

const DEFAULT_RATE_LIMITS: RateLimitsConfig = {
  max_evaluations_per_day: 15,
  min_evaluation_gap_minutes: 10,
  batch_throttled: false,
};

interface RateLimitsSectionProps {
  rateLimits: RateLimitsConfig;
  onChange: (rateLimits: RateLimitsConfig) => void;
}

export function RateLimitsSection({ rateLimits, onChange }: RateLimitsSectionProps) {
  const cfg = { ...DEFAULT_RATE_LIMITS, ...rateLimits };

  function update(partial: Partial<RateLimitsConfig>) {
    onChange({ ...cfg, ...partial });
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Rate Limits</h2>
      <p className="text-sm text-muted-foreground">
        Control how many automatic evaluations run per day and the minimum gap between them.
        These limits are global (across all projects). Manual retriggers bypass the daily cap.
      </p>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="mb-1 block text-sm font-medium">Max evaluations per day</label>
          <input
            type="number"
            value={cfg.max_evaluations_per_day}
            min={1}
            onChange={(e) => {
              const val = Number(e.target.value);
              if (val >= 1) update({ max_evaluations_per_day: val });
            }}
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
          />
          <p className="mt-1 text-xs text-muted-foreground">
            Maximum automatic evaluations per day (across all projects).
          </p>
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">Min gap between evaluations (minutes)</label>
          <input
            type="number"
            value={cfg.min_evaluation_gap_minutes}
            min={0}
            onChange={(e) => {
              const val = Number(e.target.value);
              if (val >= 0) update({ min_evaluation_gap_minutes: val });
            }}
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
          />
          <p className="mt-1 text-xs text-muted-foreground">
            Minimum minutes between automatic evaluations. Set to 0 to disable.
          </p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={() => update({ batch_throttled: !cfg.batch_throttled })}
          className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
            cfg.batch_throttled ? "bg-accent" : "bg-border"
          }`}
        >
          <span
            className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
              cfg.batch_throttled ? "left-[22px]" : "left-0.5"
            }`}
          />
        </button>
        <div>
          <span className="text-sm">Batch throttled triggers</span>
          <p className="text-xs text-muted-foreground">
            When enabled, deferred evaluations are drained one at a time by the scheduler instead of all at once.
          </p>
        </div>
      </div>
    </div>
  );
}
