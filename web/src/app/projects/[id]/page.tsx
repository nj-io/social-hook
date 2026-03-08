"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  fetchProjectDetail,
  fetchProjectDecisions,
  fetchProjectPosts,
  fetchProjectUsage,
  updateProjectSummary,
  regenerateProjectSummary,
  createDraftFromDecision,
  deleteDecision,
  retriggerDecision,
  fetchEnabledPlatforms,
  consolidateDecisions,
  fetchMemories,
  fetchDecisionBranches,
  fetchImportPreview,
  importCommits,
  type BackgroundTask,
} from "@/lib/api";
import type { Decision, Memory, PostRecord, ProjectDetail, UsageSummary } from "@/lib/types";
import { StatusBadge } from "@/components/status-badge";
import { DecisionBadge } from "@/components/decision-badge";
import { SimpleMarkdown } from "@/components/simple-markdown";
import { MemoriesSection } from "@/components/memories-section";
import { ArcsSection } from "@/components/arcs-section";
import { useDataEvents } from "@/lib/use-data-events";
import { useBackgroundTasks } from "@/lib/use-background-tasks";

const DECISIONS_PER_PAGE = 10;

export default function ProjectDetailPage() {
  const params = useParams();
  const id = params.id as string;

  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [posts, setPosts] = useState<PostRecord[]>([]);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [decisionOffset, setDecisionOffset] = useState(0);
  const [hasMoreDecisions, setHasMoreDecisions] = useState(false);
  const [editingSummary, setEditingSummary] = useState(false);
  const [summaryDraft, setSummaryDraft] = useState("");
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryExpanded, setSummaryExpanded] = useState(() => {
    if (typeof window === "undefined") return false;
    return localStorage.getItem("project-summary-expanded") !== "false";
  });
  const [expandedDecisions, setExpandedDecisions] = useState<Set<string>>(new Set());
  const [draftResult, setDraftResult] = useState<Record<string, { count?: number; error?: string }>>({});
  const [platformCount, setPlatformCount] = useState<number>(0);
  const [selectedDecisions, setSelectedDecisions] = useState<Set<string>>(new Set());
  const [consolidateResult, setConsolidateResult] = useState<{ count?: number; error?: string } | null>(null);
  const [confirmRedraft, setConfirmRedraft] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmRetrigger, setConfirmRetrigger] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [branchFilter, setBranchFilter] = useState<string>("");
  const [decisionBranches, setDecisionBranches] = useState<string[]>([]);
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [importPreview, setImportPreview] = useState<{ total_commits: number; already_tracked: number; importable: number } | null>(null);
  const [importBranch, setImportBranch] = useState<string>("");
  const [importLoading, setImportLoading] = useState(false);
  const [importRefreshKey, setImportRefreshKey] = useState(0);
  // Consolidate uses a special ref_id key since it spans multiple decisions
  const CONSOLIDATE_REF = "__consolidate__";

  const onTaskCompleted = useCallback((task: BackgroundTask) => {
    if (task.status === "completed" && task.result) {
      if (task.type === "create_draft") {
        const count = (task.result as Record<string, unknown>).count as number | undefined;
        if (count != null) {
          setDraftResult((prev) => ({ ...prev, [task.ref_id]: { count } }));
          setDecisions((prev) =>
            prev.map((d) =>
              d.id === task.ref_id ? { ...d, draft_count: d.draft_count + count } : d,
            ),
          );
        }
      } else if (task.type === "consolidate") {
        const count = (task.result as Record<string, unknown>).count as number | undefined;
        setConsolidateResult({ count });
        setSelectedDecisions(new Set());
      } else if (task.type === "import_commits") {
        setImportModalOpen(false);
        setImportLoading(false);
        // Trigger re-fetch by bumping a counter
        setImportRefreshKey((k) => k + 1);
      }
    } else if (task.status === "failed") {
      const error = task.error ?? "Task failed";
      if (task.type === "create_draft") {
        setDraftResult((prev) => ({ ...prev, [task.ref_id]: { error } }));
      } else if (task.type === "consolidate") {
        setConsolidateResult({ error });
      } else if (task.type === "import_commits") {
        setImportLoading(false);
      }
    }
  }, []);

  const { trackTask, isRunning: isTaskRunning } = useBackgroundTasks(id, onTaskCompleted);

  const loadMemories = useCallback(async (repoPath: string) => {
    try {
      const mem = await fetchMemories(repoPath);
      setMemories(mem.memories);
    } catch {
      // Non-critical
    }
  }, []);

  const reload = useCallback(async () => {
    try {
      const [detail, dec, po, us] = await Promise.all([
        fetchProjectDetail(id),
        fetchProjectDecisions(id, DECISIONS_PER_PAGE, decisionOffset, branchFilter || null),
        fetchProjectPosts(id, 20),
        fetchProjectUsage(id),
      ]);
      setProject(detail);
      setDecisions(dec.decisions);
      setHasMoreDecisions(dec.decisions.length === DECISIONS_PER_PAGE);
      setPosts(po.posts);
      setUsage(us);
      loadMemories(detail.repo_path);
      fetchDecisionBranches(id).then(({ branches }) => setDecisionBranches(branches)).catch(() => {});
    } catch {
      // Silent refresh failure
    }
  }, [id, decisionOffset, branchFilter, loadMemories]);

  useDataEvents(["decision", "draft", "post", "project", "arc", "task"], reload, id);

  useEffect(() => {
    async function load() {
      try {
        const [detail, dec, po, us, plat] = await Promise.all([
          fetchProjectDetail(id),
          fetchProjectDecisions(id, DECISIONS_PER_PAGE, 0, branchFilter || null),
          fetchProjectPosts(id, 20),
          fetchProjectUsage(id),
          fetchEnabledPlatforms(),
        ]);
        setProject(detail);
        setDecisions(dec.decisions);
        setHasMoreDecisions(dec.decisions.length === DECISIONS_PER_PAGE);
        setPosts(po.posts);
        setUsage(us);
        setPlatformCount(plat.count);
        loadMemories(detail.repo_path);
        fetchDecisionBranches(id).then(({ branches }) => setDecisionBranches(branches)).catch(() => {});
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load project");
      } finally {
        setLoading(false);
      }
    }
    load();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, branchFilter, importRefreshKey, loadMemories]);

  async function loadMoreDecisions(offset: number) {
    try {
      const res = await fetchProjectDecisions(id, DECISIONS_PER_PAGE, offset, branchFilter || null);
      setDecisions(res.decisions);
      setDecisionOffset(offset);
      setHasMoreDecisions(res.decisions.length === DECISIONS_PER_PAGE);
      setSelectedDecisions(new Set());
    } catch {
      // Keep existing data
    }
  }

  function onCreateDraftClick(decisionId: string, hasDrafts: boolean) {
    if (hasDrafts) {
      setConfirmRedraft(decisionId);
    } else {
      handleCreateDraft(decisionId);
    }
  }

  async function handleCreateDraft(decisionId: string) {
    setConfirmRedraft(null);
    setDraftResult((prev) => { const next = { ...prev }; delete next[decisionId]; return next; });
    try {
      const res = await createDraftFromDecision(decisionId);
      trackTask(res.task_id, decisionId, "create_draft");
    } catch (e) {
      setDraftResult((prev) => ({
        ...prev,
        [decisionId]: { error: e instanceof Error ? e.message : "Failed" },
      }));
    }
  }

  async function handleConsolidate() {
    setConsolidateResult(null);
    try {
      const res = await consolidateDecisions(Array.from(selectedDecisions));
      trackTask(res.task_id, CONSOLIDATE_REF, "consolidate");
    } catch (e) {
      setConsolidateResult({ error: e instanceof Error ? e.message : "Failed" });
    }
  }

  function toggleSelected(decisionId: string) {
    setSelectedDecisions((prev) => {
      const next = new Set(prev);
      if (next.has(decisionId)) next.delete(decisionId);
      else next.add(decisionId);
      return next;
    });
  }

  if (loading) {
    return <p className="text-center text-muted-foreground">Loading...</p>;
  }

  if (error || !project) {
    return (
      <div className="space-y-4">
        <Link href="/" className="text-sm text-accent hover:underline">
          &larr; Back to dashboard
        </Link>
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error || "Project not found"}
        </div>
      </div>
    );
  }

  const confidencePct = project.lifecycle ? Math.round(project.lifecycle.confidence * 100) : null;

  return (
    <div className="space-y-8">
      <Link href="/" className="text-sm text-accent hover:underline">
        &larr; Back to dashboard
      </Link>

      {/* Overview */}
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">{project.name}</h1>
          {project.paused === 1 && <StatusBadge status="paused" />}
        </div>
        <p className="mt-1 truncate text-sm text-muted-foreground">{project.repo_path}</p>
        {/* Project Summary */}
        <div className="mt-4 rounded-lg border border-border">
          <button
            type="button"
            onClick={() => {
              const next = !summaryExpanded;
              setSummaryExpanded(next);
              localStorage.setItem("project-summary-expanded", String(next));
            }}
            className="flex w-full items-center justify-between p-4 text-left"
          >
            <div className="min-w-0 flex-1">
              <h2 className="text-sm font-medium text-muted-foreground">Project Summary</h2>
              {!summaryExpanded && project.summary && (
                <p className="mt-1 truncate text-xs text-muted-foreground/70">
                  {project.summary.replace(/[*`#\n]+/g, " ").trim()}
                </p>
              )}
            </div>
            <span className="ml-3 shrink-0 text-xs text-muted-foreground">{summaryExpanded ? "\u25B2" : "\u25BC"}</span>
          </button>

          {summaryExpanded && (
            <div className="border-t border-border px-4 pb-4 pt-3">
              <div className="mb-2 flex items-center justify-end gap-2">
                {!editingSummary && (
                  <>
                    <button
                      onClick={() => {
                        setSummaryDraft(project.summary || "");
                        setEditingSummary(true);
                      }}
                      className="text-xs text-accent hover:underline"
                    >
                      Edit
                    </button>
                    <button
                      onClick={async () => {
                        setSummaryLoading(true);
                        try {
                          const res = await regenerateProjectSummary(id);
                          setProject((prev) => prev ? { ...prev, summary: res.summary } : prev);
                        } catch {
                          // Silent failure
                        } finally {
                          setSummaryLoading(false);
                        }
                      }}
                      disabled={summaryLoading}
                      className="text-xs text-accent hover:underline disabled:opacity-50"
                    >
                      {summaryLoading ? "Regenerating..." : "Regenerate"}
                    </button>
                  </>
                )}
              </div>

              {editingSummary ? (
                <div className="space-y-2">
                  <textarea
                    rows={4}
                    value={summaryDraft}
                    onChange={(e) => setSummaryDraft(e.target.value)}
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={async () => {
                        setSummaryLoading(true);
                        try {
                          await updateProjectSummary(id, summaryDraft);
                          setProject((prev) => prev ? { ...prev, summary: summaryDraft } : prev);
                          setEditingSummary(false);
                        } catch {
                          // Silent failure
                        } finally {
                          setSummaryLoading(false);
                        }
                      }}
                      disabled={summaryLoading}
                      className="rounded-md bg-accent px-3 py-1 text-xs font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
                    >
                      Save
                    </button>
                    <button
                      onClick={() => setEditingSummary(false)}
                      className="rounded-md border border-border px-3 py-1 text-xs hover:bg-muted"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : project.summary ? (
                <SimpleMarkdown content={project.summary} />
              ) : (
                <p className="text-sm text-muted-foreground">No summary yet. Click Regenerate to create one.</p>
              )}

              <p className="mt-2 text-xs text-muted-foreground">
                Adjust context depth in{" "}
                <Link href="/settings?section=context" className="text-accent hover:underline">
                  Settings &gt; Context
                </Link>
              </p>
            </div>
          )}
        </div>

        {/* Lifecycle */}
        {project.lifecycle && (
          <div className="mt-4 rounded-lg border border-border p-4">
            <h2 className="mb-2 text-sm font-medium text-muted-foreground">Lifecycle</h2>
            <div className="flex items-center gap-3">
              <span className="text-sm font-medium capitalize">{project.lifecycle.phase}</span>
              {confidencePct != null && (
                <div className="flex items-center gap-2">
                  <div className="h-2 w-32 rounded-full bg-border">
                    <div
                      className="h-2 rounded-full bg-accent"
                      style={{ width: `${confidencePct}%` }}
                    />
                  </div>
                  <span className="text-xs text-muted-foreground">{confidencePct}%</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Stats */}
        <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <StatCard
            label="Decisions"
            value={
              Object.entries(project.decision_counts || {})
                .filter(([k]) => k !== "imported")
                .reduce((a, [, b]) => a + b, 0)
            }
            secondary={
              (project.decision_counts?.imported ?? 0) > 0
                ? `+${project.decision_counts.imported} imported`
                : undefined
            }
          />
          <Link href={`/drafts?from=${id}&name=${encodeURIComponent(project.name)}`} className="block">
            <StatCard label="Drafts" value={project.draft_count ?? 0} />
          </Link>
          <StatCard label="Published" value={project.post_count ?? 0} />
          <Link href="/settings?section=journey-capture" className="block">
            <StatCard
              label="Narrative Debt"
              value={project.narrative_debt?.debt_counter ?? 0}
            />
          </Link>
        </div>

        {/* Journey Capture status */}
        <div className="mt-2">
          {project.journey_capture_enabled ? (
            <p className="text-xs text-green-600 dark:text-green-400">Journey Capture: On</p>
          ) : (
            <Link href="/settings?section=journey-capture" className="text-xs text-muted-foreground hover:text-foreground">
              Journey Capture: Off — enable in settings
            </Link>
          )}
        </div>
      </div>

      {/* Evaluator Decisions */}
      <div>
        <div className="mb-3 flex items-center gap-3">
          <h2 className="text-lg font-semibold">Evaluator Decisions</h2>
          <select
            className="h-7 rounded-md border border-border bg-background px-2 text-xs text-foreground"
            value={branchFilter}
            onChange={(e) => { setBranchFilter(e.target.value); setDecisionOffset(0); }}
          >
            <option value="">All branches{!project.trigger_branch ? " (active)" : ""}</option>
            {(() => {
              const branches = [...decisionBranches];
              if (project.trigger_branch && !branches.includes(project.trigger_branch)) {
                branches.push(project.trigger_branch);
                branches.sort();
              }
              return branches.map((b) => (
                <option key={b} value={b}>
                  {b}{project.trigger_branch === b ? " (active)" : ""}
                </option>
              ));
            })()}
          </select>
          <button
            onClick={async () => {
              setImportModalOpen(true);
              setImportBranch("");
              try {
                const preview = await fetchImportPreview(id);
                setImportPreview(preview);
              } catch { setImportPreview(null); }
            }}
            className="rounded-md border border-border px-2 py-1 text-xs font-medium transition-colors hover:bg-muted"
          >
            Import History
          </button>
          <span className="text-xs text-muted-foreground">
            {platformCount === 0
              ? "No platforms configured — drafts use preview mode"
              : `${platformCount} platform${platformCount !== 1 ? "s" : ""} enabled`}
          </span>
        </div>
        {decisions.length === 0 ? (
          <p className="text-sm text-muted-foreground">No decisions yet.</p>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-border text-xs text-muted-foreground">
                    <th className="pb-2 pr-2 font-medium w-8"></th>
                    <th className="pb-2 pr-4 font-medium">Decision</th>
                    <th className="pb-2 pr-4 font-medium">Commit</th>
                    <th className="pb-2 pr-4 font-medium">Angle</th>
                    <th className="hidden pb-2 pr-4 font-medium sm:table-cell">Episode</th>
                    <th className="hidden pb-2 pr-4 font-medium md:table-cell">Category</th>
                    <th className="pb-2 pr-4 font-medium">Date</th>
                    <th className="pb-2 pr-4 font-medium">Drafts</th>
                    <th className="pb-2 pr-4 font-medium">Actions</th>
                    <th className="pb-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {decisions.map((d) => {
                    const isExpanded = expandedDecisions.has(d.id);
                    const isCreating = isTaskRunning(d.id);
                    const result = draftResult[d.id];
                    return (
                      <tr
                        key={d.id}
                        className="group cursor-pointer hover:bg-muted/30"
                        onClick={() => {
                          setExpandedDecisions((prev) => {
                            const next = new Set(prev);
                            if (next.has(d.id)) next.delete(d.id);
                            else next.add(d.id);
                            return next;
                          });
                        }}
                      >
                        <td className="py-2 pr-2" onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={selectedDecisions.has(d.id)}
                            onChange={() => toggleSelected(d.id)}
                            className="h-4 w-4 rounded border-border accent-accent"
                          />
                        </td>
                        <td className="py-2 pr-4">
                          <DecisionBadge decision={d.decision} />
                        </td>
                        <td className="py-2 pr-4">
                          <div>
                            <code className="text-xs">{d.commit_hash.slice(0, 7)}</code>
                            <p className="text-xs text-muted-foreground">
                              {d.commit_message?.split("\n")[0]}
                            </p>
                            {isExpanded && (
                              <div className="mt-2 space-y-2">
                                {d.commit_message?.includes("\n") && (
                                  <div className="rounded border border-border bg-muted/50 p-2">
                                    <p className="text-xs font-medium text-muted-foreground">Commit Message</p>
                                    <p className="mt-1 whitespace-pre-wrap text-xs">{d.commit_message}</p>
                                  </div>
                                )}
                                <div className="rounded border border-border bg-muted/50 p-2">
                                  <p className="text-xs font-medium text-muted-foreground">Reasoning</p>
                                  <p className="mt-1 whitespace-pre-wrap text-xs">{d.reasoning || "No reasoning recorded."}</p>
                                </div>
                                {d.media_tool && (
                                  <p className="text-xs text-muted-foreground">
                                    Media: <span className="font-medium text-foreground">{d.media_tool}</span>
                                  </p>
                                )}
                                {d.arc_id && (
                                  <p className="text-xs text-muted-foreground">
                                    Arc: <span className="font-mono text-foreground">{d.arc_id.slice(0, 12)}</span>
                                  </p>
                                )}
                                {d.draft_ids && d.draft_ids.length > 0 && (
                                  <div className="text-xs text-muted-foreground">
                                    Drafts:{" "}
                                    {d.draft_ids.map((draftId, i) => (
                                      <span key={draftId}>
                                        {i > 0 && ", "}
                                        <Link
                                          href={`/drafts/${draftId}`}
                                          className="font-mono text-accent hover:underline"
                                          onClick={(e) => e.stopPropagation()}
                                        >
                                          {draftId.slice(0, 14)}
                                        </Link>
                                      </span>
                                    ))}
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        </td>
                        <td className="py-2 pr-4 text-xs">{d.angle || "-"}</td>
                        <td className="hidden py-2 pr-4 text-xs sm:table-cell">{d.episode_type || "-"}</td>
                        <td className="hidden py-2 pr-4 text-xs md:table-cell">{d.post_category || "-"}</td>
                        <td className="py-2 pr-4 text-xs text-muted-foreground">
                          {new Date(d.created_at).toLocaleDateString()}
                        </td>
                        <td className="py-2 pr-4" onClick={(e) => e.stopPropagation()}>
                          {d.draft_count > 0 ? (
                            <Link
                              href={`/drafts?from=${id}&name=${encodeURIComponent(project.name)}&decision=${encodeURIComponent(d.id)}`}
                              className="text-xs text-accent hover:underline"
                            >
                              {d.draft_count} draft{d.draft_count !== 1 ? "s" : ""}
                            </Link>
                          ) : (
                            <span className="text-xs text-muted-foreground">-</span>
                          )}
                        </td>
                        <td className="py-2 pr-4" onClick={(e) => e.stopPropagation()}>
                          <div className="flex items-center gap-1.5">
                            {d.decision === "imported" ? (
                              <button
                                onClick={async () => {
                                  setActionLoading(true);
                                  setActionError(null);
                                  try {
                                    await retriggerDecision(d.id);
                                    reload();
                                  } catch (err) {
                                    setActionError(err instanceof Error ? err.message : "Evaluate failed");
                                  } finally {
                                    setActionLoading(false);
                                  }
                                }}
                                disabled={actionLoading}
                                className="inline-flex items-center gap-1.5 rounded-md border border-indigo-300 px-2 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-50 dark:border-indigo-700 dark:text-indigo-400 dark:hover:bg-indigo-950 disabled:opacity-70"
                                title="Run evaluator on this imported commit"
                              >
                                Evaluate
                              </button>
                            ) : (
                              <button
                                onClick={() => onCreateDraftClick(d.id, d.draft_count > 0)}
                                disabled={isCreating}
                                className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium disabled:opacity-70 ${
                                  d.draft_count > 0 && !isCreating
                                    ? "border border-green-300 text-green-700 hover:bg-green-50 dark:border-green-700 dark:text-green-400 dark:hover:bg-green-950"
                                    : "bg-accent text-accent-foreground hover:bg-accent/80"
                                }`}
                                title={platformCount === 0 ? "Uses preview mode" : `Draft for ${platformCount} platform${platformCount !== 1 ? "s" : ""}`}
                              >
                                {isCreating && (
                                  <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                                  </svg>
                                )}
                                {isCreating
                                  ? "Creating..."
                                  : d.draft_count > 0
                                    ? "Draft Created"
                                    : "Create Draft"}
                              </button>
                            )}
                          </div>
                        </td>
                        <td className="py-2" onClick={(e) => e.stopPropagation()}>
                          {result?.count != null && (
                            <span className="text-xs text-green-600 dark:text-green-400">
                              +{result.count} draft{result.count !== 1 ? "s" : ""} created
                            </span>
                          )}
                          {result?.error && (
                            <span className="text-xs text-destructive">{result.error}</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {/* Pagination */}
            <div className="mt-3 flex items-center gap-2">
              <button
                onClick={() => loadMoreDecisions(decisionOffset - DECISIONS_PER_PAGE)}
                disabled={decisionOffset === 0}
                className="rounded-md border border-border px-3 py-1 text-xs disabled:opacity-30"
              >
                Previous
              </button>
              <span className="text-xs text-muted-foreground">
                Page {Math.floor(decisionOffset / DECISIONS_PER_PAGE) + 1}
              </span>
              <button
                onClick={() => loadMoreDecisions(decisionOffset + DECISIONS_PER_PAGE)}
                disabled={!hasMoreDecisions}
                className="rounded-md border border-border px-3 py-1 text-xs disabled:opacity-30"
              >
                Next
              </button>
            </div>
          </>
        )}
      </div>

      {/* Arcs */}
      <ArcsSection
        arcs={project.arcs}
        projectId={project.id}
        onRefresh={reload}
      />

      {/* Published Posts */}
      <div>
        <h2 className="mb-3 text-lg font-semibold">Published Posts</h2>
        {posts.length === 0 ? (
          <p className="text-sm text-muted-foreground">No published posts yet.</p>
        ) : (
          <div className="space-y-2">
            {posts.map((post) => (
              <div key={post.id} className="rounded-lg border border-border p-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <PlatformBadge platform={post.platform} />
                    {post.external_url && (
                      <a
                        href={post.external_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-accent hover:underline"
                      >
                        View post
                      </a>
                    )}
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {new Date(post.posted_at).toLocaleDateString()}
                  </span>
                </div>
                <p className="mt-1 truncate text-sm">{post.content}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Voice Memories */}
      <MemoriesSection
        memories={memories}
        projectPath={project.repo_path}
        onRefresh={() => loadMemories(project.repo_path)}
      />

      {/* Usage */}
      {usage && (
        <div>
          <h2 className="mb-3 text-lg font-semibold">API Usage</h2>
          <div className="grid grid-cols-3 gap-4">
            <StatCard label="Input Tokens" value={usage.total_input_tokens} />
            <StatCard label="Output Tokens" value={usage.total_output_tokens} />
            <StatCard
              label="Cost"
              value={`$${(usage.total_cost_cents / 100).toFixed(2)}`}
            />
          </div>
        </div>
      )}

      {/* Re-draft confirmation modal */}
      {confirmRedraft && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setConfirmRedraft(null)}>
          <div className="mx-4 w-full max-w-sm rounded-lg border border-border bg-background p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-semibold">Create another draft?</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              This decision already has drafts. Creating a new one will call the LLM again and add another draft.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => setConfirmRedraft(null)}
                className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted"
              >
                Cancel
              </button>
              <button
                onClick={() => handleCreateDraft(confirmRedraft)}
                className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-foreground hover:bg-accent/80"
              >
                Create Draft
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete confirmation modal */}
      {confirmDelete && (() => {
        const ids = Array.from(selectedDecisions);
        const totalDrafts = decisions
          .filter((d) => ids.includes(d.id))
          .reduce((sum, d) => sum + d.draft_count, 0);
        return (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => !actionLoading && setConfirmDelete(false)}>
            <div className="mx-4 w-full max-w-sm rounded-lg border border-border bg-background p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
              <h3 className="text-sm font-semibold">Delete {ids.length === 1 ? "decision" : `${ids.length} decisions`}?</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                This will permanently delete {ids.length} decision{ids.length !== 1 ? "s" : ""}{totalDrafts > 0 ? ` and ${totalDrafts} associated draft${totalDrafts !== 1 ? "s" : ""}` : ""}.
              </p>
              {actionError && (
                <p className="mt-2 text-sm text-destructive">{actionError}</p>
              )}
              <div className="mt-4 flex justify-end gap-2">
                <button
                  onClick={() => setConfirmDelete(false)}
                  disabled={actionLoading}
                  className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  onClick={async () => {
                    setActionLoading(true);
                    setActionError(null);
                    try {
                      await Promise.all(ids.map((did) => deleteDecision(did)));
                      setDecisions((prev) => prev.filter((d) => !ids.includes(d.id)));
                      setSelectedDecisions(new Set());
                      setConfirmDelete(false);
                    } catch (err) {
                      setActionError(err instanceof Error ? err.message : "Delete failed");
                    } finally {
                      setActionLoading(false);
                    }
                  }}
                  disabled={actionLoading}
                  className="rounded-md bg-destructive px-3 py-1.5 text-sm font-medium text-destructive-foreground hover:bg-destructive/80 disabled:opacity-50"
                >
                  {actionLoading ? "Deleting..." : "Delete"}
                </button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* Re-evaluate confirmation modal */}
      {confirmRetrigger && (() => {
        const did = Array.from(selectedDecisions)[0];
        const dec = decisions.find((d) => d.id === did);
        return (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => !actionLoading && setConfirmRetrigger(false)}>
            <div className="mx-4 w-full max-w-sm rounded-lg border border-border bg-background p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
              <h3 className="text-sm font-semibold">Re-evaluate commit?</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                This will delete the current decision for commit <code className="text-xs">{dec?.commit_hash.slice(0, 7)}</code> and re-run the evaluator. The result may differ from the original evaluation.
              </p>
              {actionError && (
                <p className="mt-2 text-sm text-destructive">{actionError}</p>
              )}
              <div className="mt-4 flex justify-end gap-2">
                <button
                  onClick={() => setConfirmRetrigger(false)}
                  disabled={actionLoading}
                  className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  onClick={async () => {
                    setActionLoading(true);
                    setActionError(null);
                    try {
                      const res = await retriggerDecision(did);
                      if (res.status === "retriggered") {
                        setSelectedDecisions(new Set());
                        setConfirmRetrigger(false);
                        reload();
                      } else {
                        setActionError(`Re-evaluation failed (exit code ${res.exit_code})`);
                      }
                    } catch (err) {
                      setActionError(err instanceof Error ? err.message : "Retrigger failed");
                    } finally {
                      setActionLoading(false);
                    }
                  }}
                  disabled={actionLoading}
                  className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
                >
                  {actionLoading ? "Re-evaluating..." : "Re-evaluate"}
                </button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* Import history modal */}
      {importModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => !importLoading && setImportModalOpen(false)}>
          <div className="mx-4 w-full max-w-sm rounded-lg border border-border bg-background p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-semibold">Import Historical Commits</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              Import past commits as &ldquo;imported&rdquo; decisions so you can evaluate them later.
            </p>
            {importPreview ? (
              <div className="mt-3 space-y-1 rounded-md border border-border bg-muted/50 p-3 text-xs">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Total commits</span>
                  <span className="font-medium">{importPreview.total_commits}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Already tracked</span>
                  <span className="font-medium">{importPreview.already_tracked}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Importable</span>
                  <span className="font-medium text-accent">{importPreview.importable}</span>
                </div>
              </div>
            ) : (
              <p className="mt-3 text-xs text-muted-foreground">Loading preview...</p>
            )}
            <div className="mt-3">
              <label className="text-xs text-muted-foreground">Branch (optional)</label>
              <select
                className="mt-1 h-8 w-full rounded-md border border-border bg-background px-2 text-sm text-foreground"
                value={importBranch}
                onChange={async (e) => {
                  const branch = e.target.value;
                  setImportBranch(branch);
                  try {
                    const preview = await fetchImportPreview(id, branch || null);
                    setImportPreview(preview);
                  } catch { setImportPreview(null); }
                }}
              >
                <option value="">All branches</option>
                {decisionBranches.map((b) => (
                  <option key={b} value={b}>{b}</option>
                ))}
              </select>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => setImportModalOpen(false)}
                disabled={importLoading}
                className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={async () => {
                  setImportLoading(true);
                  try {
                    const res = await importCommits(id, importBranch || null);
                    trackTask(res.task_id, "__import__", "import_commits");
                  } catch {
                    setImportLoading(false);
                  }
                }}
                disabled={importLoading || isTaskRunning("__import__") || (importPreview != null && importPreview.importable === 0)}
                className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
              >
                {importLoading || isTaskRunning("__import__") ? "Importing..." : "Import"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Floating action bar */}
      {(selectedDecisions.size >= 1 || isTaskRunning(CONSOLIDATE_REF)) && (
        <div className="fixed bottom-0 left-0 right-0 z-40 border-t border-border bg-background p-3 shadow-lg">
          <div className="mx-auto flex max-w-5xl items-center justify-between">
            <span className="text-sm text-muted-foreground">
              {selectedDecisions.size} decision{selectedDecisions.size !== 1 ? "s" : ""} selected
            </span>
            <div className="flex items-center gap-3">
              {consolidateResult?.count != null && (
                <span className="text-xs text-green-600 dark:text-green-400">
                  {consolidateResult.count} draft{consolidateResult.count !== 1 ? "s" : ""} created
                </span>
              )}
              {consolidateResult?.error && (
                <span className="text-xs text-destructive">{consolidateResult.error}</span>
              )}
              <button
                onClick={() => setSelectedDecisions(new Set())}
                className="rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted"
              >
                Clear
              </button>
              {selectedDecisions.size === 1 && (
                <button
                  onClick={() => { setActionError(null); setConfirmRetrigger(true); }}
                  className="rounded-md border border-accent px-4 py-1.5 text-sm font-medium text-accent hover:bg-accent/10"
                >
                  Re-evaluate
                </button>
              )}
              <button
                onClick={() => { setActionError(null); setConfirmDelete(true); }}
                className="rounded-md border border-destructive/50 px-4 py-1.5 text-sm font-medium text-destructive hover:bg-destructive/10"
              >
                Delete {selectedDecisions.size === 1 ? "decision" : `${selectedDecisions.size} decisions`}
              </button>
              {selectedDecisions.size >= 2 && (
                <button
                  onClick={handleConsolidate}
                  disabled={isTaskRunning(CONSOLIDATE_REF)}
                  className="rounded-md bg-accent px-4 py-1.5 text-sm font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
                >
                  {isTaskRunning(CONSOLIDATE_REF)
                    ? "Consolidating..."
                    : `Consolidate ${selectedDecisions.size} → Create Draft`}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, secondary }: { label: string; value: number | string; secondary?: string }) {
  return (
    <div className="rounded-lg border border-border p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="text-2xl font-bold">{value}</p>
      {secondary && <p className="text-xs text-muted-foreground">{secondary}</p>}
    </div>
  );
}

function PlatformBadge({ platform }: { platform: string }) {
  const labels: Record<string, string> = {
    x: "X",
    linkedin: "LinkedIn",
  };
  return (
    <span className="inline-flex items-center rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
      {labels[platform] ?? platform}
    </span>
  );
}
