"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ContentSuggestion, Strategy } from "@/lib/types";
import type { BackgroundTask } from "@/lib/api";
import { fetchSuggestions, createSuggestion, dismissSuggestion, fetchStrategies } from "@/lib/api";
import { useDataEvents } from "@/lib/use-data-events";
import { useBackgroundTasks } from "@/lib/use-background-tasks";
import { AsyncButton } from "@/components/async-button";
import { Modal } from "@/components/ui/modal";

const STATUS_STYLES: Record<string, string> = {
  pending: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
  accepted: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  dismissed: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
  evaluating: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
};

export function ContentSuggestions({ projectId }: { projectId: string }) {
  const [suggestions, setSuggestions] = useState<ContentSuggestion[]>([]);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [suggestOpen, setSuggestOpen] = useState(false);
  const [idea, setIdea] = useState("");
  const [strategy, setStrategy] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [confirmDismiss, setConfirmDismiss] = useState<string | null>(null);
  const [dismissing, setDismissing] = useState(false);
  const loadRef = useRef<() => void>(() => {});

  const onTaskCompleted = useCallback((_task: BackgroundTask) => {
    loadRef.current();
  }, []);

  const { trackTask } = useBackgroundTasks(projectId, onTaskCompleted);

  const load = useCallback(async () => {
    try {
      const [s, st] = await Promise.all([
        fetchSuggestions(projectId),
        fetchStrategies(projectId),
      ]);
      setSuggestions(s.suggestions);
      // API returns {strategies: {name: {...}}} — convert to array
      const stratMap = st.strategies;
      if (stratMap && typeof stratMap === "object" && !Array.isArray(stratMap)) {
        setStrategies(
          Object.entries(stratMap).map(([name]: [string, unknown]) => ({ name, template: false }))
        );
      } else {
        setStrategies([]);
      }
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [projectId]);
  loadRef.current = load;

  useEffect(() => { load(); }, [load]);
  useDataEvents(["suggestion", "topic"], load, projectId);

  async function handleSuggest() {
    if (!idea.trim()) return;
    setSubmitting(true);
    try {
      const res = await createSuggestion(projectId, {
        idea: idea.trim(),
        strategy: strategy || undefined,
      });
      if (res.task_id) {
        trackTask(res.task_id, `suggest:${res.task_id}`, "suggestion_evaluate");
      }
      setSuggestOpen(false);
      setIdea("");
      setStrategy("");
      await load();
    } catch {
      // silent
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDismiss(id: string) {
    setDismissing(true);
    try {
      await dismissSuggestion(projectId, id);
      setConfirmDismiss(null);
      await load();
    } catch {
      // silent
    } finally {
      setDismissing(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Content Suggestions</h2>
        <button
          onClick={() => setSuggestOpen(true)}
          className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-foreground hover:bg-accent/80"
        >
          Suggest Content
        </button>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : suggestions.length === 0 ? (
        <p className="text-sm text-muted-foreground">No suggestions yet. Use the button above to suggest content ideas.</p>
      ) : (
        <div className="space-y-2">
          {suggestions.map((s) => (
            <div key={s.id} className="flex items-center justify-between rounded-lg border border-border p-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                    STATUS_STYLES[s.status] ?? "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400"
                  }`}>
                    {s.status}
                  </span>
                  {s.strategy && (
                    <span className="text-xs text-muted-foreground">{s.strategy}</span>
                  )}
                  <span className="text-xs text-muted-foreground">
                    {new Date(s.created_at).toLocaleDateString()}
                  </span>
                </div>
                <p className="mt-1 text-sm">{s.idea}</p>
              </div>
              {s.status !== "dismissed" && (
                <button
                  onClick={() => setConfirmDismiss(s.id)}
                  className="ml-3 shrink-0 text-xs text-muted-foreground hover:text-foreground"
                >
                  Dismiss
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Suggest modal */}
      <Modal open={suggestOpen} onClose={() => setSuggestOpen(false)} maxWidth="max-w-md">
        <h3 className="text-sm font-semibold">Suggest Content</h3>
        <p className="mt-1 text-xs text-muted-foreground">Describe a content idea. If no strategy is selected, the evaluator will decide.</p>
        <div className="mt-3 space-y-3">
          <div>
            <label className="mb-1 block text-sm font-medium">Idea</label>
            <textarea
              rows={3}
              value={idea}
              onChange={(e) => setIdea(e.target.value)}
              placeholder="Describe your content idea..."
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
              autoFocus
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Strategy (optional)</label>
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
            >
              <option value="">Evaluator decides</option>
              {strategies.map((s) => (
                <option key={s.name} value={s.name}>{s.name}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={() => setSuggestOpen(false)} className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted">
            Cancel
          </button>
          <AsyncButton
            loading={submitting}
            loadingText="Submitting"
            onClick={handleSuggest}
            disabled={!idea.trim()}
            className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
          >
            Submit
          </AsyncButton>
        </div>
      </Modal>

      {/* Dismiss confirmation */}
      <Modal open={!!confirmDismiss} onClose={() => setConfirmDismiss(null)} maxWidth="max-w-sm">
        <h3 className="text-sm font-semibold">Dismiss Suggestion</h3>
        <p className="mt-2 text-sm text-muted-foreground">Are you sure you want to dismiss this suggestion?</p>
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={() => setConfirmDismiss(null)} className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted">
            Cancel
          </button>
          <button
            onClick={() => confirmDismiss && handleDismiss(confirmDismiss)}
            disabled={dismissing}
            className="rounded-md bg-destructive px-3 py-1.5 text-sm font-medium text-destructive-foreground hover:bg-destructive/80 disabled:opacity-50"
          >
            {dismissing ? "Dismissing..." : "Dismiss"}
          </button>
        </div>
      </Modal>
    </div>
  );
}
