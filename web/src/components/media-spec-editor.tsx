"use client";

import { useState } from "react";
import { updateDraftMediaSpec } from "@/lib/api";

interface MediaSpecEditorProps {
  draftId: string;
  mediaSpec: Record<string, unknown>;
  onUpdate: () => void;
}

export function MediaSpecEditor({ draftId, mediaSpec, onUpdate }: MediaSpecEditorProps) {
  const [rawJson, setRawJson] = useState(() => JSON.stringify(mediaSpec, null, 2));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSave() {
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(rawJson);
    } catch {
      setError("Invalid JSON");
      return;
    }
    setSaving(true);
    try {
      await updateDraftMediaSpec(draftId, parsed);
      onUpdate();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-muted-foreground">Raw JSON</label>
      <textarea
        value={rawJson}
        onChange={(e) => {
          setRawJson(e.target.value);
          setError("");
        }}
        rows={8}
        className="w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-xs outline-none focus:ring-2 focus:ring-accent"
      />
      {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
      <div className="mt-2 flex gap-2">
        <button
          onClick={handleSave}
          disabled={saving}
          className="rounded-md bg-accent px-3 py-1 text-xs font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
        >
          {saving ? "Saving..." : "Save JSON"}
        </button>
      </div>
    </div>
  );
}
