"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useToast } from "@/lib/toast-context";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  fetchProjectDetail,
  fetchProjectDecisions,
  fetchProjectPosts,
  fetchProjectUsage,
  createDraftFromDecision,
  createContent,
  deleteDecision,
  retriggerDecision,
  batchEvaluateDecisions,
  fetchEnabledPlatforms,
  consolidateDecisions,
  fetchMemories,
  fetchDecisionBranches,
  fetchImportPreview,
  importCommits,
  fetchTasks,
  fetchTopics,
  uploadProjectDocs,
  type BackgroundTask,
} from "@/lib/api";
import type { Decision, Memory, PostRecord, ProjectDetail, Topic, UsageSummary } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Modal } from "@/components/ui/modal";
import { ExpandableText } from "@/components/ui/expandable-text";
import { MemoriesSection } from "@/components/memories-section";
import { ArcsSection } from "@/components/arcs-section";
import { RateLimitCard } from "@/components/rate-limit-card";
import { AnalysisQueueCard } from "@/components/analysis-queue-card";
import { useDataEvents } from "@/lib/use-data-events";
import { useBackgroundTasks } from "@/lib/use-background-tasks";
import { EvaluationCycles } from "@/components/evaluation-cycles";
import { TopicQueue } from "@/components/topic-queue";
import { BriefEditor } from "@/components/brief-editor";
import { ContentSuggestions } from "@/components/content-suggestions";
import { AsyncButton } from "@/components/async-button";

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
  const [totalDecisions, setTotalDecisions] = useState(0);
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
  const { addToast } = useToast();
  const [branchFilter, setBranchFilter] = useState<string>("");
  const [sortKey, setSortKey] = useState<string>("created_at");
  const [sortDir, setSortDir] = useState<string>("desc");
  const [decisionFilter, setDecisionFilter] = useState<string>("");
  const [classificationFilter, setClassificationFilter] = useState<string>("");
  const [decisionBranches, setDecisionBranches] = useState<string[]>([]);
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [importPreview, setImportPreview] = useState<{ total_commits: number; already_tracked: number; importable: number; branches?: string[] } | null>(null);
  const [importBranch, setImportBranch] = useState<string>("");
  const [importLimit, setImportLimit] = useState<string>("");
  const [importLoading, setImportLoading] = useState(false);
  const [importRefreshKey, setImportRefreshKey] = useState(0);
  const [topicNameById, setTopicNameById] = useState<Record<string, string>>({});
  const [activeTab, setActiveTab] = useState<"cycles" | "commits" | "topics" | "brief">(() => {
    if (typeof window === "undefined") return "cycles";
    const validTabs = ["cycles", "commits", "topics", "brief"] as const;
    const param = new URLSearchParams(window.location.search).get("tab");
    if (param && (validTabs as readonly string[]).includes(param)) {
      return param as typeof validTabs[number];
    }
    return "cycles";
  });
  // Create content modal state
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [createIdea, setCreateIdea] = useState("");
  const [createVehicle, setCreateVehicle] = useState<string>("");
  const [createRefFiles, setCreateRefFiles] = useState<File[]>([]);
  const createRefInputRef = useRef<HTMLInputElement>(null);
  const CREATE_REF = "__create_content__";

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
      } else if (task.type === "create_content") {
        setCreateModalOpen(false);
        setCreateIdea("");
        setCreateVehicle("");
        setCreateRefFiles([]);
        reload();
      } else if (task.type === "import_commits") {
        setImportModalOpen(false);
        setImportLoading(false);
        setImportRefreshKey((k) => k + 1);
      } else if (task.type === "retrigger") {
        reload();
      } else if (task.type === "batch_evaluate") {
        reload();
      }
    } else if (task.status === "failed") {
      const error = task.error ?? "Task failed";
      if (task.type === "create_draft") {
        setDraftResult((prev) => ({ ...prev, [task.ref_id]: { error } }));
        addToast("Draft creation failed", { variant: "error", detail: error });
      } else if (task.type === "create_content") {
        addToast("Content creation failed", { variant: "error", detail: error });
      } else if (task.type === "consolidate") {
        setConsolidateResult({ error });
        addToast("Consolidation failed", { variant: "error", detail: error });
      } else if (task.type === "import_commits") {
        setImportLoading(false);
        addToast("Import failed", { variant: "error", detail: error });
      } else if (task.type === "retrigger") {
        addToast("Re-evaluation failed", { variant: "error", detail: error });
      } else if (task.type === "batch_evaluate") {
        addToast("Batch evaluation failed", { variant: "error", detail: error });
      }
    }
  }, []);

  const { trackTask, isRunning: isTaskRunning, getTask } = useBackgroundTasks(id, onTaskCompleted);

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
        fetchProjectDecisions(id, DECISIONS_PER_PAGE, decisionOffset, branchFilter || null, sortKey, sortDir, decisionFilter || null, classificationFilter || null),
        fetchProjectPosts(id, 20),
        fetchProjectUsage(id),
      ]);
      setProject(detail);
      setDecisions(dec.decisions);
      setHasMoreDecisions(dec.decisions.length === DECISIONS_PER_PAGE);
      setTotalDecisions(dec.total ?? 0);
      setPosts(po.posts);
      setUsage(us);
      loadMemories(detail.repo_path);
      fetchDecisionBranches(id).then(({ branches }) => setDecisionBranches(branches)).catch(() => {});
      fetchTopics(id).then(({ topics }) => {
        const lookup: Record<string, string> = {};
        for (const t of topics) lookup[t.id] = t.topic;
        setTopicNameById(lookup);
      }).catch(() => {});
    } catch {
      // Silent refresh failure
    }
  }, [id, decisionOffset, branchFilter, sortKey, sortDir, decisionFilter, classificationFilter, loadMemories]);

  useDataEvents(["decision", "draft", "post", "project", "arc", "task"], reload, id);

  useEffect(() => {
    async function load() {
      try {
        const [detail, dec, po, us, plat] = await Promise.all([
          fetchProjectDetail(id),
          fetchProjectDecisions(id, DECISIONS_PER_PAGE, 0, branchFilter || null, sortKey, sortDir, decisionFilter || null, classificationFilter || null),
          fetchProjectPosts(id, 20),
          fetchProjectUsage(id),
          fetchEnabledPlatforms(),
        ]);
        setProject(detail);
        setDecisions(dec.decisions);
        setHasMoreDecisions(dec.decisions.length === DECISIONS_PER_PAGE);
      setTotalDecisions(dec.total ?? 0);
        setPosts(po.posts);
        setUsage(us);
        setPlatformCount(plat.real_count);
        loadMemories(detail.repo_path);
        fetchDecisionBranches(id).then(({ branches }) => setDecisionBranches(branches)).catch(() => {});
        fetchTopics(id).then(({ topics }) => {
          const lookup: Record<string, string> = {};
          for (const t of topics) lookup[t.id] = t.topic;
          setTopicNameById(lookup);
        }).catch(() => {});
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load project");
      } finally {
        setLoading(false);
      }
    }
    load();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, branchFilter, sortKey, sortDir, decisionFilter, classificationFilter, importRefreshKey, loadMemories]);

  async function loadMoreDecisions(offset: number) {
    try {
      const res = await fetchProjectDecisions(id, DECISIONS_PER_PAGE, offset, branchFilter || null, sortKey, sortDir, decisionFilter || null, classificationFilter || null);
      setDecisions(res.decisions);
      setDecisionOffset(offset);
      setHasMoreDecisions(res.decisions.length === DECISIONS_PER_PAGE);
      setTotalDecisions(res.total ?? 0);
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
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">{project.name}</h1>
            {!!project.paused && <Badge value="paused" variant="status" />}
          </div>
          <AsyncButton
            loading={isTaskRunning(CREATE_REF)}
            startTime={getTask(CREATE_REF)?.created_at}
            loadingText="Creating"
            className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
            disabled={isTaskRunning(CREATE_REF)}
            onClick={() => setCreateModalOpen(true)}
          >
            Create Content
          </AsyncButton>
        </div>
        <p className="mt-1 truncate text-sm text-muted-foreground">{project.repo_path}</p>

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

        {/* Rate Limits + Analysis Queue + Journey Capture status */}
        <div className="mt-4 flex gap-4">
          <RateLimitCard />
          <AnalysisQueueCard projectId={id} />
        </div>
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

      {/* Content Suggestions */}
      <ContentSuggestions projectId={id} />

      {/* Tab bar */}
      <div className="border-b border-border">
        <div className="flex gap-0">
          {([
            { key: "cycles", label: "Evaluation Cycles" },
            { key: "commits", label: "Commit Log" },
            { key: "topics", label: "Topic Queue" },
            { key: "brief", label: "Brief" },
          ] as const).map((tab) => (
            <button
              key={tab.key}
              onClick={() => {
                setActiveTab(tab.key);
                window.history.replaceState({}, "", `?tab=${tab.key}`);
              }}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.key
                  ? "border-accent text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Evaluation Cycles tab */}
      {activeTab === "cycles" && (
        <EvaluationCycles projectId={id} />
      )}

      {/* Topic Queue tab */}
      {activeTab === "topics" && (
        <TopicQueue projectId={id} />
      )}

      {/* Brief tab */}
      {activeTab === "brief" && (
        <BriefEditor projectId={id} />
      )}

      {/* Commit Log tab (existing Evaluator Decisions) */}
      {activeTab === "commits" && <div>
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
          <select
            className="h-7 rounded-md border border-border bg-background px-2 text-xs text-foreground"
            value={decisionFilter}
            onChange={(e) => { setDecisionFilter(e.target.value); setDecisionOffset(0); }}
          >
            <option value="">All decisions</option>
            <option value="draft">draft</option>
            <option value="hold">hold</option>
            <option value="skip">skip</option>
            <option value="imported">imported</option>
            <option value="deferred_eval">deferred</option>
            <option value="processing">processing</option>
          </select>
          <select
            className="h-7 rounded-md border border-border bg-background px-2 text-xs text-foreground"
            value={classificationFilter}
            onChange={(e) => { setClassificationFilter(e.target.value); setDecisionOffset(0); }}
          >
            <option value="">All types</option>
            <option value="feature">feature</option>
            <option value="bugfix">bugfix</option>
            <option value="refactor">refactor</option>
            <option value="docs">docs</option>
            <option value="chore">chore</option>
            <option value="test">test</option>
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
                    <SortTh column="decision" label="Decision" sortKey={sortKey} sortDir={sortDir} onSort={(col) => { setSortKey(col); setSortDir(sortKey === col && sortDir === "asc" ? "desc" : "asc"); setDecisionOffset(0); }} />
                    <SortTh column="commit_hash" label="Commit" sortKey={sortKey} sortDir={sortDir} onSort={(col) => { setSortKey(col); setSortDir(sortKey === col && sortDir === "asc" ? "desc" : "asc"); setDecisionOffset(0); }} />
                    <th className="pb-2 pr-4 font-medium">Reasoning</th>
                    <th className="pb-2 pr-4 font-medium min-w-[120px]">Angle</th>
                    <th className="hidden pb-2 pr-4 font-medium sm:table-cell">Episode</th>
                    <th className="hidden pb-2 pr-4 font-medium md:table-cell">Category</th>
                    <SortTh column="created_at" label="Date" sortKey={sortKey} sortDir={sortDir} onSort={(col) => { setSortKey(col); setSortDir(sortKey === col && sortDir === "asc" ? "desc" : "asc"); setDecisionOffset(0); }} />
                    <SortTh column="branch" label="Branch" sortKey={sortKey} sortDir={sortDir} onSort={(col) => { setSortKey(col); setSortDir(sortKey === col && sortDir === "asc" ? "desc" : "asc"); setDecisionOffset(0); }} className="hidden lg:table-cell" />
                    <th className="pb-2 pr-4 font-medium">Drafts</th>
                    <th className="pb-2 pr-4 font-medium">Actions</th>
                    <th className="pb-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {(() => {
                    const rows: React.ReactNode[] = [];
                    const seenBatches2 = new Set<string>();
                    for (let i = 0; i < decisions.length; i++) {
                      const d = decisions[i];
                      if (d.batch_id && !seenBatches2.has(d.batch_id)) {
                        seenBatches2.add(d.batch_id);
                        const batchMembers = decisions.filter((dd) => dd.batch_id === d.batch_id);
                        const batchMemberIds = new Set(batchMembers.map((dd) => dd.id));
                        const allSelected = batchMembers.every((dd) => selectedDecisions.has(dd.id));
                        const someSelected = batchMembers.some((dd) => selectedDecisions.has(dd.id));
                        // Batch header row
                        rows.push(
                          <tr
                            key={`batch-${d.batch_id}`}
                            className="bg-indigo-50/50 dark:bg-indigo-950/20"
                          >
                            <td className="py-2 pr-2" onClick={(e) => e.stopPropagation()}>
                              <input
                                type="checkbox"
                                checked={allSelected}
                                ref={(el) => { if (el) el.indeterminate = someSelected && !allSelected; }}
                                onChange={() => {
                                  setSelectedDecisions((prev) => {
                                    const next = new Set(prev);
                                    if (allSelected) {
                                      batchMemberIds.forEach((bid) => next.delete(bid));
                                    } else {
                                      batchMemberIds.forEach((bid) => next.add(bid));
                                    }
                                    return next;
                                  });
                                }}
                                className="h-4 w-4 rounded border-border accent-accent"
                              />
                            </td>
                            <td colSpan={11} className="py-2 pr-4">
                              <div className="flex items-center gap-2">
                                <code className="rounded bg-indigo-100 px-1.5 py-0.5 text-[10px] font-medium text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-400">
                                  batch {d.batch_id.slice(0, 12)}
                                </code>
                                <span className="text-xs text-muted-foreground">
                                  {batchMembers.length} commit{batchMembers.length !== 1 ? "s" : ""}
                                </span>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    const ids = batchMembers.map((dd) => dd.id);
                                    setSelectedDecisions(new Set(ids));
                                    // Use consolidateDecisions directly
                                    consolidateDecisions(ids).then((res) => {
                                      trackTask(res.task_id, CONSOLIDATE_REF, "consolidate");
                                    }).catch(() => {});
                                  }}
                                  className="rounded border border-indigo-300 px-2 py-0.5 text-[10px] font-medium text-indigo-700 hover:bg-indigo-50 dark:border-indigo-700 dark:text-indigo-400 dark:hover:bg-indigo-950"
                                >
                                  Create Draft
                                </button>
                              </div>
                            </td>
                          </tr>,
                        );
                        // Render each batch member
                        for (const bd of batchMembers) {
                          rows.push(renderDecisionRow(bd));
                        }
                      } else if (!d.batch_id) {
                        rows.push(renderDecisionRow(d));
                      }
                      // Skip batch members that were already rendered in the group
                    }
                    return rows;

                    function renderDecisionRow(d: Decision) {
                    const isExpanded = expandedDecisions.has(d.id);
                    const isCreating = isTaskRunning(d.id);
                    const batchTask = getTask("batch-evaluate");
                    const isBatchRunning = batchTask?.status === "running";
                    const isProcessing = isTaskRunning(`retrigger-${d.id}`) || d.decision === "processing" || (isBatchRunning && !!d.batch_id);
                    const evalTask = getTask(`retrigger-${d.id}`);
                    const stageLabel = batchTask?.stage_label || evalTask?.stage_label;
                    const stageTime = batchTask?.stage_started_at || evalTask?.stage_started_at;
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
                          <div className="flex flex-wrap items-center gap-1">
                            <Badge value={d.decision === "deferred_eval" && d.batch_id ? "batched" : d.decision} variant="decision" />
                            {(() => {
                              const topicIds = new Set<string>();
                              if (d.targets && typeof d.targets === "object") {
                                for (const v of Object.values(d.targets)) {
                                  const tid = (v as Record<string, unknown>)?.topic_id;
                                  if (typeof tid === "string" && tid) topicIds.add(tid);
                                }
                              }
                              return Array.from(topicIds).map((tid) => (
                                <span
                                  key={tid}
                                  className="rounded-full bg-purple-100 px-2 py-0.5 text-[10px] font-medium text-purple-800 dark:bg-purple-900/30 dark:text-purple-400"
                                  title={tid}
                                >
                                  {topicNameById[tid] || tid.slice(0, 10)}
                                </span>
                              ));
                            })()}
                          </div>
                        </td>
                        <td className="py-2 pr-4">
                          <div>
                            <div className="flex items-center gap-1.5">
                              <code className="text-xs">{d.commit_hash.slice(0, 7)}</code>
                              {d.classification && (
                                <Badge value={d.classification} variant="classification" />
                              )}
                            </div>
                            <p className="text-xs text-muted-foreground">
                              {d.commit_message?.split("\n")[0]}
                            </p>
                            {isExpanded && (
                              <div className="mt-2 space-y-2">
                                {d.commit_message && (
                                  <div className="rounded border border-border bg-muted/50 p-2">
                                    <p className="text-xs font-medium text-muted-foreground">Commit Message</p>
                                    <p className="mt-1 whitespace-pre-wrap text-xs">{d.commit_message}</p>
                                  </div>
                                )}
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
                        <td className="py-2 pr-4 text-xs max-w-[300px]">
                          {d.decision === "deferred_eval" && d.batch_id ? (
                            <span className="text-muted-foreground">Included in batch <code className="rounded bg-muted px-1 py-0.5 text-xs">{d.batch_id.slice(0, 12)}</code></span>
                          ) : (
                            <ExpandableText text={d.decision === "processing" ? "" : d.reasoning} expanded={isExpanded} />
                          )}
                        </td>
                        <td className="py-2 pr-4 text-xs max-w-[200px]">
                          <ExpandableText text={d.angle} expanded={isExpanded} />
                        </td>
                        <td className="hidden py-2 pr-4 sm:table-cell">
                          {d.episode_type ? <Badge value={d.episode_type} variant="category" /> : <span className="text-xs">-</span>}
                        </td>
                        <td className="hidden py-2 pr-4 md:table-cell">
                          {d.post_category ? <Badge value={d.post_category} variant="category" /> : <span className="text-xs">-</span>}
                        </td>
                        <td className="py-2 pr-4 text-xs text-muted-foreground">
                          {new Date(d.created_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                        </td>
                        <td className="hidden py-2 pr-4 lg:table-cell">
                          {d.branch ? (
                            <code className="rounded bg-muted px-1.5 py-0.5 text-xs">{d.branch}</code>
                          ) : (
                            <span className="text-xs text-muted-foreground">&mdash;</span>
                          )}
                        </td>
                        <td className="py-2 pr-4" onClick={(e) => e.stopPropagation()}>
                          {d.draft_count > 0 ? (
                            <Link
                              href={`/drafts?from=${id}&name=${encodeURIComponent(project?.name ?? "")}&decision=${encodeURIComponent(d.id)}`}
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
                            {d.decision === "deferred_eval" && d.batch_id ? (
                              <span className="text-xs text-muted-foreground">Batched</span>
                            ) : (d.decision === "imported" || d.decision === "processing" || (d.decision === "deferred_eval" && !d.batch_id)) ? (
                              <AsyncButton
                                loading={isProcessing}
                                startTime={stageTime || evalTask?.created_at || batchTask?.created_at}
                                loadingText={stageLabel || "Processing"}
                                onClick={async () => {
                                  setActionError(null);
                                  try {
                                    const res = await retriggerDecision(d.id);
                                    if (res.task_id) {
                                      trackTask(res.task_id, `retrigger-${d.id}`, "retrigger");
                                    }
                                  } catch (err) {
                                    setActionError(err instanceof Error ? err.message : "Evaluate failed");
                                  }
                                }}
                                disabled={isProcessing}
                                className="inline-flex items-center gap-1.5 rounded-md border border-indigo-300 px-2 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-50 dark:border-indigo-700 dark:text-indigo-400 dark:hover:bg-indigo-950 disabled:opacity-70"
                              >
                                Evaluate
                              </AsyncButton>
                            ) : (
                              <AsyncButton
                                loading={isCreating}
                                startTime={getTask(d.id)?.created_at}
                                loadingText="Drafting"
                                onClick={() => onCreateDraftClick(d.id, d.draft_count > 0)}
                                disabled={isCreating}
                                className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium disabled:opacity-70 ${
                                  d.draft_count > 0 && !isCreating
                                    ? "border border-green-300 text-green-700 hover:bg-green-50 dark:border-green-700 dark:text-green-400 dark:hover:bg-green-950"
                                    : "bg-accent text-accent-foreground hover:bg-accent/80"
                                }`}
                              >
                                {d.draft_count > 0 ? "Draft Created" : "Create Draft"}
                              </AsyncButton>
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
                    }
                  })()}
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
                {totalDecisions > 0 && ` of ${Math.ceil(totalDecisions / DECISIONS_PER_PAGE)}`}
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
      </div>}

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
      <Modal open={!!confirmRedraft} onClose={() => setConfirmRedraft(null)} maxWidth="max-w-sm">
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
            onClick={() => confirmRedraft && handleCreateDraft(confirmRedraft)}
            className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-foreground hover:bg-accent/80"
          >
            Create Draft
          </button>
        </div>
      </Modal>

      {/* Delete confirmation modal */}
      {confirmDelete && (() => {
        const ids = Array.from(selectedDecisions);
        const totalDrafts = decisions
          .filter((d) => ids.includes(d.id))
          .reduce((sum, d) => sum + d.draft_count, 0);
        return (
          <Modal open={true} onClose={() => !actionLoading && setConfirmDelete(false)} maxWidth="max-w-sm">
            <h3 className="text-sm font-semibold">
              {decisions.filter((d) => ids.includes(d.id)).every((d) => d.decision === "imported")
                ? `Remove ${ids.length === 1 ? "import" : `${ids.length} imports`}?`
                : `Delete ${ids.length === 1 ? "decision" : `${ids.length} decisions`}?`}
            </h3>
            <p className="mt-2 text-sm text-muted-foreground">
              This will permanently remove {ids.length} record{ids.length !== 1 ? "s" : ""}{totalDrafts > 0 ? ` and ${totalDrafts} associated draft${totalDrafts !== 1 ? "s" : ""}` : ""}.
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
          </Modal>
        );
      })()}

      {/* Re-evaluate confirmation modal */}
      {confirmRetrigger && (() => {
        const did = Array.from(selectedDecisions)[0];
        const dec = decisions.find((d) => d.id === did);
        return (
          <Modal open={true} onClose={() => !actionLoading && setConfirmRetrigger(false)} maxWidth="max-w-sm">
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
                    if (res.task_id) {
                      trackTask(res.task_id, `retrigger-${did}`, "retrigger");
                    }
                    setSelectedDecisions(new Set());
                    setConfirmRetrigger(false);
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
          </Modal>
        );
      })()}

      {/* Create content modal */}
      <Modal open={createModalOpen} onClose={() => !isTaskRunning(CREATE_REF) && setCreateModalOpen(false)} maxWidth="max-w-sm">
        <h3 className="text-sm font-semibold">Create Content</h3>
        <p className="mt-2 text-sm text-muted-foreground">
          Draft content from an idea — bypasses the evaluator.
        </p>
        <div className="mt-3">
          <label className="text-xs text-muted-foreground">Idea *</label>
          <textarea
            className="mt-1 w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground"
            rows={3}
            placeholder="Describe what you want to post about..."
            value={createIdea}
            onChange={(e) => setCreateIdea(e.target.value)}
          />
        </div>
        <div className="mt-3">
          <label className="text-xs text-muted-foreground">Vehicle</label>
          <select
            className="mt-1 h-8 w-full rounded-md border border-border bg-background px-2 text-sm text-foreground"
            value={createVehicle}
            onChange={(e) => setCreateVehicle(e.target.value)}
          >
            <option value="">Auto</option>
            <option value="single">Single</option>
            <option value="thread">Thread</option>
            <option value="article">Article</option>
          </select>
        </div>
        <div className="mt-3">
          <label className="text-xs text-muted-foreground">Reference files (optional)</label>
          <div
            onClick={() => createRefInputRef.current?.click()}
            className="mt-1 cursor-pointer rounded-md border-2 border-dashed border-border p-3 text-center text-sm text-muted-foreground transition-colors hover:border-accent/50"
          >
            <input
              ref={createRefInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(e) => {
                const selected = Array.from(e.target.files || []);
                if (selected.length > 0) {
                  setCreateRefFiles((prev) => [...prev, ...selected]);
                }
                e.target.value = "";
              }}
            />
            Click to select files
          </div>
          {createRefFiles.length > 0 && (
            <div className="mt-2 space-y-1">
              {createRefFiles.map((f, i) => (
                <div key={i} className="flex items-center justify-between rounded border border-border px-2 py-1 text-xs">
                  <span className="truncate">{f.name}</span>
                  <button
                    onClick={() => setCreateRefFiles((prev) => prev.filter((_, j) => j !== i))}
                    className="ml-2 shrink-0 text-muted-foreground hover:text-destructive"
                  >
                    x
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={() => setCreateModalOpen(false)}
            disabled={isTaskRunning(CREATE_REF)}
            className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted disabled:opacity-50"
          >
            Cancel
          </button>
          <AsyncButton
            loading={isTaskRunning(CREATE_REF)}
            startTime={getTask(CREATE_REF)?.created_at}
            loadingText="Creating"
            className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
            disabled={!createIdea.trim() || isTaskRunning(CREATE_REF)}
            onClick={async () => {
              try {
                // Upload reference files first, then pass their names as paths
                let refFiles: string[] | undefined;
                if (createRefFiles.length > 0) {
                  await uploadProjectDocs(id, createRefFiles);
                  refFiles = createRefFiles.map((f) => f.name);
                }
                const res = await createContent(id, {
                  idea: createIdea.trim(),
                  vehicle: createVehicle || undefined,
                  reference_files: refFiles,
                });
                trackTask(res.task_id, CREATE_REF, "create_content");
              } catch (e) {
                setActionError(e instanceof Error ? e.message : "Create failed");
              }
            }}
          >
            Create
          </AsyncButton>
        </div>
      </Modal>

      {/* Import history modal */}
      <Modal open={importModalOpen} onClose={() => !importLoading && setImportModalOpen(false)} maxWidth="max-w-sm">
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
              const lim = importLimit ? parseInt(importLimit, 10) : null;
              try {
                const preview = await fetchImportPreview(id, branch || null, lim && lim > 0 ? lim : null);
                setImportPreview(preview);
              } catch { setImportPreview(null); }
            }}
          >
            <option value="">All branches</option>
            {(importPreview?.branches || []).map((b) => (
              <option key={b} value={b}>{b}</option>
            ))}
          </select>
        </div>
        <div className="mt-3">
          <label className="text-xs text-muted-foreground">Limit (optional)</label>
          <input
            type="number"
            min="1"
            placeholder="All commits"
            className="mt-1 h-8 w-full rounded-md border border-border bg-background px-2 text-sm text-foreground"
            value={importLimit}
            onChange={async (e) => {
              const val = e.target.value;
              setImportLimit(val);
              const lim = val ? parseInt(val, 10) : null;
              try {
                const preview = await fetchImportPreview(id, importBranch || null, lim && lim > 0 ? lim : null);
                setImportPreview(preview);
              } catch { setImportPreview(null); }
            }}
          />
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
                const lim = importLimit ? parseInt(importLimit, 10) : null;
                const res = await importCommits(id, importBranch || null, lim && lim > 0 ? lim : null);
                trackTask(res.task_id, "__import__", "import_commits");
                // Poll for completion since WebSocket callback can miss fast tasks
                const poll = setInterval(async () => {
                  try {
                    const { tasks: all } = await fetchTasks({ project_id: id });
                    const task = all.find((t) => t.id === res.task_id);
                    if (task && task.status !== "running") {
                      clearInterval(poll);
                      setImportModalOpen(false);
                      setImportLoading(false);
                      setImportRefreshKey((k) => k + 1);
                    }
                  } catch { /* keep polling */ }
                }, 2000);
                // Safety: stop polling after 5 minutes
                setTimeout(() => clearInterval(poll), 300_000);
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
      </Modal>

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
              {(() => {
                const selectedList = decisions.filter((d) => selectedDecisions.has(d.id));
                const allEvaluable = selectedList.length > 0 && selectedList.every((d) => d.decision === "imported" || (d.decision === "deferred_eval" && !d.batch_id));
                const allEvaluated = selectedList.length > 0 && selectedList.every((d) => d.decision !== "imported" && !(d.decision === "deferred_eval" && !d.batch_id));
                const isMixed = !allEvaluable && !allEvaluated;
                const batchEvalLoading = isTaskRunning("batch-evaluate");
                return (
                  <>
                    <button
                      onClick={() => setSelectedDecisions(new Set())}
                      className="rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted"
                    >
                      Clear
                    </button>
                    {selectedDecisions.size === 1 && allEvaluated && (
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
                      {allEvaluable
                        ? `Remove ${selectedDecisions.size === 1 ? "import" : `${selectedDecisions.size} imports`}`
                        : `Delete ${selectedDecisions.size === 1 ? "decision" : `${selectedDecisions.size} decisions`}`}
                    </button>
                    {allEvaluable && selectedDecisions.size >= 1 && (
                      <AsyncButton
                        loading={batchEvalLoading}
                        startTime={getTask("batch-evaluate")?.created_at}
                        loadingText="Evaluating"
                        onClick={async () => {
                          setActionError(null);
                          try {
                            const res = await batchEvaluateDecisions(Array.from(selectedDecisions));
                            trackTask(res.task_id, "batch-evaluate", "batch_evaluate");
                            setSelectedDecisions(new Set());
                          } catch (err) {
                            setActionError(err instanceof Error ? err.message : "Evaluate failed");
                          }
                        }}
                        disabled={batchEvalLoading}
                        className="rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                      >
                        {`Evaluate (${selectedDecisions.size})`}
                      </AsyncButton>
                    )}
                    {allEvaluated && selectedDecisions.size >= 2 && (
                      <button
                        onClick={handleConsolidate}
                        disabled={isTaskRunning(CONSOLIDATE_REF) || isMixed}
                        className="rounded-md bg-accent px-4 py-1.5 text-sm font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
                      >
                        {isTaskRunning(CONSOLIDATE_REF)
                          ? "Consolidating..."
                          : `Consolidate ${selectedDecisions.size} → Create Draft`}
                      </button>
                    )}
                    {isMixed && selectedDecisions.size >= 2 && (
                      <span className="text-xs text-muted-foreground">Mixed selection — select only evaluable or only evaluated decisions</span>
                    )}
                  </>
                );
              })()}
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

function SortTh({ column, label, sortKey, sortDir, onSort, className = "" }: {
  column: string;
  label: string;
  sortKey: string;
  sortDir: string;
  onSort: (column: string) => void;
  className?: string;
}) {
  const isActive = sortKey === column;
  return (
    <th
      className={`pb-2 pr-4 font-medium cursor-pointer select-none hover:text-foreground ${className}`}
      onClick={() => onSort(column)}
    >
      {label}
      {isActive && (
        <span className="ml-1">{sortDir === "asc" ? "\u25B2" : "\u25BC"}</span>
      )}
    </th>
  );
}
