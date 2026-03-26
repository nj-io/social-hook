"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useDataEvents } from "@/lib/use-data-events";

interface AnalysisQueueData {
  count: number;
  interval: number;
}

export function AnalysisQueueCard({ projectId }: { projectId: string }) {
  const [data, setData] = useState<AnalysisQueueData | null>(null);

  const load = useCallback(async () => {
    try {
      const [projRes, configRes] = await Promise.all([
        fetch(`/api/projects/${encodeURIComponent(projectId)}`),
        fetch("/api/settings/content-config/parsed"),
      ]);
      if (!projRes.ok || !configRes.ok) return;
      const proj = await projRes.json();
      const config = await configRes.json();
      const interval = config?.context?.commit_analysis_interval ?? 1;
      const count = proj?.analysis_commit_count ?? 0;
      setData({ count, interval });
    } catch {
      // Silent — card just won't show
    }
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  useDataEvents(["decision", "pipeline"], load, projectId);

  if (!data || data.interval <= 1) return null;

  const pct = data.interval > 0
    ? Math.min(100, (data.count / data.interval) * 100)
    : 0;

  return (
    <Link
      href="/settings?section=rate-limits"
      className="block rounded-lg border border-border p-4 transition-colors hover:bg-muted"
    >
      <p className="text-sm text-muted-foreground">Analysis Queue</p>
      <p className="text-2xl font-bold">
        {data.count}/{data.interval}
      </p>

      <div className="mt-2 h-1.5 w-full rounded-full bg-muted">
        <div
          className={`h-1.5 rounded-full transition-all ${
            pct >= 100 ? "bg-accent" : "bg-blue-500"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>

      <p className="mt-2 text-xs text-muted-foreground">
        {data.count === 0
          ? "Next commit triggers full evaluation"
          : pct >= 100
            ? "Threshold reached — next commit evaluates"
            : `${data.interval - data.count} more commit${data.interval - data.count !== 1 ? "s" : ""} until evaluation`}
      </p>
    </Link>
  );
}
