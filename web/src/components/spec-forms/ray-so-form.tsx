"use client";

import { useState } from "react";
import type { Draft } from "@/lib/types";
import { TOOL_SCHEMAS } from "@/lib/media-tool-schemas";
import { useSyncedSpec } from "@/lib/use-synced-spec";
import { updateDraftMediaSpec } from "@/lib/api";

interface FormProps {
  draft: Draft;
  onUpdate: () => void;
}

export function RaySoForm({ draft, onUpdate }: FormProps) {
  const schema = TOOL_SCHEMAS.ray_so;
  const [spec, setSpec] = useSyncedSpec(draft.media_spec);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  function updateField(key: string, value: unknown) {
    setSpec((prev) => ({ ...prev, [key]: value }));
    setErrors((prev) => { const next = { ...prev }; delete next[key]; return next; });
  }

  async function handleSave() {
    const { valid, errors: validationErrors } = schema.validate(spec);
    if (!valid) { setErrors(validationErrors); return; }

    setSaving(true);
    try {
      await updateDraftMediaSpec(draft.id, spec);
      onUpdate();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-3">
      <div>
        <label className="mb-1 block text-xs font-medium text-muted-foreground">
          Code <span className="text-destructive">*</span>
        </label>
        <textarea
          value={(spec.code as string) ?? ""}
          onChange={(e) => updateField("code", e.target.value)}
          placeholder="console.log('hello')"
          rows={6}
          className="w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-sm"
        />
        {errors.code && <p className="mt-1 text-xs text-destructive">{errors.code}</p>}
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Language</label>
          <select
            value={(spec.language as string) ?? ""}
            onChange={(e) => updateField("language", e.target.value || undefined)}
            className="w-full rounded-md border border-border bg-background px-2 py-1 text-sm"
          >
            <option value="">Auto</option>
            <option value="python">Python</option>
            <option value="javascript">JavaScript</option>
            <option value="typescript">TypeScript</option>
            <option value="go">Go</option>
            <option value="rust">Rust</option>
            <option value="java">Java</option>
            <option value="bash">Bash</option>
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Theme</label>
          <select
            value={(spec.theme as string) ?? ""}
            onChange={(e) => updateField("theme", e.target.value || undefined)}
            className="w-full rounded-md border border-border bg-background px-2 py-1 text-sm"
          >
            <option value="">Default (Candy)</option>
            <option value="candy">Candy</option>
            <option value="breeze">Breeze</option>
            <option value="midnight">Midnight</option>
            <option value="sunset">Sunset</option>
            <option value="raindrop">Raindrop</option>
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Padding</label>
          <select
            value={(spec.padding as string) ?? ""}
            onChange={(e) => updateField("padding", e.target.value || undefined)}
            className="w-full rounded-md border border-border bg-background px-2 py-1 text-sm"
          >
            <option value="">Default (64)</option>
            <option value="16">16</option>
            <option value="32">32</option>
            <option value="64">64</option>
            <option value="128">128</option>
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Title</label>
          <input
            type="text"
            value={(spec.title as string) ?? ""}
            onChange={(e) => updateField("title", e.target.value || undefined)}
            placeholder="main.py"
            className="w-full rounded-md border border-border bg-background px-2 py-1 text-sm"
          />
        </div>
      </div>
      <button
        onClick={handleSave}
        disabled={saving}
        className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
      >
        {saving ? "Saving..." : "Save Spec"}
      </button>
    </div>
  );
}
