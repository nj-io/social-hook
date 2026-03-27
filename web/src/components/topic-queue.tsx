"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Topic, Strategy } from "@/lib/types";
import type { BackgroundTask } from "@/lib/api";
import { fetchTopics, fetchStrategies, addTopic, updateTopic, reorderTopics, draftNowTopic, setTopicStatus, combineTopics } from "@/lib/api";
import { useDataEvents } from "@/lib/use-data-events";
import { useBackgroundTasks } from "@/lib/use-background-tasks";
import { AsyncButton } from "@/components/async-button";
import { useToast } from "@/lib/toast-context";

const STATUS_STYLES: Record<string, string> = {
  uncovered: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  holding: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400",
  partial: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
  covered: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  dismissed: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
};

const TOPIC_STATUSES = ["uncovered", "holding", "partial", "covered"];

export function TopicQueue({ projectId }: { projectId: string }) {
  const [topics, setTopics] = useState<Topic[]>([]);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterStrategy, setFilterStrategy] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [addStrategy, setAddStrategy] = useState("");
  const [addTopic_, setAddTopic_] = useState("");
  const [addDesc, setAddDesc] = useState("");
  const [adding, setAdding] = useState(false);
  const [editingTopic, setEditingTopic] = useState<string | null>(null);
  const [editDesc, setEditDesc] = useState("");
  const [dragFrom, setDragFrom] = useState<{ strategy: string; index: number } | null>(null);
  const [dragTo, setDragTo] = useState<{ strategy: string; index: number } | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [combining, setCombining] = useState(false);
  const [collapsedStrategies, setCollapsedStrategies] = useState<Set<string>>(() => {
    if (typeof window === "undefined") return new Set();
    try {
      const saved = localStorage.getItem("topic-queue-collapsed");
      return saved ? new Set(JSON.parse(saved)) : new Set();
    } catch { return new Set(); }
  });
  const [dismissedOpen, setDismissedOpen] = useState(() => {
    if (typeof window === "undefined") return false;
    return localStorage.getItem("topic-queue-dismissed-open") === "true";
  });
  const loadRef = useRef<() => void>(() => {});
  const { addToast } = useToast();

  const onTaskCompleted = useCallback((_task: BackgroundTask) => {
    loadRef.current();
  }, []);

  const { trackTask, isRunning, getTask } = useBackgroundTasks(projectId, onTaskCompleted);

  const load = useCallback(async () => {
    try {
      const [t, s] = await Promise.all([
        fetchTopics(projectId, filterStrategy || undefined, true),
        fetchStrategies(projectId),
      ]);
      setTopics(t.topics);
      // API returns {strategies: {name: {...}}} — convert to array
      const stratMap = s.strategies;
      if (stratMap && typeof stratMap === "object" && !Array.isArray(stratMap)) {
        setStrategies(
          Object.entries(stratMap).map(([name]: [string, unknown]) => ({ name, template: false }))
        );
      } else {
        setStrategies([]);
      }
    } catch {
      // silent — failed fetch during auto-refresh
    } finally {
      setLoading(false);
    }
  }, [projectId, filterStrategy]);
  loadRef.current = load;

  useEffect(() => { load(); }, [load]);
  useDataEvents(["topic", "draft"], load, projectId);

  // Pre-select strategy when add form opens
  useEffect(() => {
    if (addOpen && !addStrategy) {
      if (filterStrategy) {
        setAddStrategy(filterStrategy);
      } else if (strategies.length > 0) {
        setAddStrategy(strategies[0].name);
      }
    }
  }, [addOpen, addStrategy, filterStrategy, strategies]);

  async function handleAdd() {
    if (!addStrategy || !addTopic_.trim()) return;
    setAdding(true);
    try {
      await addTopic(projectId, {
        strategy: addStrategy,
        topic: addTopic_.trim(),
        description: addDesc.trim() || undefined,
      });
      setAddOpen(false);
      setAddTopic_("");
      setAddDesc("");
      setAddStrategy("");
      addToast("Topic added");
      await load();
    } catch (e) {
      addToast("Failed to add topic", { variant: "error", detail: e instanceof Error ? e.message : undefined });
    } finally {
      setAdding(false);
    }
  }

  async function handleSaveDesc(topicId: string) {
    try {
      await updateTopic(projectId, topicId, { description: editDesc });
      setEditingTopic(null);
      await load();
    } catch (e) {
      addToast("Failed to save description", { variant: "error", detail: e instanceof Error ? e.message : undefined });
    }
  }

  async function handleDraftNow(topicId: string) {
    try {
      const res = await draftNowTopic(projectId, topicId);
      trackTask(res.task_id, `draft-now:${topicId}`, "draft_now");
    } catch (e) {
      addToast("Failed to start draft", { variant: "error", detail: e instanceof Error ? e.message : undefined });
    }
  }

  async function handleStatusChange(topicId: string, newStatus: string) {
    try {
      await setTopicStatus(projectId, topicId, newStatus);
      await load();
    } catch (e) {
      addToast("Failed to update status", { variant: "error", detail: e instanceof Error ? e.message : undefined });
    }
  }

  function handleDismiss(topicId: string) {
    return handleStatusChange(topicId, "dismissed");
  }

  async function handleCombine() {
    if (selected.size < 2) return;
    setCombining(true);
    try {
      const res = await combineTopics(projectId, Array.from(selected));
      trackTask(res.task_id, `combine:${Array.from(selected)[0]}`, "combine_topics");
      setSelected(new Set());
    } catch (e) {
      addToast("Failed to combine topics", { variant: "error", detail: e instanceof Error ? e.message : undefined });
    } finally {
      setCombining(false);
    }
  }

  function toggleSelect(topicId: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(topicId)) next.delete(topicId);
      else next.add(topicId);
      return next;
    });
  }

  async function handleDrop(from: { strategy: string; index: number }, to: { strategy: string; index: number }) {
    // Only allow reorder within the same strategy group
    if (from.strategy !== to.strategy || from.index === to.index) return;
    const strategyTopics = activeGrouped[from.strategy];
    if (!strategyTopics) return;
    const reordered = [...strategyTopics];
    const [moved] = reordered.splice(from.index, 1);
    reordered.splice(to.index, 0, moved);
    // Optimistic update within the full topics array
    const reorderedIds = new Set(reordered.map((t) => t.id));
    const updated = topics.map((t) => {
      if (!reorderedIds.has(t.id)) return t;
      return reordered[reordered.findIndex((r) => r.id === t.id)];
    });
    setTopics(updated);
    try {
      await reorderTopics(projectId, reordered.map((t) => t.id));
    } catch {
      await load();
    }
  }

  // Separate active vs dismissed topics
  const activeTopics = topics.filter((t) => t.status !== "dismissed");
  const dismissedTopics = topics.filter((t) => t.status === "dismissed");

  // Group active topics by strategy
  const activeGrouped = activeTopics.reduce<Record<string, Topic[]>>((acc, t) => {
    const key = t.strategy;
    if (!acc[key]) acc[key] = [];
    acc[key].push(t);
    return acc;
  }, {});

  function toggleStrategyCollapsed(stratName: string) {
    setCollapsedStrategies((prev) => {
      const next = new Set(prev);
      if (next.has(stratName)) next.delete(stratName);
      else next.add(stratName);
      localStorage.setItem("topic-queue-collapsed", JSON.stringify([...next]));
      return next;
    });
  }

  function toggleDismissedOpen() {
    setDismissedOpen((prev) => {
      const next = !prev;
      localStorage.setItem("topic-queue-dismissed-open", String(next));
      return next;
    });
  }

  function createdByLabel(createdBy?: string): string | null {
    if (!createdBy) return null;
    if (createdBy === "discovery" || createdBy === "track1") return "auto";
    if (createdBy === "user" || createdBy === "operator") return "manual";
    return null;
  }

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading topics...</p>;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Topic Queue</h2>
        <div className="flex items-center gap-2">
          {selected.size >= 2 && (
            <button
              onClick={handleCombine}
              disabled={combining}
              className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
            >
              {combining ? "Combining..." : `Combine (${selected.size})`}
            </button>
          )}
          <select
            value={filterStrategy}
            onChange={(e) => setFilterStrategy(e.target.value)}
            className="h-7 rounded-md border border-border bg-background px-2 text-xs"
          >
            <option value="">All strategies</option>
            {strategies.map((s) => (
              <option key={s.name} value={s.name}>{s.name}</option>
            ))}
          </select>
          <button
            onClick={() => setAddOpen(true)}
            className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-foreground hover:bg-accent/80"
          >
            Add Topic
          </button>
        </div>
      </div>

      {activeTopics.length === 0 ? (
        <div className="rounded-lg border-2 border-dashed border-border p-6 text-center">
          <p className="text-sm text-muted-foreground">No topics in the queue.</p>
        </div>
      ) : (
        Object.entries(activeGrouped).map(([stratName, stratTopics]) => {
          const isCollapsed = collapsedStrategies.has(stratName);
          return (
          <div key={stratName}>
            <button
              onClick={() => toggleStrategyCollapsed(stratName)}
              className="mb-2 flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground"
            >
              <span className={`transition-transform ${isCollapsed ? "" : "rotate-90"}`}>&#x25B6;</span>
              {stratName}
              <span className="ml-1 text-xs font-normal">({stratTopics.length})</span>
            </button>
            {!isCollapsed && <div className="space-y-1">
              {stratTopics.map((topic, index) => {
                const refId = `draft-now:${topic.id}`;
                const isDrafting = isRunning(refId);
                const task = getTask(refId);
                const cbLabel = createdByLabel(topic.created_by);
                return (
                  <div
                    key={topic.id}
                    draggable
                    onDragStart={() => setDragFrom({ strategy: stratName, index })}
                    onDragOver={(e) => { e.preventDefault(); setDragTo({ strategy: stratName, index }); }}
                    onDragEnd={() => {
                      if (dragFrom !== null && dragTo !== null) handleDrop(dragFrom, dragTo);
                      setDragFrom(null);
                      setDragTo(null);
                    }}
                    className={`flex items-center gap-3 rounded-lg border border-border p-3 transition-colors ${
                      dragTo?.strategy === stratName && dragTo?.index === index ? "border-accent bg-accent/5" : "hover:bg-muted/30"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={selected.has(topic.id)}
                      onChange={() => toggleSelect(topic.id)}
                      className="h-3.5 w-3.5 shrink-0 rounded border-border"
                      title="Select for combine"
                    />
                    <span className="shrink-0 text-xs font-mono text-muted-foreground w-6 text-right">#{index + 1}</span>
                    <span className="cursor-grab text-muted-foreground" title="Drag to reorder">
                      &#x2630;
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-sm">{topic.topic}</span>
                        <select
                          value={topic.status}
                          onChange={(e) => handleStatusChange(topic.id, e.target.value)}
                          className={`rounded-full px-2 py-0.5 text-xs font-medium border-0 cursor-pointer ${
                            STATUS_STYLES[topic.status] ?? "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400"
                          }`}
                        >
                          {TOPIC_STATUSES.map((s) => (
                            <option key={s} value={s}>{s}</option>
                          ))}
                        </select>
                        {cbLabel && (
                          <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600 dark:bg-gray-800 dark:text-gray-400">
                            {cbLabel}
                          </span>
                        )}
                      </div>
                      {editingTopic === topic.id ? (
                        <div className="mt-1 flex items-center gap-2">
                          <input
                            type="text"
                            value={editDesc}
                            onChange={(e) => setEditDesc(e.target.value)}
                            className="flex-1 rounded-md border border-border bg-background px-2 py-1 text-xs outline-none focus:ring-2 focus:ring-accent"
                            autoFocus
                          />
                          <button
                            onClick={() => handleSaveDesc(topic.id)}
                            className="text-xs text-accent hover:underline"
                          >
                            Save
                          </button>
                          <button
                            onClick={() => setEditingTopic(null)}
                            className="text-xs text-muted-foreground hover:underline"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <p
                          className="mt-0.5 text-xs text-muted-foreground cursor-pointer hover:text-foreground"
                          onClick={(e) => {
                            e.stopPropagation();
                            setEditingTopic(topic.id);
                            setEditDesc(topic.description || "");
                          }}
                        >
                          {topic.description || "Click to add description"}
                        </p>
                      )}
                      <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
                        {topic.commit_count != null && (
                          <span>{topic.commit_count} commit{topic.commit_count !== 1 ? "s" : ""}</span>
                        )}
                        {topic.last_posted_at && (
                          <span>Last posted: {new Date(topic.last_posted_at).toLocaleDateString()}</span>
                        )}
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {(topic.status === "holding" || topic.status === "uncovered") && (
                        <AsyncButton
                          loading={isDrafting}
                          startTime={task?.created_at}
                          loadingText="Drafting"
                          onClick={() => handleDraftNow(topic.id)}
                          className="rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
                        >
                          Draft Now
                        </AsyncButton>
                      )}
                      <button
                        onClick={() => handleDismiss(topic.id)}
                        className="text-xs text-muted-foreground hover:text-amber-600"
                        title="Dismiss topic"
                      >
                        Dismiss
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>}
          </div>
          );
        })
      )}

      {/* Dismissed topics collapsed section */}
      {dismissedTopics.length > 0 && (
        <div>
          <button
            onClick={toggleDismissedOpen}
            className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <span className={`transition-transform ${dismissedOpen ? "rotate-90" : ""}`}>&#x25B6;</span>
            Dismissed ({dismissedTopics.length})
          </button>
          {dismissedOpen && (
            <div className="mt-2 space-y-1">
              {dismissedTopics.map((topic) => (
                <div
                  key={topic.id}
                  className="flex items-center gap-3 rounded-lg border border-border p-3 opacity-50"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm">{topic.topic}</span>
                      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES.dismissed}`}>
                        dismissed
                      </span>
                      <span className="text-xs text-muted-foreground">{topic.strategy}</span>
                    </div>
                    {topic.description && (
                      <p className="mt-0.5 text-xs text-muted-foreground">{topic.description}</p>
                    )}
                  </div>
                  <button
                    onClick={() => handleStatusChange(topic.id, "uncovered")}
                    className="shrink-0 text-xs text-muted-foreground hover:text-accent"
                  >
                    Restore
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Add topic form */}
      {addOpen && (
        <div className="rounded-lg border border-border p-4">
          <h3 className="text-sm font-semibold">Add Topic</h3>
          <div className="mt-3 space-y-2">
            <div>
              <label className="mb-1 block text-xs font-medium">Strategy</label>
              <select
                value={addStrategy}
                onChange={(e) => setAddStrategy(e.target.value)}
                className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm"
              >
                <option value="">Select strategy</option>
                {strategies.map((s) => (
                  <option key={s.name} value={s.name}>{s.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium">Topic</label>
              <input
                type="text"
                value={addTopic_}
                onChange={(e) => setAddTopic_(e.target.value)}
                placeholder="Topic name"
                className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-accent"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium">Description (optional)</label>
              <input
                type="text"
                value={addDesc}
                onChange={(e) => setAddDesc(e.target.value)}
                placeholder="Brief description"
                className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-accent"
              />
            </div>
            <div className="flex gap-2">
              <button
                onClick={handleAdd}
                disabled={adding || !addStrategy || !addTopic_.trim()}
                className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
              >
                {adding ? "Adding..." : "Add"}
              </button>
              <button
                onClick={() => setAddOpen(false)}
                className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
