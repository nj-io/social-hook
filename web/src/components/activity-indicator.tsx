"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useGateway } from "@/lib/gateway-context";
import type { GatewayEnvelope } from "@/lib/websocket";
import type { DataChangeEvent } from "@/lib/types";

const ACTIVE_ACTIONS = new Set(["discovering", "analyzing", "evaluating", "drafting", "started", "created"]);
const DONE_ACTIONS = new Set(["completed", "failed"]);
const DEBOUNCE_IN_MS = 5_000;
const TIMEOUT_MS = 5_000;

/**
 * Small pulsing dot in the nav bar that indicates LLM activity.
 *
 * Activates after 5s of sustained pipeline/task events, deactivates
 * 5s after last event or on task completion. Links to /system.
 */
export function ActivityIndicator() {
  const [active, setActive] = useState(false);
  const [visible, setVisible] = useState(false);
  const { addListener, removeListener } = useGateway();

  const firstEventRef = useRef<number | null>(null);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const timeoutTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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
        // Reset inactivity timeout on every activity event
        if (timeoutTimerRef.current) {
          clearTimeout(timeoutTimerRef.current);
          timeoutTimerRef.current = null;
        }

        // Start debounce-in timer on first event
        if (firstEventRef.current === null) {
          firstEventRef.current = Date.now();
          debounceTimerRef.current = setTimeout(() => {
            setActive(true);
          }, DEBOUNCE_IN_MS);
        }

        // Set inactivity timeout — if no events for 5s, deactivate
        timeoutTimerRef.current = setTimeout(() => {
          firstEventRef.current = null;
          setActive(false);
        }, TIMEOUT_MS);
      } else if (isDone) {
        // Clear everything on completion
        firstEventRef.current = null;
        if (debounceTimerRef.current) {
          clearTimeout(debounceTimerRef.current);
          debounceTimerRef.current = null;
        }
        if (timeoutTimerRef.current) {
          clearTimeout(timeoutTimerRef.current);
          timeoutTimerRef.current = null;
        }
        setActive(false);
      }
    };

    addListener("activity-indicator", handler);
    return () => {
      removeListener("activity-indicator");
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
      if (timeoutTimerRef.current) clearTimeout(timeoutTimerRef.current);
    };
  }, [addListener, removeListener]);

  // Smooth fade: delay visibility change so CSS transition can run
  useEffect(() => {
    if (active) {
      setVisible(true);
    } else {
      // Keep visible briefly for fade-out, then hide
      const t = setTimeout(() => setVisible(false), 600);
      return () => clearTimeout(t);
    }
  }, [active]);

  return (
    <Link
      href="/system"
      aria-label="System activity"
      title={active ? "Pipeline running — click to view" : "System status"}
    >
      <span
        className="relative block h-2.5 w-2.5 rounded-full transition-opacity duration-500 ease-in-out"
        style={{ opacity: visible ? 1 : 0.3 }}
      >
        {/* Base dot */}
        <span
          className={`absolute inset-0 rounded-full transition-colors duration-500 ${
            active ? "bg-accent" : "bg-muted-foreground/40"
          }`}
        />
        {/* Pulse ring — only when active */}
        {active && (
          <span className="absolute inset-0 animate-ping rounded-full bg-accent/40" />
        )}
      </span>
    </Link>
  );
}
