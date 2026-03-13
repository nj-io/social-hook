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

export function MermaidForm({ draft, onUpdate }: FormProps) {
  const schema = TOOL_SCHEMAS.mermaid;
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
          Diagram <span className="text-destructive">*</span>
        </label>
        <textarea
          value={(spec.diagram as string) ?? ""}
          onChange={(e) => updateField("diagram", e.target.value)}
          placeholder="graph TD\n  A-->B"
          rows={6}
          className="w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-sm"
        />
        {errors.diagram && <p className="mt-1 text-xs text-destructive">{errors.diagram}</p>}
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Theme</label>
          <select
            value={(spec.theme as string) ?? ""}
            onChange={(e) => updateField("theme", e.target.value || undefined)}
            className="w-full rounded-md border border-border bg-background px-2 py-1 text-sm"
          >
            <option value="">Default</option>
            <option value="dark">Dark</option>
            <option value="forest">Forest</option>
            <option value="neutral">Neutral</option>
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Format</label>
          <select
            value={(spec.format as string) ?? ""}
            onChange={(e) => updateField("format", e.target.value || undefined)}
            className="w-full rounded-md border border-border bg-background px-2 py-1 text-sm"
          >
            <option value="">Default (PNG)</option>
            <option value="png">PNG</option>
            <option value="svg">SVG</option>
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Width</label>
          <input
            type="number"
            value={(spec.width as number) ?? ""}
            onChange={(e) => updateField("width", e.target.value ? Number(e.target.value) : undefined)}
            placeholder="800"
            className="w-full rounded-md border border-border bg-background px-2 py-1 text-sm"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Height</label>
          <input
            type="number"
            value={(spec.height as number) ?? ""}
            onChange={(e) => updateField("height", e.target.value ? Number(e.target.value) : undefined)}
            placeholder="600"
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
