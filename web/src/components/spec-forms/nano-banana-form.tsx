"use client";

import { useState } from "react";
import type { Draft, MediaSpecItem } from "@/lib/types";
import { TOOL_SCHEMAS } from "@/lib/media-tool-schemas";
import { useSyncedSpec } from "@/lib/use-synced-spec";
import { updateMediaItem } from "@/lib/api";

interface FormProps {
  draft: Draft;
  mediaItem: MediaSpecItem;
  onUpdate: () => void;
}

export function NanaBananaForm({ draft, mediaItem, onUpdate }: FormProps) {
  const schema = TOOL_SCHEMAS.nano_banana_pro;
  const [spec, setSpec] = useSyncedSpec(mediaItem.spec);
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
      await updateMediaItem(draft.id, mediaItem.id, { tool: mediaItem.tool, spec });
      onUpdate();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-3">
      <div>
        <label className="mb-1 block text-xs font-medium text-muted-foreground">
          Prompt <span className="text-destructive">*</span>
        </label>
        <textarea
          value={(spec.prompt as string) ?? ""}
          onChange={(e) => updateField("prompt", e.target.value)}
          placeholder="A colorful illustration of..."
          rows={4}
          className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
        />
        {errors.prompt && <p className="mt-1 text-xs text-destructive">{errors.prompt}</p>}
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
