"use client";

import { useCallback, useEffect, useState } from "react";
import type { Strategy, Project } from "@/lib/types";
import { fetchStrategies, updateStrategy, resetStrategy, fetchProjects, createStrategy, deleteStrategy } from "@/lib/api";
import { Modal } from "@/components/ui/modal";
import { useToast } from "@/lib/toast-context";

const EDITABLE_FIELDS: (keyof Strategy)[] = ["audience", "voice", "angle", "post_when", "avoid", "format_preference", "media_preference"];
const FIELD_LABELS: Record<string, string> = {
  audience: "Audience",
  voice: "Voice",
  angle: "Angle",
  post_when: "Post When",
  avoid: "Avoid",
  format_preference: "Format Preference",
  media_preference: "Media Preference",
};

export function StrategiesSection() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState("");
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState<Partial<Strategy>>({});
  const [saving, setSaving] = useState(false);
  const [confirmReset, setConfirmReset] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createFields, setCreateFields] = useState<Partial<Strategy>>({});
  const [creating, setCreating] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const { addToast } = useToast();

  const loadProjects = useCallback(async () => {
    try {
      const res = await fetchProjects();
      setProjects(res.projects);
      if (res.projects.length > 0 && !selectedProject) {
        setSelectedProject(res.projects[0].id);
      }
    } catch {
      // silent — failed initial load
    } finally {
      setLoading(false);
    }
  }, [selectedProject]);

  useEffect(() => { loadProjects(); }, [loadProjects]);

  const loadStrategies = useCallback(async (projectId: string) => {
    if (!projectId) return;
    try {
      const res = await fetchStrategies(projectId);
      // API returns {strategies: {name: {...}}} — convert to array
      const strats = res.strategies;
      if (strats && typeof strats === "object" && !Array.isArray(strats)) {
        setStrategies(
          Object.entries(strats).map(([name, val]: [string, Record<string, unknown>]) => ({
            name,
            template: false,
            audience: (val.audience as string) || undefined,
            voice: (val.voice as string) || undefined,
            angle: (val.angle as string) || undefined,
            post_when: (val.post_when as string) || undefined,
            avoid: (val.avoid as string) || undefined,
            format_preference: (val.format_preference as string) || undefined,
            media_preference: (val.media_preference as string) || undefined,
          }))
        );
      } else {
        setStrategies([]);
      }
    } catch {
      // silent — failed fetch during refresh
    }
  }, []);

  useEffect(() => {
    if (selectedProject) loadStrategies(selectedProject);
  }, [selectedProject, loadStrategies]);

  function startEdit(s: Strategy) {
    setEditing(s.name);
    setEditDraft({
      audience: s.audience || "",
      voice: s.voice || "",
      angle: s.angle || "",
      post_when: s.post_when || "",
      avoid: s.avoid || "",
      format_preference: s.format_preference || "",
      media_preference: s.media_preference || "",
    });
  }

  async function handleSave() {
    if (!editing) return;
    setSaving(true);
    try {
      await updateStrategy(selectedProject, editing, editDraft);
      setEditing(null);
      await loadStrategies(selectedProject);
    } catch (e) {
      addToast("Failed to save strategy", { variant: "error", detail: e instanceof Error ? e.message : undefined });
    } finally {
      setSaving(false);
    }
  }

  async function handleReset(name: string) {
    setResetting(true);
    try {
      await resetStrategy(selectedProject, name);
      setConfirmReset(null);
      await loadStrategies(selectedProject);
    } catch (e) {
      addToast("Failed to reset strategy", { variant: "error", detail: e instanceof Error ? e.message : undefined });
    } finally {
      setResetting(false);
    }
  }

  async function handleCreate() {
    if (!createName.trim()) return;
    setCreating(true);
    try {
      await createStrategy(selectedProject, {
        name: createName.trim(),
        audience: (createFields.audience as string) || undefined,
        voice: (createFields.voice as string) || undefined,
        angle: (createFields.angle as string) || undefined,
        post_when: (createFields.post_when as string) || undefined,
        avoid: (createFields.avoid as string) || undefined,
      });
      setCreateOpen(false);
      setCreateName("");
      setCreateFields({});
      addToast("Strategy created", { variant: "success" });
      await loadStrategies(selectedProject);
    } catch (e) {
      addToast("Failed to create strategy", { variant: "error", detail: e instanceof Error ? e.message : undefined });
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(name: string) {
    setDeleting(true);
    try {
      await deleteStrategy(selectedProject, name);
      setConfirmDelete(null);
      addToast("Strategy deleted");
      await loadStrategies(selectedProject);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "";
      if (msg.includes("409") || msg.toLowerCase().includes("referenced") || msg.toLowerCase().includes("target")) {
        addToast("Cannot delete strategy", { variant: "error", detail: "Strategy is referenced by targets. Remove targets first." });
      } else {
        addToast("Failed to delete strategy", { variant: "error", detail: msg || undefined });
      }
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Strategies</h2>
          <p className="text-sm text-muted-foreground">Content strategies define audience, voice, and posting rules.</p>
        </div>
        <button
          onClick={() => setCreateOpen(true)}
          disabled={!selectedProject}
          className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
        >
          New Strategy
        </button>
      </div>

      {projects.length > 1 && (
        <div>
          <label className="mb-1 block text-sm font-medium">Project</label>
          <select
            value={selectedProject}
            onChange={(e) => setSelectedProject(e.target.value)}
            className="rounded-md border border-border bg-background px-3 py-1.5 text-sm"
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
      )}

      {/* Create form */}
      {createOpen && (
        <div className="rounded-lg border border-border p-4">
          <h3 className="text-sm font-semibold">New Strategy</h3>
          <div className="mt-3 space-y-2">
            <div>
              <label className="mb-1 block text-xs font-medium">Name</label>
              <input
                type="text"
                value={createName}
                onChange={(e) => setCreateName(e.target.value)}
                placeholder="e.g., brand-primary"
                className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-accent"
              />
            </div>
            {(["audience", "voice", "angle", "post_when", "avoid"] as const).map((field) => (
              <div key={field}>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">{FIELD_LABELS[field]}</label>
                <input
                  type="text"
                  value={(createFields[field] as string) ?? ""}
                  onChange={(e) => setCreateFields((prev) => ({ ...prev, [field]: e.target.value }))}
                  className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-accent"
                />
              </div>
            ))}
            <div className="flex gap-2">
              <button
                onClick={handleCreate}
                disabled={creating || !createName.trim()}
                className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
              >
                {creating ? "Creating..." : "Create"}
              </button>
              <button
                onClick={() => { setCreateOpen(false); setCreateName(""); setCreateFields({}); }}
                className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : strategies.length === 0 ? (
        <div className="rounded-lg border-2 border-dashed border-border p-6 text-center">
          <p className="text-sm text-muted-foreground">
            {projects.length === 0 ? "Register a project first to manage strategies." : "No strategies found for this project."}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {strategies.map((s) => (
            <div key={s.name} className="rounded-lg border border-border p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{s.name}</span>
                  {s.template && (
                    <span className="rounded-full bg-indigo-100 px-2.5 py-0.5 text-xs font-medium text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-400">
                      built-in
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {editing === s.name ? (
                    <>
                      <button
                        onClick={() => setEditing(null)}
                        className="rounded-md border border-border px-3 py-1 text-xs hover:bg-muted"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={handleSave}
                        disabled={saving}
                        className="rounded-md bg-accent px-3 py-1 text-xs font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
                      >
                        {saving ? "Saving..." : "Save"}
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        onClick={() => startEdit(s)}
                        className="text-xs text-accent hover:underline"
                      >
                        Edit
                      </button>
                      {s.template && (
                        <button
                          onClick={() => setConfirmReset(s.name)}
                          className="text-xs text-muted-foreground hover:text-foreground"
                        >
                          Reset to Default
                        </button>
                      )}
                      <button
                        onClick={() => setConfirmDelete(s.name)}
                        className="text-xs text-muted-foreground hover:text-destructive"
                      >
                        Delete
                      </button>
                    </>
                  )}
                </div>
              </div>

              {editing === s.name ? (
                <div className="mt-3 space-y-2">
                  {EDITABLE_FIELDS.map((field) => (
                    <div key={field}>
                      <label className="mb-1 block text-xs font-medium text-muted-foreground">{FIELD_LABELS[field]}</label>
                      <input
                        type="text"
                        value={(editDraft[field] as string) ?? ""}
                        onChange={(e) => setEditDraft((prev) => ({ ...prev, [field]: e.target.value }))}
                        className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-accent"
                      />
                    </div>
                  ))}
                </div>
              ) : (
                <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1">
                  {EDITABLE_FIELDS.map((field) => {
                    const val = s[field] as string | undefined;
                    if (!val) return null;
                    return (
                      <div key={field} className="text-xs">
                        <span className="text-muted-foreground">{FIELD_LABELS[field]}: </span>
                        <span>{val}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Reset confirmation */}
      <Modal open={!!confirmReset} onClose={() => setConfirmReset(null)} maxWidth="max-w-sm">
        <h3 className="text-sm font-semibold">Reset Strategy</h3>
        <p className="mt-2 text-sm text-muted-foreground">
          Reset &ldquo;{confirmReset}&rdquo; to its built-in template defaults? Project overrides will be removed.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={() => setConfirmReset(null)} className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted">
            Cancel
          </button>
          <button
            onClick={() => confirmReset && handleReset(confirmReset)}
            disabled={resetting}
            className="rounded-md bg-destructive px-3 py-1.5 text-sm font-medium text-destructive-foreground hover:bg-destructive/80 disabled:opacity-50"
          >
            {resetting ? "Resetting..." : "Reset"}
          </button>
        </div>
      </Modal>

      {/* Delete confirmation */}
      <Modal open={!!confirmDelete} onClose={() => setConfirmDelete(null)} maxWidth="max-w-sm">
        <h3 className="text-sm font-semibold">Delete Strategy</h3>
        <p className="mt-2 text-sm text-muted-foreground">
          Delete &ldquo;{confirmDelete}&rdquo;? This will remove the strategy and its configuration. Targets using this strategy will need to be reassigned.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={() => setConfirmDelete(null)} className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted">
            Cancel
          </button>
          <button
            onClick={() => confirmDelete && handleDelete(confirmDelete)}
            disabled={deleting}
            className="rounded-md bg-destructive px-3 py-1.5 text-sm font-medium text-destructive-foreground hover:bg-destructive/80 disabled:opacity-50"
          >
            {deleting ? "Deleting..." : "Delete"}
          </button>
        </div>
      </Modal>
    </div>
  );
}
