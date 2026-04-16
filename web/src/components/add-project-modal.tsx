"use client";

import { useRef, useState } from "react";
import { Modal } from "@/components/ui/modal";
import { FolderPickerModal } from "@/components/settings/folder-picker-modal";
import { registerProject, uploadProjectDocs } from "@/lib/api";

interface AddProjectModalProps {
  open: boolean;
  onClose: () => void;
  onComplete: () => void;
}

export function AddProjectModal({ open, onClose, onComplete }: AddProjectModalProps) {
  const [repoPath, setRepoPath] = useState("");
  const [projectName, setProjectName] = useState("");
  const [docFiles, setDocFiles] = useState<File[]>([]);
  const [folderPickerOpen, setFolderPickerOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  function reset() {
    setRepoPath("");
    setProjectName("");
    setDocFiles([]);
    setError("");
    setLoading(false);
  }

  function handleClose() {
    if (!loading) {
      reset();
      onClose();
    }
  }

  async function handleSubmit() {
    if (!repoPath.trim()) return;
    setLoading(true);
    setError("");

    try {
      const res = await registerProject(repoPath.trim(), projectName.trim() || undefined, true);
      const projectId = res.project?.id;

      // Upload docs if provided
      if (projectId && docFiles.length > 0) {
        await uploadProjectDocs(projectId, docFiles);
      }

      reset();
      onComplete();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Registration failed");
      setLoading(false);
    }
  }

  if (!open) return null;

  return (
    <>
      <Modal open={true} onClose={handleClose} maxWidth="max-w-sm">
        <h3 className="text-sm font-semibold">Add Project</h3>
        <p className="mt-2 text-sm text-muted-foreground">
          Register a git repo or plain directory. Optionally upload docs for context.
        </p>

        <div className="mt-3">
          <label className="text-xs text-muted-foreground">Project path *</label>
          <div className="mt-1 flex items-center gap-2">
            <input
              type="text"
              value={repoPath}
              onChange={(e) => setRepoPath(e.target.value)}
              placeholder="/path/to/project"
              className="min-w-0 flex-1 rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground outline-none focus:ring-2 focus:ring-accent"
            />
            <button
              onClick={() => setFolderPickerOpen(true)}
              className="shrink-0 rounded-md border border-border px-2 py-1.5 text-sm hover:bg-muted"
            >
              Browse
            </button>
          </div>
        </div>

        <div className="mt-3">
          <label className="text-xs text-muted-foreground">Name (optional)</label>
          <input
            type="text"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            placeholder="Auto-detected from directory"
            className="mt-1 h-8 w-full rounded-md border border-border bg-background px-2 text-sm text-foreground"
          />
        </div>

        <div className="mt-3">
          <label className="text-xs text-muted-foreground">Documentation files (optional)</label>
          <div
            onClick={() => fileInputRef.current?.click()}
            className="mt-1 cursor-pointer rounded-md border-2 border-dashed border-border p-3 text-center text-sm text-muted-foreground transition-colors hover:border-accent/50"
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(e) => {
                const selected = Array.from(e.target.files || []);
                if (selected.length > 0) {
                  setDocFiles((prev) => [...prev, ...selected]);
                }
                e.target.value = "";
              }}
            />
            Click to select files
          </div>
          {docFiles.length > 0 && (
            <div className="mt-2 space-y-1">
              {docFiles.map((f, i) => (
                <div key={i} className="flex items-center justify-between rounded border border-border px-2 py-1 text-xs">
                  <span className="truncate">{f.name}</span>
                  <button
                    onClick={() => setDocFiles((prev) => prev.filter((_, j) => j !== i))}
                    className="ml-2 shrink-0 text-muted-foreground hover:text-destructive"
                  >
                    x
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {error && (
          <div className="mt-3 rounded-md border border-destructive/50 bg-destructive/10 p-2 text-xs text-destructive">
            {error}
          </div>
        )}

        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={handleClose}
            disabled={loading}
            className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!repoPath.trim() || loading}
            className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
          >
            {loading ? "Registering..." : "Add Project"}
          </button>
        </div>
      </Modal>

      <FolderPickerModal
        open={folderPickerOpen}
        onClose={() => setFolderPickerOpen(false)}
        onSelect={(path) => setRepoPath(path)}
      />
    </>
  );
}
