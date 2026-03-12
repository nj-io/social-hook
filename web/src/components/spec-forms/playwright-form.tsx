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

export function PlaywrightForm({ draft, onUpdate }: FormProps) {
  const schema = TOOL_SCHEMAS.playwright;
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
          URL <span className="text-destructive">*</span>
        </label>
        <input
          type="text"
          value={(spec.url as string) ?? ""}
          onChange={(e) => updateField("url", e.target.value)}
          placeholder="https://example.com"
          className="w-full rounded-md border border-border bg-background px-3 py-1 text-sm"
        />
        {errors.url && <p className="mt-1 text-xs text-destructive">{errors.url}</p>}
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">CSS Selector</label>
          <input
            type="text"
            value={(spec.selector as string) ?? ""}
            onChange={(e) => updateField("selector", e.target.value || undefined)}
            placeholder=".main-content"
            className="w-full rounded-md border border-border bg-background px-2 py-1 text-sm"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Width</label>
          <input
            type="number"
            value={(spec.width as number) ?? ""}
            onChange={(e) => updateField("width", e.target.value ? Number(e.target.value) : undefined)}
            placeholder="1280"
            className="w-full rounded-md border border-border bg-background px-2 py-1 text-sm"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Height</label>
          <input
            type="number"
            value={(spec.height as number) ?? ""}
            onChange={(e) => updateField("height", e.target.value ? Number(e.target.value) : undefined)}
            placeholder="720"
            className="w-full rounded-md border border-border bg-background px-2 py-1 text-sm"
          />
        </div>
        <div className="flex items-end">
          <label className="flex items-center gap-2 py-1 text-sm">
            <input
              type="checkbox"
              checked={!!spec.full_page}
              onChange={(e) => updateField("full_page", e.target.checked)}
              className="rounded"
            />
            <span className="text-xs font-medium text-muted-foreground">Full Page</span>
          </label>
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
