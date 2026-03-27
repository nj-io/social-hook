"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchSystemEvents, type SystemEvent } from "@/lib/api";
import { useDataEvents } from "@/lib/use-data-events";

const ENTITY_STYLES: Record<string, string> = {
  pipeline: "text-blue-700 dark:text-blue-400",
  decision: "text-emerald-700 dark:text-emerald-400",
  task: "text-purple-700 dark:text-purple-400",
  draft: "text-amber-700 dark:text-amber-400",
  topic: "text-indigo-700 dark:text-indigo-400",
  cycle: "text-cyan-700 dark:text-cyan-400",
};

const ACTION_LABELS: Record<string, string> = {
  discovering: "Generating project brief",
  analyzing: "Analyzing commit",
  evaluating: "Evaluating strategies",
  drafting: "Drafting content",
  promoting: "Scheduling draft",
  queued: "Commit queued",
};

function formatTime(isoStr: string): string {
  try {
    const d = new Date(isoStr.endsWith("Z") ? isoStr : isoStr + "Z");
    return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return isoStr;
  }
}

export function EventLog() {
  const [events, setEvents] = useState<SystemEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [entityFilter, setEntityFilter] = useState("");

  const load = useCallback(async () => {
    try {
      const res = await fetchSystemEvents({
        entity: entityFilter || undefined,
        limit: 50,
      });
      setEvents(res.events);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [entityFilter]);

  useEffect(() => { load(); }, [load]);

  // Auto-refresh on any data change event
  useDataEvents(["pipeline", "decision", "task", "draft", "topic", "cycle"], load);

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading events...</p>;
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Event Log</h3>
        <select
          value={entityFilter}
          onChange={(e) => setEntityFilter(e.target.value)}
          className="h-7 rounded-md border border-border bg-background px-2 text-xs"
        >
          <option value="">All events</option>
          <option value="pipeline">Pipeline</option>
          <option value="decision">Decisions</option>
          <option value="task">Tasks</option>
          <option value="draft">Drafts</option>
          <option value="topic">Topics</option>
          <option value="cycle">Cycles</option>
        </select>
      </div>

      {events.length === 0 ? (
        <p className="text-xs text-muted-foreground">No recent events.</p>
      ) : (
        <div className="max-h-80 overflow-y-auto rounded-md border border-border">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-background">
              <tr className="border-b border-border text-left">
                <th className="px-2 py-1.5 font-medium">Time</th>
                <th className="px-2 py-1.5 font-medium">Entity</th>
                <th className="px-2 py-1.5 font-medium">Action</th>
                <th className="px-2 py-1.5 font-medium">ID</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.id} className="border-b border-border/50 hover:bg-muted/30">
                  <td className="px-2 py-1 text-muted-foreground">{formatTime(e.created_at)}</td>
                  <td className={`px-2 py-1 font-medium ${ENTITY_STYLES[e.entity] ?? "text-foreground"}`}>
                    {e.entity}
                  </td>
                  <td className="px-2 py-1">
                    {e.entity === "pipeline" ? (ACTION_LABELS[e.action] ?? e.action) : e.action}
                  </td>
                  <td className="px-2 py-1 font-mono text-muted-foreground">
                    {e.entity_id ? e.entity_id.slice(0, 16) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
