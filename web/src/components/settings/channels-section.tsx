"use client";

import { useCallback, useEffect, useState } from "react";
import type { ChannelConfig, ChannelsStatusResponse } from "@/lib/types";
import { fetchChannelsStatus, testChannel, startBotDaemon, stopBotDaemon, updateEnv } from "@/lib/api";

interface ChannelsSectionProps {
  channels: Record<string, ChannelConfig>;
  onChange: (channels: Record<string, ChannelConfig>) => void;
  env: Record<string, string>;
  onEnvRefresh: () => void;
}

export function ChannelsSection({ channels, onChange, env, onEnvRefresh }: ChannelsSectionProps) {
  const [status, setStatus] = useState<ChannelsStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [testing, setTesting] = useState(false);
  const [daemonAction, setDaemonAction] = useState(false);
  const [tokenValue, setTokenValue] = useState("");
  const [tokenSaving, setTokenSaving] = useState(false);

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

  async function handleTokenSave() {
    if (!tokenValue) return;
    setTokenSaving(true);
    try {
      await updateEnv("TELEGRAM_BOT_TOKEN", tokenValue);
      setTokenValue("");
      onEnvRefresh();
      await loadStatus();
    } catch {
      // Input retains value so user can retry
    } finally {
      setTokenSaving(false);
    }
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

          {/* Bot Token */}
          <div>
            <label className="mb-1 block text-sm font-medium">Bot Token</label>
            <div className="flex gap-2">
              <input
                type="password"
                value={tokenValue}
                onChange={(e) => setTokenValue(e.target.value)}
                placeholder={env.TELEGRAM_BOT_TOKEN ? `Current: ${env.TELEGRAM_BOT_TOKEN}` : "Not set"}
                className="flex-1 rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
              />
              <button
                onClick={handleTokenSave}
                disabled={!tokenValue || tokenSaving}
                className="rounded-md bg-accent px-3 py-2 text-sm font-medium text-accent-foreground transition-colors hover:bg-accent/80 disabled:opacity-50"
              >
                {tokenSaving ? "..." : "Save"}
              </button>
            </div>
          </div>

          {telegramConfig.enabled && (
            <div>
              <label className="mb-1 flex items-center gap-1.5 text-sm font-medium">
                Allowed Chat IDs (comma-separated)
                <span className="group relative cursor-help text-muted-foreground">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
                    <path fillRule="evenodd" d="M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0ZM8.94 6.94a.75.75 0 1 1-1.061-1.061 3 3 0 1 1 2.871 5.026v.345a.75.75 0 0 1-1.5 0v-.5c0-.72.57-1.172 1.081-1.287A1.5 1.5 0 1 0 8.94 6.94ZM10 15a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z" clipRule="evenodd" />
                  </svg>
                  <span className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1.5 w-48 -translate-x-1/2 rounded-md bg-popover px-3 py-2 text-xs text-popover-foreground shadow-md opacity-0 transition-opacity group-hover:opacity-100">
                    Message <strong>@userinfobot</strong> on Telegram to get your chat ID.
                  </span>
                </span>
              </label>
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

          {telegramConfig.enabled && !status?.daemon_running && (
            <div className="rounded-md bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-900/20 dark:text-amber-400">
              <p>
                The bot daemon must be running to receive button presses and messages from this channel.
                Notifications will be sent without interactive buttons until the daemon is started.
              </p>
              <button
                onClick={handleDaemonToggle}
                disabled={daemonAction}
                className="mt-2 rounded-md bg-amber-200 px-3 py-1 text-xs font-medium text-amber-900 transition-colors hover:bg-amber-300 disabled:opacity-50 dark:bg-amber-800 dark:text-amber-200 dark:hover:bg-amber-700"
              >
                {daemonAction ? "Starting..." : "Start Daemon"}
              </button>
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
        {(() => {
          const webConfig = channels?.web ?? { enabled: true, allowed_chat_ids: [] };
          return (
            <div className="rounded-lg border border-border p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-medium">Web</span>
                  <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-900/30 dark:text-green-400">
                    Built-in
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <button
                    onClick={() =>
                      onChange({ ...channels, web: { ...webConfig, enabled: !webConfig.enabled } })
                    }
                    className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
                      webConfig.enabled ? "bg-accent" : "bg-border"
                    }`}
                  >
                    <span
                      className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
                        webConfig.enabled ? "left-[22px]" : "left-0.5"
                      }`}
                    />
                  </button>
                  <span className="text-sm">{webConfig.enabled ? "Enabled" : "Disabled"}</span>
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                Receive draft notifications in the web dashboard. Active when the dashboard is running.
              </p>
            </div>
          );
        })()}
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
