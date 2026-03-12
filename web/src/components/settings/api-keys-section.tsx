"use client";

import { useState } from "react";
import { updateEnv, validateApiKey } from "@/lib/api";
import { ElapsedTime, Spinner } from "@/components/async-button";

interface ApiKeysSectionProps {
  env: Record<string, string>;
  knownKeys: string[];
  keyGroups?: Record<string, string[]>;
  onRefresh: () => void;
}

export function ApiKeysSection({ env, knownKeys, keyGroups, onRefresh }: ApiKeysSectionProps) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [validating, setValidating] = useState<string | null>(null);
  const [validateStartTime, setValidateStartTime] = useState<string | null>(null);
  const [validationResults, setValidationResults] = useState<Record<string, { valid: boolean; error?: string }>>({});
  const [saving, setSaving] = useState<string | null>(null);

  function providerForKey(key: string): string {
    if (key.includes("ANTHROPIC")) return "anthropic";
    if (key.includes("OPENAI")) return "openai";
    if (key.includes("OPENROUTER")) return "openrouter";
    return "unknown";
  }

  async function handleSave(key: string) {
    const value = values[key];
    if (!value) return;
    setSaving(key);
    try {
      await updateEnv(key, value);
      setValues((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
      onRefresh();
    } catch {
      // Error handling - the UI will show the old masked value
    } finally {
      setSaving(null);
    }
  }

  async function handleValidate(key: string) {
    const value = values[key];
    if (!value) return;
    setValidating(key);
    setValidateStartTime(new Date().toISOString());
    try {
      const result = await validateApiKey(providerForKey(key), value);
      setValidationResults((prev) => ({ ...prev, [key]: result }));
    } catch {
      setValidationResults((prev) => ({ ...prev, [key]: { valid: false, error: "Validation failed" } }));
    } finally {
      setValidating(null);
      setValidateStartTime(null);
    }
  }

  function renderKeyInput(key: string) {
    const masked = env[key];
    const editing = key in values;
    const result = validationResults[key];

    return (
      <div key={key}>
        <label className="mb-1 block text-sm font-medium">{key}</label>
        <div className="flex gap-2">
          <input
            type="password"
            value={editing ? values[key] : masked ?? ""}
            onChange={(e) => setValues((prev) => ({ ...prev, [key]: e.target.value }))}
            placeholder={masked ? `Current: ${masked}` : "Not set"}
            className="flex-1 rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
          />
          <button
            onClick={() => handleSave(key)}
            disabled={!editing || saving === key}
            className="rounded-md bg-accent px-3 py-2 text-sm font-medium text-accent-foreground transition-colors hover:bg-accent/80 disabled:opacity-50"
          >
            {saving === key ? "..." : "Save"}
          </button>
          <button
            onClick={() => handleValidate(key)}
            disabled={!editing || validating === key}
            className="rounded-md border border-border px-3 py-2 text-sm font-medium transition-colors hover:bg-muted disabled:opacity-50"
          >
            {validating === key ? (
              <span className="inline-flex items-center gap-1.5">
                <Spinner className="h-3 w-3" />
                <span>Validating</span>
                {validateStartTime && <ElapsedTime startTime={validateStartTime} />}
              </span>
            ) : "Validate"}
          </button>
        </div>
        {result && (
          <p className={`mt-1 text-xs ${result.valid ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}>
            {result.valid ? "Key is valid" : `Invalid: ${result.error}`}
          </p>
        )}
      </div>
    );
  }

  // If key_groups available, render grouped; otherwise fall back to flat list
  const groups = keyGroups && Object.keys(keyGroups).length > 0 ? keyGroups : null;

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">API Keys</h2>
      <p className="text-sm text-muted-foreground">
        Manage API keys for LLM providers. Keys are stored in {`~/.${process.env.NEXT_PUBLIC_PROJECT_SLUG || "social-hook"}/.env`}.
      </p>
      {groups ? (
        Object.entries(groups).map(([groupName, groupKeys]) => (
          <div key={groupName} className="space-y-3">
            <h3 className="border-b border-border pb-1 text-sm font-semibold text-muted-foreground">
              {groupName}
            </h3>
            {groupKeys.map((key) => renderKeyInput(key))}
          </div>
        ))
      ) : (
        knownKeys.map((key) => renderKeyInput(key))
      )}
    </div>
  );
}
