"use client";

import { useCallback, useEffect, useState } from "react";
import type { InstallationsStatus } from "@/lib/types";
import {
  fetchInstallationsStatus,
  installComponent,
  uninstallComponent,
} from "@/lib/api";

const COMPONENTS = [
  {
    key: "narrative_hook",
    name: "Claude Code Narrative Hook",
    description: "Captures dev session context on compaction (Claude Code only)",
  },
  {
    key: "scheduler_cron",
    name: "Scheduler Cron",
    description: "Posts scheduled drafts every minute",
  },
] as const;

export function InstallationsSection() {
  const [status, setStatus] = useState<InstallationsStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);
  const [message, setMessage] = useState("");

  const loadStatus = useCallback(async () => {
    try {
      const res = await fetchInstallationsStatus();
      setStatus(res);
    } catch {
      // Silently handle
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  async function handleAction(component: string, action: "install" | "uninstall") {
    setActionInProgress(component);
    setMessage("");
    try {
      const result = action === "install" ? await installComponent(component) : await uninstallComponent(component);
      setMessage(result.message);
      await loadStatus();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Action failed");
    } finally {
      setActionInProgress(null);
      setTimeout(() => setMessage(""), 3000);
    }
  }

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading installation status...</p>;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Installations</h2>
      <p className="text-sm text-muted-foreground">
        Manage hooks and cron jobs that power the content pipeline. Commit hook controls are in the Projects section.
      </p>

      {message && (
        <p className="text-sm text-muted-foreground">{message}</p>
      )}

      <div className="space-y-2">
        {COMPONENTS.map((comp) => {
          const isInstalled = status?.[comp.key as keyof InstallationsStatus] ?? false;

          return (
            <div
              key={comp.key}
              className="flex items-center justify-between rounded-lg border border-border p-4"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{comp.name}</span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                      isInstalled
                        ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400"
                        : "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400"
                    }`}
                  >
                    {isInstalled ? "Installed" : "Not installed"}
                  </span>
                </div>
                <p className="mt-0.5 text-xs text-muted-foreground">{comp.description}</p>
              </div>
              <button
                onClick={() => handleAction(comp.key, isInstalled ? "uninstall" : "install")}
                disabled={actionInProgress === comp.key}
                className="ml-4 shrink-0 rounded-md border border-border px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted disabled:opacity-50"
              >
                {actionInProgress === comp.key ? "..." : isInstalled ? "Uninstall" : "Install"}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
