"use client";

import { useState } from "react";
import type { Memory } from "@/lib/types";
import { addMemory, deleteMemory, clearMemories } from "@/lib/api";

interface MemoriesSectionProps {
  memories: Memory[];
  projectPath: string;
  onRefresh: () => void;
}

export function MemoriesSection({ memories, projectPath, onRefresh }: MemoriesSectionProps) {
  const [showForm, setShowForm] = useState(false);
  const [context, setContext] = useState("");
  const [feedback, setFeedback] = useState("");
  const [draftId, setDraftId] = useState("");
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState<number | null>(null);

  async function handleAdd() {
    if (!context.trim() || !feedback.trim()) return;
    setSaving(true);
    try {
      await addMemory(projectPath, context.trim(), feedback.trim(), draftId.trim());
      setContext("");
      setFeedback("");
      setDraftId("");
      setShowForm(false);
      onRefresh();
    } catch {
      // Keep form open for retry
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(index: number) {
    setDeleting(index);
    try {
      await deleteMemory(projectPath, index);
      onRefresh();
    } catch {
      // Silent
    } finally {
      setDeleting(null);
    }
  }

  async function handleClear() {
    if (!confirm("Clear all memories? This cannot be undone.")) return;
    try {
      await clearMemories(projectPath);
      onRefresh();
    } catch {
      // Silent
    }
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold">Voice Memories</h2>
          {memories.length > 0 && (
            <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
              {memories.length}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {memories.length > 0 && (
            <button
              onClick={handleClear}
              className="text-xs text-destructive hover:underline"
            >
              Clear all
            </button>
          )}
          <button
            onClick={() => setShowForm(!showForm)}
            className="rounded-md bg-accent px-3 py-1 text-xs font-medium text-accent-foreground hover:bg-accent/80"
          >
            {showForm ? "Cancel" : "Add memory"}
          </button>
        </div>
      </div>

      {/* Add form */}
      {showForm && (
        <div className="mb-4 space-y-2 rounded-lg border border-border p-3">
          <div>
            <label className="mb-1 block text-xs font-medium">Context</label>
            <input
              type="text"
              value={context}
              onChange={(e) => setContext(e.target.value)}
              placeholder="Brief description of content type..."
              className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-accent"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium">Feedback</label>
            <textarea
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="Human feedback or voice note..."
              rows={2}
              className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-accent"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Draft ID (optional)</label>
            <input
              type="text"
              value={draftId}
              onChange={(e) => setDraftId(e.target.value)}
              placeholder="Reference to original draft..."
              className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-accent"
            />
          </div>
          <button
            onClick={handleAdd}
            disabled={saving || !context.trim() || !feedback.trim()}
            className="rounded-md bg-accent px-4 py-1.5 text-sm font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
          >
            {saving ? "Adding..." : "Add"}
          </button>
        </div>
      )}

      {/* Table */}
      {memories.length === 0 ? (
        <p className="text-sm text-muted-foreground">No memories yet. Add feedback to guide the AI&apos;s voice.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-border text-xs text-muted-foreground">
                <th className="pb-2 pr-4 font-medium">#</th>
                <th className="pb-2 pr-4 font-medium">Date</th>
                <th className="pb-2 pr-4 font-medium">Context</th>
                <th className="pb-2 pr-4 font-medium">Feedback</th>
                <th className="pb-2 pr-4 font-medium">Draft ID</th>
                <th className="pb-2 font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {memories.map((m, i) => (
                <tr key={`${m.date}-${i}`}>
                  <td className="py-2 pr-4 text-xs text-muted-foreground">{i + 1}</td>
                  <td className="py-2 pr-4 text-xs text-muted-foreground whitespace-nowrap">{m.date}</td>
                  <td className="py-2 pr-4 text-xs" style={{ maxWidth: "200px" }}>
                    <p className="truncate">{m.context}</p>
                  </td>
                  <td className="py-2 pr-4 text-xs" style={{ maxWidth: "250px" }}>
                    <p className="truncate">{m.feedback}</p>
                  </td>
                  <td className="py-2 pr-4 text-xs text-muted-foreground">
                    {m.draft_id ? <code className="text-xs">{m.draft_id}</code> : "-"}
                  </td>
                  <td className="py-2">
                    <button
                      onClick={() => handleDelete(i)}
                      disabled={deleting === i}
                      className="text-xs text-destructive hover:underline disabled:opacity-50"
                    >
                      {deleting === i ? "..." : "Delete"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
