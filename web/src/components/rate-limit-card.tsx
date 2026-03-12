"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { fetchRateLimits } from "@/lib/api";
import { useDataEvents } from "@/lib/use-data-events";
import type { RateLimitStatus } from "@/lib/types";

export function RateLimitCard() {
  const [data, setData] = useState<RateLimitStatus | null>(null);
  const [countdown, setCountdown] = useState(0);

  const load = useCallback(async () => {
    try {
      const status = await fetchRateLimits();
      setData(status);
      if (status.next_available_in_seconds > 0) {
        setCountdown(status.next_available_in_seconds);
      } else {
        setCountdown(0);
      }
    } catch {
      // Silent failure — card just won't show data
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 30_000);
    return () => clearInterval(interval);
  }, [load]);

  // Refresh immediately when a pipeline event arrives (decision created, etc.)
  useDataEvents(["decision", "pipeline"], load);

  // Countdown timer
  useEffect(() => {
    if (countdown <= 0) return;
    const timer = setInterval(() => {
      setCountdown((c) => Math.max(0, c - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, [countdown]);

  if (!data) return null;

  const pct = data.max_evaluations_per_day > 0
    ? Math.min(100, (data.evaluations_today / data.max_evaluations_per_day) * 100)
    : 0;

  const minutes = Math.floor(countdown / 60);
  const seconds = countdown % 60;

  return (
    <Link
      href="/settings?section=rate-limits"
      className="block rounded-lg border border-border p-4 transition-colors hover:bg-muted"
    >
      <p className="text-sm text-muted-foreground">Evaluations Today</p>
      <p className="text-2xl font-bold">
        {data.evaluations_today}/{data.max_evaluations_per_day}
      </p>

      {/* Progress bar */}
      <div className="mt-2 h-1.5 w-full rounded-full bg-muted">
        <div
          className={`h-1.5 rounded-full transition-all ${
            pct >= 100 ? "bg-destructive" : pct >= 75 ? "bg-yellow-500" : "bg-accent"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="mt-2 space-y-0.5">
        {/* Countdown or available */}
        <p className="text-xs text-muted-foreground">
          {data.next_available_in_seconds === -1
            ? "Daily cap reached"
            : countdown > 0
              ? `Next in ${minutes}m ${seconds.toString().padStart(2, "0")}s`
              : "Available now"}
        </p>

        {/* Queued triggers */}
        {data.queued_triggers > 0 && (
          <p className="text-xs text-yellow-600 dark:text-yellow-400">
            {data.queued_triggers} queued
          </p>
        )}

        {/* Cost */}
        {data.cost_today_cents > 0 && (
          <p className="text-xs text-muted-foreground">
            ${(data.cost_today_cents / 100).toFixed(2)} today
          </p>
        )}
      </div>
    </Link>
  );
}
