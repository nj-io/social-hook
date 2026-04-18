"use client";

import { useState } from "react";
import { AsyncButton } from "./async-button";
import { Modal } from "./ui/modal";
import { useToast } from "@/lib/toast-context";
import { useBackgroundTasks } from "@/lib/use-background-tasks";
import { removeMediaItem, updateMediaItem } from "@/lib/api";
import type { BackgroundTask } from "@/lib/api";
import type { Draft, MediaSpecItem } from "@/lib/types";
import { TOOL_SCHEMAS } from "@/lib/media-tool-schemas";

interface MediaToolHeaderProps {
  draft: Draft;
  item: MediaSpecItem;
  itemIndex: number;
  errorText: string | null;
  onUpdate: () => void;
  onEditSpec: () => void;
}

/**
 * Per-item header for the tabbed MediaSection. Shows the stable media id
 * (trimmed for readability), the tool name, per-item regen (AsyncButton +
 * useBackgroundTasks), edit, and remove (Modal confirm).
 *
 * LLM-bearing actions (``regen``) dispatch through
 * ``updateMediaItem`` which returns 202 + task_id; the hook picks up the
 * stage events automatically. Quick operations (remove) use a simple
 * ``disabled:opacity-50`` pattern.
 */
export function MediaToolHeader({
  draft,
  item,
  itemIndex,
  errorText,
  onUpdate,
  onEditSpec,
}: MediaToolHeaderProps) {
  const { addToast } = useToast();
  const refId = `media_regen:${draft.id}:${item.id}`;
  const { trackTask, isRunning, getTask } = useBackgroundTasks(
    draft.project_id,
    (task: BackgroundTask) => {
      if (task.ref_id !== refId) return;
      if (task.status === "failed") {
        addToast("Regeneration failed", {
          variant: "error",
          detail: task.error ?? undefined,
        });
      } else if (task.status === "completed") {
        addToast("Media regenerated", { variant: "success" });
        onUpdate();
      }
    },
  );
  const loading = isRunning(refId);
  const task = getTask(refId);

  const [showRemove, setShowRemove] = useState(false);
  const [removing, setRemoving] = useState(false);

  const tool = TOOL_SCHEMAS[item.tool];
  const shortId = item.id.length > 20 ? `${item.id.slice(0, 18)}…` : item.id;

  async function handleRegen() {
    try {
      const res = await updateMediaItem(draft.id, item.id, {
        tool: item.tool,
        spec: item.spec,
        caption: item.caption,
      });
      trackTask(res.task_id, refId, "media_regen");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Unknown error";
      addToast("Regen request failed", { variant: "error", detail: msg });
    }
  }

  async function handleRemoveConfirm() {
    setRemoving(true);
    try {
      await removeMediaItem(draft.id, item.id);
      setShowRemove(false);
      addToast("Media item removed", { variant: "success" });
      onUpdate();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Unknown error";
      addToast("Remove failed", { variant: "error", detail: msg });
    } finally {
      setRemoving(false);
    }
  }

  return (
    <>
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 text-sm">
          <span className="font-medium text-muted-foreground">
            Media {itemIndex + 1}
          </span>
          <span className="rounded bg-muted px-2 py-0.5 font-mono text-xs text-muted-foreground">
            {shortId}
          </span>
          {item.user_uploaded && (
            <span className="rounded bg-blue-100 px-2 py-0.5 text-xs text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
              upload
            </span>
          )}
        </div>
        {tool && (
          <span className="text-xs text-muted-foreground">{tool.description}</span>
        )}
        {errorText && (
          <span className="text-xs text-red-600 dark:text-red-400">
            {errorText}
          </span>
        )}
        <div className="ml-auto flex gap-2">
          <button
            onClick={onEditSpec}
            className="rounded-md border border-border px-3 py-1 text-xs font-medium text-foreground transition-colors hover:bg-muted"
          >
            Edit spec
          </button>
          <AsyncButton
            loading={loading}
            startTime={task?.created_at}
            loadingText={task?.stage_label ?? "Regenerating"}
            onClick={handleRegen}
            className="rounded-md bg-accent px-3 py-1 text-xs font-medium text-accent-foreground transition-colors hover:bg-accent/80 disabled:opacity-50"
          >
            Regenerate
          </AsyncButton>
          <button
            onClick={() => setShowRemove(true)}
            disabled={loading || removing}
            className="rounded-md border border-red-300 px-3 py-1 text-xs font-medium text-red-700 transition-colors hover:bg-red-50 disabled:opacity-50 dark:border-red-700 dark:text-red-400 dark:hover:bg-red-900/20"
          >
            Remove
          </button>
        </div>
      </div>

      <Modal open={showRemove} onClose={() => !removing && setShowRemove(false)}>
        <h3 className="mb-2 text-base font-medium">Remove this media item?</h3>
        <p className="mb-4 text-sm text-muted-foreground">
          This removes media <span className="font-mono">{shortId}</span> from
          the draft. Tokens referencing this id in the article content will
          become broken references until resolved.
        </p>
        <div className="flex justify-end gap-2">
          <button
            onClick={() => setShowRemove(false)}
            disabled={removing}
            className="rounded-md border border-border px-3 py-1 text-sm text-foreground hover:bg-muted disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={handleRemoveConfirm}
            disabled={removing}
            className="rounded-md bg-red-600 px-3 py-1 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
          >
            {removing ? "Removing…" : "Remove"}
          </button>
        </div>
      </Modal>
    </>
  );
}
