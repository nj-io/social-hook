"use client";

import { useState } from "react";
import type { Draft, MediaSpecItem } from "@/lib/types";
import { Note } from "./ui/note";
import { MediaToolHeader } from "./media-tool-header";
import { MediaActionBar } from "./media-action-bar";
import { ToolSpecForm } from "./tool-spec-form";
import { addMediaItem } from "@/lib/api";
import { useToast } from "@/lib/toast-context";
import { getAvailableTools, TOOL_SCHEMAS } from "@/lib/media-tool-schemas";

interface MediaSectionProps {
  draft: Draft;
  onUpdate: () => void;
  /**
   * Per-(vehicle, platform) cap surfaced as the "+ Add" disabled tooltip when
   * supplied. Backend is authoritative; this is purely UX.
   */
  maxCount?: number;
  /**
   * Legacy props from the singular-media era. Accepted for caller-signature
   * compatibility while other surfaces migrate to the multi-media API; no
   * longer used — per-item regen flows through ``updateMediaItem``, and
   * batch replanning flows through ``replanMediaSpecs``.
   */
  onGenerateSpec?: (draftId: string, mediaType: string) => void;
  isGeneratingSpec?: boolean;
}

/**
 * Tabbed media layout: one tab per media item, plus a "+ Add" trailing
 * control. Each tab's panel renders the per-item header (edit/regen/remove),
 * a preview ``<img>``, the error string when present, and a raw-JSON spec
 * editor. The bottom bar carries batch actions (Regen All, Replan Specs),
 * both LLM background tasks.
 */
export function MediaSection({ draft, onUpdate, maxCount }: MediaSectionProps) {
  const specs: MediaSpecItem[] = draft.media_specs ?? [];
  const paths: string[] = draft.media_paths ?? [];
  const errors: (string | null)[] = draft.media_errors ?? [];
  const count = specs.length;

  const [activeIdx, setActiveIdx] = useState(() => (count > 0 ? 0 : -1));
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const { addToast } = useToast();

  const atCap = typeof maxCount === "number" && count >= maxCount;

  async function handleAddItem(tool: string) {
    try {
      await addMediaItem(draft.id, { tool, spec: {} });
      addToast("Media item added", { variant: "success" });
      onUpdate();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Unknown error";
      addToast("Could not add media item", { variant: "error", detail: msg });
    }
  }

  const safeActive = activeIdx >= 0 && activeIdx < count ? activeIdx : -1;
  const activeItem = safeActive >= 0 ? specs[safeActive] : null;
  const activePath = safeActive >= 0 ? paths[safeActive] : null;
  const activeError = safeActive >= 0 ? errors[safeActive] : null;
  const tools = getAvailableTools();
  const defaultTool = tools[0]?.name;

  return (
    <div className="space-y-3 rounded-lg border border-border p-4">
      {/* Tab strip */}
      <div
        className="flex flex-wrap gap-1 border-b border-border pb-2"
        role="tablist"
        aria-label="Media items"
      >
        {specs.map((item, i) => {
          const hasError = errors[i];
          const active = i === safeActive;
          return (
            <button
              key={item.id}
              role="tab"
              aria-selected={active}
              onClick={() => setActiveIdx(i)}
              className={
                "rounded-t-md border-b-2 px-3 py-1 text-xs font-medium transition-colors " +
                (active
                  ? "border-accent text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground")
              }
            >
              Media {i + 1}
              {hasError ? (
                <span className="ml-1 text-red-600 dark:text-red-400">✗</span>
              ) : (
                <span className="ml-1 text-green-600 dark:text-green-400">●</span>
              )}
            </button>
          );
        })}
        <div className="ml-2 flex items-center gap-1">
          {defaultTool && (
            <button
              onClick={() => handleAddItem(defaultTool)}
              disabled={atCap}
              title={
                atCap
                  ? `Max ${maxCount} media items for this vehicle/platform`
                  : `Add ${TOOL_SCHEMAS[defaultTool]?.displayName ?? defaultTool}`
              }
              className="rounded-md border border-dashed border-border px-3 py-1 text-xs font-medium text-muted-foreground hover:text-foreground disabled:opacity-50"
            >
              + Add
            </button>
          )}
          {!atCap && tools.length > 1 && (
            <select
              defaultValue=""
              onChange={(e) => {
                const tool = e.target.value;
                if (tool) {
                  handleAddItem(tool);
                  e.target.value = "";
                }
              }}
              className="rounded-md border border-border bg-background px-1 py-1 text-xs text-muted-foreground"
              aria-label="Add item with specific tool"
            >
              <option value="" disabled>
                more…
              </option>
              {tools.map((t) => (
                <option key={t.name} value={t.name}>
                  + {t.displayName}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {atCap && (
        <Note variant="info">
          Maximum {maxCount} media item{maxCount === 1 ? "" : "s"} reached for
          this {draft.vehicle} on {draft.platform}.
        </Note>
      )}

      {activeItem ? (
        <div className="space-y-3" role="tabpanel">
          <MediaToolHeader
            draft={draft}
            item={activeItem}
            itemIndex={safeActive}
            errorText={activeError ?? null}
            onUpdate={onUpdate}
            onEditSpec={() => setEditingIdx(safeActive)}
          />

          {activePath ? (
            <MediaItemPreview path={activePath} caption={activeItem.caption} />
          ) : (
            <div className="rounded-md bg-muted p-3 text-xs text-muted-foreground">
              No media file rendered yet.
            </div>
          )}

          {editingIdx === safeActive && (
            <ToolSpecForm
              draft={draft}
              mediaItem={activeItem}
              onUpdate={() => {
                setEditingIdx(null);
                onUpdate();
              }}
              onCancel={() => setEditingIdx(null)}
            />
          )}
        </div>
      ) : (
        <div className="rounded-md bg-muted p-4 text-sm text-muted-foreground">
          No media attached. Use + Add above or Replan Specs below to let the
          drafter suggest media items.
        </div>
      )}

      <MediaActionBar draft={draft} onUpdate={onUpdate} />
    </div>
  );
}

function MediaItemPreview({
  path,
  caption,
}: {
  path: string;
  caption: string | null;
}) {
  return (
    <figure className="space-y-1">
      <img
        src={`/api/media/${encodeURIComponent(path)}`}
        alt={caption ?? "Media preview"}
        className="max-h-64 rounded-md border border-border object-contain"
      />
      {caption && (
        <figcaption className="text-xs text-muted-foreground">
          {caption}
        </figcaption>
      )}
    </figure>
  );
}
