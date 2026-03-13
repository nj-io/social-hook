"use client";

import { useCallback, useEffect, useState } from "react";
import type { Project } from "@/lib/types";
import {
  deleteProject,
  fetchInstallationsStatus,
  fetchProjectBranches,
  fetchProjects,
  installComponent,
  installGitHook,
  registerProject,
  toggleProjectPause,
  uninstallComponent,
  uninstallGitHook,
  updateProjectTriggerBranch,
} from "@/lib/api";
import { Modal } from "@/components/ui/modal";
import { FolderPickerModal } from "./folder-picker-modal";

export function ProjectsSection() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState<string | null>(null);
  const [claudeHookInstalled, setClaudeHookInstalled] = useState<boolean | null>(null);
  const [claudeHookAction, setClaudeHookAction] = useState(false);
  const [branchesMap, setBranchesMap] = useState<Record<string, { branches: string[]; current: string | null; loaded: boolean }>>({});
  const [branchLoading, setBranchLoading] = useState<string | null>(null);

  // Add project form
  const [folderPickerOpen, setFolderPickerOpen] = useState(false);
  const [selectedPath, setSelectedPath] = useState("");
  const [projectName, setProjectName] = useState("");
  const [installHook, setInstallHook] = useState(true);
  const [registering, setRegistering] = useState(false);
  const [registerError, setRegisterError] = useState("");

  // Per-project hook toggling
  const [hookToggling, setHookToggling] = useState<Record<string, boolean>>({});

  // Delete confirmation
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const loadProjects = useCallback(async () => {
    try {
      const [res, status] = await Promise.all([
        fetchProjects(),
        fetchInstallationsStatus(),
      ]);
      setProjects(res.projects);
      setClaudeHookInstalled(status.commit_hook);
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

  async function loadBranches(projectId: string, repoPath: string) {
    if (branchesMap[projectId]?.loaded) return;
    setBranchLoading(projectId);
    try {
      const res = await fetchProjectBranches(projectId);
      setBranchesMap((prev) => ({
        ...prev,
        [projectId]: { branches: res.branches, current: res.current, loaded: true },
      }));
    } catch {
      setBranchesMap((prev) => ({
        ...prev,
        [projectId]: { branches: [], current: null, loaded: true },
      }));
    } finally {
      setBranchLoading(null);
    }
  }

  async function handleBranchChange(projectId: string, value: string) {
    const branch = value === "" ? null : value;
    try {
      const res = await updateProjectTriggerBranch(projectId, branch);
      setProjects((prev) =>
        prev.map((p) =>
          p.id === projectId ? { ...p, trigger_branch: res.trigger_branch } : p,
        ),
      );
    } catch {
      // Silently handle
    }
  }

  async function handleClaudeHookAction(action: "install" | "uninstall") {
    setClaudeHookAction(true);
    try {
      if (action === "install") {
        await installComponent("commit_hook");
        setClaudeHookInstalled(true);
      } else {
        await uninstallComponent("commit_hook");
        setClaudeHookInstalled(false);
      }
    } catch {
      // Silently handle
    } finally {
      setClaudeHookAction(false);
    }
  }

  async function handleRegister() {
    if (!selectedPath) return;
    setRegistering(true);
    setRegisterError("");
    try {
      await registerProject(selectedPath, projectName || undefined, installHook);
      setSelectedPath("");
      setProjectName("");
      setInstallHook(true);
      await loadProjects();
    } catch (e) {
      setRegisterError(e instanceof Error ? e.message : "Registration failed");
    } finally {
      setRegistering(false);
    }
  }

  async function handleToggleGitHook(projectId: string, currentlyInstalled: boolean) {
    setHookToggling((prev) => ({ ...prev, [projectId]: true }));
    try {
      if (currentlyInstalled) {
        await uninstallGitHook(projectId);
      } else {
        await installGitHook(projectId);
      }
      setProjects((prev) =>
        prev.map((p) =>
          p.id === projectId ? { ...p, git_hook_installed: !currentlyInstalled } : p,
        ),
      );
    } catch {
      // Silently handle
    } finally {
      setHookToggling((prev) => ({ ...prev, [projectId]: false }));
    }
  }

  async function handleDelete(projectId: string) {
    setDeleting(true);
    try {
      await deleteProject(projectId);
      setProjects((prev) => prev.filter((p) => p.id !== projectId));
      setConfirmDelete(null);
    } catch {
      // Silently handle
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Projects</h2>
      <p className="text-sm text-muted-foreground">
        Registered projects that feed the content pipeline. Pause a project to temporarily stop processing its commits.
      </p>

      {/* Commit Detection card */}
      <div className="rounded-lg border border-border p-4">
        <h3 className="text-sm font-semibold">Commit Detection</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          Choose one method. Only one can be active at a time to avoid duplicate evaluations.
        </p>
        {(() => {
          const anyGitHook = projects.some((p) => p.git_hook_installed);
          return (
            <div className="mt-3 space-y-2">
              {/* Git hook info */}
              <div className={`flex items-center justify-between rounded-md px-3 py-2 ${claudeHookInstalled ? "bg-muted/30 opacity-60" : "bg-muted/50"}`}>
                <div>
                  <span className="text-sm font-medium">Git Hook</span>
                  <span className="ml-2 rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-900/30 dark:text-green-400">
                    recommended
                  </span>
                  {anyGitHook && (
                    <span className="ml-2 rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-900/30 dark:text-green-400">
                      Active
                    </span>
                  )}
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {claudeHookInstalled
                      ? "Uninstall Claude Code hook first to use git hooks."
                      : "Per-project post-commit hook. Install individually below."}
                  </p>
                </div>
              </div>
              {/* Claude Code hook */}
              <div className={`flex items-center justify-between rounded-md px-3 py-2 ${anyGitHook ? "bg-muted/30 opacity-60" : "bg-muted/50"}`}>
                <div>
                  <span className="text-sm font-medium">Claude Code Hook</span>
                  {claudeHookInstalled === true && (
                    <span className="ml-2 rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-900/30 dark:text-green-400">
                      Installed
                    </span>
                  )}
                  {claudeHookInstalled === false && !anyGitHook && (
                    <span className="ml-2 rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800 dark:bg-red-900/30 dark:text-red-400">
                      Not installed
                    </span>
                  )}
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {anyGitHook
                      ? "Uninstall git hooks first to use Claude Code hook."
                      : "Global PostToolUse hook via Claude Code settings."}
                  </p>
                </div>
                {claudeHookInstalled !== null && (
                  <button
                    onClick={() => handleClaudeHookAction(claudeHookInstalled ? "uninstall" : "install")}
                    disabled={claudeHookAction || (anyGitHook && !claudeHookInstalled)}
                    className="ml-4 shrink-0 rounded-md border border-border px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted disabled:opacity-50"
                  >
                    {claudeHookAction ? "..." : claudeHookInstalled ? "Uninstall" : "Install"}
                  </button>
                )}
              </div>
            </div>
          );
        })()}
      </div>

      {/* Add Project form */}
      <div className="rounded-lg border border-border p-4">
        <h3 className="text-sm font-semibold">Add Project</h3>
        <div className="mt-3 space-y-3">
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={selectedPath}
              onChange={(e) => setSelectedPath(e.target.value)}
              placeholder="Repository path"
              className="min-w-0 flex-1 rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
            />
            <button
              onClick={() => setFolderPickerOpen(true)}
              className="shrink-0 rounded-md border border-border px-3 py-2 text-sm font-medium transition-colors hover:bg-muted"
            >
              Browse
            </button>
          </div>
          <input
            type="text"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            placeholder="Project name (optional, defaults to folder name)"
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
          />
          <label className={`flex items-center gap-2 text-sm ${claudeHookInstalled ? "opacity-50" : ""}`}>
            <input
              type="checkbox"
              checked={installHook && !claudeHookInstalled}
              onChange={(e) => setInstallHook(e.target.checked)}
              disabled={claudeHookInstalled === true}
              className="rounded border-border"
            />
            Install git hook
            {claudeHookInstalled && (
              <span className="text-xs text-muted-foreground">(Claude Code hook active)</span>
            )}
          </label>
          {registerError && <p className="text-xs text-destructive">{registerError}</p>}
          <button
            onClick={handleRegister}
            disabled={!selectedPath || registering}
            className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-foreground transition-colors hover:bg-accent/80 disabled:opacity-50"
          >
            {registering ? "Adding..." : "Add Project"}
          </button>
        </div>
      </div>

      <FolderPickerModal
        open={folderPickerOpen}
        onClose={() => setFolderPickerOpen(false)}
        onSelect={(path) => setSelectedPath(path)}
      />

      {/* Project list */}
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading projects...</p>
      ) : projects.length === 0 ? (
        <div className="rounded-lg border-2 border-dashed border-border p-6 text-center">
          <p className="text-sm text-muted-foreground">No projects registered yet.</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Use the form above or the CLI to register your first project.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {projects.map((project) => {
            const isPaused = !!project.paused;
            const gitHookInstalled = project.git_hook_installed === true;
            return (
              <div
                key={project.id}
                className="rounded-lg border border-border p-4"
              >
                <div className="flex items-center justify-between">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{project.name}</span>
                      {isPaused ? (
                        <span className="rounded-full bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400">
                          Paused
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
                  <div className="ml-4 flex items-center gap-2">
                    <button
                      onClick={() => handleTogglePause(project.id)}
                      disabled={toggling === project.id}
                      className="shrink-0 rounded-md border border-border px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted disabled:opacity-50"
                    >
                      {toggling === project.id ? "..." : isPaused ? "Resume" : "Pause"}
                    </button>
                    <button
                      onClick={() => setConfirmDelete(project.id)}
                      className="shrink-0 rounded-md border border-red-300 px-3 py-1.5 text-sm font-medium text-red-600 transition-colors hover:bg-red-50 dark:border-red-700 dark:text-red-400 dark:hover:bg-red-900/20"
                    >
                      Remove
                    </button>
                  </div>
                </div>

                {/* Branch selector + git hook status */}
                <div className="mt-2 flex items-center gap-3">
                  <select
                    className="h-7 rounded-md border border-border bg-background px-2 text-xs text-foreground"
                    value={project.trigger_branch || ""}
                    onFocus={() => loadBranches(project.id, project.repo_path)}
                    onChange={(e) => handleBranchChange(project.id, e.target.value)}
                  >
                    <option value="">All branches</option>
                    {(() => {
                      const data = branchesMap[project.id];
                      const options: string[] = data?.branches || [];
                      const hasCurrent = project.trigger_branch && options.includes(project.trigger_branch);
                      return (
                        <>
                          {!hasCurrent && project.trigger_branch && (
                            <option value={project.trigger_branch}>
                              {project.trigger_branch} (not found)
                            </option>
                          )}
                          {options.map((b) => (
                            <option key={b} value={b}>{b}</option>
                          ))}
                        </>
                      );
                    })()}
                  </select>
                  {branchLoading === project.id && (
                    <span className="text-xs text-muted-foreground">Loading...</span>
                  )}
                  {project.trigger_branch && (
                    <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-800 dark:bg-blue-900/30 dark:text-blue-400">
                      {project.trigger_branch} only
                    </span>
                  )}

                  <div className="ml-auto flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">
                      Git hook: {gitHookInstalled ? "installed" : "not installed"}
                    </span>
                    <button
                      onClick={() => handleToggleGitHook(project.id, gitHookInstalled)}
                      disabled={hookToggling[project.id] || (claudeHookInstalled === true && !gitHookInstalled)}
                      title={claudeHookInstalled === true && !gitHookInstalled ? "Uninstall Claude Code hook first" : undefined}
                      className="rounded-md border border-border px-2 py-1 text-xs font-medium transition-colors hover:bg-muted disabled:opacity-50"
                    >
                      {hookToggling[project.id] ? "..." : gitHookInstalled ? "Uninstall" : "Install"}
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Delete confirmation dialog */}
      <Modal open={!!confirmDelete} onClose={() => setConfirmDelete(null)} maxWidth="max-w-sm">
        <h3 className="text-lg font-semibold">Remove Project</h3>
        <p className="mt-2 text-sm text-muted-foreground">
          This will unregister the project, remove the git hook, and delete all associated data (decisions, drafts, posts). This cannot be undone.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={() => setConfirmDelete(null)}
            className="rounded-md border border-border px-4 py-2 text-sm font-medium transition-colors hover:bg-muted"
          >
            Cancel
          </button>
          <button
            onClick={() => confirmDelete && handleDelete(confirmDelete)}
            disabled={deleting}
            className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-700 disabled:opacity-50"
          >
            {deleting ? "Removing..." : "Remove"}
          </button>
        </div>
      </Modal>
    </div>
  );
}
