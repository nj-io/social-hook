"use client";

import { useCallback, useEffect, useState } from "react";
import type { ChannelConfig, ChannelsStatusResponse } from "@/lib/types";
import { fetchChannelsStatus, testChannel, startBotDaemon, stopBotDaemon } from "@/lib/api";

interface ChannelsSectionProps {
  channels: Record<string, ChannelConfig>;
  onChange: (channels: Record<string, ChannelConfig>) => void;
}

export function ChannelsSection({ channels, onChange }: ChannelsSectionProps) {
  const [status, setStatus] = useState<ChannelsStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [testing, setTesting] = useState(false);
  const [daemonAction, setDaemonAction] = useState(false);

  const loadStatus = useCallback(async () => {
    try {
      const res = await fetchChannelsStatus();
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

  // Re-fetch status when channels prop changes
  useEffect(() => {
    loadStatus();
  }, [channels, loadStatus]);

  const telegramStatus = status?.channels?.telegram;
  const telegramConfig = channels?.telegram ?? { enabled: false, allowed_chat_ids: [] };
  const [chatIdsInput, setChatIdsInput] = useState(telegramConfig.allowed_chat_ids.join(", "));

  // Sync local input when prop changes externally
  useEffect(() => {
    setChatIdsInput(telegramConfig.allowed_chat_ids.join(", "));
  }, [telegramConfig.allowed_chat_ids.join(",")]);

  async function handleTest() {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await testChannel("telegram");
      if (res.success) {
        setTestResult({ success: true, message: `Connected as @${res.info?.username ?? "unknown"}` });
      } else {
        setTestResult({ success: false, message: res.error ?? "Test failed" });
      }
    } catch (e) {
      setTestResult({ success: false, message: e instanceof Error ? e.message : "Test failed" });
    } finally {
      setTesting(false);
      setTimeout(() => setTestResult(null), 5000);
    }
  }

  async function handleDaemonToggle() {
    setDaemonAction(true);
    try {
      if (status?.daemon_running) {
        await stopBotDaemon();
      } else {
        await startBotDaemon();
      }
      await loadStatus();
    } catch {
      // Silently handle
    } finally {
      setDaemonAction(false);
    }
  }

  function navigateToApiKeys() {
    window.dispatchEvent(new CustomEvent("settings-navigate", { detail: "api-keys" }));
  }

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading channels status...</p>;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Channels</h2>
      <p className="text-sm text-muted-foreground">
        Configure messaging channels for draft approval and bot interactions.
      </p>

      <div className="space-y-3">
        {/* Telegram card */}
        <div className="rounded-lg border border-border p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="font-medium">Telegram</span>
              <span
                className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                  telegramStatus?.credentials_configured
                    ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400"
                    : "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400"
                }`}
              >
                {telegramStatus?.credentials_configured ? "Configured" : "Not configured"}
              </span>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={() =>
                  onChange({ ...channels, telegram: { ...telegramConfig, enabled: !telegramConfig.enabled } })
                }
                className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
                  telegramConfig.enabled ? "bg-accent" : "bg-border"
                }`}
              >
                <span
                  className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
                    telegramConfig.enabled ? "left-[22px]" : "left-0.5"
                  }`}
                />
              </button>
              <span className="text-sm">{telegramConfig.enabled ? "Enabled" : "Disabled"}</span>
            </div>
          </div>

          {!telegramStatus?.credentials_configured && (
            <button
              onClick={navigateToApiKeys}
              className="rounded-md border border-border px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted"
            >
              Set up in API Keys
            </button>
          )}

          {telegramConfig.enabled && (
            <div>
              <label className="mb-1 block text-sm font-medium">Allowed Chat IDs (comma-separated)</label>
              <input
                type="text"
                value={chatIdsInput}
                onChange={(e) => setChatIdsInput(e.target.value)}
                onBlur={() => {
                  const ids = chatIdsInput
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean);
                  onChange({ ...channels, telegram: { ...telegramConfig, allowed_chat_ids: ids } });
                }}
                placeholder="e.g. 123456789, -100987654321"
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
              />
            </div>
          )}

          <div className="flex items-center gap-2">
            <button
              onClick={handleTest}
              disabled={testing}
              className="rounded-md border border-border px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted disabled:opacity-50"
            >
              {testing ? "Testing..." : "Test Connection"}
            </button>
            {testResult && (
              <span
                className={`text-sm ${
                  testResult.success ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"
                }`}
              >
                {testResult.message}
              </span>
            )}
          </div>
        </div>

        {/* Slack card */}
        <div className="rounded-lg border border-border p-4">
          <div className="flex items-center gap-2">
            <span className="font-medium">Slack</span>
            <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
              Coming Soon
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">Slack integration is not yet available.</p>
        </div>

        {/* Web card */}
        <div className="rounded-lg border border-border p-4">
          <div className="flex items-center gap-2">
            <span className="font-medium">Web</span>
            <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-900/30 dark:text-green-400">
              Built-in
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Active when the dashboard is running. No configuration needed.
          </p>
        </div>
      </div>

      {/* Daemon controls */}
      <div className="rounded-lg border border-border p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="font-medium">Bot Daemon</span>
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                status?.daemon_running
                  ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400"
                  : "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400"
              }`}
            >
              {status?.daemon_running ? "Running" : "Stopped"}
            </span>
          </div>
          <button
            onClick={handleDaemonToggle}
            disabled={daemonAction}
            className="rounded-md border border-border px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted disabled:opacity-50"
          >
            {daemonAction ? "..." : status?.daemon_running ? "Stop" : "Start"}
          </button>
        </div>
        <p className="text-xs text-muted-foreground">
          The bot daemon runs all enabled channels as a single process. Currently supports Telegram.
        </p>
      </div>
    </div>
  );
}
