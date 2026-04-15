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

/** Canonical sections shown first in order, followed by any extras alphabetically. */
const CANONICAL_ORDER = ["what_it_does", "key_capabilities", "technical_architecture", "current_state"];

function sectionLabel(key: string): string {
  return SECTION_LABELS[key] || key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function BriefEditor({ projectId }: { projectId: string }) {
  const [brief, setBrief] = useState<Brief | null>(null);
  const [loading, setLoading] = useState(true);
  const [editingSection, setEditingSection] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [addingSection, setAddingSection] = useState(false);
  const [newSectionName, setNewSectionName] = useState("");

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

  async function handleDelete(section: string) {
    if (!brief) return;
    setSaving(true);
    try {
      const updated = { ...brief.sections };
      delete updated[section];
      await updateBrief(projectId, updated);
      setBrief({ sections: updated });
      setEditingSection(null);
    } catch {
      // silent
    } finally {
      setSaving(false);
    }
  }

  function handleAddSection() {
    if (!newSectionName.trim() || !brief) return;
    const key = newSectionName.trim().toLowerCase().replace(/\s+/g, "_");
    if (brief.sections[key] !== undefined) return; // already exists
    setBrief({ sections: { ...brief.sections, [key]: "" } });
    setNewSectionName("");
    setAddingSection(false);
    setEditingSection(key);
    setEditDraft("");
  }

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading brief...</p>;
  }

  const sections = brief?.sections || {};

  // Order: canonical sections first, then extras alphabetically
  const allKeys = Object.keys(sections);
  const canonicalPresent = CANONICAL_ORDER.filter((k) => allKeys.includes(k));
  const extras = allKeys.filter((k) => !CANONICAL_ORDER.includes(k)).sort();
  const orderedKeys = [...canonicalPresent, ...extras];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Project Brief</h2>
        {!addingSection && (
          <button
            onClick={() => setAddingSection(true)}
            className="rounded-md border border-border px-3 py-1 text-xs font-medium text-muted-foreground hover:bg-muted"
          >
            Add Section
          </button>
        )}
      </div>

      {addingSection && (
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={newSectionName}
            onChange={(e) => setNewSectionName(e.target.value)}
            placeholder="Section name"
            className="rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-accent"
            autoFocus
            onKeyDown={(e) => e.key === "Enter" && handleAddSection()}
          />
          <button
            onClick={handleAddSection}
            disabled={!newSectionName.trim()}
            className="rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
          >
            Add
          </button>
          <button
            onClick={() => { setAddingSection(false); setNewSectionName(""); }}
            className="text-xs text-muted-foreground hover:underline"
          >
            Cancel
          </button>
        </div>
      )}

      {orderedKeys.map((key) => {
        const label = sectionLabel(key);
        const content = sections[key] || "";
        const isEditing = editingSection === key;
        const isCanonical = CANONICAL_ORDER.includes(key);

        return (
          <div key={key} className="rounded-lg border border-border p-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium">{label}</h3>
              {isEditing ? (
                <div className="flex items-center gap-2">
                  {!isCanonical && (
                    <button
                      onClick={() => handleDelete(key)}
                      disabled={saving}
                      className="text-xs text-destructive hover:underline disabled:opacity-50"
                    >
                      Delete
                    </button>
                  )}
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
                rows={6}
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
    </div>
  );
}
