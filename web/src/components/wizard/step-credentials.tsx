"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchOAuthAuthorize, fetchOAuthStatus } from "@/lib/api";
import { platformLabel } from "@/lib/platform";
import { Note } from "@/components/ui/note";

interface StepCredentialsProps {
  llmApiKey: string;
  platformCredentials: Record<string, string>;
  enabledPlatforms: string[];
  onLlmApiKeyChange: (v: string) => void;
  onPlatformCredentialsChange: (v: Record<string, string>) => void;
  templatePreFilled: boolean;
  hasClaudeCli?: boolean;
}

const OAUTH_PLATFORMS = ["x", "linkedin"];

const PLATFORM_CREDENTIAL_KEYS: Record<string, { label: string; keys: { key: string; label: string; placeholder: string }[] }> = {
  x: {
    label: "X (Twitter)",
    keys: [
      { key: "X_CLIENT_ID", label: "Client ID", placeholder: "Your X Client ID" },
      { key: "X_CLIENT_SECRET", label: "Client Secret", placeholder: "Your X Client Secret" },
    ],
  },
  linkedin: {
    label: "LinkedIn",
    keys: [
      { key: "LINKEDIN_CLIENT_ID", label: "Client ID", placeholder: "Your LinkedIn Client ID" },
      { key: "LINKEDIN_CLIENT_SECRET", label: "Client Secret", placeholder: "Your LinkedIn Client Secret" },
    ],
  },
};

const OAUTH_PORTAL_URLS: Record<string, { label: string; url: string }> = {
  x: { label: "X Developer Portal", url: "https://developer.x.com/en/portal/dashboard" },
  linkedin: { label: "LinkedIn Developer Portal", url: "https://www.linkedin.com/developers/apps" },
};

const MEDIA_CREDENTIAL_KEYS = [
  { key: "GEMINI_API_KEY", label: "Gemini API Key", description: "For AI-generated images (Nano Banana Pro)", placeholder: "Your Gemini API key" },
];

