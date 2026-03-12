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
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [confirmAction, setConfirmAction] = useState<{ id: string; action: string } | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [hiddenIds, setHiddenIds] = useState<Set<string>>(new Set());
  const [editingNotes, setEditingNotes] = useState<{ id: string; value: string } | null>(null);
  const [savingNotes, setSavingNotes] = useState(false);

  const activeArcs = arcs.filter((a) => a.status === "active");
  const inactiveArcs = arcs.filter((a) => a.status !== "active");
  const visibleArcs = showAll
    ? arcs.filter((a) => !hiddenIds.has(a.id))
    : activeArcs.filter((a) => !hiddenIds.has(a.id));
  const hiddenCount = hiddenIds.size;
  const displayedArcs = visibleArcs;

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
    setConfirmAction(null);
    try {
      await updateProjectArc(projectId, arcId, { status });
      onRefresh();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "";
      if (msg.includes("409")) {
        setError("Maximum 3 active arcs. Complete or abandon one first.");
      }
    } finally {
      setUpdatingId(null);
    }
  }

  async function handleSaveNotes(arcId: string, value: string) {
    setSavingNotes(true);
    try {
      await updateProjectArc(projectId, arcId, { notes: value });
      setEditingNotes(null);
      onRefresh();
    } catch {
      // Keep editing state on failure
    } finally {
      setSavingNotes(false);
    }
  }

  function formatDate(dateStr?: string) {
    if (!dateStr) return null;
    try {
      return new Date(dateStr + (dateStr.endsWith("Z") ? "" : "Z")).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    } catch {
      return dateStr;
    }
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold">Narrative Arcs</h2>
          {activeArcs.length > 0 && (
            <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
              {activeArcs.length} active
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {hiddenCount > 0 && (
            <button
              onClick={() => setHiddenIds(new Set())}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              Show {hiddenCount} hidden
            </button>
          )}
          {inactiveArcs.length > 0 && (
            <button
              onClick={() => setShowAll(!showAll)}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              {showAll ? "Show active only" : `Show all (${arcs.filter((a) => !hiddenIds.has(a.id)).length})`}
            </button>
          )}
          <button
            onClick={() => setShowForm(!showForm)}
            className="rounded-md bg-accent px-3 py-1 text-xs font-medium text-accent-foreground hover:bg-accent/80"
          >
            {showForm ? "Cancel" : "Add arc"}
          </button>
        </div>
      </div>

      {error && (
        <p className="mb-2 text-xs text-destructive">{error}</p>
      )}

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
          <button
            onClick={handleCreate}
            disabled={saving || !theme.trim()}
            className="rounded-md bg-accent px-4 py-1.5 text-sm font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
          >
            {saving ? "Creating..." : "Create"}
          </button>
        </div>
      )}

      {displayedArcs.length === 0 && !showForm ? (
        <p className="text-sm text-muted-foreground">
          {arcs.length === 0
            ? "No arcs yet. Arcs are content themes that help the evaluator link related commits into a narrative thread."
            : "No active arcs."}
        </p>
      ) : (
        <div className="space-y-2">
          {displayedArcs.map((arc) => {
            const isExpanded = expandedId === arc.id;
            const isConfirming = confirmAction?.id === arc.id;
            const isUpdating = updatingId === arc.id;
            const isEditingNotes = editingNotes?.id === arc.id;

            return (
              <div key={arc.id} className="rounded-lg border border-border">
                {/* Collapsed row */}
                <div
                  className="flex cursor-pointer items-center justify-between p-3"
                  onClick={() => setExpandedId(isExpanded ? null : arc.id)}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">{isExpanded ? "▼" : "▶"}</span>
                      <span className="text-sm font-medium">{arc.theme}</span>
                      <span className="text-xs text-muted-foreground">{arc.post_count} posts</span>
                      <ArcStatusBadge status={arc.status} />
                    </div>
                  </div>
                  {/* Quick actions on collapsed row */}
                  <div className="ml-3 flex shrink-0 items-center gap-1" onClick={(e) => e.stopPropagation()}>
                    {arc.status === "active" && !isConfirming && (
                      <>
                        <button
                          onClick={() => setConfirmAction({ id: arc.id, action: "completed" })}
                          disabled={isUpdating}
                          className="rounded-md border border-border px-2 py-0.5 text-xs hover:bg-muted disabled:opacity-50"
                        >
                          Complete
                        </button>
                        <button
                          onClick={() => setConfirmAction({ id: arc.id, action: "abandoned" })}
                          disabled={isUpdating}
                          className="rounded-md border border-border px-2 py-0.5 text-xs text-muted-foreground hover:bg-muted disabled:opacity-50"
                        >
                          Abandon
                        </button>
                      </>
                    )}
                    {arc.status !== "active" && (
                      <button
                        onClick={() => handleStatusChange(arc.id, "active")}
                        disabled={isUpdating}
                        className="rounded-md border border-border px-2 py-0.5 text-xs hover:bg-muted disabled:opacity-50"
                      >
                        {isUpdating ? "..." : "Resume"}
                      </button>
                    )}
                    <button
                      onClick={() => {
                        setHiddenIds((prev) => new Set([...prev, arc.id]));
                        if (expandedId === arc.id) setExpandedId(null);
                      }}
                      className="rounded-md px-1 py-0.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
                      title="Hide from list"
                    >
                      ✕
                    </button>
                  </div>
                </div>

                {/* Confirmation bar */}
                {isConfirming && (
                  <div className="flex items-center gap-2 border-t border-border bg-muted/50 px-3 py-2">
                    <span className="text-xs text-muted-foreground">
                      {confirmAction.action === "completed" ? "Complete" : "Abandon"} this arc?
                    </span>
                    <button
                      onClick={() => handleStatusChange(arc.id, confirmAction.action)}
                      disabled={isUpdating}
                      className="rounded-md bg-accent px-2 py-0.5 text-xs font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
                    >
                      {isUpdating ? "..." : "Confirm"}
                    </button>
                    <button
                      onClick={() => setConfirmAction(null)}
                      className="text-xs text-muted-foreground hover:text-foreground"
                    >
                      Cancel
                    </button>
                  </div>
                )}

                {/* Expanded details */}
                {isExpanded && (
                  <div className="space-y-3 border-t border-border px-3 pb-3 pt-2">
                    {/* Dates */}
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                      <span>ID: {arc.id}</span>
                      {arc.started_at && <span>Started: {formatDate(arc.started_at)}</span>}
                      {arc.ended_at && <span>Ended: {formatDate(arc.ended_at)}</span>}
                      {arc.last_post_at && <span>Last post: {formatDate(arc.last_post_at)}</span>}
                    </div>

                    {/* Notes */}
                    <div>
                      <div className="mb-1 flex items-center justify-between">
                        <span className="text-xs font-medium text-muted-foreground">Notes</span>
                        {!isEditingNotes && (
                          <button
                            onClick={() => setEditingNotes({ id: arc.id, value: arc.notes || "" })}
                            className="text-xs text-muted-foreground hover:text-foreground"
                          >
                            Edit
                          </button>
                        )}
                      </div>
                      {isEditingNotes ? (
                        <div className="space-y-1">
                          <textarea
                            value={editingNotes.value}
                            onChange={(e) => setEditingNotes({ id: arc.id, value: e.target.value })}
                            rows={3}
                            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-xs outline-none focus:ring-2 focus:ring-accent"
                            placeholder="Add notes about this arc..."
                          />
                          <div className="flex gap-1">
                            <button
                              onClick={() => handleSaveNotes(arc.id, editingNotes.value)}
                              disabled={savingNotes}
                              className="rounded-md bg-accent px-2 py-0.5 text-xs font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
                            >
                              {savingNotes ? "..." : "Save"}
                            </button>
                            <button
                              onClick={() => setEditingNotes(null)}
                              className="text-xs text-muted-foreground hover:text-foreground"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <p className="text-xs text-muted-foreground">
                          {arc.notes || "No notes."}
                        </p>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
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
