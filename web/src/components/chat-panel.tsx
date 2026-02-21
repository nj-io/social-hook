"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { WebEvent } from "@/lib/types";
import { sendCommand, sendMessage } from "@/lib/api";
import { ButtonRow } from "./button-row";

export function ChatPanel() {
  const [events, setEvents] = useState<WebEvent[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const lastIdRef = useRef(0);
  const listRef = useRef<HTMLDivElement>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const addEvents = useCallback((newEvents: WebEvent[]) => {
    setEvents((prev) => {
      const existing = new Set(prev.map((e) => e.id));
      const unique = newEvents.filter((e) => !existing.has(e.id));
      return [...prev, ...unique];
    });
  }, []);

  // SSE connection with auto-reconnect
  useEffect(() => {
    let cancelled = false;

    function connect() {
      const eventSource = new EventSource(`/api/events?lastId=${lastIdRef.current}`);

      eventSource.onmessage = (e) => {
        try {
          const event: WebEvent = JSON.parse(e.data);
          lastIdRef.current = event.id;
          addEvents([event]);
        } catch {
          // Ignore parse errors from keepalive
        }
      };

      eventSource.onerror = () => {
        eventSource.close();
        if (!cancelled) {
          reconnectTimeoutRef.current = setTimeout(connect, 3000);
        }
      };

      return eventSource;
    }

    const es = connect();

    return () => {
      cancelled = true;
      es.close();
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [addEvents]);

  // Auto-scroll to bottom
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

    try {
      const result = text.startsWith("/")
        ? await sendCommand(text)
        : await sendMessage(text);
      addEvents(result.events);
    } catch {
      // Error will appear in chat if server responds
    } finally {
      setSending(false);
    }
  }

  function renderEvent(event: WebEvent) {
    const data = event.data;
    const text = (data.text as string) ?? JSON.stringify(data);
    const buttons = data.buttons as { label: string; action: string; payload: string }[][] | undefined;

    return (
      <div key={event.id} className="rounded-lg border border-border p-3">
        <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
          <span className="font-medium">{event.type}</span>
          <span>{new Date(event.created_at).toLocaleTimeString()}</span>
        </div>
        <p className="whitespace-pre-wrap text-sm">{text}</p>
        {buttons && buttons.length > 0 && (
          <div className="mt-2">
            <ButtonRow buttons={buttons} onEvents={(evts) => addEvents(evts as WebEvent[])} />
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
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
