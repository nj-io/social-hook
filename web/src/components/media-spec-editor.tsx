"use client";

import { useState } from "react";
import { updateDraftMediaSpec } from "@/lib/api";

interface MediaSpecEditorProps {
  draftId: string;
  mediaSpec: Record<string, unknown>;
  onUpdate: () => void;
}

export function MediaSpecEditor({ draftId, mediaSpec, onUpdate }: MediaSpecEditorProps) {
  const [editing, setEditing] = useState(false);
  const [rawJson, setRawJson] = useState(() => JSON.stringify(mediaSpec, null, 2));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  if (!editing) {
    const isEmpty = !mediaSpec || Object.keys(mediaSpec).length === 0;
    return (
      <div className="rounded-lg border border-border p-4">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-medium text-muted-foreground">Media Spec</h2>
          <button
            onClick={() => {
              setRawJson(JSON.stringify(mediaSpec, null, 2));
              setEditing(true);
              setError("");
            }}
            className="text-xs text-accent hover:underline"
          >
            Edit
          </button>
        </div>
        {isEmpty ? (
          <p className="text-xs text-muted-foreground">No media spec set.</p>
        ) : (
          <pre className="overflow-x-auto rounded bg-muted/50 p-2 text-xs">{JSON.stringify(mediaSpec, null, 2)}</pre>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-medium text-muted-foreground">Media Spec</h2>
      </div>
      <textarea
        value={rawJson}
        onChange={(e) => {
          setRawJson(e.target.value);
          setError("");
        }}
        rows={6}
        className="w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-xs outline-none focus:ring-2 focus:ring-accent"
      />
      {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
      <div className="mt-2 flex gap-2">
        <button
          onClick={async () => {
            let parsed: Record<string, unknown>;
            try {
              parsed = JSON.parse(rawJson);
            } catch {
              setError("Invalid JSON");
              return;
            }
            setSaving(true);
            try {
              await updateDraftMediaSpec(draftId, parsed);
              setEditing(false);
              onUpdate();
            } catch (e) {
              setError(e instanceof Error ? e.message : "Save failed");
            } finally {
              setSaving(false);
            }
          }}
          disabled={saving}
          className="rounded-md bg-accent px-3 py-1 text-xs font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
        >
          {saving ? "Saving..." : "Save"}
        </button>
        <button
          onClick={() => {
            setEditing(false);
            setError("");
          }}
          className="rounded-md border border-border px-3 py-1 text-xs hover:bg-muted"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
