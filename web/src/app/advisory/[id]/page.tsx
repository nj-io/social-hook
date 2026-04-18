"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { getAdvisory, updateAdvisoryItem } from "@/lib/api";
import { Note } from "@/components/ui/note";
import { useDataEvents } from "@/lib/use-data-events";
import { useToast } from "@/lib/toast-context";
import { ArticlePreview } from "@/components/article-preview";
import type { Advisory, DiagnosticItem } from "@/lib/types";

interface PageParams {
  id: string;
}

/**
 * Advisory detail page — used for non-auto-postable vehicles (articles) that
 * have been approved. Renders the server-provided ``rendered_content``
 * (markdown with tokens already resolved to ``/api/media/...`` URLs)
 * inline, surfaces any draft diagnostics as a banner, and offers
 * complete/dismiss actions.
 *
 * Falls back to the advisory ``description`` when ``rendered_content`` is
 * absent (non-article advisories, or legacy rows where the backend
 * decided not to populate it).
 */
export default function AdvisoryDetailPage({
  params,
}: {
  params: Promise<PageParams>;
}) {
  const { id } = use(params);
  const [advisory, setAdvisory] = useState<Advisory | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [acting, setActing] = useState(false);
  const { addToast } = useToast();

  const load = useCallback(async () => {
    try {
      const data = await getAdvisory(id);
      setAdvisory(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load advisory");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  // Stay live: reload when any advisory or draft event fires for this project
  useDataEvents(["advisory", "draft"], load);

  async function handleComplete() {
    if (!advisory) return;
    setActing(true);
    try {
      await updateAdvisoryItem(advisory.id, { status: "completed" });
      addToast("Advisory completed", { variant: "success" });
      load();
    } catch {
      addToast("Failed to complete advisory", { variant: "error" });
    } finally {
      setActing(false);
    }
  }

  if (loading) {
    return (
      <main className="mx-auto max-w-3xl p-6 text-sm text-muted-foreground">
        Loading advisory…
      </main>
    );
  }
  if (error || !advisory) {
    return (
      <main className="mx-auto max-w-3xl p-6">
        <Note variant="error">{error ?? "Advisory not found"}</Note>
        <Link
          href="/advisory"
          className="mt-4 inline-block text-sm text-accent hover:underline"
        >
          ← Back to Advisory list
        </Link>
      </main>
    );
  }

  const diagnostics: DiagnosticItem[] = advisory.diagnostics ?? [];
  const actionable = diagnostics.filter(
    (d) => d.severity === "warning" || d.severity === "error",
  );

  const isArticle =
    advisory.linked_entity_type === "draft" &&
    typeof advisory.rendered_content === "string" &&
    advisory.rendered_content.length > 0;

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-6">
      <header className="space-y-2">
        <Link
          href="/advisory"
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          ← Advisory
        </Link>
        <h1 className="text-2xl font-semibold">{advisory.title}</h1>
        <div className="flex flex-wrap gap-2 text-xs">
          <StatusPill status={advisory.status} />
          <UrgencyPill urgency={advisory.urgency} />
          {advisory.due_date && (
            <span className="rounded bg-muted px-2 py-0.5 text-muted-foreground">
              Due {advisory.due_date}
            </span>
          )}
        </div>
      </header>

      {actionable.length > 0 && (
        <Note variant="warning">
          <div className="space-y-1">
            <div className="font-medium">
              {actionable.length} warning{actionable.length === 1 ? "" : "s"} on
              this draft
            </div>
            <ul className="list-disc space-y-0.5 pl-5 text-xs">
              {actionable.map((d) => (
                <li key={d.code}>
                  {d.message}
                  {d.suggestion && (
                    <span className="ml-1 opacity-75">— {d.suggestion}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        </Note>
      )}

      {isArticle ? (
        <ArticlePreview content={advisory.rendered_content ?? ""} />
      ) : advisory.description ? (
        <div className="whitespace-pre-wrap rounded-lg border border-border p-4 text-sm">
          {advisory.description}
        </div>
      ) : (
        <div className="rounded-lg border border-border p-4 text-sm italic text-muted-foreground">
          No description.
        </div>
      )}

      {advisory.status === "pending" && (
        <div className="flex gap-2">
          <button
            onClick={handleComplete}
            disabled={acting}
            className="rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
          >
            Mark complete
          </button>
        </div>
      )}
    </main>
  );
}

function StatusPill({ status }: { status: string }) {
  const colors: Record<string, string> = {
    pending:
      "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
    completed:
      "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
    dismissed: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
  };
  const cls = colors[status] ?? colors.pending;
  return (
    <span className={`rounded px-2 py-0.5 ${cls}`}>{status}</span>
  );
}

function UrgencyPill({ urgency }: { urgency: string }) {
  const colors: Record<string, string> = {
    blocking: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
    normal: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
  };
  const cls = colors[urgency] ?? colors.normal;
  return <span className={`rounded px-2 py-0.5 ${cls}`}>{urgency}</span>;
}
