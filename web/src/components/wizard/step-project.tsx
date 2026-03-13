"use client";

import { useState } from "react";
import { FolderPickerModal } from "@/components/settings/folder-picker-modal";

interface StepProjectProps {
  repoPath: string;
  projectName: string;
  installGitHook: boolean;
  onRepoPathChange: (v: string) => void;
  onProjectNameChange: (v: string) => void;
  onInstallGitHookChange: (v: boolean) => void;
}

export function StepProject({
  repoPath,
  projectName,
  installGitHook,
  onRepoPathChange,
  onProjectNameChange,
  onInstallGitHookChange,
}: StepProjectProps) {
  const [folderPickerOpen, setFolderPickerOpen] = useState(false);

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
