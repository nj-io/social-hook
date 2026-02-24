"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchDrafts, fetchProjects } from "@/lib/api";
import type { Draft, Project } from "@/lib/types";
import { StatusBadge } from "@/components/status-badge";

export default function DashboardPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

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

      {/* Summary stats */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Total Drafts" value={drafts.length} />
        <StatCard label="Pending Review" value={statusCounts["draft"] ?? 0} />
        <StatCard label="Scheduled" value={statusCounts["scheduled"] ?? 0} />
        <StatCard label="Posted" value={statusCounts["posted"] ?? 0} />
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
                <div
                  key={project.id}
                  className="rounded-lg border border-border p-4"
                >
                  <h3 className="font-medium">{project.name}</h3>
                  <p className="mb-2 truncate text-xs text-muted-foreground">{project.repo_path}</p>
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
                </div>
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
