"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useGateway } from "@/lib/gateway-context";
import type { GatewayEnvelope } from "@/lib/websocket";
import type { DataChangeEvent } from "@/lib/types";

interface Toast {
  id: string;
  message: string;
  detail?: string;
  ts: number;
}

const TOAST_TTL = 6000;

export function PipelineToasts() {
  const { addListener, removeListener } = useGateway();
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counterRef = useRef(0);

  const addToast = useCallback((message: string, detail?: string) => {
    const id = `toast-${++counterRef.current}`;
    setToasts((prev) => [...prev, { id, message, detail, ts: Date.now() }]);
  }, []);

  // Expire old toasts
  useEffect(() => {
    if (toasts.length === 0) return;
    const timer = setInterval(() => {
      setToasts((prev) => prev.filter((t) => Date.now() - t.ts < TOAST_TTL));
    }, 1000);
    return () => clearInterval(timer);
  }, [toasts.length]);

  // Listen for pipeline/draft events
  useEffect(() => {
    const handler = (envelope: GatewayEnvelope) => {
      // Server wraps web_events as: { type: "event", payload: { type: "data_change", data: {...} } }
      const inner = envelope.payload as Record<string, unknown>;
      if (envelope.type !== "event" || inner?.type !== "data_change") return;
      const data = inner.data as DataChangeEvent;

      if (data.entity === "pipeline") {
        if (data.action === "evaluating") {
          addToast("Evaluating commit", data.entity_id);
        } else if (data.action === "drafting") {
          addToast("Drafting content", data.entity_id);
        }
      } else if (data.entity === "draft" && data.action === "created") {
        const platform = data.platform ? ` (${data.platform})` : "";
        const preview = data.content ? data.content.slice(0, 80) : "";
        addToast(`Draft created${platform}`, preview);
      } else if (data.entity === "decision") {
        addToast(`Decision: ${data.action}`, data.entity_id);
      }
    };

    addListener("pipeline-toasts", handler);
    return () => removeListener("pipeline-toasts");
  }, [addListener, removeListener, addToast]);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className="bg-zinc-900 border border-zinc-700 text-zinc-100 rounded-lg px-4 py-3 shadow-lg animate-in slide-in-from-right"
          role="status"
        >
          <p className="text-sm font-medium">{toast.message}</p>
          {toast.detail && (
            <p className="text-xs text-zinc-400 mt-1 truncate">{toast.detail}</p>
          )}
        </div>
      ))}
    </div>
  );
}
