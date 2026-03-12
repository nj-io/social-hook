import { useEffect, useRef } from "react";
import { useGateway } from "@/lib/gateway-context";
import type { GatewayEnvelope } from "@/lib/websocket";
import type { DataChangeEvent } from "@/lib/types";

export function useDataEvents(
  entities: string[],
  onDataChange: () => void,
  projectId?: string,
): void {
  const { addListener, removeListener } = useGateway();
  const callbackRef = useRef(onDataChange);
  callbackRef.current = onDataChange;

  const entitiesKey = entities.join(",");

  useEffect(() => {
    const listenerId = `data-events-${entitiesKey}-${projectId ?? "all"}`;
    let timer: ReturnType<typeof setTimeout> | undefined;

    addListener(listenerId, (envelope: GatewayEnvelope) => {
      if (envelope.type !== "event") return;
      const payload = envelope.payload as Record<string, unknown>;
      if (payload.type !== "data_change") return;
      const data = payload.data as DataChangeEvent | undefined;
      if (!data) return;
      if (!entities.includes(data.entity)) return;
      if (projectId && data.project_id && data.project_id !== projectId) return;

      // Debounce: collapse rapid events into one refetch
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        callbackRef.current();
      }, 500);
    });

    return () => {
      removeListener(listenerId);
      if (timer) clearTimeout(timer);
    };
  }, [entitiesKey, projectId, addListener, removeListener]);
}
