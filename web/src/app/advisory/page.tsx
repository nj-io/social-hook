"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useDataEvents } from "@/lib/use-data-events";
import { useToast } from "@/lib/toast-context";
import { fetchAdvisoryItems, fetchProjects, updateAdvisoryItem } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Modal } from "@/components/ui/modal";
import type { Project } from "@/lib/types";

interface AdvisoryItem {
  id: string;
  project_id: string;
  category: string;
  title: string;
  description: string | null;
  status: string;
  urgency: string;
  created_by: string;
  linked_entity_type: string | null;
  linked_entity_id: string | null;
  handler_type: string | null;
  automation_level: string;
  verification_method: string | null;
  due_date: string | null;
  dismissed_reason: string | null;
  completed_at: string | null;
  created_at: string | null;
}

const categoryLabels: Record<string, string> = {
  platform_presence: "Platform",
  product_infrastructure: "Infrastructure",
  content_asset: "Content",
  code_change: "Code",
  external_action: "External",
  outreach: "Outreach",
};

const urgencyStyles: Record<string, string> = {
  blocking: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  normal: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
};

const statusStyles: Record<string, string> = {
  pending: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
  completed: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  dismissed: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
};

export default function AdvisoryPage() {
  const [items, setItems] = useState<AdvisoryItem[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [filterProject, setFilterProject] = useState("");
  const [filterStatus, setFilterStatus] = useState("pending");
  const [filterCategory, setFilterCategory] = useState("");
  const [filterUrgency, setFilterUrgency] = useState("");
  const [dismissItem, setDismissItem] = useState<AdvisoryItem | null>(null);
  const [dismissReason, setDismissReason] = useState("");
  const [dismissing, setDismissing] = useState(false);
  const { addToast } = useToast();

  const load = useCallback(async () => {
    const data = await fetchAdvisoryItems({
      project_id: filterProject || undefined,
      status: filterStatus || undefined,
      category: filterCategory || undefined,
      urgency: filterUrgency || undefined,
    });
    setItems((data.advisory_items || []) as unknown as AdvisoryItem[]);
  }, [filterProject, filterStatus, filterCategory, filterUrgency]);

  useEffect(() => {
    fetchProjects()
      .then((d) => setProjects(d.projects || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useDataEvents(["advisory"], load);

  async function handleComplete(item: AdvisoryItem) {
    try {
      await updateAdvisoryItem(item.id, { status: "completed" });
      addToast("Advisory completed", { variant: "success" });
      load();
    } catch {
      addToast("Failed to complete advisory", { variant: "error" });
    }
  }

  async function handleDismiss() {
    if (!dismissItem) return;
    setDismissing(true);
    try {
      await updateAdvisoryItem(dismissItem.id, {
        status: "dismissed",
        dismissed_reason: dismissReason || undefined,
      });
      setDismissItem(null);
      setDismissReason("");
      addToast("Advisory dismissed", {});
      load();
    } catch {
      addToast("Failed to dismiss advisory", { variant: "error" });
    } finally {
      setDismissing(false);
    }
  }

  const projectMap = Object.fromEntries(projects.map((p) => [p.id, p.name]));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Advisory Items</h1>
        <p className="text-muted-foreground">
          Action items that need your attention — manual posts, platform setup, and more.
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <select
          value={filterProject}
          onChange={(e) => setFilterProject(e.target.value)}
          className="rounded border border-border bg-background px-3 py-1.5 text-sm"
        >
          <option value="">All Projects</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
        <select
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
          className="rounded border border-border bg-background px-3 py-1.5 text-sm"
        >
          <option value="">All Statuses</option>
          <option value="pending">Pending</option>
          <option value="completed">Completed</option>
          <option value="dismissed">Dismissed</option>
        </select>
        <select
          value={filterCategory}
          onChange={(e) => setFilterCategory(e.target.value)}
          className="rounded border border-border bg-background px-3 py-1.5 text-sm"
        >
          <option value="">All Categories</option>
          {Object.entries(categoryLabels).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
        <select
          value={filterUrgency}
          onChange={(e) => setFilterUrgency(e.target.value)}
          className="rounded border border-border bg-background px-3 py-1.5 text-sm"
        >
          <option value="">All Urgencies</option>
          <option value="blocking">Blocking</option>
          <option value="normal">Normal</option>
        </select>
      </div>

      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">No advisory items match the current filters.</p>
      ) : (
        <div className="space-y-6">
          {/* Upcoming: pending items with future due_date */}
          {(() => {
            const now = new Date();
            const upcoming = items.filter(
              (i) => i.status === "pending" && i.due_date && new Date(i.due_date) > now
            );
            const rest = items.filter(
              (i) => !(i.status === "pending" && i.due_date && new Date(i.due_date) > now)
            );
            return (
              <>
                {upcoming.length > 0 && (
                  <div>
                    <h2 className="mb-3 text-sm font-semibold text-muted-foreground uppercase tracking-wide">Upcoming</h2>
                    <div className="space-y-3">
                      {upcoming.map((item) => (
                        <AdvisoryCard key={item.id} item={item} projectMap={projectMap} onComplete={handleComplete} onDismiss={setDismissItem} showCountdown />
                      ))}
                    </div>
                  </div>
                )}
                {rest.length > 0 && (
                  <div>
                    {upcoming.length > 0 && (
                      <h2 className="mb-3 text-sm font-semibold text-muted-foreground uppercase tracking-wide">Action Required</h2>
                    )}
                    <div className="space-y-3">
                      {rest.map((item) => (
                        <AdvisoryCard key={item.id} item={item} projectMap={projectMap} onComplete={handleComplete} onDismiss={setDismissItem} />
                      ))}
                    </div>
                  </div>
                )}
              </>
            );
          })()}
        </div>
      )}

      {dismissItem && (
        <Modal
          open={!!dismissItem}
          onClose={() => { setDismissItem(null); setDismissReason(""); }}
        >
          <h3 className="text-lg font-semibold mb-3">Dismiss Advisory</h3>
          <p className="mb-3 text-sm">Dismiss: {dismissItem.title}</p>
          <input
            type="text"
            placeholder="Reason (optional)"
            value={dismissReason}
            onChange={(e) => setDismissReason(e.target.value)}
            className="mb-4 w-full rounded border border-border bg-background px-3 py-2 text-sm"
          />
          <div className="flex justify-end gap-2">
            <button
              onClick={() => { setDismissItem(null); setDismissReason(""); }}
              disabled={dismissing}
              className="rounded border border-border px-4 py-2 text-sm hover:bg-muted disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              onClick={handleDismiss}
              disabled={dismissing}
              className="rounded bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
            >
              Dismiss
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function AdvisoryCard({
  item,
  projectMap,
  onComplete,
  onDismiss,
  showCountdown,
}: {
  item: AdvisoryItem;
  projectMap: Record<string, string>;
  onComplete: (item: AdvisoryItem) => void;
  onDismiss: (item: AdvisoryItem) => void;
  showCountdown?: boolean;
}) {
  return (
    <div className="rounded-lg border border-border p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex items-center gap-2">
            <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${statusStyles[item.status] || ""}`}>
              {item.status}
            </span>
            <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${urgencyStyles[item.urgency] || ""}`}>
              {item.urgency}
            </span>
            <Badge value={categoryLabels[item.category] || item.category} variant="category" />
            {projectMap[item.project_id] && (
              <span className="text-xs text-muted-foreground">{projectMap[item.project_id]}</span>
            )}
          </div>
          <p className="font-medium text-sm">{item.title}</p>
          {item.description && (
            <p className="mt-1 text-sm text-muted-foreground">{item.description}</p>
          )}
          {item.linked_entity_type === "draft" && item.linked_entity_id && (
            <Link href={`/drafts/${item.linked_entity_id}`} className="mt-1 inline-block text-xs text-accent hover:underline">
              View linked draft
            </Link>
          )}
          {item.linked_entity_type && item.linked_entity_type !== "draft" && item.linked_entity_id && (
            <p className="mt-1 text-xs text-muted-foreground">
              Linked: {item.linked_entity_type} {item.linked_entity_id.slice(0, 12)}
            </p>
          )}
          <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
            {item.created_at && <span>Created: {new Date(item.created_at).toLocaleString()}</span>}
            {item.due_date && <span>Due: {new Date(item.due_date).toLocaleString()}</span>}
            {showCountdown && item.due_date && <Countdown target={item.due_date} />}
          </div>
        </div>
        {item.status === "pending" && (
          <div className="flex shrink-0 gap-2">
            <button
              onClick={() => onComplete(item)}
              className="rounded bg-emerald-600 px-3 py-1 text-xs font-medium text-white hover:bg-emerald-700"
            >
              Complete
            </button>
            <button
              onClick={() => onDismiss(item)}
              className="rounded border border-border px-3 py-1 text-xs font-medium text-muted-foreground hover:bg-muted"
            >
              Dismiss
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function Countdown({ target }: { target: string }) {
  const [label, setLabel] = useState("");

  useEffect(() => {
    function update() {
      const diff = new Date(target).getTime() - Date.now();
      if (diff <= 0) {
        setLabel("now");
        return;
      }
      const hours = Math.floor(diff / 3600000);
      const minutes = Math.floor((diff % 3600000) / 60000);
      if (hours > 0) {
        setLabel(`in ${hours}h ${minutes}m`);
      } else {
        setLabel(`in ${minutes}m`);
      }
    }
    update();
    const timer = setInterval(update, 60000);
    return () => clearInterval(timer);
  }, [target]);

  if (!label) return null;
  return <span className="font-medium text-purple-600 dark:text-purple-400">{label}</span>;
}
