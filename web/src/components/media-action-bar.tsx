"use client";

import { useState } from "react";
import { sendCallback } from "@/lib/api";
import { useToast } from "@/lib/toast-context";
import type { Draft } from "@/lib/types";

interface MediaActionBarProps {
  draft: Draft;
  onUpdate: () => void;
}

const REGEN_ACTIONS = new Set(["media_regen", "media_retry"]);

export function MediaActionBar({ draft, onUpdate }: MediaActionBarProps) {
  const [pending, setPending] = useState("");
  const { addToast } = useToast();

  // Only show for editable drafts with media
  if (!["draft", "deferred"].includes(draft.status)) return null;
  if (!draft.media_paths) return null;

  async function handleAction(action: string) {
    setPending(action);
    if (REGEN_ACTIONS.has(action)) {
      addToast("Regenerating...");
    }
    try {
      await sendCallback(action, draft.id);
      onUpdate();
      if (REGEN_ACTIONS.has(action)) {
        addToast("Media regenerated", { variant: "success" });
      }
    } catch (e) {
      if (REGEN_ACTIONS.has(action)) {
        const msg = e instanceof Error ? e.message : "Unknown error";
        addToast(`Regeneration failed: ${msg}`, { variant: "error" });
      }
    } finally {
      setPending("");
    }
  }

  const specChanged = draft.media_spec !== draft.media_spec_used;

  return (
    <div className="flex flex-wrap gap-2">
      <button
        onClick={() => handleAction("media_regen")}
        disabled={!!pending || !specChanged}
        title={!specChanged ? "Spec unchanged — edit spec first or use Retry" : "Regenerate media from current spec"}
        className="rounded-md border border-border px-3 py-1 text-xs font-medium text-foreground transition-colors hover:bg-muted disabled:opacity-50"
      >
        {pending === "media_regen" ? "..." : "Regenerate"}
      </button>
      <button
        onClick={() => handleAction("media_retry")}
        disabled={!!pending}
        title="Retry media generation with current spec"
        className="rounded-md border border-border px-3 py-1 text-xs font-medium text-foreground transition-colors hover:bg-muted disabled:opacity-50"
      >
        {pending === "media_retry" ? "..." : "Retry"}
      </button>
      <button
        onClick={() => handleAction("media_remove")}
        disabled={!!pending}
        className="rounded-md border border-red-300 px-3 py-1 text-xs font-medium text-red-700 transition-colors hover:bg-red-50 disabled:opacity-50 dark:border-red-700 dark:text-red-400 dark:hover:bg-red-900/20"
      >
        {pending === "media_remove" ? "..." : "Remove"}
      </button>
    </div>
  );
}
