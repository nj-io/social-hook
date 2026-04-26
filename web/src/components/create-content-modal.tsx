"use client";

import { useRef, useState } from "react";
import { AsyncButton } from "./async-button";
import { Modal } from "./ui/modal";
import { Note } from "./ui/note";
import { useBackgroundTasks } from "@/lib/use-background-tasks";
import { useToast } from "@/lib/toast-context";
import { createContent, uploadImage, uploadProjectDocs } from "@/lib/api";
import type { BackgroundTask } from "@/lib/api";
import type { PendingUpload } from "@/lib/types";

interface CreateContentModalProps {
  open: boolean;
  onClose: () => void;
  projectId: string;
  onCreated?: () => void;
}

interface ReferenceImage {
  /** Resolved upload_id returned by POST /api/projects/{id}/uploads. */
  uploadId: string;
  /** Local display name for the operator. */
  name: string;
  /** Per-file context — used by the drafter to build vision content blocks. */
  context: string;
}

const CREATE_REF_PREFIX = "create_content:";
const ACCEPTED_IMAGE_TYPES = new Set([
  "image/png",
  "image/jpeg",
  "image/jpg",
  "image/webp",
  "image/gif",
]);
const MAX_IMAGE_BYTES = 5 * 1024 * 1024; // matches SINGLE_IMAGE.max_size on the backend

/**
 * Create Content modal — extracted from projects/[id]/page.tsx with
 * multi-media support. Two upload flows:
 *
 *  • **Reference images** (drag-drop): each file is POSTed to
 *    ``/api/projects/{id}/uploads`` on drop, yielding an ``upload_id`` and
 *    staging path. The drafter uses these as vision content blocks when
 *    ``upload_ids`` is passed with ``createContent``. Per-file context
 *    textarea lets the operator tell the drafter what each image is.
 *  • **Reference documents** (legacy plain-file picker): non-image files
 *    (PDFs, .md, etc.) still flow through ``uploadProjectDocs`` and become
 *    entries in ``reference_files``. Images and docs are disjoint concerns.
 *
 * Size + format guards run client-side before the POST so a 413/415 from
 * the backend is extremely rare — but when it happens the operator sees
 * the toast with the structured error.
 */
