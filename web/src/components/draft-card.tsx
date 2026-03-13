import Link from "next/link";
import type { Draft } from "@/lib/types";
import { parseTags } from "@/lib/types";
import { platformLabel } from "@/lib/platform";
import { Badge } from "./ui/badge";

export function DraftCard({ draft }: { draft: Draft }) {
  const preview = draft.content.length > 140
    ? draft.content.slice(0, 140) + "..."
    : draft.content;

  return (
    <Link
      href={`/drafts/${draft.id}`}
      className="block rounded-lg border border-border p-4 transition-colors hover:bg-muted"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex items-center gap-2">
            <span className="text-xs font-medium text-muted-foreground">
              {platformLabel(draft.platform)}
            </span>
            <Badge value={draft.status} variant="status" />
            {draft.is_intro && <Badge value="INTRO" variant="system" />}
            {draft.platform === "preview" && <Badge value="Preview" variant="system" />}
          </div>
          <p className="text-sm text-foreground">{preview}</p>
          {draft.decision && (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {draft.decision.episode_type && <Badge value={draft.decision.episode_type} variant="category" />}
              {draft.decision.post_category && <Badge value={draft.decision.post_category} variant="category" />}
              {parseTags(draft.decision.episode_tags).slice(0, 3).map((tag) => (
                <Badge key={tag} value={tag} variant="default" />
              ))}
              {parseTags(draft.decision.episode_tags).length > 3 && (
                <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs text-muted-foreground">
                  +{parseTags(draft.decision.episode_tags).length - 3} more
                </span>
              )}
            </div>
          )}
          {draft.suggested_time && (
            <p className="mt-1 text-xs text-muted-foreground">
              Scheduled: {new Date(draft.suggested_time).toLocaleString()}
            </p>
          )}
        </div>
        <span className="shrink-0 text-xs text-muted-foreground">
          {new Date(draft.created_at).toLocaleDateString()}
        </span>
      </div>
    </Link>
  );
}
