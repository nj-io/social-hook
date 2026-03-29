"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useGateway } from "@/lib/gateway-context";
import type { GatewayEnvelope } from "@/lib/websocket";
import type { DataChangeEvent } from "@/lib/types";

const ACTIVE_ACTIONS = new Set(["discovering", "analyzing", "evaluating", "drafting", "started", "created"]);
const DONE_ACTIONS = new Set(["completed", "failed"]);
const SHOW_AFTER_MS = 5_000;
const HIDE_AFTER_MS = 5_000;

/**
 * Pulsing dot in the center of the nav bar. Only visible when a background
 * task has been running for 5+ seconds. Fades out 5s after last event or
 * on task completion. Links to /system.
 */
export function ActivityIndicator() {
  const [active, setActive] = useState(false);
  const { addListener, removeListener } = useGateway();

  const firstEventRef = useRef<number | null>(null);
  const showTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const handler = (envelope: GatewayEnvelope) => {
      if (envelope.type !== "event") return;
      const payload = envelope.payload as Record<string, unknown>;
      if (payload.type !== "data_change") return;
      const data = payload.data as DataChangeEvent | undefined;
      if (!data) return;

      const isStart =
        (data.entity === "pipeline" && ACTIVE_ACTIONS.has(data.action)) ||
        (data.entity === "task" && ACTIVE_ACTIONS.has(data.action));

      const isDone =
        (data.entity === "pipeline" && DONE_ACTIONS.has(data.action)) ||
        (data.entity === "task" && DONE_ACTIONS.has(data.action));

      if (isStart) {
        // Reset hide timer on every activity event
        if (hideTimerRef.current) {
          clearTimeout(hideTimerRef.current);
          hideTimerRef.current = null;
        }

        // Start show timer on first event — only show after 5s sustained
        if (firstEventRef.current === null) {
          firstEventRef.current = Date.now();
          showTimerRef.current = setTimeout(() => {
            setActive(true);
          }, SHOW_AFTER_MS);
        }

        // Auto-hide if no events for 5s
        hideTimerRef.current = setTimeout(() => {
          firstEventRef.current = null;
          setActive(false);
        }, HIDE_AFTER_MS);
      } else if (isDone) {
        firstEventRef.current = null;
        if (showTimerRef.current) {
          clearTimeout(showTimerRef.current);
          showTimerRef.current = null;
        }
        if (hideTimerRef.current) {
          clearTimeout(hideTimerRef.current);
          hideTimerRef.current = null;
        }
        setActive(false);
      }
    };

    addListener("activity-indicator", handler);
    return () => {
      removeListener("activity-indicator");
      if (showTimerRef.current) clearTimeout(showTimerRef.current);
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    };
  }, [addListener, removeListener]);

  return (
    <Link
      href="/system"
      aria-label="System activity"
      title="Pipeline running — click to view"
      className={`transition-opacity duration-500 ease-in-out ${active ? "opacity-100" : "pointer-events-none opacity-0"}`}
    >
      <span className="relative block h-2.5 w-2.5">
        <span className="absolute inset-0 rounded-full bg-accent" />
        <span className="absolute inset-0 animate-ping rounded-full bg-accent/40" />
      </span>
    </Link>
  );
}
