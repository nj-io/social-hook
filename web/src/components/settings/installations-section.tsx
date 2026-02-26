"use client";

import { useCallback, useEffect, useState } from "react";
import type { InstallationsStatus } from "@/lib/types";
import {
  fetchInstallationsStatus,
  installComponent,
  uninstallComponent,
  startBotDaemon,
  stopBotDaemon,
} from "@/lib/api";

const COMPONENTS = [
  {
    key: "commit_hook",
    name: "Commit Hook",
    description: "Triggers evaluation on git commits via Claude Code",
  },
  {
    key: "narrative_hook",
    name: "Narrative Hook",
    description: "Captures dev narratives on context compaction",
  },
  {
    key: "scheduler_cron",
    name: "Scheduler Cron",
    description: "Posts scheduled drafts every minute",
  },
  {
    key: "bot_daemon",
    name: "Bot Daemon",
    description: "Interactive messaging (Telegram, future platforms)",
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

  async function handleAction(component: string, action: "install" | "uninstall" | "start" | "stop") {
    setActionInProgress(component);
    setMessage("");
    try {
      let result: { success: boolean; message: string };
      if (component === "bot_daemon") {
        result = action === "start" ? await startBotDaemon() : await stopBotDaemon();
      } else {
        result = action === "install" ? await installComponent(component) : await uninstallComponent(component);
      }
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
        Manage hooks, cron jobs, and daemons that power the content pipeline.
      </p>

      {message && (
        <p className="text-sm text-muted-foreground">{message}</p>
      )}

      <div className="space-y-2">
        {COMPONENTS.map((comp) => {
          const isInstalled = status?.[comp.key as keyof InstallationsStatus] ?? false;
          const isBotDaemon = comp.key === "bot_daemon";

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
                    {isBotDaemon
                      ? isInstalled ? "Running" : "Stopped"
                      : isInstalled ? "Installed" : "Not installed"}
                  </span>
                </div>
                <p className="mt-0.5 text-xs text-muted-foreground">{comp.description}</p>
              </div>
              <button
                onClick={() => {
                  if (isBotDaemon) {
                    handleAction(comp.key, isInstalled ? "stop" : "start");
                  } else {
                    handleAction(comp.key, isInstalled ? "uninstall" : "install");
                  }
                }}
                disabled={actionInProgress === comp.key}
                className="ml-4 shrink-0 rounded-md border border-border px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted disabled:opacity-50"
              >
                {actionInProgress === comp.key
                  ? "..."
                  : isBotDaemon
                    ? isInstalled ? "Stop" : "Start"
                    : isInstalled ? "Uninstall" : "Install"}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
