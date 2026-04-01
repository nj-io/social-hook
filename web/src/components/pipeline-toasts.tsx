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
        // Pipeline stage events — maps to PipelineStage constants from models/enums.py
        const stageMessages: Record<string, string> = {
          discovering: "Generating project brief",
          analyzing: "Analyzing commit",
          evaluating: "Evaluating strategies",
          deciding: "Processing decision",
          drafting: "Drafting content",
          promoting: "Scheduling draft",
          queued: "Commit queued for batch evaluation",
        };
        const msg = stageMessages[data.action];
        if (msg) {
          addToast(msg, { detail: data.entity_id });
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
      }
      // Decision status changes are NOT toasted — they are implementation details.
      // Pipeline stage events (ANALYZING, EVALUATING, DRAFTING, QUEUED) provide
      // user-facing feedback. The commit log auto-refreshes via useDataEvents.
      // Entity CRUD events (topic, target, suggestion, cycle) are NOT handled here.
      // Those get feedback from their respective component handlers via addToast.
      // PipelineToasts is for background pipeline status only.
    };

    addListener("pipeline-toasts", handler);
    return () => removeListener("pipeline-toasts");
  }, [addListener, removeListener, addToast]);

  return null;
}
