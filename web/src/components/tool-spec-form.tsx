"use client";

import { useEffect, useRef, useState } from "react";
import type { Draft, MediaSpecItem } from "@/lib/types";
import { TOOL_SCHEMAS } from "@/lib/media-tool-schemas";
import { MermaidForm } from "./spec-forms/mermaid-form";
import { NanaBananaForm } from "./spec-forms/nano-banana-form";
import { RaySoForm } from "./spec-forms/ray-so-form";
import { PlaywrightForm } from "./spec-forms/playwright-form";
import { updateMediaItem } from "@/lib/api";

interface ToolSpecFormProps {
  draft: Draft;
  /** The specific media item being edited. Identified by stable id. */
  mediaItem: MediaSpecItem;
  onUpdate: () => void;
  onCancel: () => void;
}

function specToJson(spec: Record<string, unknown>): string {
  return JSON.stringify(spec ?? {}, null, 2);
}

export function ToolSpecForm({ draft, mediaItem, onUpdate, onCancel }: ToolSpecFormProps) {
  const [rawMode, setRawMode] = useState(false);
  const [rawJson, setRawJson] = useState(() => specToJson(mediaItem.spec));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // Sync rawJson when the upstream spec object changes (e.g. after a
  // background task writes a new spec and the draft reloads via WebSocket).
  const prevSpec = useRef(mediaItem.spec);
  useEffect(() => {
    if (mediaItem.spec !== prevSpec.current) {
      prevSpec.current = mediaItem.spec;
      setRawJson(specToJson(mediaItem.spec));
    }
  }, [mediaItem.spec]);

  const toolName = mediaItem.tool;
  const hasSpecificForm = toolName && TOOL_SCHEMAS[toolName];

  async function handleRawSave() {
    setSaving(true);
    setError("");
    try {
      const spec = JSON.parse(rawJson);
      await updateMediaItem(draft.id, mediaItem.id, { tool: toolName, spec });
      onUpdate();
    } catch (e) {
      setError(e instanceof SyntaxError ? "Invalid JSON" : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  // Raw JSON fallback mode — used when no tool-specific form exists or the
  // operator opts into raw editing from the form view.
  if (rawMode || !hasSpecificForm) {
    return (
      <div className="space-y-2 rounded-md border border-border p-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">Media Spec (JSON)</span>
          <div className="flex gap-2">
            {hasSpecificForm && (
              <button onClick={() => setRawMode(false)} className="text-xs text-accent hover:underline">
                Form view
              </button>
            )}
            <button onClick={onCancel} className="text-xs text-muted-foreground hover:text-foreground">
              Cancel
            </button>
          </div>
        </div>
        <textarea
          value={rawJson}
          onChange={(e) => setRawJson(e.target.value)}
          rows={8}
          className="w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-sm"
        />
        {error && <p className="text-xs text-destructive">{error}</p>}
        <button
          onClick={handleRawSave}
          disabled={saving}
          className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
        >
          {saving ? "Saving..." : "Save Spec"}
        </button>
      </div>
    );
  }

  const FormComponent = {
    mermaid: MermaidForm,
    nano_banana_pro: NanaBananaForm,
    ray_so: RaySoForm,
    playwright: PlaywrightForm,
  }[toolName];

  if (!FormComponent) return null;

  return (
    <div className="space-y-2 rounded-md border border-border p-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">{TOOL_SCHEMAS[toolName].displayName} Spec</span>
        <div className="flex gap-2">
          <button onClick={() => setRawMode(true)} className="text-xs text-accent hover:underline">
            Raw JSON
          </button>
          <button onClick={onCancel} className="text-xs text-muted-foreground hover:text-foreground">
            Cancel
          </button>
        </div>
      </div>
      <FormComponent draft={draft} mediaItem={mediaItem} onUpdate={onUpdate} />
    </div>
  );
}
