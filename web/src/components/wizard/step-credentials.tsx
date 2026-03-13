"use client";

import { useState } from "react";

interface StepCredentialsProps {
  llmApiKey: string;
  platformCredentials: Record<string, string>;
  enabledPlatforms: string[];
  onLlmApiKeyChange: (v: string) => void;
  onPlatformCredentialsChange: (v: Record<string, string>) => void;
  templatePreFilled: boolean;
}

const PLATFORM_CREDENTIAL_KEYS: Record<string, { label: string; keys: { key: string; label: string; placeholder: string }[] }> = {
  x: {
    label: "X (Twitter)",
    keys: [
      { key: "X_API_KEY", label: "API Key", placeholder: "Your X API key" },
      { key: "X_API_SECRET", label: "API Secret", placeholder: "Your X API secret" },
      { key: "X_ACCESS_TOKEN", label: "Access Token", placeholder: "Your X access token" },
      { key: "X_ACCESS_SECRET", label: "Access Secret", placeholder: "Your X access secret" },
    ],
  },
  linkedin: {
    label: "LinkedIn",
    keys: [
      { key: "LINKEDIN_ACCESS_TOKEN", label: "Access Token", placeholder: "Your LinkedIn access token" },
    ],
  },
};

export function StepCredentials({
  llmApiKey,
  platformCredentials,
  enabledPlatforms,
  onLlmApiKeyChange,
  onPlatformCredentialsChange,
  templatePreFilled,
}: StepCredentialsProps) {
  const [expanded, setExpanded] = useState(!templatePreFilled);
  const platformsNeedingCreds = enabledPlatforms.filter((p) => p !== "preview" && PLATFORM_CREDENTIAL_KEYS[p]);
  const hasAllCreds = !!llmApiKey;

  if (templatePreFilled && hasAllCreds && !expanded) {
    return (
      <div className="animate-wizard-dissolve space-y-4">
        <div>
          <h3 className="text-lg font-semibold">Credentials</h3>
          <p className="mt-1 text-sm text-muted-foreground">API keys appear to be configured.</p>
        </div>
        <div className="rounded-md border border-border bg-muted/50 p-4 text-sm text-muted-foreground">
          LLM API key is set. You can skip this step or customize below.
        </div>
        <button
          onClick={() => setExpanded(true)}
          className="rounded-md border border-border px-4 py-2 text-sm font-medium transition-colors hover:bg-muted"
        >
          Customize
        </button>
      </div>
    );
  }

  return (
    <div className="animate-wizard-dissolve space-y-4">
      <div>
        <h3 className="text-lg font-semibold">Credentials</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          API keys for the LLM and any platforms you want to post to.
        </p>
      </div>

      <div className="space-y-3 rounded-lg border border-border p-4">
        <h4 className="text-sm font-medium">LLM API Key</h4>
        <p className="text-xs text-muted-foreground">
          Required for content generation. If you use Claude Code, the key may auto-detect from your environment.
        </p>
        <input
          type="password"
          value={llmApiKey}
          onChange={(e) => onLlmApiKeyChange(e.target.value)}
          placeholder="sk-ant-... or sk-..."
          className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
        />
      </div>

      {platformsNeedingCreds.map((platformName) => {
        const info = PLATFORM_CREDENTIAL_KEYS[platformName];
        if (!info) return null;
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
          </div>
        );
      })}

      {platformsNeedingCreds.length === 0 && (
        <div className="rounded-md border border-border bg-muted/50 p-4 text-sm text-muted-foreground">
          No platform credentials needed. Preview platform does not require API keys.
        </div>
      )}
    </div>
  );
}
