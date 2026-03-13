"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { fetchDrafts, fetchEnabledPlatforms, fetchProjects } from "@/lib/api";
import type { Draft, Project } from "@/lib/types";
import { RateLimitCard } from "@/components/rate-limit-card";
import { StatusBadge } from "@/components/status-badge";
import { useDataEvents } from "@/lib/use-data-events";

export default function DashboardPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [platformCount, setPlatformCount] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    try {
      const [p, d] = await Promise.all([fetchProjects(), fetchDrafts()]);
      setProjects(p.projects);
      setDrafts(d.drafts);
    } catch {
      // Silent refresh failure
    }
  }, []);

  // Fetch platform count separately (not on reload — only on mount)
  useEffect(() => {
    fetchEnabledPlatforms()
      .then((res) => setPlatformCount(res.real_count))
      .catch(() => setPlatformCount(null));
  }, []);

  useDataEvents(["decision", "draft", "post", "project"], reload);

  useEffect(() => {
    async function load() {
      try {
        const [p, d] = await Promise.all([fetchProjects(), fetchDrafts()]);
        setProjects(p.projects);
        setDrafts(d.drafts);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load data");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return <p className="text-center text-muted-foreground">Loading...</p>;
  }

  if (error) {
    return (
      <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
        {error}
      </div>
    );
  }

  const statusCounts = drafts.reduce<Record<string, number>>((acc, d) => {
    acc[d.status] = (acc[d.status] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="text-muted-foreground">Overview of your social media content pipeline.</p>
      </div>

      {platformCount === 0 && (
        <div className="rounded-lg border border-yellow-300 bg-yellow-50 p-4 text-sm text-yellow-800 dark:border-yellow-700 dark:bg-yellow-900/20 dark:text-yellow-300">
          No platforms are enabled — drafts won&apos;t be generated from commits.
          Enable a platform in{" "}
          <Link href="/settings?section=platforms" className="font-medium underline hover:no-underline">
            Settings &rarr; Platforms
          </Link>
          , or add a Preview platform to test draft generation.
        </div>
      )}

      {/* Summary stats */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
        <StatCard label="Total Drafts" value={drafts.length} />
        <StatCard label="Pending Review" value={statusCounts["draft"] ?? 0} />
        <StatCard label="Scheduled" value={statusCounts["scheduled"] ?? 0} />
        <StatCard label="Posted" value={statusCounts["posted"] ?? 0} />
        <RateLimitCard />
      </div>

      {/* Projects */}
      <div>
        <h2 className="mb-3 text-lg font-semibold">Projects</h2>
        {projects.length === 0 ? (
          <p className="text-sm text-muted-foreground">No projects registered yet. Push a commit to a tracked project to get started.</p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {projects.map((project) => {
              const projectDrafts = drafts.filter((d) => d.project_id === project.id);
              const projectStatusCounts = projectDrafts.reduce<Record<string, number>>((acc, d) => {
                acc[d.status] = (acc[d.status] || 0) + 1;
                return acc;
              }, {});

              return (
                <Link
                  key={project.id}
                  href={`/projects/${project.id}`}
                  className="block rounded-lg border border-border p-4 transition-colors hover:bg-muted"
                >
                  <div className="flex items-center gap-2">
                    <h3 className="font-medium">{project.name}</h3>
                    {project.phase && <LifecycleBadge phase={project.phase} />}
                  </div>
                  <p className="mb-1 truncate text-xs text-muted-foreground">{project.repo_path}</p>
                  {project.summary && (
                    <p className="mb-2 text-xs text-muted-foreground">
                      {project.summary.length > 100 ? project.summary.slice(0, 100) + "..." : project.summary}
                    </p>
                  )}
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(projectStatusCounts).map(([status, count]) => (
                      <div key={status} className="flex items-center gap-1">
                        <StatusBadge status={status} />
                        <span className="text-xs text-muted-foreground">{count}</span>
                      </div>
                    ))}
                    {projectDrafts.length === 0 && (
                      <span className="text-xs text-muted-foreground">No drafts</span>
                    )}
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </div>

      {/* Recent drafts */}
      <div>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Recent Drafts</h2>
          <Link href="/drafts" className="text-sm text-accent hover:underline">
            View all
          </Link>
        </div>
        {drafts.length === 0 ? (
          <p className="text-sm text-muted-foreground">No drafts yet.</p>
        ) : (
          <div className="space-y-2">
            {drafts.slice(0, 5).map((draft) => (
              <Link
                key={draft.id}
                href={`/drafts/${draft.id}`}
                className="block rounded-lg border border-border p-3 transition-colors hover:bg-muted"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-muted-foreground">{draft.platform}</span>
                    <StatusBadge status={draft.status} />
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {new Date(draft.created_at).toLocaleDateString()}
                  </span>
                </div>
                <p className="mt-1 truncate text-sm">{draft.content}</p>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-border p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="text-2xl font-bold">{value}</p>
    </div>
  );
}

const phaseStyles: Record<string, string> = {
  research: "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400",
  build: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400",
  demo: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
  launch: "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400",
  post_launch: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
};

function LifecycleBadge({ phase }: { phase: string }) {
  const style = phaseStyles[phase] ?? "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300";
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${style}`}>
      {phase}
    </span>
  );
}
