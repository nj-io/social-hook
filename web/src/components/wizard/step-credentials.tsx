"use client";

import { useState } from "react";

interface StepCredentialsProps {
  llmApiKey: string;
  platformCredentials: Record<string, string>;
  enabledPlatforms: string[];
  onLlmApiKeyChange: (v: string) => void;
  onPlatformCredentialsChange: (v: Record<string, string>) => void;
  templatePreFilled: boolean;
  hasClaudeCli?: boolean;
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
  const realPlatforms = enabledPlatforms.filter((p) => p !== "preview" && PLATFORM_CREDENTIAL_KEYS[p]);
  const previewOnly = enabledPlatforms.length === 0 || (enabledPlatforms.length === 1 && enabledPlatforms[0] === "preview");
  const needsLlmKey = !hasClaudeCli;

  // Nothing needed: Claude CLI detected + preview only
  if (hasClaudeCli && previewOnly && !expanded) {
    return (
      <div className="animate-wizard-dissolve space-y-4">
        <div>
          <h3 className="text-lg font-semibold">Credentials</h3>
        </div>
        <div className="rounded-md border border-green-200 bg-green-50 p-4 text-sm text-green-800 dark:border-green-800 dark:bg-green-900/20 dark:text-green-300">
          <span className="font-medium">Claude Code detected</span> — content generation will use your existing Claude subscription at no extra cost.
          No additional API keys are needed for preview mode.
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
        </>
      )}

      {realPlatforms.length === 0 && needsLlmKey && (
        <p className="text-xs text-muted-foreground">
          No platform API keys needed — preview mode does not require publishing credentials.
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
