"use client";

import { useCallback, useEffect, useState } from "react";
import type { SystemError, SystemHealth } from "@/lib/types";
import { fetchSystemErrors, fetchSystemHealth } from "@/lib/api";

const SEVERITY_STYLES: Record<string, string> = {
  info: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
  warning: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
  error: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  critical: "bg-red-200 text-red-900 dark:bg-red-900/50 dark:text-red-300",
};

export function ErrorFeed() {
  const [errors, setErrors] = useState<SystemError[]>([]);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [e, h] = await Promise.all([
        fetchSystemErrors(),
        fetchSystemHealth(),
      ]);
      setErrors(e.errors);
      setHealth(h);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading system status...</p>;
  }

  return (
    <div className="space-y-4">
      {health && (
        <div className="rounded-lg border border-border p-4">
          <div className="flex items-center gap-2">
            <span className={`h-2.5 w-2.5 rounded-full ${
              health.status === "healthy" ? "bg-green-500" : health.status === "degraded" ? "bg-yellow-500" : "bg-red-500"
            }`} />
            <span className="font-medium capitalize">{health.status}</span>
            {health.error_count > 0 && (
              <span className="text-xs text-muted-foreground">
                {health.error_count} recent error{health.error_count !== 1 ? "s" : ""}
              </span>
            )}
          </div>
        </div>
      )}

      <div>
        <h3 className="mb-2 text-sm font-medium text-muted-foreground">Recent Errors</h3>
        {errors.length === 0 ? (
          <p className="text-sm text-muted-foreground">No recent errors.</p>
        ) : (
          <div className="space-y-2">
            {errors.map((err) => (
              <div key={err.id} className="rounded-lg border border-border p-3">
                <div className="flex items-center gap-2">
                  <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                    SEVERITY_STYLES[err.severity] ?? SEVERITY_STYLES.error
                  }`}>
                    {err.severity}
                  </span>
                  {err.source && (
                    <span className="text-xs text-muted-foreground">{err.source}</span>
                  )}
                  <span className="text-xs text-muted-foreground">
                    {new Date(err.created_at).toLocaleString()}
                  </span>
                </div>
                <p className="mt-1 text-sm">{err.message}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
