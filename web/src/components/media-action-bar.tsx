"use client";

import { useMemo } from "react";
import { AsyncButton } from "./async-button";
import { useToast } from "@/lib/toast-context";
import { useMediaTasks } from "./media-section-context";
import { regenAllMedia, replanMediaSpecs } from "@/lib/api";
import type { Draft } from "@/lib/types";

interface MediaActionBarProps {
  draft: Draft;
}

/**
 * Batch action bar for the MediaSection. Two LLM-bearing actions:
 *
 * * **Regen All** — re-runs each existing spec through its adapter.
 * * **Replan Specs** — LLM re-plans the full spec list for this draft.
 *
 * Both dispatch via ``_run_background_task`` server-side and return 202 +
 * task_id; the MediaSection-scoped subscription picks up per-item stage events
 * and dispatches toasts. Per-item actions (edit/regen/remove) are on
 * ``MediaToolHeader`` — not this component.
 */
export function MediaActionBar({ draft }: MediaActionBarProps) {
  const { addToast } = useToast();

  const refRegen = useMemo(() => `media_regen_all:${draft.id}`, [draft.id]);
  const refReplan = useMemo(() => `media_replan:${draft.id}`, [draft.id]);

  const { trackTask, isRunning, getTask } = useMediaTasks();

  const regenLoading = isRunning(refRegen);
  const replanLoading = isRunning(refReplan);
  const regenTask = getTask(refRegen);
  const replanTask = getTask(refReplan);
  const busy = regenLoading || replanLoading;

  // Hide when not editable (mirrors the previous per-item bar behavior)
  if (!["draft", "deferred"].includes(draft.status)) return null;

  const count = draft.media_specs?.length ?? 0;

  async function handleRegenAll() {
    try {
      const res = await regenAllMedia(draft.id);
      trackTask(res.task_id, refRegen, "media_regen_all");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Unknown error";
      addToast("Regen All request failed", { variant: "error", detail: msg });
    }
  }

  async function handleReplan() {
    try {
      const res = await replanMediaSpecs(draft.id);
      trackTask(res.task_id, refReplan, "media_replan");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Unknown error";
      addToast("Replan request failed", { variant: "error", detail: msg });
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
      <span className="text-xs text-muted-foreground">
        {count} item{count === 1 ? "" : "s"}
      </span>
      <div className="ml-auto flex gap-2">
        <AsyncButton
          loading={regenLoading}
          startTime={regenTask?.created_at}
          loadingText={regenTask?.stage_label ?? "Regenerating all"}
          onClick={handleRegenAll}
          disabled={busy || count === 0}
          className="rounded-md border border-border px-3 py-1 text-xs font-medium text-foreground transition-colors hover:bg-muted disabled:opacity-50"
        >
          Regen All
        </AsyncButton>
        <AsyncButton
          loading={replanLoading}
          startTime={replanTask?.created_at}
          loadingText={replanTask?.stage_label ?? "Replanning"}
          onClick={handleReplan}
          disabled={busy}
          className="rounded-md bg-accent px-3 py-1 text-xs font-medium text-accent-foreground transition-colors hover:bg-accent/80 disabled:opacity-50"
        >
          Replan Specs
        </AsyncButton>
      </div>
    </div>
  );
}
