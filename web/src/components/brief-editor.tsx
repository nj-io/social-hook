"use client";

import { useCallback, useEffect, useState } from "react";
import type { Brief } from "@/lib/types";
import { fetchBrief, updateBrief } from "@/lib/api";

const SECTION_LABELS: Record<string, string> = {
  what_it_does: "What It Does",
  key_capabilities: "Key Capabilities",
  technical_architecture: "Technical Architecture",
  current_state: "Current State",
};

const SECTION_ORDER = ["what_it_does", "key_capabilities", "technical_architecture", "current_state"];

export function BriefEditor({ projectId }: { projectId: string }) {
  const [brief, setBrief] = useState<Brief | null>(null);
  const [loading, setLoading] = useState(true);
  const [editingSection, setEditingSection] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await fetchBrief(projectId);
      setBrief(res);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { load(); }, [load]);

  async function handleSave(section: string) {
    if (!brief) return;
    setSaving(true);
    try {
      const updated = { ...brief.sections, [section]: editDraft };
      await updateBrief(projectId, updated);
      setBrief({ sections: updated });
      setEditingSection(null);
    } catch {
      // silent
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading brief...</p>;
  }

  const sections = brief?.sections || {};

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Project Brief</h2>

      {SECTION_ORDER.map((key) => {
        const label = SECTION_LABELS[key] || key;
        const content = sections[key] || "";
        const isEditing = editingSection === key;

        return (
          <div key={key} className="rounded-lg border border-border p-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium">{label}</h3>
              {isEditing ? (
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setEditingSection(null)}
                    className="text-xs text-muted-foreground hover:underline"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => handleSave(key)}
                    disabled={saving}
                    className="rounded-md bg-accent px-3 py-1 text-xs font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
                  >
                    {saving ? "Saving..." : "Save"}
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => {
                    setEditingSection(key);
                    setEditDraft(content);
                  }}
                  className="text-xs text-accent hover:underline"
                >
                  Edit
                </button>
              )}
            </div>
            {isEditing ? (
              <textarea
                rows={4}
                value={editDraft}
                onChange={(e) => setEditDraft(e.target.value)}
                className="mt-2 w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
                autoFocus
              />
            ) : content ? (
              <p className="mt-2 whitespace-pre-wrap text-sm text-muted-foreground">{content}</p>
            ) : (
              <p className="mt-2 text-sm italic text-muted-foreground/50">Not yet written</p>
            )}
          </div>
        );
      })}

      {/* Show any extra sections not in the predefined list */}
      {Object.entries(sections)
        .filter(([key]) => !SECTION_ORDER.includes(key))
        .map(([key, content]) => (
          <div key={key} className="rounded-lg border border-border p-4">
            <h3 className="text-sm font-medium">{key}</h3>
            <p className="mt-2 whitespace-pre-wrap text-sm text-muted-foreground">{content}</p>
          </div>
        ))}
    </div>
  );
}
