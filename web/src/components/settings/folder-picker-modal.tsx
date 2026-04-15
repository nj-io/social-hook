"use client";

import { useCallback, useEffect, useState } from "react";
import { browseDirectory } from "@/lib/api";
import { Modal } from "@/components/ui/modal";

interface FolderPickerModalProps {
  open: boolean;
  onClose: () => void;
  onSelect: (path: string) => void;
}

export function FolderPickerModal({ open, onClose, onSelect }: FolderPickerModalProps) {
  const [currentPath, setCurrentPath] = useState("");
  const [parentPath, setParentPath] = useState("");
  const [currentIsGit, setCurrentIsGit] = useState(false);
  const [directories, setDirectories] = useState<{ name: string; path: string; is_git: boolean }[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const browse = useCallback(async (path?: string) => {
    setLoading(true);
    setError("");
    try {
      const res = await browseDirectory(path);
      setCurrentPath(res.current);
      setParentPath(res.parent);
      setCurrentIsGit(res.is_git);
      setDirectories(res.directories);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to browse directory");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      browse();
    }
  }, [open, browse]);

  if (!open) return null;

  return (
    <Modal open={open} onClose={onClose} maxWidth="max-w-lg">
      <h3 className="mb-4 text-lg font-semibold">Select Project Folder</h3>

      <div className="mb-3 flex items-center gap-2">
        <button
          onClick={() => browse(parentPath)}
          disabled={loading || currentPath === parentPath}
          className="shrink-0 rounded-md border border-border px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted disabled:opacity-50"
        >
          Up
        </button>
        <span className="truncate text-sm text-muted-foreground">{currentPath}</span>
        {currentIsGit && (
          <span className="ml-auto shrink-0 rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-800 dark:bg-blue-900/30 dark:text-blue-400">
            git
          </span>
        )}
      </div>

      {error && <p className="mb-3 text-sm text-destructive">{error}</p>}

      <div className="max-h-72 overflow-y-auto rounded-md border border-border">
        {loading ? (
          <p className="p-4 text-center text-sm text-muted-foreground">Loading...</p>
        ) : directories.length === 0 ? (
          <p className="p-4 text-center text-sm text-muted-foreground">No subdirectories</p>
        ) : (
          directories.map((d) => (
            <div
              key={d.path}
              className="flex w-full items-center gap-2 border-b border-border px-3 py-2 text-sm last:border-b-0"
            >
              <button
                onClick={() => browse(d.path)}
                className="flex min-w-0 flex-1 items-center gap-2 text-left transition-colors hover:text-accent"
              >
                <span className="shrink-0">{d.is_git ? "G" : "D"}</span>
                <span className="truncate">{d.name}</span>
              </button>
              {d.is_git && (
                <span className="shrink-0 rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-800 dark:bg-blue-900/30 dark:text-blue-400">
                  git
                </span>
              )}
              <button
                onClick={() => {
                  onSelect(d.path);
                  onClose();
                }}
                className="shrink-0 rounded-md bg-accent px-2.5 py-1 text-xs font-medium text-accent-foreground transition-colors hover:bg-accent/80"
              >
                Select
              </button>
            </div>
          ))
        )}
      </div>

      <div className="mt-4 flex items-center justify-between">
        <div>
          {currentPath && (
            <p className="text-xs text-muted-foreground">
              {currentIsGit ? "Git repository" : "Plain directory"}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={onClose}
            className="rounded-md border border-border px-4 py-2 text-sm font-medium transition-colors hover:bg-muted"
          >
            Cancel
          </button>
          <button
            onClick={() => {
              onSelect(currentPath);
              onClose();
            }}
            disabled={!currentPath}
            className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-foreground transition-colors hover:bg-accent/80 disabled:opacity-50"
          >
            Select
          </button>
        </div>
      </div>
    </Modal>
  );
}
