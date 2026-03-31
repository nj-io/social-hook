import { useCallback, useEffect, useRef, useState } from "react";
import { useGateway } from "@/lib/gateway-context";
import type { GatewayEnvelope } from "@/lib/websocket";
import type { DataChangeEvent } from "@/lib/types";
import { fetchTasks, type BackgroundTask } from "@/lib/api";

/** Default client-side timeout: 10 minutes (matches backend _STALE_TASK_TIMEOUT_SECONDS). */
const DEFAULT_TIMEOUT_MS = 600_000;

/** How often to check for timed-out tasks (seconds). */
const TIMEOUT_CHECK_INTERVAL_MS = 5_000;

interface TrackOptions {
  /** Client-side timeout in ms. Default: 600_000 (10 min). */
  timeoutMs?: number;
}

/** Internal tracking entry: the task plus its timeout deadline. */
interface TrackedEntry {
  task: BackgroundTask;
  deadlineMs: number;
}

/**
 * Tracks background tasks for a given project via DB polling + WebSocket events.
 *
 * On mount, queries running tasks to restore state (survives page refresh).
 * Listens for "task" data_change events to update when tasks complete/fail.
 *
 * Returns a map of ref_id -> BackgroundTask for running/recently-completed tasks,
 * plus a helper to start tracking a newly-created task.
 *
 * IMPORTANT: Tasks are keyed and deduplicated by ref_id. If two different task
 * types share the same ref_id and run concurrently, only one will be tracked.
 * Prefix ref_id with the task type when this is possible (e.g. "summary:proj_123").
 */
export function useBackgroundTasks(
  projectId: string,
  onTaskCompleted?: (task: BackgroundTask) => void,
) {
  const [tasks, setTasks] = useState<Map<string, BackgroundTask>>(new Map());
  const { addListener, removeListener } = useGateway();
  const onCompletedRef = useRef(onTaskCompleted);
  onCompletedRef.current = onTaskCompleted;

  // Ref that bridges React state batching: trackTask writes here immediately
  // so refreshTasks can see tracked tasks even before React applies setTasks.
  const trackedRef = useRef<Map<string, TrackedEntry>>(new Map());

  const fireCompleted = useCallback((task: BackgroundTask) => {
    onCompletedRef.current?.(task);
  }, []);

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
        // Merge trackedRef into prev so we detect transitions even when
        // React batched the trackTask setTasks with this one.
        const merged = new Map(prev);
        for (const [refId, entry] of trackedRef.current) {
          if (!merged.has(refId)) {
            merged.set(refId, entry.task);
          }
        }

        const next = new Map(merged);
        for (const t of latestTasks) {
          const existing = next.get(t.ref_id);
          // Only update if we're tracking this ref_id or it's running
          if (existing || t.status === "running") {
            // Preserve in-memory stage data (not stored in DB)
            next.set(t.ref_id, {
              ...t,
              current_stage: existing?.current_stage,
              stage_label: existing?.stage_label,
              stage_started_at: existing?.stage_started_at,
            });
          }
        }
        // Fire callback for tasks that just completed
        for (const t of latestTasks) {
          const existing = merged.get(t.ref_id);
          if (existing?.status === "running" && t.status !== "running") {
            fireCompleted(t);
          }
        }
        return next;
      });
    } catch {
      // Non-critical
    }
  }, [projectId, fireCompleted]);

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

      if (data.action === "stage") {
        // Stage change — update in-memory (no DB round-trip)
        setTasks((prev) => {
          const next = new Map(prev);
          for (const [refId, task] of next) {
            if (task.id === data.entity_id) {
              next.set(refId, {
                ...task,
                current_stage: data.stage,
                stage_label: data.stage_label,
                stage_started_at: new Date().toISOString(),
              });
              break;
            }
          }
          return next;
        });
      } else {
        // started/completed/failed — full refetch from DB
        refreshTasks();
      }
    });

    return () => removeListener(listenerId);
  }, [projectId, addListener, removeListener, refreshTasks]);

  // Client-side timeout: periodically check tracked tasks against deadlines
  useEffect(() => {
    const id = setInterval(() => {
      const now = Date.now();
      for (const [refId, entry] of trackedRef.current) {
        if (entry.task.status === "running" && now >= entry.deadlineMs) {
          const timedOut: BackgroundTask = {
            ...entry.task,
            status: "failed",
            error: "Operation timed out. You can retry from the dashboard.",
            updated_at: new Date().toISOString(),
          };
          trackedRef.current.set(refId, { ...entry, task: timedOut });
          setTasks((prev) => {
            const next = new Map(prev);
            next.set(refId, timedOut);
            return next;
          });
          fireCompleted(timedOut);
        }
      }
    }, TIMEOUT_CHECK_INTERVAL_MS);
    return () => clearInterval(id);
  }, [fireCompleted]);

  /** Register a task_id + ref_id that was just kicked off via a 202 response. */
  const trackTask = useCallback(
    (taskId: string, refId: string, type: string, opts?: TrackOptions) => {
      const timeoutMs = opts?.timeoutMs ?? DEFAULT_TIMEOUT_MS;
      const entry: TrackedEntry = {
        task: {
          id: taskId,
          type,
          ref_id: refId,
          project_id: projectId,
          status: "running",
          result: null,
          error: null,
          created_at: new Date().toISOString(),
          updated_at: null,
        },
        deadlineMs: Date.now() + timeoutMs,
      };
      trackedRef.current.set(refId, entry);
      setTasks((prev) => {
        const next = new Map(prev);
        next.set(refId, entry.task);
        return next;
      });
      // The task may have already completed before trackTask was called
      // (race: background thread finishes before the 202 response arrives).
      // Refresh immediately to catch the completion.
      refreshTasks();
    },
    [projectId, refreshTasks],
  );

  /** Stop tracking a ref_id (e.g. after processing a completion). */
  const clearTask = useCallback((refId: string) => {
    trackedRef.current.delete(refId);
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
