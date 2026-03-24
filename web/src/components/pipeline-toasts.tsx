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
      } else if (data.entity === "draft") {
        const platform = data.platform ? ` (${data.platform})` : "";
        const preview = data.content ? data.content.slice(0, 80) : "";
        const toastMap: Record<string, { msg: string; variant?: "success" }> = {
          created: { msg: "Draft created" },
          edited: { msg: "Draft edited" },
          approved: { msg: "Draft approved", variant: "success" },
          scheduled: { msg: "Draft scheduled", variant: "success" },
          cancelled: { msg: "Draft cancelled" },
          rejected: { msg: "Draft rejected" },
          unapproved: { msg: "Approval reverted" },
          unscheduled: { msg: "Schedule reverted" },
          reopened: { msg: "Draft reopened" },
        };
        const entry = toastMap[data.action];
        if (entry) {
          addToast(`${entry.msg}${platform}`, { detail: preview, variant: entry.variant });
        }
      } else if (data.entity === "decision") {
        addToast(`Decision: ${data.action}`, { detail: data.entity_id });
      } else if (data.entity === "target") {
        const actionLabels: Record<string, string> = {
          created: "Target added", disabled: "Target disabled", enabled: "Target enabled",
        };
        const msg = actionLabels[data.action] ?? `Target ${data.action}`;
        addToast(msg, { detail: data.entity_id });
      } else if (data.entity === "topic") {
        const actionLabels: Record<string, string> = {
          created: "Topic added", updated: "Topic updated", reordered: "Topics reordered",
        };
        const msg = actionLabels[data.action] ?? `Topic ${data.action}`;
        addToast(msg, { detail: data.entity_id });
      } else if (data.entity === "suggestion") {
        const actionLabels: Record<string, string> = {
          created: "Suggestion submitted", dismissed: "Suggestion dismissed",
        };
        const msg = actionLabels[data.action] ?? `Suggestion ${data.action}`;
        addToast(msg, { detail: data.entity_id });
      } else if (data.entity === "cycle") {
        addToast("Evaluation cycle completed", { detail: data.entity_id });
      }
    };

    addListener("pipeline-toasts", handler);
    return () => removeListener("pipeline-toasts");
  }, [addListener, removeListener, addToast]);

  return null;
}
