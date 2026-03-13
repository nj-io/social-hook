"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { GatewayClient, type GatewayEnvelope } from "@/lib/websocket";

interface GatewayContextValue {
  connected: boolean;
  send: (envelope: GatewayEnvelope) => void;
  sendCommand: (command: string, text: string, extra?: Record<string, unknown>) => void;
  subscribe: (channel: string, lastSeenId?: number) => void;
  addListener: (id: string, handler: (envelope: GatewayEnvelope) => void) => void;
  removeListener: (id: string) => void;
}

const GatewayContext = createContext<GatewayContextValue | null>(null);

export function GatewayProvider({ children }: { children: ReactNode }) {
  const [connected, setConnected] = useState(false);
  const clientRef = useRef<GatewayClient | null>(null);
  const listenersRef = useRef<Map<string, (envelope: GatewayEnvelope) => void>>(new Map());

  useEffect(() => {
    const client = new GatewayClient(
      (envelope: GatewayEnvelope) => {
        // Auto-reload on DB restore (snapshot restore via API)
        if (envelope.type === "event") {
          const payload = envelope.payload as Record<string, unknown>;
          if (payload.type === "data_change") {
            const data = payload.data as Record<string, unknown> | undefined;
            if (data?.entity === "system" && data?.action === "db_restored") {
              window.location.reload();
              return;
            }
          }
        }
        for (const handler of listenersRef.current.values()) {
          try { handler(envelope); } catch { /* ignore listener errors */ }
        }
      },
      (isConnected: boolean) => {
        setConnected(isConnected);
      },
    );
    clientRef.current = client;
    client.connect();

    return () => {
      client.disconnect();
      clientRef.current = null;
    };
  }, []);

  const send = useCallback((envelope: GatewayEnvelope) => {
    clientRef.current?.send(envelope);
  }, []);

  const sendCommand = useCallback((command: string, text: string, extra?: Record<string, unknown>) => {
    clientRef.current?.sendCommand(command, text, extra);
  }, []);

  const subscribe = useCallback((channel: string, lastSeenId?: number) => {
    clientRef.current?.subscribe(channel, lastSeenId);
  }, []);

  const addListener = useCallback((id: string, handler: (envelope: GatewayEnvelope) => void) => {
    listenersRef.current.set(id, handler);
  }, []);

  const removeListener = useCallback((id: string) => {
    listenersRef.current.delete(id);
  }, []);

  const value = useMemo<GatewayContextValue>(() => ({
    connected, send, sendCommand, subscribe, addListener, removeListener,
  }), [connected, send, sendCommand, subscribe, addListener, removeListener]);

  return <GatewayContext.Provider value={value}>{children}</GatewayContext.Provider>;
}

export function useGateway(): GatewayContextValue {
  const ctx = useContext(GatewayContext);
  if (!ctx) throw new Error("useGateway must be used within GatewayProvider");
  return ctx;
}
