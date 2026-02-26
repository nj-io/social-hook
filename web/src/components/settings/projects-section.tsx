"use client";

import { useCallback, useEffect, useState } from "react";
import type { Project } from "@/lib/types";
import { fetchInstallationsStatus, fetchProjects, installComponent, toggleProjectPause } from "@/lib/api";

export function ProjectsSection() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState<string | null>(null);
  const [hookInstalled, setHookInstalled] = useState<boolean | null>(null);
  const [installing, setInstalling] = useState(false);

  const loadProjects = useCallback(async () => {
    try {
      const [res, status] = await Promise.all([
        fetchProjects(),
        fetchInstallationsStatus(),
      ]);
      setProjects(res.projects);
      setHookInstalled(status.commit_hook);
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

  async function handleInstallHook() {
    setInstalling(true);
    try {
      await installComponent("commit_hook");
      setHookInstalled(true);
    } catch {
      // Silently handle
    } finally {
      setInstalling(false);
    }
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Projects</h2>
      <p className="text-sm text-muted-foreground">
        Registered projects that feed the content pipeline. Pause a project to temporarily stop processing its commits.
      </p>

      {/* Hook status banner */}
      {hookInstalled === false && (
        <div className="flex items-center justify-between rounded-lg border border-yellow-300 bg-yellow-50 p-3 dark:border-yellow-700 dark:bg-yellow-900/20">
          <p className="text-sm text-yellow-800 dark:text-yellow-300">
            Commit hook not installed — commits won&apos;t trigger evaluations.
          </p>
          <button
            onClick={handleInstallHook}
            disabled={installing}
            className="ml-4 shrink-0 rounded-md bg-yellow-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-yellow-700 disabled:opacity-50"
          >
            {installing ? "Installing..." : "Install"}
          </button>
        </div>
      )}
      {hookInstalled === true && (
        <p className="text-xs text-green-600 dark:text-green-400">Commit hook active</p>
      )}

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
                    {isPaused ? (
                      <span className="rounded-full bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400">
                        Paused
                      </span>
                    ) : hookInstalled === false ? (
                      <span className="rounded-full bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400">
                        Active (no hook)
                      </span>
                    ) : (
                      <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-900/30 dark:text-green-400">
                        Active
                      </span>
                    )}
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
{`  ${process.env.NEXT_PUBLIC_PROJECT_SLUG || "social-hook"} project register /path/to/repo
  ${process.env.NEXT_PUBLIC_PROJECT_SLUG || "social-hook"} project unregister <project-id>
  ${process.env.NEXT_PUBLIC_PROJECT_SLUG || "social-hook"} project list`}
        </pre>
      </div>
    </div>
  );
}
