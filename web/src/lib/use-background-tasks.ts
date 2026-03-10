import { useCallback, useEffect, useRef, useState } from "react";
import { useGateway } from "@/lib/gateway-context";
import type { GatewayEnvelope } from "@/lib/websocket";
import type { DataChangeEvent } from "@/lib/types";
import { fetchTasks, type BackgroundTask } from "@/lib/api";

/**
 * Tracks background tasks for a given project via DB polling + WebSocket events.
 *
 * On mount, queries running tasks to restore state (survives page refresh).
 * Listens for "task" data_change events to update when tasks complete/fail.
 *
 * Returns a map of ref_id -> BackgroundTask for running/recently-completed tasks,
 * plus a helper to start tracking a newly-created task.
 */
export function useBackgroundTasks(
  projectId: string,
  onTaskCompleted?: (task: BackgroundTask) => void,
) {
  const [tasks, setTasks] = useState<Map<string, BackgroundTask>>(new Map());
  const { addListener, removeListener } = useGateway();
  const onCompletedRef = useRef(onTaskCompleted);
  onCompletedRef.current = onTaskCompleted;

  const refreshTasks = useCallback(async () => {
    try {
      const { tasks: allTasks } = await fetchTasks({ project_id: projectId });
      // Deduplicate: keep only the newest task per ref_id.
      // API returns ORDER BY created_at DESC, so first seen = newest.
      const seen = new Set<string>();
      const latestTasks: BackgroundTask[] = [];
      for (const t of allTasks) {
        if (seen.has(t.ref_id)) continue;
        seen.add(t.ref_id);
        latestTasks.push(t);
      }
      setTasks((prev) => {
        const next = new Map(prev);
        for (const t of latestTasks) {
          const existing = next.get(t.ref_id);
          // Only update if we're tracking this ref_id or it's running
          if (existing || t.status === "running") {
            next.set(t.ref_id, t);
          }
        }
        // Fire callback for tasks that just completed
        for (const t of latestTasks) {
          const existing = prev.get(t.ref_id);
          if (existing?.status === "running" && t.status !== "running") {
            onCompletedRef.current?.(t);
          }
        }
        return next;
      });
    } catch {
      // Non-critical
    }
  }, [projectId]);

  // On mount: restore running tasks from DB
  useEffect(() => {
    fetchTasks({ project_id: projectId, status: "running" })
      .then(({ tasks: running }) => {
        if (running.length > 0) {
          setTasks(new Map(running.map((t) => [t.ref_id, t])));
        }
      })
      .catch(() => {});
  }, [projectId]);

  // Listen for task events via WebSocket
  useEffect(() => {
    const listenerId = `bg-tasks-${projectId}`;

    addListener(listenerId, (envelope: GatewayEnvelope) => {
      if (envelope.type !== "event") return;
      const payload = envelope.payload as Record<string, unknown>;
      if (payload.type !== "data_change") return;
      const data = payload.data as DataChangeEvent | undefined;
      if (!data) return;
      if (data.entity !== "task") return;
      if (data.project_id && data.project_id !== projectId) return;
      // A task changed — refresh from DB to get full state
      refreshTasks();
    });

    return () => removeListener(listenerId);
  }, [projectId, addListener, removeListener, refreshTasks]);

  /** Register a task_id + ref_id that was just kicked off via a 202 response. */
  const trackTask = useCallback((taskId: string, refId: string, type: string) => {
    setTasks((prev) => {
      const next = new Map(prev);
      next.set(refId, {
        id: taskId,
        type,
        ref_id: refId,
        project_id: projectId,
        status: "running",
        result: null,
        error: null,
        created_at: new Date().toISOString(),
        updated_at: null,
      });
      return next;
    });
    // The task may have already completed before trackTask was called
    // (race: background thread finishes before the 202 response arrives).
    // Refresh immediately to catch the completion.
    refreshTasks();
  }, [projectId, refreshTasks]);

  /** Stop tracking a ref_id (e.g. after processing a completion). */
  const clearTask = useCallback((refId: string) => {
    setTasks((prev) => {
      const next = new Map(prev);
      next.delete(refId);
      return next;
    });
  }, []);

  const isRunning = useCallback(
    (refId: string) => tasks.get(refId)?.status === "running",
    [tasks],
  );

  const getTask = useCallback(
    (refId: string) => tasks.get(refId) ?? null,
    [tasks],
  );

  return { tasks, trackTask, clearTask, isRunning, getTask, refreshTasks };
}
