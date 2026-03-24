"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import type { EvaluationCycle, CycleStrategyOutcome } from "@/lib/types";
import { fetchCycles, approveAllCycleDrafts } from "@/lib/api";
import { useDataEvents } from "@/lib/use-data-events";
import { Badge } from "@/components/ui/badge";

export function EvaluationCycles({ projectId }: { projectId: string }) {
  const [cycles, setCycles] = useState<EvaluationCycle[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedCycles, setExpandedCycles] = useState<Set<string>>(new Set());
  const [expandAll, setExpandAll] = useState(false);
  const [approvingCycle, setApprovingCycle] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetchCycles(projectId);
      setCycles(res.cycles);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { load(); }, [load]);
  useDataEvents(["cycle", "draft", "decision"], load, projectId);

  function toggleCycle(id: string) {
    setExpandedCycles((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function handleExpandAll() {
    if (expandAll) {
      setExpandedCycles(new Set());
    } else {
      setExpandedCycles(new Set(cycles.map((c) => c.id)));
    }
    setExpandAll(!expandAll);
  }

  async function handleApproveAll(cycleId: string) {
    setApprovingCycle(cycleId);
    try {
      await approveAllCycleDrafts(projectId, cycleId);
      await load();
    } catch {
      // silent — data events will refresh
    } finally {
      setApprovingCycle(null);
    }
  }

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading evaluation cycles...</p>;
  }

  if (cycles.length === 0) {
    return <p className="text-sm text-muted-foreground">No evaluation cycles yet.</p>;
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Evaluation Cycles</h2>
        <div className="flex items-center gap-3">
          <button
            onClick={handleExpandAll}
            className="text-xs text-accent hover:underline"
          >
            {expandAll ? "Collapse All" : "Expand All"}
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-border text-xs text-muted-foreground">
              <th className="pb-2 pr-4 font-medium">Trigger</th>
              <th className="pb-2 pr-4 font-medium">Strategies</th>
              <th className="pb-2 pr-4 font-medium">Status</th>
              <th className="pb-2 font-medium">Time</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {cycles.map((cycle) => {
              const isExpanded = expandedCycles.has(cycle.id);
              const strategyEntries = Object.entries(cycle.strategies || {});
              return (
                <tr
                  key={cycle.id}
                  className="group cursor-pointer hover:bg-muted/30"
                  onClick={() => toggleCycle(cycle.id)}
                >
                  <td className="py-3 pr-4">
                    <span className="text-sm">{cycle.trigger}</span>
                    {isExpanded && strategyEntries.length > 0 && (
                      <div className="mt-3 space-y-3">
                        {strategyEntries.map(([stratName, outcome]) => (
                          <StrategyOutcomeCard
                            key={stratName}
                            strategy={stratName}
                            outcome={outcome}
                            projectId={projectId}
                          />
                        ))}
                        {strategyEntries.some(([, o]) => o.draft_id && o.draft_status === "draft") && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleApproveAll(cycle.id);
                            }}
                            disabled={approvingCycle === cycle.id}
                            className="mt-2 rounded bg-emerald-600 px-3 py-1 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                          >
                            {approvingCycle === cycle.id ? "Approving..." : "Approve All"}
                          </button>
                        )}
                      </div>
                    )}
                  </td>
                  <td className="py-3 pr-4">
                    <div className="flex flex-wrap gap-1">
                      {strategyEntries.map(([name, outcome]) => (
                        <span
                          key={name}
                          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                            outcome.decision === "draft"
                              ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400"
                              : outcome.decision === "hold"
                              ? "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400"
                              : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400"
                          }`}
                        >
                          {name}: {outcome.decision}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="py-3 pr-4">
                    <Badge value={cycle.status} variant="status" />
                  </td>
                  <td className="py-3 text-xs text-muted-foreground">
                    {new Date(cycle.created_at).toLocaleString()}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StrategyOutcomeCard({
  strategy,
  outcome,
  projectId,
}: {
  strategy: string;
  outcome: CycleStrategyOutcome;
  projectId: string;
}) {
  return (
    <div className="rounded-md border border-border bg-muted/30 p-3" onClick={(e) => e.stopPropagation()}>
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">{strategy}</span>
        <Badge value={outcome.decision} variant="decision" />
      </div>
      {outcome.reasoning && (
        <p className="mt-1 text-xs text-muted-foreground">{outcome.reasoning}</p>
      )}
      <div className="mt-2 space-y-1 text-xs">
        {outcome.topic_matched && (
          <p><span className="text-muted-foreground">Topic: </span>{outcome.topic_matched}</p>
        )}
        {outcome.arc_reference && (
          <p><span className="text-muted-foreground">Arc: </span>{outcome.arc_reference}</p>
        )}
        {outcome.content_source && (
          <p><span className="text-muted-foreground">Source: </span>{outcome.content_source}</p>
        )}
        {outcome.draft_id && (
          <div className="mt-2">
            <Link
              href={`/drafts/${outcome.draft_id}`}
              className="text-accent hover:underline"
            >
              View draft
            </Link>
            {outcome.draft_status && (
              <span className="ml-2">
                <Badge value={outcome.draft_status} variant="status" />
              </span>
            )}
            {outcome.draft_content && (
              <p className="mt-1 rounded border border-border bg-background p-2 text-xs">
                {outcome.draft_content.slice(0, 200)}
                {outcome.draft_content.length > 200 ? "..." : ""}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
