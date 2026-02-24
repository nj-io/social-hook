"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { WebEvent } from "@/lib/types";
import { clearChatHistory, fetchChatHistory, sendCommand, sendMessage } from "@/lib/api";
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
      if (unique.length === 0) return prev;
      const merged = [...prev, ...unique];
      merged.sort((a, b) => a.id - b.id);
      return merged;
    });
  }, []);

  // Load history on mount, then start SSE for live updates
  useEffect(() => {
    let cancelled = false;

    async function init() {
      try {
        const { events: history } = await fetchChatHistory();
        if (cancelled) return;
        if (history.length > 0) {
          setEvents(history);
          lastIdRef.current = history[history.length - 1].id;
        }
      } catch {
        // History unavailable — SSE will catch up
      }
      if (!cancelled) connect();
    }

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
    }

    init();

    return () => {
      cancelled = true;
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

    // Show user message instantly while POST blocks for LLM response
    const tempId = -(Date.now());
    setEvents((prev) => [
      ...prev,
      { id: tempId, type: "user", data: { text }, created_at: new Date().toISOString() },
    ]);

    try {
      const result = text.startsWith("/")
        ? await sendCommand(text)
        : await sendMessage(text);
      // Replace optimistic event with real persisted events
      setEvents((prev) => {
        const withoutTemp = prev.filter((e) => e.id !== tempId);
        const existing = new Set(withoutTemp.map((e) => e.id));
        const unique = result.events.filter((e) => !existing.has(e.id));
        const merged = [...withoutTemp, ...unique];
        merged.sort((a, b) => a.id - b.id);
        // Update lastIdRef so SSE doesn't re-fetch these
        for (const ev of unique) {
          if (ev.id > lastIdRef.current) lastIdRef.current = ev.id;
        }
        return merged;
      });
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
        <div className="flex justify-end border-b border-border px-4 py-2">
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
