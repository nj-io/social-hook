"use client";

import { useEffect, useState } from "react";

interface TextEditorSectionProps {
  title: string;
  description: string;
  content: string;
  filePath?: string;
  onSave: (content: string) => Promise<void>;
  language?: "markdown" | "yaml";
}

export function TextEditorSection({ title, description, content: initial, filePath, onSave, language }: TextEditorSectionProps) {
  const [content, setContent] = useState(initial);
  useEffect(() => { setContent(initial); }, [initial]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  const hasChanges = content !== initial;

  async function handleSave() {
    setSaving(true);
    setError("");
    setSaved(false);
    try {
      await onSave(content);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">{title}</h2>
          <p className="text-sm text-muted-foreground">{description}</p>
        </div>
        <button
          onClick={handleSave}
          disabled={saving || !hasChanges}
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-foreground transition-colors hover:bg-accent/80 disabled:opacity-50"
        >
          {saving ? "Saving..." : saved ? "Saved" : "Save"}
        </button>
      </div>
      {filePath && (
        <p className="text-xs text-muted-foreground">File: {filePath}</p>
      )}
      {error && (
        <p className="text-sm text-destructive">{error}</p>
      )}
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        rows={20}
        className={`w-full rounded-md border border-border bg-background p-3 text-sm outline-none focus:ring-2 focus:ring-accent ${
          language === "yaml" ? "font-mono" : ""
        }`}
        spellCheck={language !== "yaml"}
      />
    </div>
  );
}
