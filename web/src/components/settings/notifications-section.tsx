"use client";

import type { WebDashboardConfig } from "@/lib/types";

interface NotificationsSectionProps {
  webCfg: WebDashboardConfig;
  onChange: (web: WebDashboardConfig) => void;
  telegramConfigured: boolean;
}

export function NotificationsSection({ webCfg, onChange, telegramConfigured }: NotificationsSectionProps) {
  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Notifications</h2>
      <p className="text-sm text-muted-foreground">
        Configure how you receive draft notifications and interact with the pipeline.
      </p>

      {/* Web notifications */}
      <div className="rounded-lg border border-border p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-medium">Web Notifications</h3>
            <p className="text-xs text-muted-foreground">
              Enable the web dashboard for reviewing and approving drafts in your browser.
            </p>
          </div>
          <button
            onClick={() => onChange({ ...webCfg, enabled: !webCfg.enabled })}
            className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
              webCfg.enabled ? "bg-accent" : "bg-border"
            }`}
          >
            <span
              className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
                webCfg.enabled ? "left-[22px]" : "left-0.5"
              }`}
            />
          </button>
        </div>

        {webCfg.enabled && (
          <div>
            <label className="mb-1 block text-sm font-medium">Port</label>
            <input
              type="number"
              value={webCfg.port}
              onChange={(e) => onChange({ ...webCfg, port: Number(e.target.value) })}
              className="rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
            />
          </div>
        )}
      </div>

      {/* Telegram status */}
      <div className="rounded-lg border border-border p-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-medium">Telegram</h3>
            <p className="text-xs text-muted-foreground">
              Receive draft notifications and approve/reject via Telegram bot.
            </p>
          </div>
          <span
            className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
              telegramConfigured
                ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400"
                : "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400"
            }`}
          >
            {telegramConfigured ? "Configured" : "Not configured"}
          </span>
        </div>
        {!telegramConfigured && (
          <p className="mt-2 text-xs text-muted-foreground">
            Set <code className="rounded bg-muted px-1 py-0.5">TELEGRAM_BOT_TOKEN</code> and{" "}
            <code className="rounded bg-muted px-1 py-0.5">TELEGRAM_ALLOWED_CHAT_IDS</code> in the{" "}
            <button
              onClick={() => {
                // Navigate to API Keys section - parent handles via section state
                const event = new CustomEvent("settings-navigate", { detail: "api-keys" });
                window.dispatchEvent(event);
              }}
              className="text-accent underline underline-offset-2 hover:text-accent/80"
            >
              API Keys
            </button>{" "}
            section.
          </p>
        )}
      </div>
    </div>
  );
}
