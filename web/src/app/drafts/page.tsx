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
  const tagParam = searchParams.get("tag");

  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("All");
  const [tagFilter, setTagFilter] = useState(tagParam || "");
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
    const tag = tagFilter.trim();
    if (tag) filters.tag = tag;
    return filters;
  }, [fromProjectId, decisionFilter, commitFilter, tagFilter]);

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
  }, [filter, tagFilter, buildFilters]);

  const hasActiveFilters = fromProjectId || decisionFilter || commitFilter || tagParam;

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

      {/* Status filter tabs + tag filter */}
      <div className="flex items-end justify-between gap-4 border-b border-border">
        <div className="flex gap-1">
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
        <div className="flex items-center gap-2 pb-1.5">
          <input
            type="text"
            placeholder="Filter by tag..."
            value={tagFilter}
            onChange={(e) => setTagFilter(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                const val = tagFilter.trim();
                if (val) {
                  const params = new URLSearchParams(searchParams.toString());
                  params.set("tag", val);
                  router.replace(`${pathname}?${params.toString()}`);
                } else {
                  removeParam("tag");
                }
              }
            }}
            className="w-36 rounded-md border border-border bg-background px-2.5 py-1.5 text-sm placeholder:text-muted-foreground focus:border-accent focus:outline-none"
          />
        </div>
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
          {tagParam && (
            <span className="inline-flex items-center gap-1 rounded-full bg-muted px-3 py-1 text-xs font-medium text-muted-foreground">
              Tag: <code>{tagParam}</code>
              <button onClick={() => { removeParam("tag"); setTagFilter(""); }} className="ml-0.5 hover:text-foreground">&times;</button>
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
