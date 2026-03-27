"use client";

import { useCallback, useEffect, useState } from "react";
import type { SystemError, SystemHealth } from "@/lib/types";
import { fetchSystemErrors, fetchSystemHealth, clearSystemErrors } from "@/lib/api";
import { useDataEvents } from "@/lib/use-data-events";
import { Modal } from "@/components/ui/modal";

const SEVERITY_STYLES: Record<string, string> = {
  info: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
  warning: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
  error: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  critical: "bg-red-200 text-red-900 dark:bg-red-900/50 dark:text-red-300",
};

const POLL_INTERVAL_MS = 30_000;

export function ErrorFeed() {
  const [errors, setErrors] = useState<SystemError[]>([]);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [severityFilter, setSeverityFilter] = useState("");
  const [componentFilter, setComponentFilter] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [clearing, setClearing] = useState(false);

  const load = useCallback(async () => {
    try {
      const params: Record<string, string> = {};
      if (severityFilter) params.severity = severityFilter;
      if (componentFilter) params.component = componentFilter;
      const [e, h] = await Promise.all([
        fetchSystemErrors(Object.keys(params).length > 0 ? params : undefined),
        fetchSystemHealth(),
      ]);
      setErrors(e.errors);
      setHealth(h);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [severityFilter, componentFilter]);

  useEffect(() => {
    load();
    const interval = setInterval(load, 30_000);
    return () => clearInterval(interval);
  }, [load]);
  useDataEvents(["error"], load);

  // WebSocket live updates
  useDataEvents(["system_error"], load);

  // 30s poll fallback
  useEffect(() => {
    const timer = setInterval(load, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [load]);

  // Collect unique components for filter dropdown
  const components = Array.from(new Set(errors.map((e) => e.component).filter(Boolean)));

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
            {health.total_errors_24h > 0 && (
              <span className="text-xs text-muted-foreground">
                {health.total_errors_24h} error{health.total_errors_24h !== 1 ? "s" : ""} in 24h
              </span>
            )}
          </div>
          {health.error_counts_24h && health.total_errors_24h > 0 && (
            <div className="mt-2 flex gap-3 text-xs text-muted-foreground">
              {Object.entries(health.error_counts_24h)
                .filter(([, count]) => count > 0)
                .map(([sev, count]) => (
                  <span key={sev} className={`rounded-full px-2 py-0.5 ${SEVERITY_STYLES[sev] ?? ""}`}>
                    {sev}: {count}
                  </span>
                ))}
            </div>
          )}
        </div>
      )}

      {/* Filters + Clear */}
      <div className="flex items-center gap-3">
        <select
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value)}
          className="rounded border border-border bg-background px-2 py-1 text-sm"
        >
          <option value="">All severities</option>
          <option value="info">Info</option>
          <option value="warning">Warning</option>
          <option value="error">Error</option>
          <option value="critical">Critical</option>
        </select>
        {components.length > 0 && (
          <select
            value={componentFilter}
            onChange={(e) => setComponentFilter(e.target.value)}
            className="rounded border border-border bg-background px-2 py-1 text-sm"
          >
            <option value="">All components</option>
            {components.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        )}
        {errors.length > 0 && (
          <button
            onClick={() => setShowClearConfirm(true)}
            className="ml-auto rounded border border-red-300 px-2 py-1 text-xs text-red-600 hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-900/20"
          >
            Clear all
          </button>
        )}
      </div>

      <div>
        <h3 className="mb-2 text-sm font-medium text-muted-foreground">Recent Errors</h3>
        {errors.length === 0 ? (
          <p className="text-sm text-muted-foreground">No recent errors.</p>
        ) : (
          <div className="space-y-2">
            {errors.map((err) => (
              <div
                key={err.id}
                className="rounded-lg border border-border p-3 cursor-pointer"
                onClick={() => setExpandedId(expandedId === err.id ? null : err.id)}
              >
                <div className="flex items-center gap-2">
                  <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                    SEVERITY_STYLES[err.severity] ?? SEVERITY_STYLES.error
                  }`}>
                    {err.severity}
                  </span>
                  {err.component && (
                    <span className="rounded bg-muted px-1.5 py-0.5 text-xs">{err.component}</span>
                  )}
                  {err.source && (
                    <span className="text-xs text-muted-foreground">{err.source}</span>
                  )}
                  <span className="text-xs text-muted-foreground">
                    {new Date(err.created_at).toLocaleString()}
                  </span>
                </div>
                <p className="mt-1 text-sm">{err.message}</p>
                {expandedId === err.id && err.context && err.context !== "{}" && (
                  <pre className="mt-2 max-h-48 overflow-auto rounded bg-muted p-2 text-xs">
                    {(() => {
                      try {
                        return JSON.stringify(JSON.parse(err.context), null, 2);
                      } catch {
                        return err.context;
                      }
                    })()}
                  </pre>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <Modal open={showClearConfirm} onClose={() => !clearing && setShowClearConfirm(false)} maxWidth="max-w-sm">
        <h3 className="text-sm font-semibold">Clear all system errors?</h3>
        <p className="mt-2 text-sm text-muted-foreground">
          This will permanently delete {errors.length} error record{errors.length !== 1 ? "s" : ""}.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={() => setShowClearConfirm(false)}
            disabled={clearing}
            className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={async () => {
              setClearing(true);
              try {
                await clearSystemErrors();
                setShowClearConfirm(false);
                load();
              } finally {
                setClearing(false);
              }
            }}
            disabled={clearing}
            className="rounded-md bg-red-600 px-3 py-1.5 text-sm text-white hover:bg-red-700 disabled:opacity-50"
          >
            {clearing ? "Clearing..." : "Clear all"}
          </button>
        </div>
      </Modal>
    </div>
  );
}
