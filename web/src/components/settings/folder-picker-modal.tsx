"use client";

import { useCallback, useEffect, useState } from "react";
import { browseDirectory } from "@/lib/api";

interface FolderPickerModalProps {
  open: boolean;
  onClose: () => void;
  onSelect: (path: string) => void;
}

export function FolderPickerModal({ open, onClose, onSelect }: FolderPickerModalProps) {
  const [currentPath, setCurrentPath] = useState("");
  const [parentPath, setParentPath] = useState("");
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="w-full max-w-lg rounded-lg border border-border bg-background p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="mb-4 text-lg font-semibold">Select Folder</h3>

        <div className="mb-3 flex items-center gap-2">
          <button
            onClick={() => browse(parentPath)}
            disabled={loading || currentPath === parentPath}
            className="shrink-0 rounded-md border border-border px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted disabled:opacity-50"
          >
            Up
          </button>
          <span className="truncate text-sm text-muted-foreground">{currentPath}</span>
        </div>

        {error && <p className="mb-3 text-sm text-destructive">{error}</p>}

        <div className="max-h-72 overflow-y-auto rounded-md border border-border">
          {loading ? (
            <p className="p-4 text-center text-sm text-muted-foreground">Loading...</p>
          ) : directories.length === 0 ? (
            <p className="p-4 text-center text-sm text-muted-foreground">No subdirectories</p>
          ) : (
            directories.map((d) => (
              <button
                key={d.path}
                onClick={() => browse(d.path)}
                className="flex w-full items-center gap-2 border-b border-border px-3 py-2 text-left text-sm transition-colors last:border-b-0 hover:bg-muted"
              >
                <span className="shrink-0">{d.is_git ? "G" : "D"}</span>
                <span className="truncate">{d.name}</span>
                {d.is_git && (
                  <span className="ml-auto shrink-0 rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-800 dark:bg-blue-900/30 dark:text-blue-400">
                    git
                  </span>
                )}
              </button>
            ))
          )}
        </div>

        <div className="mt-4 flex justify-end gap-2">
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
    </div>
  );
}
