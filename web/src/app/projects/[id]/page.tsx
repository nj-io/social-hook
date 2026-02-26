"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  fetchProjectDetail,
  fetchProjectDecisions,
  fetchProjectPosts,
  fetchProjectUsage,
} from "@/lib/api";
import type { Decision, PostRecord, ProjectDetail, UsageSummary } from "@/lib/types";
import { StatusBadge } from "@/components/status-badge";
import { DecisionBadge } from "@/components/decision-badge";

const DECISIONS_PER_PAGE = 10;

export default function ProjectDetailPage() {
  const params = useParams();
  const id = params.id as string;

  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [posts, setPosts] = useState<PostRecord[]>([]);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [decisionOffset, setDecisionOffset] = useState(0);
  const [hasMoreDecisions, setHasMoreDecisions] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const [detail, dec, po, us] = await Promise.all([
          fetchProjectDetail(id),
          fetchProjectDecisions(id, DECISIONS_PER_PAGE, 0),
          fetchProjectPosts(id, 20),
          fetchProjectUsage(id),
        ]);
        setProject(detail);
        setDecisions(dec.decisions);
        setHasMoreDecisions(dec.decisions.length === DECISIONS_PER_PAGE);
        setPosts(po.posts);
        setUsage(us);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load project");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id]);

  async function loadMoreDecisions(offset: number) {
    try {
      const res = await fetchProjectDecisions(id, DECISIONS_PER_PAGE, offset);
      setDecisions(res.decisions);
      setDecisionOffset(offset);
      setHasMoreDecisions(res.decisions.length === DECISIONS_PER_PAGE);
    } catch {
      // Keep existing data
    }
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
        {project.summary && (
          <p className="mt-2 text-sm">{project.summary}</p>
        )}

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
          <StatCard label="Decisions" value={Object.values(project.decision_counts || {}).reduce((a, b) => a + b, 0)} />
          <StatCard label="Drafts" value={project.draft_count ?? 0} />
          <StatCard label="Published" value={project.post_count ?? 0} />
          <StatCard
            label="Narrative Debt"
            value={project.narrative_debt?.debt_counter ?? 0}
          />
        </div>
      </div>

      {/* Evaluator Decisions */}
      <div>
        <h2 className="mb-3 text-lg font-semibold">Evaluator Decisions</h2>
        {decisions.length === 0 ? (
          <p className="text-sm text-muted-foreground">No decisions yet.</p>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-border text-xs text-muted-foreground">
                    <th className="pb-2 pr-4 font-medium">Decision</th>
                    <th className="pb-2 pr-4 font-medium">Commit</th>
                    <th className="pb-2 pr-4 font-medium">Angle</th>
                    <th className="hidden pb-2 pr-4 font-medium sm:table-cell">Episode</th>
                    <th className="hidden pb-2 pr-4 font-medium md:table-cell">Category</th>
                    <th className="pb-2 font-medium">Date</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {decisions.map((d) => (
                    <tr key={d.id}>
                      <td className="py-2 pr-4">
                        <DecisionBadge decision={d.decision} />
                      </td>
                      <td className="py-2 pr-4">
                        <div>
                          <code className="text-xs">{d.commit_hash.slice(0, 7)}</code>
                          <p className="truncate text-xs text-muted-foreground" style={{ maxWidth: "200px" }}>
                            {d.commit_message}
                          </p>
                        </div>
                      </td>
                      <td className="py-2 pr-4 text-xs">{d.angle || "-"}</td>
                      <td className="hidden py-2 pr-4 text-xs sm:table-cell">{d.episode_type || "-"}</td>
                      <td className="hidden py-2 pr-4 text-xs md:table-cell">{d.post_category || "-"}</td>
                      <td className="py-2 text-xs text-muted-foreground">
                        {new Date(d.created_at).toLocaleDateString()}
                      </td>
                    </tr>
                  ))}
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
      {project.arcs.length > 0 && (
        <div>
          <h2 className="mb-3 text-lg font-semibold">Narrative Arcs</h2>
          <div className="space-y-2">
            {project.arcs.map((arc) => (
              <div key={arc.id} className="flex items-center justify-between rounded-lg border border-border p-3">
                <div>
                  <span className="text-sm font-medium">{arc.theme}</span>
                  <span className="ml-2 text-xs text-muted-foreground">{arc.post_count} posts</span>
                </div>
                <ArcStatusBadge status={arc.status} />
              </div>
            ))}
          </div>
        </div>
      )}

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
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-lg border border-border p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="text-2xl font-bold">{value}</p>
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
