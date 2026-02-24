"use client";

import { useCallback, useEffect, useState } from "react";
import type { Project } from "@/lib/types";
import { fetchProjects, toggleProjectPause } from "@/lib/api";

export function ProjectsSection() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState<string | null>(null);

  const loadProjects = useCallback(async () => {
    try {
      const res = await fetchProjects();
      setProjects(res.projects);
    } catch {
      // Silently handle - empty list shown
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  async function handleTogglePause(projectId: string) {
    setToggling(projectId);
    try {
      const res = await toggleProjectPause(projectId);
      setProjects((prev) =>
        prev.map((p) => (p.id === projectId ? { ...p, paused: res.paused } : p)),
      );
    } catch {
      // Silently handle
    } finally {
      setToggling(null);
    }
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Projects</h2>
      <p className="text-sm text-muted-foreground">
        Registered projects that feed the content pipeline. Pause a project to temporarily stop processing its commits.
      </p>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading projects...</p>
      ) : projects.length === 0 ? (
        <div className="rounded-lg border-2 border-dashed border-border p-6 text-center">
          <p className="text-sm text-muted-foreground">No projects registered yet.</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Use the CLI to register your first project.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {projects.map((project) => {
            const isPaused = project.paused === 1;
            return (
              <div
                key={project.id}
                className="flex items-center justify-between rounded-lg border border-border p-4"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{project.name}</span>
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        isPaused
                          ? "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400"
                          : "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400"
                      }`}
                    >
                      {isPaused ? "Paused" : "Active"}
                    </span>
                  </div>
                  <p className="mt-0.5 truncate text-xs text-muted-foreground">
                    {project.repo_path}
                  </p>
                </div>
                <button
                  onClick={() => handleTogglePause(project.id)}
                  disabled={toggling === project.id}
                  className="ml-4 shrink-0 rounded-md border border-border px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted disabled:opacity-50"
                >
                  {toggling === project.id ? "..." : isPaused ? "Resume" : "Pause"}
                </button>
              </div>
            );
          })}
        </div>
      )}

      {/* CLI hint */}
      <div className="rounded-md bg-muted/50 p-3">
        <p className="text-xs text-muted-foreground">
          To register or unregister projects, use the CLI:
        </p>
        <pre className="mt-1 text-xs text-muted-foreground">
{`  social-hook project register /path/to/repo
  social-hook project unregister <project-id>
  social-hook project list`}
        </pre>
      </div>
    </div>
  );
}
