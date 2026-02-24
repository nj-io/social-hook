"use client";

import type { SchedulingConfig } from "@/lib/types";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

interface SchedulingSectionProps {
  scheduling: SchedulingConfig;
  onChange: (scheduling: SchedulingConfig) => void;
}

export function SchedulingSection({ scheduling, onChange }: SchedulingSectionProps) {
  function update(partial: Partial<SchedulingConfig>) {
    onChange({ ...scheduling, ...partial });
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Scheduling</h2>
      <p className="text-sm text-muted-foreground">
        Global scheduling defaults. Platforms can override these in their advanced settings.
      </p>

      <div>
        <label className="mb-1 block text-sm font-medium">Timezone</label>
        <input
          type="text"
          value={scheduling.timezone}
          onChange={(e) => update({ timezone: e.target.value })}
          placeholder="UTC"
          className="rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="mb-1 block text-sm font-medium">Max posts per day</label>
          <input
            type="number"
            value={scheduling.max_posts_per_day}
            onChange={(e) => update({ max_posts_per_day: Number(e.target.value) })}
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">Min gap (minutes)</label>
          <input
            type="number"
            value={scheduling.min_gap_minutes}
            onChange={(e) => update({ min_gap_minutes: Number(e.target.value) })}
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">Max posts per week</label>
          <input
            type="number"
            value={scheduling.max_per_week ?? 10}
            onChange={(e) => update({ max_per_week: Number(e.target.value) })}
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">Min tweets for thread</label>
          <input
            type="number"
            value={scheduling.thread_min_tweets ?? 4}
            onChange={(e) => update({ thread_min_tweets: Number(e.target.value) })}
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
          />
        </div>
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">Optimal days</label>
        <div className="flex flex-wrap gap-1">
          {DAYS.map((day) => {
            const selected = scheduling.optimal_days.includes(day);
            return (
              <button
                key={day}
                onClick={() => {
                  const next = selected
                    ? scheduling.optimal_days.filter((d) => d !== day)
                    : [...scheduling.optimal_days, day];
                  update({ optimal_days: next });
                }}
                className={`rounded px-3 py-1.5 text-sm transition-colors ${
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

      <div>
        <label className="mb-1 block text-sm font-medium">Optimal hours</label>
        <div className="flex flex-wrap gap-1">
          {Array.from({ length: 24 }, (_, i) => i).map((h) => {
            const selected = scheduling.optimal_hours.includes(h);
            return (
              <button
                key={h}
                onClick={() => {
                  const next = selected
                    ? scheduling.optimal_hours.filter((x) => x !== h)
                    : [...scheduling.optimal_hours, h].sort((a, b) => a - b);
                  update({ optimal_hours: next });
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
  );
}
