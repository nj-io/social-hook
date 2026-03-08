"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { fetchDrafts } from "@/lib/api";
import type { Draft } from "@/lib/types";
import { DraftCard } from "@/components/draft-card";
import { useDataEvents } from "@/lib/use-data-events";

const STATUSES = ["All", "draft", "approved", "scheduled", "deferred", "posted", "rejected", "failed"];

export default function DraftsPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const fromProjectId = searchParams.get("from");
  const fromProjectName = searchParams.get("name");
  const decisionFilter = searchParams.get("decision");
  const commitFilter = searchParams.get("commit");

  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("All");
  const filterRef = useRef(filter);
  filterRef.current = filter;

  function removeParam(key: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.delete(key);
    const qs = params.toString();
    router.replace(`${pathname}${qs ? `?${qs}` : ""}`);
  }

  const buildFilters = useCallback(() => {
    const filters: Record<string, string> = {};
    const status = filterRef.current === "All" ? undefined : filterRef.current;
    if (status) filters.status = status;
    if (fromProjectId) filters.project_id = fromProjectId;
    if (decisionFilter) filters.decision_id = decisionFilter;
    if (commitFilter) filters.commit = commitFilter;
    return filters;
  }, [fromProjectId, decisionFilter, commitFilter]);

  const reload = useCallback(async () => {
    try {
      const result = await fetchDrafts(buildFilters());
      setDrafts(result.drafts);
    } catch {
      // Silent refresh failure
    }
  }, [buildFilters]);

  useDataEvents(["draft"], reload);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const result = await fetchDrafts(buildFilters());
        setDrafts(result.drafts);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load drafts");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [filter, buildFilters]);

  const hasActiveFilters = fromProjectId || decisionFilter || commitFilter;

  return (
    <div className="space-y-6">
      {fromProjectId && (
        <Link href={`/projects/${fromProjectId}`} className="text-sm text-accent hover:underline">
          &larr; Back to {fromProjectName || "project"}
        </Link>
      )}
      <div>
        <h1 className="text-2xl font-bold">Drafts</h1>
        <p className="text-muted-foreground">Review and manage generated content drafts.</p>
      </div>

      {/* Status filter tabs */}
      <div className="flex gap-1 border-b border-border">
        {STATUSES.map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
              filter === s
                ? "border-accent text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {s === "All" ? "All" : s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}
      </div>

      {/* Active filter chips */}
      {hasActiveFilters && (
        <div className="flex flex-wrap gap-2">
          {fromProjectId && (
            <span className="inline-flex items-center gap-1 rounded-full bg-muted px-3 py-1 text-xs font-medium text-muted-foreground">
              Project: {fromProjectName || fromProjectId.slice(0, 12)}
              <button onClick={() => removeParam("from")} className="ml-0.5 hover:text-foreground">&times;</button>
            </span>
          )}
          {decisionFilter && (
            <span className="inline-flex items-center gap-1 rounded-full bg-muted px-3 py-1 text-xs font-medium text-muted-foreground">
              Decision: <code>{decisionFilter.slice(0, 14)}</code>
              <button onClick={() => removeParam("decision")} className="ml-0.5 hover:text-foreground">&times;</button>
            </span>
          )}
          {commitFilter && (
            <span className="inline-flex items-center gap-1 rounded-full bg-muted px-3 py-1 text-xs font-medium text-muted-foreground">
              Commit: <code>{commitFilter.slice(0, 7)}</code>
              <button onClick={() => removeParam("commit")} className="ml-0.5 hover:text-foreground">&times;</button>
            </span>
          )}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-center text-sm text-muted-foreground">Loading...</p>
      ) : drafts.length === 0 ? (
        <p className="text-center text-sm text-muted-foreground">No drafts found.</p>
      ) : (
        <div className="space-y-2">
          {drafts.map((draft) => (
            <DraftCard key={draft.id} draft={draft} />
          ))}
        </div>
      )}
    </div>
  );
}
