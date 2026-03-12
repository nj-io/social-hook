"use client";

import { useEffect } from "react";
import { useGateway } from "@/lib/gateway-context";
import { useToast } from "@/lib/toast-context";
import type { GatewayEnvelope } from "@/lib/websocket";
import type { DataChangeEvent } from "@/lib/types";

/** Headless listener — feeds pipeline/draft WebSocket events into the shared toast system. */
export function PipelineToasts() {
  const { addListener, removeListener } = useGateway();
  const { addToast } = useToast();

  useEffect(() => {
    const handler = (envelope: GatewayEnvelope) => {
      // Server wraps web_events as: { type: "event", payload: { type: "data_change", data: {...} } }
      const inner = envelope.payload as Record<string, unknown>;
      if (envelope.type !== "event" || inner?.type !== "data_change") return;
      const data = inner.data as DataChangeEvent;

      if (data.entity === "pipeline") {
        if (data.action === "evaluating") {
          addToast("Evaluating commit", { detail: data.entity_id });
        } else if (data.action === "drafting") {
          addToast("Drafting content", { detail: data.entity_id });
        }
      } else if (data.entity === "draft" && data.action === "created") {
        const platform = data.platform ? ` (${data.platform})` : "";
        const preview = data.content ? data.content.slice(0, 80) : "";
        addToast(`Draft created${platform}`, { detail: preview });
      } else if (data.entity === "decision") {
        addToast(`Decision: ${data.action}`, { detail: data.entity_id });
      }
    };

    addListener("pipeline-toasts", handler);
    return () => removeListener("pipeline-toasts");
  }, [addListener, removeListener, addToast]);

  return null;
}
