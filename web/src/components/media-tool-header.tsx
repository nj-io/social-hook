"use client";

import { useState } from "react";
import type { Draft } from "@/lib/types";
import { updateDraftMediaSpec } from "@/lib/api";
import { TOOL_SCHEMAS, getAvailableTools } from "@/lib/media-tool-schemas";

interface MediaToolHeaderProps {
  draft: Draft;
  onUpdate: () => void;
  onEditSpec: () => void;
  onGenerateSpec: (draftId: string, mediaType: string) => void;
  isGeneratingSpec: boolean;
}

export function MediaToolHeader({
  draft, onUpdate, onEditSpec, onGenerateSpec, isGeneratingSpec,
}: MediaToolHeaderProps) {
  const [switching, setSwitching] = useState(false);
  const tools = getAvailableTools();
  const currentTool = draft.media_type ? TOOL_SCHEMAS[draft.media_type] : null;

  async function handleToolSwitch(toolName: string) {
    setSwitching(true);
    try {
      const spec = typeof draft.media_spec === "string"
        ? JSON.parse(draft.media_spec)
        : draft.media_spec ?? {};
      await updateDraftMediaSpec(draft.id, spec, toolName || undefined);
      onUpdate();
    } finally {
      setSwitching(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-muted-foreground">Media Tool:</span>
        <select
          value={draft.media_type || ""}
          onChange={(e) => handleToolSwitch(e.target.value)}
          disabled={switching}
          className="rounded-md border border-border bg-background px-2 py-1 text-sm"
        >
          <option value="">None</option>
          {tools.map((t) => (
            <option key={t.name} value={t.name}>{t.displayName}</option>
          ))}
        </select>
      </div>

      {currentTool && (
        <span className="text-xs text-muted-foreground">{currentTool.description}</span>
      )}

      <div className="ml-auto flex gap-2">
        {draft.media_type && (
          <>
            <button
              onClick={onEditSpec}
              className="rounded-md border border-border px-3 py-1 text-xs font-medium text-foreground hover:bg-muted"
            >
              Edit Spec
            </button>
            <button
              onClick={() => onGenerateSpec(draft.id, draft.media_type!)}
              disabled={isGeneratingSpec || !draft.media_type}
              className="rounded-md bg-accent px-3 py-1 text-xs font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
            >
              {isGeneratingSpec ? "Generating..." : "Generate Spec (LLM)"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