export function CreateContentModal({
  open,
  onClose,
  projectId,
  onCreated,
}: CreateContentModalProps) {
  const [idea, setIdea] = useState("");
  const [vehicle, setVehicle] = useState("");
  const [refDocs, setRefDocs] = useState<File[]>([]);
  const [refImages, setRefImages] = useState<ReferenceImage[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const docInputRef = useRef<HTMLInputElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);

  const { addToast } = useToast();
  const refId = `${CREATE_REF_PREFIX}${projectId}`;

  const { trackTask, isRunning, getTask } = useBackgroundTasks(
    projectId,
    (task: BackgroundTask) => {
      if (task.ref_id !== refId) return;
      if (task.status === "failed") {
        addToast("Create Content failed", {
          variant: "error",
          detail: task.error ?? undefined,
        });
      } else if (task.status === "completed") {
        addToast("Content created", { variant: "success" });
        reset();
        onClose();
        onCreated?.();
      }
    },
  );

  const loading = isRunning(refId);
  const task = getTask(refId);

  function reset() {
    setIdea("");
    setVehicle("");
    setRefDocs([]);
    setRefImages([]);
    setError(null);
  }

  async function handleImageDrop(files: FileList | null) {
    if (!files || files.length === 0) return;
    setUploading(true);
    setError(null);
    try {
      const results = await Promise.all(
        Array.from(files).map(async (file): Promise<ReferenceImage | null> => {
          try {
            if (!ACCEPTED_IMAGE_TYPES.has(file.type)) {
              throw new Error(
                `${file.name}: ${file.type || "unknown type"} is not a supported image format`,
              );
            }
            if (file.size > MAX_IMAGE_BYTES) {
              throw new Error(
                `${file.name}: exceeds 5 MiB limit (${(file.size / 1024 / 1024).toFixed(1)} MiB)`,
              );
            }
            const upload: PendingUpload = await uploadImage(projectId, file, "");
            return {
              uploadId: upload.upload_id,
              name: file.name,
              context: "",
            };
          } catch (err) {
            console.warn("upload failed", file.name, err);
            const msg = err instanceof Error ? err.message : "Upload failed";
            addToast("Image upload failed", { variant: "error", detail: msg });
            return null;
          }
        }),
      );
      const accepted = results.filter((r): r is ReferenceImage => r !== null);
      if (accepted.length > 0) {
        setRefImages((prev) => [...prev, ...accepted]);
      }
    } finally {
      setUploading(false);
    }
  }

  function removeImage(uploadId: string) {
    setRefImages((prev) => prev.filter((r) => r.uploadId !== uploadId));
  }

  function setImageContext(uploadId: string, context: string) {
    setRefImages((prev) =>
      prev.map((r) => (r.uploadId === uploadId ? { ...r, context } : r)),
    );
  }

  async function handleSubmit() {
    if (!idea.trim()) return;
    setError(null);
    try {
      let refDocNames: string[] | undefined;
      if (refDocs.length > 0) {
        await uploadProjectDocs(projectId, refDocs);
        refDocNames = refDocs.map((f) => f.name);
      }

      const res = await createContent(projectId, {
        idea: idea.trim(),
        vehicle: vehicle || undefined,
        reference_files: refDocNames,
        upload_ids: refImages.length ? refImages.map((r) => r.uploadId) : undefined,
      });
      trackTask(res.task_id, refId, "create_content");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Create failed";
      setError(msg);
      addToast("Create Content request failed", {
        variant: "error",
        detail: msg,
      });
    }
  }

  return (
    <Modal open={open} onClose={() => !loading && !uploading && onClose()}>
      <h3 className="text-sm font-semibold">Create Content</h3>
      <p className="mt-2 text-sm text-muted-foreground">
        Draft content from an idea — bypasses the evaluator.
      </p>

      <div className="mt-3">
        <label className="text-xs text-muted-foreground">Idea *</label>
        <textarea
          className="mt-1 w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground"
          rows={3}
          placeholder="Describe what you want to post about..."
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
        />
      </div>

      <div className="mt-3">
        <label className="text-xs text-muted-foreground">Vehicle</label>
        <select
          className="mt-1 h-8 w-full rounded-md border border-border bg-background px-2 text-sm text-foreground"
          value={vehicle}
          onChange={(e) => setVehicle(e.target.value)}
        >
          <option value="">Auto</option>
          <option value="single">Single</option>
          <option value="thread">Thread</option>
          <option value="article">Article</option>
        </select>
      </div>

      {/* Reference images — drag/drop, POSTed immediately, per-file context */}
      <div className="mt-3">
        <label className="text-xs text-muted-foreground">
          Reference images (optional)
        </label>
        <div
          onClick={() => imageInputRef.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            handleImageDrop(e.dataTransfer.files);
          }}
          className="mt-1 cursor-pointer rounded-md border-2 border-dashed border-border p-3 text-center text-sm text-muted-foreground transition-colors hover:border-accent/50"
        >
          <input
            ref={imageInputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            multiple
            className="hidden"
            onChange={(e) => {
              handleImageDrop(e.target.files);
              e.target.value = "";
            }}
          />
          {uploading ? "Uploading…" : "Drop images here or click to select"}
        </div>
        {refImages.length > 0 && (
          <div className="mt-2 space-y-2">
            {refImages.map((r) => (
              <div
                key={r.uploadId}
                className="space-y-1 rounded border border-border p-2 text-xs"
              >
                <div className="flex items-center justify-between">
                  <span className="truncate font-medium">{r.name}</span>
                  <button
                    onClick={() => removeImage(r.uploadId)}
                    className="ml-2 shrink-0 text-muted-foreground hover:text-destructive"
                  >
                    x
                  </button>
                </div>
                <textarea
                  placeholder="What is this image? (context for the drafter)"
                  value={r.context}
                  onChange={(e) => setImageContext(r.uploadId, e.target.value)}
                  rows={2}
                  className="w-full rounded border border-border bg-background px-2 py-1 text-xs"
                />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Reference docs — legacy path; non-image files */}
      <div className="mt-3">
        <label className="text-xs text-muted-foreground">
          Reference documents (optional)
        </label>
        <div
          onClick={() => docInputRef.current?.click()}
          className="mt-1 cursor-pointer rounded-md border-2 border-dashed border-border p-3 text-center text-sm text-muted-foreground transition-colors hover:border-accent/50"
        >
          <input
            ref={docInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => {
              const selected = Array.from(e.target.files || []);
              if (selected.length > 0) {
                setRefDocs((prev) => [...prev, ...selected]);
              }
              e.target.value = "";
            }}
          />
          Click to select files
        </div>
        {refDocs.length > 0 && (
          <div className="mt-2 space-y-1">
            {refDocs.map((f, i) => (
              <div
                key={i}
                className="flex items-center justify-between rounded border border-border px-2 py-1 text-xs"
              >
                <span className="truncate">{f.name}</span>
                <button
                  onClick={() =>
                    setRefDocs((prev) => prev.filter((_, j) => j !== i))
                  }
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
        <div className="mt-3">
          <Note variant="error">{error}</Note>
        </div>
      )}

      <div className="mt-4 flex justify-end gap-2">
        <button
          onClick={onClose}
          disabled={loading || uploading}
          className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted disabled:opacity-50"
        >
          Cancel
        </button>
        <AsyncButton
          loading={loading}
          startTime={task?.created_at}
          loadingText={task?.stage_label ?? "Creating"}
          disabled={!idea.trim() || loading || uploading}
          onClick={handleSubmit}
          className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
        >
          Create
        </AsyncButton>
      </div>
    </Modal>
  );
}