export function StepCredentials({
  llmApiKey,
  platformCredentials,
  enabledPlatforms,
  onLlmApiKeyChange,
  onPlatformCredentialsChange,
  templatePreFilled,
  hasClaudeCli,
}: StepCredentialsProps) {
  const [expanded, setExpanded] = useState(!templatePreFilled);
  const realPlatforms = enabledPlatforms.filter((p) => PLATFORM_CREDENTIAL_KEYS[p]);
  const noAccountsConfigured = realPlatforms.length === 0;
  const needsLlmKey = !hasClaudeCli;

  // OAuth connection state — per platform
  const oauthPlatformsEnabled = enabledPlatforms.filter((p) => OAUTH_PLATFORMS.includes(p));
  const [oauthStatuses, setOauthStatuses] = useState<Record<string, { connected: boolean; username: string }>>({});
  const [oauthLoading, setOauthLoading] = useState<Record<string, boolean>>({});
  const [callbackUrls, setCallbackUrls] = useState<Record<string, string>>({});

  const checkOAuthStatuses = useCallback(async () => {
    for (const p of oauthPlatformsEnabled) {
      try {
        const status = await fetchOAuthStatus(p);
        setOauthStatuses((prev) => ({ ...prev, [p]: status }));
        if (status.callback_url) setCallbackUrls((prev) => ({ ...prev, [p]: status.callback_url }));
      } catch {
        // ignore
      }
    }
  }, [oauthPlatformsEnabled.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    checkOAuthStatuses();
  }, [checkOAuthStatuses]);

  useEffect(() => {
    if (oauthPlatformsEnabled.length === 0) return;
    function onMessage(e: MessageEvent) {
      if (e.data === "oauth_complete") {
        checkOAuthStatuses();
      }
    }
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [oauthPlatformsEnabled.length, checkOAuthStatuses]);

  async function handleOAuthConnect(platform: string) {
    setOauthLoading((prev) => ({ ...prev, [platform]: true }));
    try {
      const data = await fetchOAuthAuthorize(platform);
      if (data.callback_url) setCallbackUrls((prev) => ({ ...prev, [platform]: data.callback_url }));
      window.open(data.auth_url, "_blank");
    } catch {
      // ignore
    } finally {
      setOauthLoading((prev) => ({ ...prev, [platform]: false }));
    }
  }

  // Nothing needed: Claude CLI detected + no accounts configured
  if (hasClaudeCli && noAccountsConfigured && !expanded) {
    return (
      <div className="animate-wizard-dissolve space-y-4">
        <div>
          <h3 className="text-lg font-semibold">Credentials</h3>
        </div>
        <div className="rounded-md border border-green-200 bg-green-50 p-4 text-sm text-green-800 dark:border-green-800 dark:bg-green-900/20 dark:text-green-300">
          <span className="font-medium">Claude Code detected</span> — content generation will use your existing Claude subscription at no extra cost.
          No API keys needed. Connect an account when you&#39;re ready to post.
        </div>
        <button
          onClick={() => setExpanded(true)}
          className="text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          Configure manually instead
        </button>
      </div>
    );
  }

  return (
    <div className="animate-wizard-dissolve space-y-4">
      <div>
        <h3 className="text-lg font-semibold">Credentials</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          API keys for content generation{realPlatforms.length > 0 ? " and publishing" : ""}.
        </p>
      </div>

      {/* LLM API Key */}
      {needsLlmKey ? (
        <div className="space-y-3 rounded-lg border border-border p-4">
          <h4 className="text-sm font-medium">LLM API Key</h4>
          <p className="text-xs text-muted-foreground">
            Required for content generation. Supports Anthropic, OpenAI, or OpenRouter keys.
          </p>
          <input
            type="password"
            value={llmApiKey}
            onChange={(e) => onLlmApiKeyChange(e.target.value)}
            placeholder="sk-ant-... or sk-..."
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
          />
        </div>
      ) : (
        <div className="rounded-md border border-green-200 bg-green-50 p-4 text-sm text-green-800 dark:border-green-800 dark:bg-green-900/20 dark:text-green-300">
          <span className="font-medium">Claude Code detected</span> — uses your existing subscription ($0 extra cost).
        </div>
      )}

      {/* Platform credentials */}
      {realPlatforms.length > 0 && (
        <>
          <h4 className="text-sm font-medium text-muted-foreground">Platform API Keys</h4>
          {realPlatforms.map((platformName) => {
            const info = PLATFORM_CREDENTIAL_KEYS[platformName];
            if (!info) return null;
            const isOAuth = OAUTH_PLATFORMS.includes(platformName);
            const clientIdKey = `${platformName.toUpperCase()}_CLIENT_ID`;
            const portal = OAUTH_PORTAL_URLS[platformName];
            const status = oauthStatuses[platformName];
            const loading = oauthLoading[platformName] ?? false;
            const cbUrl = callbackUrls[platformName];
            return (
              <div key={platformName} className="space-y-3 rounded-lg border border-border p-4">
                <h4 className="text-sm font-medium">{info.label}</h4>
                {info.keys.map((k) => (
                  <div key={k.key}>
                    <label className="mb-1 block text-xs font-medium">{k.label}</label>
                    <input
                      type="password"
                      value={platformCredentials[k.key] ?? ""}
                      onChange={(e) =>
                        onPlatformCredentialsChange({ ...platformCredentials, [k.key]: e.target.value })
                      }
                      placeholder={k.placeholder}
                      className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
                    />
                  </div>
                ))}
                {/* OAuth connect button */}
                {isOAuth && (
                  <div className="border-t border-border pt-3">
                    <p className="mb-2 text-xs font-medium text-muted-foreground">Authorization</p>
                    {status?.connected ? (
                      <div className="flex items-center gap-2">
                        <span className="inline-block h-2 w-2 rounded-full bg-green-500" />
                        <span className="text-sm text-green-700 dark:text-green-400">
                          Connected{status.username ? ` as @${status.username}` : ""}
                        </span>
                        <button
                          type="button"
                          onClick={() => handleOAuthConnect(platformName)}
                          disabled={loading}
                          className="ml-auto text-xs text-muted-foreground hover:text-foreground"
                        >
                          {loading ? "..." : "Re-authorize"}
                        </button>
                        <button
                          type="button"
                          onClick={async () => {
                            const { fetchOAuthDisconnect } = await import("@/lib/api");
                            await fetchOAuthDisconnect(platformName);
                            setOauthStatuses((prev) => ({ ...prev, [platformName]: { connected: false, username: "" } }));
                          }}
                          className="text-xs text-red-500 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300"
                        >
                          Disconnect
                        </button>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => handleOAuthConnect(platformName)}
                          disabled={loading || !platformCredentials[clientIdKey]}
                          className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-foreground transition-colors hover:bg-accent/80 disabled:opacity-50"
                        >
                          {loading ? "Opening..." : `Connect ${platformLabel(platformName)} Account`}
                        </button>
                        {!platformCredentials[clientIdKey] && (
                          <span className="text-xs text-muted-foreground">
                            Enter Client ID first
                          </span>
                        )}
                      </div>
                    )}
                    <Note variant="info" className="mt-2">
                      Ensure{" "}
                      <code className="rounded bg-muted px-1">
                        {cbUrl || `http://localhost:{api-port}/api/oauth/${platformName}/callback`}
                      </code>{" "}
                      is registered in your{" "}
                      {portal ? (
                        <a href={portal.url} target="_blank" rel="noopener noreferrer" className="underline hover:text-foreground">
                          {portal.label}
                        </a>
                      ) : (
                        <span>{platformLabel(platformName)} Developer Portal</span>
                      )}{" "}
                      Redirect URIs.
                    </Note>
                  </div>
                )}
              </div>
            );
          })}
        </>
      )}

      {realPlatforms.length === 0 && needsLlmKey && (
        <p className="text-xs text-muted-foreground">
          No API keys needed. Connect an account when you&#39;re ready to post.
          You can add platform keys later in Settings.
        </p>
      )}

      {/* Media generation credentials */}
      <div className="space-y-3">
        <h4 className="text-sm font-medium text-muted-foreground">Media Generation (optional)</h4>
        <p className="text-xs text-muted-foreground">
          API keys for generating images and media to accompany your posts. These are optional and can be added later.
        </p>
        {MEDIA_CREDENTIAL_KEYS.map((mk) => (
          <div key={mk.key} className="rounded-lg border border-border p-4">
            <label className="mb-1 block text-xs font-medium">{mk.label}</label>
            <p className="mb-2 text-xs text-muted-foreground">{mk.description}</p>
            <input
              type="password"
              value={platformCredentials[mk.key] ?? ""}
              onChange={(e) =>
                onPlatformCredentialsChange({ ...platformCredentials, [mk.key]: e.target.value })
              }
              placeholder={mk.placeholder}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
            />
          </div>
        ))}
      </div>
    </div>
  );
}
