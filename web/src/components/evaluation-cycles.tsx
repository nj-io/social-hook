"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import type { EvaluationCycle, CycleStrategyOutcome, DiagnosticItem } from "@/lib/types";
import type { BackgroundTask } from "@/lib/api";
import { fetchCycles, approveAllCycleDrafts, sendCallback, connectDraft, draftNowTopic, fetchTopics } from "@/lib/api";
import { useDataEvents } from "@/lib/use-data-events";
import { useBackgroundTasks } from "@/lib/use-background-tasks";
import { useToast } from "@/lib/toast-context";
import { AsyncButton } from "@/components/async-button";
import { Badge } from "@/components/ui/badge";
import { relativeTime, absoluteTime } from "@/lib/relative-time";

export function EvaluationCycles({ projectId }: { projectId: string }) {
  const [cycles, setCycles] = useState<EvaluationCycle[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedCycles, setExpandedCycles] = useState<Set<string>>(new Set());
  const [expandAll, setExpandAll] = useState(false);
  const [approvingCycle, setApprovingCycle] = useState<string | null>(null);
  const [topicNameById, setTopicNameById] = useState<Record<string, string>>({});

  const loadRef = useRef<() => void>(() => {});
  const { addToast } = useToast();

  const onTaskCompleted = useCallback((task: BackgroundTask) => {
    if (task.status === "failed") {
      addToast("Evaluation failed", { variant: "error", detail: task.error ?? "Unknown error" });
    }
    loadRef.current();
  }, [addToast]);

  const { trackTask, isRunning, getTask } = useBackgroundTasks(projectId, onTaskCompleted);

  const load = useCallback(async () => {
    try {
      const [res, topicsRes] = await Promise.all([
        fetchCycles(projectId),
        fetchTopics(projectId).catch(() => ({ topics: [] })),
      ]);
      setCycles(res.cycles);
      const lookup: Record<string, string> = {};
      for (const t of topicsRes.topics) lookup[t.id] = t.topic;
      setTopicNameById(lookup);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  loadRef.current = load;

  useEffect(() => { load(); }, [load]);
  useDataEvents(["cycle", "draft", "decision"], load, projectId);

  function toggleCycle(id: string) {
    setExpandedCycles((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function handleExpandAll() {
    if (expandAll) {
      setExpandedCycles(new Set());
    } else {
      setExpandedCycles(new Set(cycles.map((c) => c.id)));
    }
    setExpandAll(!expandAll);
  }

  async function handleApproveAll(cycleId: string) {
    setApprovingCycle(cycleId);
    try {
      await approveAllCycleDrafts(projectId, cycleId);
      await load();
    } catch {
      // silent — data events will refresh
    } finally {
      setApprovingCycle(null);
    }
  }

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading evaluation cycles...</p>;
  }

  if (cycles.length === 0) {
    return <p className="text-sm text-muted-foreground">No evaluation cycles yet.</p>;
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Evaluation Cycles</h2>
        <div className="flex items-center gap-3">
          <button
            onClick={handleExpandAll}
            className="text-xs text-accent hover:underline"
          >
            {expandAll ? "Collapse All" : "Expand All"}
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-border text-xs text-muted-foreground">
              <th className="pb-2 pr-4 font-medium">Trigger</th>
              <th className="pb-2 pr-4 font-medium">Strategies</th>
              <th className="pb-2 pr-4 font-medium">Status</th>
              <th className="pb-2 font-medium">Time</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {cycles.map((cycle) => {
              const isExpanded = expandedCycles.has(cycle.id);
              const strategyEntries = Object.entries(cycle.strategies || {});
              return (
                <tr
                  key={cycle.id}
                  className="group cursor-pointer hover:bg-muted/30"
                  onClick={() => toggleCycle(cycle.id)}
                >
                  <td className="py-3 pr-4">
                    <span className="text-sm">{cycle.trigger}</span>
                    <code className="ml-2 text-[10px] text-muted-foreground">{cycle.id.slice(0, 16)}</code>
                    {isExpanded && strategyEntries.length > 0 && (
                      <div className="mt-3 space-y-3">
                        {strategyEntries.map(([stratName, outcome]) => (
                          <StrategyOutcomeCard
                            key={stratName}
                            strategy={stratName}
                            outcome={outcome}
                            projectId={projectId}
                            onReload={load}
                            trackTask={trackTask}
                            isTaskRunning={isRunning}
                            getTask={getTask}
                            topicNameById={topicNameById}
                          />
                        ))}
                        {strategyEntries.some(([, o]) => o.draft_id && o.draft_status === "draft") && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleApproveAll(cycle.id);
                            }}
                            disabled={approvingCycle === cycle.id}
                            className="mt-2 rounded bg-emerald-600 px-3 py-1 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                          >
                            {approvingCycle === cycle.id ? "Approving..." : "Approve All"}
                          </button>
                        )}
                        {cycle.diagnostics && cycle.diagnostics.length > 0 && (
                          <CycleDiagnostics diagnostics={cycle.diagnostics} />
                        )}
                      </div>
                    )}
                  </td>
                  <td className="py-3 pr-4">
                    <div className="flex flex-wrap gap-1">
                      {strategyEntries.map(([name, outcome]) => {
                        const topicName = outcome.topic_matched || (outcome.topic_id ? topicNameById[outcome.topic_id] : undefined);
                        return (
                          <span
                            key={name}
                            className={`rounded-full px-2 py-0.5 text-xs font-medium ${decisionBadgeClass(outcome.decision)}`}
                          >
                            {name}: {outcome.decision}
                            {topicName && (
                              <span className="ml-1 opacity-70">({topicName})</span>
                            )}
                          </span>
                        );
                      })}
                    </div>
                  </td>
                  <td className="py-3 pr-4">
                    <div className="flex flex-col gap-1">
                      <Badge value={cycle.status} variant="status" />
                      {!!cycle.draft_count && (
                        <Link
                          href={`/drafts?from=${projectId}`}
                          className="text-xs text-accent hover:underline"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <CycleStatusCounts cycle={cycle} />
                        </Link>
                      )}
                    </div>
                  </td>
                  <td
                    className="py-3 text-xs text-muted-foreground"
                    title={absoluteTime(cycle.created_at)}
                  >
                    {relativeTime(cycle.created_at)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** 2.6: Descriptive status counts — "2 drafts pending", "1 posted, 1 pending", etc. */
function CycleStatusCounts({ cycle }: { cycle: EvaluationCycle }) {
  const parts: string[] = [];
  if (cycle.posted_count && cycle.posted_count > 0) {
    parts.push(`${cycle.posted_count} posted`);
  }
  if (cycle.approved_count && cycle.approved_count > 0) {
    parts.push(`${cycle.approved_count} approved`);
  }
  if (cycle.pending_count && cycle.pending_count > 0) {
    parts.push(`${cycle.pending_count} pending`);
  }
  if (parts.length === 0 && cycle.draft_count) {
    parts.push(`${cycle.draft_count} draft${cycle.draft_count > 1 ? "s" : ""}`);
  }
  return <>{parts.join(", ")}</>;
}

function StrategyOutcomeCard({
  strategy,
  outcome,
  projectId,
  onReload,
  trackTask,
  isTaskRunning,
  getTask,
  topicNameById,
}: {
  strategy: string;
  outcome: CycleStrategyOutcome;
  projectId: string;
  onReload: () => void;
  trackTask: (taskId: string, refId: string, type: string) => void;
  isTaskRunning: (refId: string) => boolean;
  getTask: (refId: string) => BackgroundTask | null;
  topicNameById: Record<string, string>;
}) {
  const [actionPending, setActionPending] = useState("");

  async function handleApprove() {
    if (!outcome.draft_id) return;
    setActionPending("approve");
    try {
      await sendCallback("approve", outcome.draft_id);
      onReload();
    } catch {
      onReload();
    } finally {
      setActionPending("");
    }
  }

  async function handleReject() {
    if (!outcome.draft_id) return;
    setActionPending("reject");
    try {
      await sendCallback("reject_now", outcome.draft_id);
      onReload();
    } catch {
      onReload();
    } finally {
      setActionPending("");
    }
  }

  async function handleConnect() {
    if (!outcome.draft_id) return;
    setActionPending("connect");
    try {
      // Use a placeholder — the server endpoint requires an account name.
      // For now, connect with the first matching account (the connect endpoint
      // validates platform match). The UI could be expanded to show a picker.
      await connectDraft(outcome.draft_id, "");
      onReload();
    } catch {
      onReload();
    } finally {
      setActionPending("");
    }
  }

  async function handleDraftNow() {
    if (!outcome.topic_id) return;
    try {
      const res = await draftNowTopic(projectId, outcome.topic_id);
      trackTask(res.task_id, `draft-now:${outcome.topic_id}`, "draft_now");
    } catch {
      // silent
    }
  }

  const draftNowRefId = outcome.topic_id ? `draft-now:${outcome.topic_id}` : "";
  const draftNowLoading = !!draftNowRefId && isTaskRunning(draftNowRefId);
  const draftNowTask = draftNowRefId ? getTask(draftNowRefId) : undefined;

  const isDisabled = !!actionPending;

  return (
    <div className="rounded-md border border-border bg-muted/30 p-3" onClick={(e) => e.stopPropagation()}>
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">{strategy}</span>
        <Badge value={outcome.decision} variant="decision" />
      </div>
      {outcome.reasoning && (
        <p className="mt-1 text-xs text-muted-foreground">{outcome.reasoning}</p>
      )}

      {/* 2.4: Episode tags as pill badges */}
      {!!outcome.episode_tags && outcome.episode_tags.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {outcome.episode_tags.map((tag) => (
            <Badge key={tag} value={tag} variant="tag" />
          ))}
        </div>
      )}

      <div className="mt-2 space-y-1 text-xs">
        {(outcome.topic_matched || (outcome.topic_id && topicNameById[outcome.topic_id])) && (
          <p><span className="text-muted-foreground">Topic: </span>{outcome.topic_matched || topicNameById[outcome.topic_id!]}</p>
        )}
        {outcome.arc_reference && (
          <p><span className="text-muted-foreground">Arc: </span>{outcome.arc_reference}</p>
        )}
        {outcome.content_source && (
          <p><span className="text-muted-foreground">Source: </span>{typeof outcome.content_source === "string" ? outcome.content_source : (outcome.content_source as Record<string, unknown>).types ? (outcome.content_source as Record<string, unknown[]>).types.join(", ") : JSON.stringify(outcome.content_source)}</p>
        )}

        {/* Draft section with inline actions */}
        {outcome.draft_id && (
          <div className="mt-2">
            <Link
              href={`/drafts/${outcome.draft_id}`}
              className="text-accent hover:underline"
            >
              View draft
            </Link>
            {outcome.draft_status && (
              <span className="ml-2">
                <Badge value={outcome.draft_status} variant="status" />
              </span>
            )}
            {outcome.draft_content && (
              <p className="mt-1 rounded border border-border bg-background p-2 text-xs">
                {outcome.draft_content.slice(0, 200)}
                {outcome.draft_content.length > 200 ? "..." : ""}
              </p>
            )}

            {/* 2.1: Inline approve/reject for drafts in "draft" status */}
            {outcome.draft_status === "draft" && !outcome.draft_preview_mode && (
              <div className="mt-2 flex gap-2">
                <button
                  onClick={handleApprove}
                  disabled={isDisabled}
                  className="rounded bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                >
                  {actionPending === "approve" ? "..." : "Approve"}
                </button>
                <button
                  onClick={handleReject}
                  disabled={isDisabled}
                  className="rounded border border-red-300 px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-50 dark:border-red-700 dark:text-red-400 dark:hover:bg-red-900/20"
                >
                  {actionPending === "reject" ? "..." : "Reject"}
                </button>
              </div>
            )}

            {/* 2.1: Connect Account for preview-mode drafts */}
            {!!outcome.draft_preview_mode && (
              <div className="mt-2">
                <button
                  onClick={handleConnect}
                  disabled={isDisabled}
                  className="rounded border border-blue-300 px-2.5 py-1 text-xs font-medium text-blue-700 hover:bg-blue-50 disabled:opacity-50 dark:border-blue-700 dark:text-blue-400 dark:hover:bg-blue-900/20"
                >
                  {actionPending === "connect" ? "..." : "Connect Account"}
                </button>
              </div>
            )}
          </div>
        )}

        {/* 2.2: Draft Now for held strategies with a topic */}
        {outcome.decision === "hold" && !!outcome.topic_id && !outcome.draft_id && (
          <div className="mt-2">
            <AsyncButton
              loading={draftNowLoading}
              startTime={draftNowTask?.created_at}
              loadingText="Drafting"
              onClick={handleDraftNow}
              disabled={draftNowLoading}
              className="rounded bg-amber-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-50"
            >
              Draft Now
            </AsyncButton>
          </div>
        )}
      </div>
    </div>
  );
}

function decisionBadgeClass(decision: string): string {
  switch (decision) {
    case "draft":
      return "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400";
    case "hold":
      return "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400";
    default:
      return "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400";
  }
}

function CycleDiagnostics({ diagnostics }: { diagnostics: DiagnosticItem[] }) {
  const warnings = diagnostics.filter(d => d.severity !== "info");
  if (warnings.length === 0) return null;

  return (
    <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-900/20">
      <p className="text-xs font-medium text-amber-800 dark:text-amber-300">
        Pipeline Warnings ({warnings.length})
      </p>
      <ul className="mt-1 space-y-1">
        {warnings.map((d, i) => (
          <li key={i} className="text-xs text-amber-700 dark:text-amber-400">
            <span className="font-medium">{d.code}:</span> {d.message}
            {d.suggestion && (
              <span className="ml-1 text-amber-600 dark:text-amber-500">
                — {d.suggestion}
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
