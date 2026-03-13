"use client";

import { useState } from "react";
import { Modal } from "@/components/ui/modal";

interface AddPlatformModalProps {
  open: boolean;
  onClose: () => void;
  onAdd: (name: string, config: { format?: string; description?: string; max_length?: number }) => void;
  existingNames: string[];
}

export function AddPlatformModal({ open, onClose, onAdd, existingNames }: AddPlatformModalProps) {
  const [name, setName] = useState("");
  const [format, setFormat] = useState("");
  const [description, setDescription] = useState("");
  const [maxLength, setMaxLength] = useState("");
  const [error, setError] = useState("");

  if (!open) return null;

  function handleAdd() {
    const trimmed = name.trim().toLowerCase().replace(/\s+/g, "_");
    if (!trimmed) {
      setError("Name is required");
      return;
    }
    if (existingNames.includes(trimmed)) {
      setError("Platform already exists");
      return;
    }
    if (!/^[a-z][a-z0-9_]*$/.test(trimmed)) {
      setError("Name must start with a letter and contain only letters, numbers, underscores");
      return;
    }

    onAdd(trimmed, {
      format: format.trim() || undefined,
      description: description.trim() || undefined,
      max_length: maxLength ? Number(maxLength) : undefined,
    });
    setName("");
    setFormat("");
    setDescription("");
    setMaxLength("");
    setError("");
    onClose();
  }

  return (
    <Modal open={open} onClose={onClose}>
      <h3 className="mb-4 text-lg font-semibold">Add Custom Platform</h3>

      <div className="space-y-3">
        <div>
          <label className="mb-1 block text-sm font-medium">Platform name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => { setName(e.target.value); setError(""); }}
            placeholder="blog, newsletter, mastodon..."
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
            autoFocus
          />
          {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium">Format</label>
          <input
            type="text"
            value={format}
            onChange={(e) => setFormat(e.target.value)}
            placeholder="article, post, email..."
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium">Description</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Extra context for the AI drafter..."
            rows={2}
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium">Max character length</label>
          <input
            type="number"
            value={maxLength}
            onChange={(e) => setMaxLength(e.target.value)}
            placeholder="No limit"
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
          />
        </div>
      </div>

      <div className="mt-6 flex justify-end gap-2">
        <button
          onClick={onClose}
          className="rounded-md border border-border px-4 py-2 text-sm font-medium transition-colors hover:bg-muted"
        >
          Cancel
        </button>
        <button
          onClick={handleAdd}
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-foreground transition-colors hover:bg-accent/80"
        >
          Add Platform
        </button>
      </div>
    </Modal>
  );
}
