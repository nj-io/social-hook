"use client";

import { useCallback, useEffect, useState } from "react";
import type { Target, Account, Strategy } from "@/lib/types";
import { fetchTargets, addTarget, disableTarget, enableTarget, fetchAccounts, fetchStrategies, fetchProjects } from "@/lib/api";
import type { Project } from "@/lib/types";
import { Modal } from "@/components/ui/modal";
import { useToast } from "@/lib/toast-context";
import { useDataEvents } from "@/lib/use-data-events";

export function TargetsSection() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState("");
  const [targets, setTargets] = useState<Target[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [addAccount, setAddAccount] = useState("");
  const [addDestination, setAddDestination] = useState("timeline");
  const [addStrategy, setAddStrategy] = useState("");
  const [addFrequency, setAddFrequency] = useState("");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState("");
  const [confirmDisable, setConfirmDisable] = useState<string | null>(null);
  const [toggling, setToggling] = useState<string | null>(null);
  const { addToast } = useToast();

  const loadProjects = useCallback(async () => {
    try {
      const res = await fetchProjects();
      setProjects(res.projects);
      if (res.projects.length > 0 && !selectedProject) {
        setSelectedProject(res.projects[0].id);
      }
    } catch {
      addToast("Failed to load projects", { variant: "error" });
    } finally {
      setLoading(false);
    }
  }, [selectedProject, addToast]);

  useEffect(() => { loadProjects(); }, [loadProjects]);

  const loadTargets = useCallback(async (projectId: string) => {
    if (!projectId) return;
    try {
      const [t, a, s] = await Promise.all([
        fetchTargets(projectId),
        fetchAccounts(),
        fetchStrategies(projectId),
      ]);
      setTargets(t.targets);
      // accounts API returns dict — convert to array
      const acctMap = a.accounts;
      if (acctMap && typeof acctMap === "object" && !Array.isArray(acctMap)) {
        setAccounts(
          Object.entries(acctMap).map(([name, val]: [string, Record<string, unknown>]) => ({
            name,
            platform: (val.platform as string) || "",
            tier: (val.tier as string) || "",
            created_at: (val.created_at as string) || "",
          }))
        );
      } else {
        setAccounts([]);
      }
      // strategies API returns dict — convert to array
      const stratMap = s.strategies;
      if (stratMap && typeof stratMap === "object" && !Array.isArray(stratMap)) {
        setStrategies(
          Object.entries(stratMap).map(([name]: [string, unknown]) => ({ name, template: false }))
        );
      } else {
        setStrategies([]);
      }
    } catch {
      addToast("Failed to load targets", { variant: "error" });
    }
  }, [addToast]);

  const reloadCurrentProject = useCallback(() => {
    if (selectedProject) loadTargets(selectedProject);
  }, [selectedProject, loadTargets]);
  useDataEvents(["config"], reloadCurrentProject);

  useEffect(() => {
    if (selectedProject) loadTargets(selectedProject);
  }, [selectedProject, loadTargets]);

  async function handleAdd() {
    if (!addAccount || !addStrategy) return;
    setAdding(true);
    setAddError("");
    try {
      await addTarget(selectedProject, {
        account: addAccount,
        destination: addDestination,
        strategy: addStrategy,
        frequency: addFrequency || undefined,
      });
      setAddOpen(false);
      setAddAccount("");
      setAddStrategy("");
      setAddFrequency("");
      await loadTargets(selectedProject);
    } catch (e) {
      setAddError(e instanceof Error ? e.message : "Failed to add");
    } finally {
      setAdding(false);
    }
  }

  async function handleToggle(name: string, enabled: boolean) {
    if (enabled) {
      setConfirmDisable(name);
      return;
    }
    setToggling(name);
    try {
      await enableTarget(selectedProject, name);
      addToast("Target enabled");
      await loadTargets(selectedProject);
    } catch (e) {
      addToast("Failed to enable target", { variant: "error", detail: e instanceof Error ? e.message : undefined });
    } finally {
      setToggling(null);
    }
  }

  async function handleDisable(name: string) {
    setToggling(name);
    setConfirmDisable(null);
    try {
      await disableTarget(selectedProject, name);
      addToast("Target disabled");
      await loadTargets(selectedProject);
    } catch (e) {
      addToast("Failed to disable target", { variant: "error", detail: e instanceof Error ? e.message : undefined });
    } finally {
      setToggling(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Targets</h2>
          <p className="text-sm text-muted-foreground">Where content gets posted. Each target links an account to a strategy.</p>
        </div>
        <button
          onClick={() => setAddOpen(true)}
          disabled={!selectedProject}
          className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
        >
          Add Target
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

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : targets.length === 0 ? (
        <div className="rounded-lg border-2 border-dashed border-border p-6 text-center">
          <p className="text-sm text-muted-foreground">No targets configured for this project.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {targets.map((target) => (
            <div key={target.id} className="flex items-center justify-between rounded-lg border border-border p-4">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-medium">{target.id}</span>
                  <span className="text-muted-foreground">/</span>
                  <span className="text-sm">{target.destination}</span>
                  {target.primary && (
                    <span className="rounded-full bg-accent/10 px-2.5 py-0.5 text-xs font-medium text-accent">
                      primary
                    </span>
                  )}
                  {!target.enabled && (
                    <span className="rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-400">
                      disabled
                    </span>
                  )}
                </div>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Account: {target.account_name} | Strategy: {target.strategy}
                  {target.frequency && ` | Frequency: ${target.frequency}`}
                </p>
              </div>
              <button
                onClick={() => handleToggle(target.id, target.enabled)}
                disabled={toggling === target.id}
                className={`rounded-md border px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 ${
                  target.enabled
                    ? "border-yellow-300 text-yellow-700 hover:bg-yellow-50 dark:border-yellow-700 dark:text-yellow-400 dark:hover:bg-yellow-950"
                    : "border-green-300 text-green-700 hover:bg-green-50 dark:border-green-700 dark:text-green-400 dark:hover:bg-green-950"
                }`}
              >
                {toggling === target.id ? "..." : target.enabled ? "Disable" : "Enable"}
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Add target modal */}
      <Modal open={addOpen} onClose={() => setAddOpen(false)} maxWidth="max-w-sm">
        <h3 className="text-sm font-semibold">Add Target</h3>
        <div className="mt-3 space-y-3">
          <div>
            <label className="mb-1 block text-sm font-medium">Account</label>
            <select
              value={addAccount}
              onChange={(e) => setAddAccount(e.target.value)}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
            >
              <option value="">Select account</option>
              {accounts.map((a) => (
                <option key={a.name} value={a.name}>{a.name} ({a.platform})</option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Destination</label>
            <select
              value={addDestination}
              onChange={(e) => setAddDestination(e.target.value)}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
            >
              <option value="timeline">Timeline</option>
              <option value="community">Community</option>
              <option value="quote-retweet">Quote Retweet</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Strategy</label>
            <select
              value={addStrategy}
              onChange={(e) => setAddStrategy(e.target.value)}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
            >
              <option value="">Select strategy</option>
              {strategies.map((s) => (
                <option key={s.name} value={s.name}>{s.name}{s.template ? " (built-in)" : ""}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Frequency (optional)</label>
            <input
              type="text"
              value={addFrequency}
              onChange={(e) => setAddFrequency(e.target.value)}
              placeholder="e.g. daily, 3/week"
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
            />
          </div>
          {addError && <p className="text-xs text-destructive">{addError}</p>}
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={() => setAddOpen(false)} className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted">
            Cancel
          </button>
          <button
            onClick={handleAdd}
            disabled={adding || !addAccount || !addStrategy}
            className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
          >
            {adding ? "Adding..." : "Add Target"}
          </button>
        </div>
      </Modal>

      {/* Disable confirmation */}
      <Modal open={!!confirmDisable} onClose={() => setConfirmDisable(null)} maxWidth="max-w-sm">
        <h3 className="text-sm font-semibold">Disable Target</h3>
        <p className="mt-2 text-sm text-muted-foreground">
          Disabling this target will archive any pending drafts. You can re-enable it later.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={() => setConfirmDisable(null)} className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted">
            Cancel
          </button>
          <button
            onClick={() => confirmDisable && handleDisable(confirmDisable)}
            className="rounded-md bg-destructive px-3 py-1.5 text-sm font-medium text-destructive-foreground hover:bg-destructive/80"
          >
            Disable
          </button>
        </div>
      </Modal>
    </div>
  );
}
