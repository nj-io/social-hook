"use client";

import { useCallback, useEffect, useState } from "react";
import type { PlatformCredential } from "@/lib/types";
import { fetchPlatformCredentials, addPlatformCredential, deletePlatformCredential, validatePlatformCredential } from "@/lib/api";
import { Modal } from "@/components/ui/modal";

export function CredentialsSection() {
  const [credentials, setCredentials] = useState<PlatformCredential[]>([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [addPlatform, setAddPlatform] = useState("x");
  const [addName, setAddName] = useState("");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [validating, setValidating] = useState<Record<string, boolean>>({});
  const [validationResult, setValidationResult] = useState<Record<string, { valid: boolean; error?: string }>>({});

  const load = useCallback(async () => {
    try {
      const res = await fetchPlatformCredentials();
      setCredentials(res.credentials);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleAdd() {
    if (!addName.trim()) return;
    setAdding(true);
    setAddError("");
    try {
      await addPlatformCredential({ platform: addPlatform, name: addName.trim() });
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
      await deletePlatformCredential(name);
      setConfirmDelete(null);
      await load();
    } catch {
      // silent
    } finally {
      setDeleting(false);
    }
  }

  async function handleValidate(name: string) {
    setValidating((prev) => ({ ...prev, [name]: true }));
    try {
      const res = await validatePlatformCredential(name);
      setValidationResult((prev) => ({ ...prev, [name]: res }));
    } catch (e) {
      setValidationResult((prev) => ({ ...prev, [name]: { valid: false, error: e instanceof Error ? e.message : "Validation failed" } }));
    } finally {
      setValidating((prev) => ({ ...prev, [name]: false }));
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Platform Credentials</h2>
          <p className="text-sm text-muted-foreground">App-level credentials for each platform (API keys, client secrets).</p>
        </div>
        <button
          onClick={() => setAddOpen(true)}
          className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-foreground hover:bg-accent/80"
        >
          Add Credential
        </button>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : credentials.length === 0 ? (
        <div className="rounded-lg border-2 border-dashed border-border p-6 text-center">
          <p className="text-sm text-muted-foreground">No platform credentials configured.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {credentials.map((cred) => (
            <div key={cred.name} className="flex items-center justify-between rounded-lg border border-border p-4">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-medium">{cred.name}</span>
                  <span className="rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
                    {cred.platform}
                  </span>
                  {validationResult[cred.name] && (
                    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      validationResult[cred.name].valid
                        ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400"
                        : "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400"
                    }`}>
                      {validationResult[cred.name].valid ? "valid" : "invalid"}
                    </span>
                  )}
                </div>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Added {new Date(cred.created_at).toLocaleDateString()}
                </p>
                {validationResult[cred.name]?.error && (
                  <p className="mt-1 text-xs text-destructive">{validationResult[cred.name].error}</p>
                )}
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleValidate(cred.name)}
                  disabled={validating[cred.name]}
                  className="rounded-md border border-border px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted disabled:opacity-50"
                >
                  {validating[cred.name] ? "..." : "Validate"}
                </button>
                <button
                  onClick={() => setConfirmDelete(cred.name)}
                  className="rounded-md border border-red-300 px-3 py-1.5 text-sm font-medium text-red-600 transition-colors hover:bg-red-50 dark:border-red-700 dark:text-red-400 dark:hover:bg-red-900/20"
                >
                  Remove
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add modal */}
      <Modal open={addOpen} onClose={() => setAddOpen(false)} maxWidth="max-w-sm">
        <h3 className="text-sm font-semibold">Add Platform Credential</h3>
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
            <label className="mb-1 block text-sm font-medium">Name</label>
            <input
              type="text"
              value={addName}
              onChange={(e) => setAddName(e.target.value)}
              placeholder="e.g. x-main"
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
            {adding ? "Adding..." : "Add"}
          </button>
        </div>
      </Modal>

      {/* Delete confirmation */}
      <Modal open={!!confirmDelete} onClose={() => setConfirmDelete(null)} maxWidth="max-w-sm">
        <h3 className="text-sm font-semibold">Remove Credential</h3>
        <p className="mt-2 text-sm text-muted-foreground">
          Remove credential &ldquo;{confirmDelete}&rdquo;? This will fail if accounts still reference it.
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
