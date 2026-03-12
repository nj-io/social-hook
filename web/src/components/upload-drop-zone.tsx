"use client";

import { useRef, useState } from "react";
import { uploadDraftMedia } from "@/lib/api";

interface UploadDropZoneProps {
  draftId: string;
  onUpdate: () => void;
}

const ALLOWED_EXTENSIONS = new Set(["png", "jpg", "jpeg", "gif", "webp", "svg"]);
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

export function UploadDropZone({ draftId, onUpdate }: UploadDropZoneProps) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  function validateFile(file: File): string | null {
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (!ext || !ALLOWED_EXTENSIONS.has(ext)) return `Invalid file type: .${ext}. Allowed: ${[...ALLOWED_EXTENSIONS].join(", ")}`;
    if (file.size > MAX_FILE_SIZE) return `File too large (${(file.size / 1024 / 1024).toFixed(1)}MB). Max 10MB.`;
    return null;
  }

  async function handleFile(file: File) {
    const validationError = validateFile(file);
    if (validationError) { setError(validationError); return; }

    setUploading(true);
    setError("");
    try {
      await uploadDraftMedia(draftId, file);
      onUpdate();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        const file = e.dataTransfer.files[0];
        if (file) handleFile(file);
      }}
      onClick={() => inputRef.current?.click()}
      className={`cursor-pointer rounded-md border-2 border-dashed p-4 text-center text-sm transition-colors ${
        dragging ? "border-accent bg-accent/10" : "border-border text-muted-foreground hover:border-accent/50"
      }`}
    >
      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/gif,image/webp,image/svg+xml"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
          e.target.value = "";
        }}
      />
      {uploading ? "Uploading..." : "Drop an image or click to upload custom media"}
      {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
    </div>
  );
}
