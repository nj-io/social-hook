"use client";

import { useEffect, useState } from "react";
import { fetchDrafts } from "@/lib/api";
import type { Draft } from "@/lib/types";
import { DraftCard } from "@/components/draft-card";

const STATUSES = ["All", "draft", "approved", "scheduled", "posted", "rejected", "failed"];

export default function DraftsPage() {
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("All");

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const status = filter === "All" ? undefined : filter;
        const result = await fetchDrafts(status);
        setDrafts(result.drafts);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load drafts");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [filter]);

  return (
    <div className="space-y-6">
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
