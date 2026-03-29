"use client";

import { useCallback, useEffect, useState } from "react";
import type { Account } from "@/lib/types";
import { fetchAccounts, addAccount, deleteAccount, validateAccounts } from "@/lib/api";
import { Modal } from "@/components/ui/modal";
import { useToast } from "@/lib/toast-context";
import { useDataEvents } from "@/lib/use-data-events";

export function AccountsSection() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [addPlatform, setAddPlatform] = useState("x");
  const [addName, setAddName] = useState("");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [validating, setValidating] = useState(false);
  const [validationResults, setValidationResults] = useState<Record<string, { valid: boolean; error?: string }> | null>(null);
  const { addToast } = useToast();

  const load = useCallback(async () => {
    try {
      const res = await fetchAccounts();
      // API returns {accounts: {name: {platform, ...}}} — convert to array
      const accts = res.accounts;
      if (accts && typeof accts === "object" && !Array.isArray(accts)) {
        setAccounts(
          Object.entries(accts).map(([name, val]: [string, Record<string, unknown>]) => ({
            name,
            platform: (val.platform as string) || "",
            tier: (val.tier as string) || "",
            identity: (val.identity as string) || undefined,
            target_count: (val.target_count as number) ?? undefined,
            created_at: (val.created_at as string) || "",
          }))
        );
      } else {
        setAccounts([]);
      }
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  useDataEvents(["config"], load);

  async function handleAdd() {
    if (!addName.trim()) return;
    setAdding(true);
    setAddError("");
    try {
      const res = await addAccount({ platform: addPlatform, name: addName.trim() });
      if (res.auth_url) {
        window.open(res.auth_url, "_blank", "width=600,height=700");
      }
      setAddOpen(false);
      setAddName("");
      await load();
    } catch (e) {
      setAddError(e instanceof Error ? e.message : "Failed to add");
    } finally {
      setAdding(false);
    }
  }

  async function handleDelete(name: string) {
    setDeleting(true);
    try {
      await deleteAccount(name);
      setConfirmDelete(null);
      addToast("Account removed");
      await load();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "";
      if (msg.includes("409") || msg.toLowerCase().includes("target")) {
        addToast("Cannot remove account", { variant: "error", detail: "Account is referenced by targets. Remove targets first." });
      } else {
        addToast("Failed to remove account", { variant: "error", detail: msg || undefined });
      }
    } finally {
      setDeleting(false);
    }
  }

  async function handleValidateAll() {
    setValidating(true);
    try {
      const res = await validateAccounts();
      setValidationResults(res.results);
    } catch {
      // silent
    } finally {
      setValidating(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Accounts</h2>
          <p className="text-sm text-muted-foreground">Authenticated platform accounts for posting.</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleValidateAll}
            disabled={validating}
            className="rounded-md border border-border px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted disabled:opacity-50"
          >
            {validating ? "Validating..." : "Validate All"}
          </button>
          <button
            onClick={() => setAddOpen(true)}
            className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-foreground hover:bg-accent/80"
          >
            Add Account
          </button>
        </div>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : accounts.length === 0 ? (
        <div className="rounded-lg border-2 border-dashed border-border p-6 text-center">
          <p className="text-sm text-muted-foreground">No accounts configured. Add an account to start posting.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {accounts.map((acct) => {
            const vr = validationResults?.[acct.name];
            return (
              <div key={acct.name} className="flex items-center justify-between rounded-lg border border-border p-4">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{acct.name}</span>
                    <span className="rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
                      {acct.platform}
                    </span>
                    <span className="rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-medium text-blue-800 dark:bg-blue-900/30 dark:text-blue-400">
                      {acct.tier}
                    </span>
                    {vr && (
                      <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        vr.valid
                          ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400"
                          : "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400"
                      }`}>
                        {vr.valid ? "valid" : "invalid"}
                      </span>
                    )}
                  </div>
                  {acct.identity && (
                    <p className="mt-0.5 text-xs text-muted-foreground">{acct.identity}</p>
                  )}
                  {acct.target_count != null && acct.target_count > 0 && (
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {acct.target_count} target{acct.target_count !== 1 ? "s" : ""} linked
                    </p>
                  )}
                  {vr?.error && <p className="mt-1 text-xs text-destructive">{vr.error}</p>}
                </div>
                <button
                  onClick={() => setConfirmDelete(acct.name)}
                  className="rounded-md border border-red-300 px-3 py-1.5 text-sm font-medium text-red-600 transition-colors hover:bg-red-50 dark:border-red-700 dark:text-red-400 dark:hover:bg-red-900/20"
                >
                  Remove
                </button>
              </div>
            );
          })}
        </div>
      )}

      {/* Add modal */}
      <Modal open={addOpen} onClose={() => setAddOpen(false)} maxWidth="max-w-sm">
        <h3 className="text-sm font-semibold">Add Account</h3>
        <p className="mt-1 text-xs text-muted-foreground">This will open a browser window for OAuth authentication.</p>
        <div className="mt-3 space-y-3">
          <div>
            <label className="mb-1 block text-sm font-medium">Platform</label>
            <select
              value={addPlatform}
              onChange={(e) => setAddPlatform(e.target.value)}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
            >
              <option value="x">X (Twitter)</option>
              <option value="linkedin">LinkedIn</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Account Name</label>
            <input
              type="text"
              value={addName}
              onChange={(e) => setAddName(e.target.value)}
              placeholder="e.g. lead"
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
            disabled={adding || !addName.trim()}
            className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-foreground hover:bg-accent/80 disabled:opacity-50"
          >
            {adding ? "Connecting..." : "Connect"}
          </button>
        </div>
      </Modal>

      {/* Delete confirmation */}
      <Modal open={!!confirmDelete} onClose={() => setConfirmDelete(null)} maxWidth="max-w-sm">
        <h3 className="text-sm font-semibold">Remove Account</h3>
        <p className="mt-2 text-sm text-muted-foreground">
          Remove account &ldquo;{confirmDelete}&rdquo;? This will fail if targets still reference it.
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
            {deleting ? "Removing..." : "Remove"}
          </button>
        </div>
      </Modal>
    </div>
  );
}
