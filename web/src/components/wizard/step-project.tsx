"use client";

import { useEffect, useState } from "react";
import { FolderPickerModal } from "@/components/settings/folder-picker-modal";
import { fetchGitBranches } from "@/lib/api";

interface StepProjectProps {
  repoPath: string;
  projectName: string;
  installGitHook: boolean;
  triggerBranch: string;
  onRepoPathChange: (v: string) => void;
  onProjectNameChange: (v: string) => void;
  onInstallGitHookChange: (v: boolean) => void;
  onTriggerBranchChange: (v: string) => void;
}

export function StepProject({
  repoPath,
  projectName,
  installGitHook,
  triggerBranch,
  onRepoPathChange,
  onProjectNameChange,
  onInstallGitHookChange,
  onTriggerBranchChange,
}: StepProjectProps) {
  const [folderPickerOpen, setFolderPickerOpen] = useState(false);
  const [branches, setBranches] = useState<string[]>([]);
  const [currentBranch, setCurrentBranch] = useState<string | null>(null);

  // Fetch branches when repo path changes
  useEffect(() => {
    if (!repoPath || repoPath.length < 2) {
      setBranches([]);
      return;
    }
    const timeout = setTimeout(() => {
      fetchGitBranches(repoPath)
        .then((res) => {
          setBranches(res.branches);
          setCurrentBranch(res.current);
        })
        .catch(() => setBranches([]));
    }, 500); // debounce
    return () => clearTimeout(timeout);
  }, [repoPath]);

  return (
    <div className="animate-wizard-dissolve space-y-4">
      <div>
        <h3 className="text-lg font-semibold">Project</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Register a git repository to start generating content from your commits.
        </p>
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">Repository path</label>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={repoPath}
            onChange={(e) => onRepoPathChange(e.target.value)}
            placeholder="/path/to/your/repo"
            className="min-w-0 flex-1 rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
          />
          <button
            onClick={() => setFolderPickerOpen(true)}
            className="shrink-0 rounded-md border border-border px-3 py-2 text-sm font-medium transition-colors hover:bg-muted"
          >
            Browse
          </button>
        </div>
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">Project name (optional)</label>
        <input
          type="text"
          value={projectName}
          onChange={(e) => onProjectNameChange(e.target.value)}
          placeholder="Defaults to folder name"
          className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
        />
      </div>

      {branches.length > 0 && (
        <div>
          <label className="mb-1 block text-sm font-medium">Branch to monitor</label>
          <select
            value={triggerBranch}
            onChange={(e) => onTriggerBranchChange(e.target.value)}
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
          >
            <option value="">All branches</option>
            {branches.map((b) => (
              <option key={b} value={b}>
                {b}{b === currentBranch ? " (current)" : ""}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-muted-foreground">
            Only commits on this branch will trigger evaluations. Leave as &quot;All branches&quot; to monitor everything.
          </p>
        </div>
      )}

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={installGitHook}
          onChange={(e) => onInstallGitHookChange(e.target.checked)}
          className="rounded border-border"
        />
        Install git hook for automatic commit detection
      </label>

      <FolderPickerModal
        open={folderPickerOpen}
        onClose={() => setFolderPickerOpen(false)}
        onSelect={(path) => onRepoPathChange(path)}
      />
    </div>
  );
}
