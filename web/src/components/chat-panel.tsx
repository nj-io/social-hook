"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { WebEvent, DataChangeEvent } from "@/lib/types";
import { clearChatHistory, fetchChatHistory } from "@/lib/api";
import { useGateway } from "@/lib/gateway-context";
import { useToast } from "@/lib/toast-context";
import { getSessionId } from "@/lib/session";
import { ButtonRow } from "./button-row";

export function ChatPanel() {
  const [events, setEvents] = useState<WebEvent[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const chatTaskIdRef = useRef<string | null>(null);
  const lastIdRef = useRef(0);
  const listRef = useRef<HTMLDivElement>(null);
  const { connected, send, sendCommand, addListener, removeListener } = useGateway();
  const { addToast } = useToast();

  const addEvents = useCallback((newEvents: WebEvent[]) => {
    setEvents((prev) => {
      const existing = new Set(prev.map((e) => e.id));
      const unique = newEvents.filter((e) => !existing.has(e.id));
      if (unique.length === 0) return prev;
      const merged = [...prev, ...unique];
      merged.sort((a, b) => a.id - b.id);
      return merged;
    });
  }, []);

  // Load chat history on mount
  useEffect(() => {
    let cancelled = false;
    async function init() {
      try {
        const { events: history } = await fetchChatHistory();
        if (cancelled) return;
        const chatEvents = history.filter((e) => e.type !== "data_change");
        if (chatEvents.length > 0) {
          setEvents(chatEvents);
          lastIdRef.current = chatEvents[chatEvents.length - 1].id;
        }
      } catch {
        // History unavailable — WS will catch up
      }
    }
    init();
    return () => { cancelled = true; };
  }, []);

  // Register listener for chat events
  useEffect(() => {
    addListener("chat-panel", (envelope) => {
      // Track background task from ack with task_id
      if (envelope.type === "ack" && envelope.payload?.task_id) {
        chatTaskIdRef.current = envelope.payload.task_id as string;
      }
      if (envelope.type === "event" && envelope.payload) {
        const ev = envelope.payload as unknown as WebEvent;
        // Handle task completion/failure for tracked chat tasks
        if (ev.type === "data_change") {
          const data = ev.data as unknown as DataChangeEvent | undefined;
          if (data?.entity === "task" && data.entity_id === chatTaskIdRef.current) {
            if (data.action === "completed" || data.action === "failed") {
              chatTaskIdRef.current = null;
              setSending(false);
              if (data.action === "failed") {
                addToast("Message failed", { variant: "error" });
              }
            }
          }
          return; // data_change events handled by useDataEvents
        }
        if (ev.id) {
          if (ev.id > lastIdRef.current) lastIdRef.current = ev.id;
          addEvents([ev]);
        }
      }
    });
    return () => {
      removeListener("chat-panel");
    };
  }, [addListener, removeListener, addEvents]);

  // Subscribe on connect for gap-free delivery, including session_id for scoped routing
  useEffect(() => {
    if (connected) {
      send({
        type: "subscribe",
        payload: {
          channel: "web",
          session_id: getSessionId(),
          ...(lastIdRef.current ? { last_seen_id: lastIdRef.current } : {}),
        },
      });
    }
  }, [connected, send]);

  // Auto-scroll
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [events]);

  async function handleSend() {
    const text = input.trim();
    if (!text || sending) return;

    setInput("");
    setSending(true);

    // Optimistic user message
    const tempId = -(Date.now());
    setEvents((prev) => [
      ...prev,
      { id: tempId, type: "user", data: { text }, created_at: new Date().toISOString() },
    ]);

    try {
      const command = text.startsWith("/") ? "send_command" : "send_message";
      sendCommand(command, text);
      // For send_message: sending stays true until background task completes (via ack listener)
      // For send_command: no background task, clear sending immediately
      if (command === "send_command") {
        setSending(false);
      }
      // send_message: setSending(false) happens in the ack/task-completion listener
    } catch {
      setSending(false);
    }
  }

  function renderEvent(event: WebEvent) {
    const data = event.data;
    if (!data.text && event.type !== "user") return null;
    const text = (data.text as string) ?? JSON.stringify(data);
    const buttons = data.buttons as { label: string; action: string; payload: string }[][] | undefined;
    const isUser = event.type === "user";

    return (
      <div key={event.id} className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
        <div
          className={`max-w-[85%] rounded-lg p-3 ${
            isUser
              ? "bg-accent text-accent-foreground"
              : "border border-border"
          }`}
        >
          <div className={`mb-1 flex items-center text-xs ${isUser ? "justify-end gap-2 text-accent-foreground/70" : "justify-between text-muted-foreground"}`}>
            <span className="font-medium">{isUser ? "you" : event.type}</span>
            <span>{new Date(event.created_at).toLocaleTimeString()}</span>
          </div>
          <p className="whitespace-pre-wrap text-sm">{text}</p>
          {buttons && buttons.length > 0 && (
            <div className="mt-2">
              <ButtonRow buttons={buttons} onEvents={(evts) => addEvents(evts as WebEvent[])} />
            </div>
          )}
        </div>
      </div>
    );
  }

  async function handleClear() {
    try {
      await clearChatHistory();
      setEvents([]);
      lastIdRef.current = 0;
    } catch {
      // ignore
    }
  }

  return (
    <div className="flex h-full flex-col">
      {events.length > 0 && (
        <div className="flex items-center justify-end gap-2 border-b border-border px-4 py-2">
          <span
            className={`h-2 w-2 rounded-full ${connected ? "bg-green-500" : "bg-red-500"}`}
            title={connected ? "Connected" : "Disconnected"}
          />
          <button
            onClick={handleClear}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            Clear history
          </button>
        </div>
      )}
      <div ref={listRef} className="flex-1 space-y-3 overflow-y-auto p-4">
        {events.length === 0 && (
          <p className="text-center text-sm text-muted-foreground">
            No messages yet. Send a command to get started.
          </p>
        )}
        {events.map(renderEvent)}
      </div>
      <div className="border-t border-border p-4">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="flex gap-2"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type a command (/help) or message..."
            className="flex-1 rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
            disabled={sending}
          />
          <button
            type="submit"
            disabled={sending || !input.trim()}
            className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-foreground transition-colors hover:bg-accent/80 disabled:opacity-50"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
