"use client";

import { useState } from "react";
import type { Arc } from "@/lib/types";
import { createProjectArc, updateProjectArc } from "@/lib/api";

interface ArcsSectionProps {
  arcs: Arc[];
  projectId: string;
  onRefresh: () => void;
}

export function ArcsSection({ arcs, projectId, onRefresh }: ArcsSectionProps) {
  const [showForm, setShowForm] = useState(false);
  const [theme, setTheme] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [updatingId, setUpdatingId] = useState<string | null>(null);

  async function handleCreate() {
    if (!theme.trim()) return;
    setSaving(true);
    setError("");
    try {
      await createProjectArc(projectId, theme.trim(), notes.trim() || undefined);
      setTheme("");
      setNotes("");
      setShowForm(false);
      onRefresh();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to create arc";
      if (msg.includes("409")) {
        setError("Maximum 3 active arcs. Complete or abandon one first.");
      } else {
        setError(msg);
      }
    } finally {
      setSaving(false);
    }
  }

  async function handleStatusChange(arcId: string, status: string) {
    setUpdatingId(arcId);
    try {
      await updateProjectArc(projectId, arcId, { status });
      onRefresh();
    } catch {
      // Silent
    } finally {
      setUpdatingId(null);
    }
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold">Narrative Arcs</h2>
          {arcs.length > 0 && (
            <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
              {arcs.length}
            </span>
          )}
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="rounded-md bg-accent px-3 py-1 text-xs font-medium text-accent-foreground hover:bg-accent/80"
        >
          {showForm ? "Cancel" : "Add arc"}
        </button>
      </div>

      {showForm && (
        <div className="mb-4 space-y-2 rounded-lg border border-border p-3">
          <div>
            <label className="mb-1 block text-xs font-medium">Theme</label>
            <input
              type="text"
              value={theme}
              onChange={(e) => setTheme(e.target.value)}
              placeholder="e.g. Building the auth system"
              className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-accent"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Notes (optional)</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Context or goals for this arc..."
              rows={2}
              className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-accent"
            />
          </div>
          {error && (
            <p className="text-xs text-destructive">{error}</p>
          )}
          <button
            onClick={handleCreate}
            disabled={saving || !theme.trim()}
            className="rounded-md bg-accent px-4 py-1.5 text-sm font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
          >
            {saving ? "Creating..." : "Create"}
          </button>
        </div>
      )}

      {arcs.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No arcs yet. Arcs are content themes that help the evaluator link related commits into a narrative thread.
        </p>
      ) : (
        <div className="space-y-2">
          {arcs.map((arc) => (
            <div key={arc.id} className="flex items-center justify-between rounded-lg border border-border p-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{arc.theme}</span>
                  <span className="text-xs text-muted-foreground">{arc.post_count} posts</span>
                </div>
                {arc.notes && (
                  <p className="mt-0.5 truncate text-xs text-muted-foreground">{arc.notes}</p>
                )}
              </div>
              <div className="ml-3 flex shrink-0 items-center gap-2">
                {arc.status === "active" && (
                  <>
                    <button
                      onClick={() => handleStatusChange(arc.id, "completed")}
                      disabled={updatingId === arc.id}
                      className="rounded-md border border-border px-2 py-0.5 text-xs hover:bg-muted disabled:opacity-50"
                    >
                      Complete
                    </button>
                    <button
                      onClick={() => handleStatusChange(arc.id, "abandoned")}
                      disabled={updatingId === arc.id}
                      className="rounded-md border border-border px-2 py-0.5 text-xs text-muted-foreground hover:bg-muted disabled:opacity-50"
                    >
                      Abandon
                    </button>
                  </>
                )}
                <ArcStatusBadge status={arc.status} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ArcStatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    active: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400",
    completed: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
    abandoned: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
  };
  const style = styles[status] ?? "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300";
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${style}`}>
      {status}
    </span>
  );
}
