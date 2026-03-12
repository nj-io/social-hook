/**
 * Reconnecting WebSocket client for the gateway.
 *
 * WS URL derived from window.location — works regardless of how the app is served.
 * Cannot use NEXT_PUBLIC_API_URL because it's a build-time constant and may be undefined.
 */

export interface GatewayEnvelope {
  type: string;
  payload: Record<string, unknown>;
  id?: string;
  channel?: string;
  timestamp?: string;
  reply_to?: string;
}

function getWsUrl(): string {
  if (typeof window === "undefined") return "";
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const apiPort = process.env.NEXT_PUBLIC_API_PORT || "8741";
  return `${proto}//${window.location.hostname}:${apiPort}/ws`;
}

let envelopeCounter = 0;
function nextEnvelopeId(): string {
  return `ws-${Date.now()}-${++envelopeCounter}`;
}

export class GatewayClient {
  private ws: WebSocket | null = null;
  private reconnectTimeout: ReturnType<typeof setTimeout> | undefined;
  private url: string;
  private shouldReconnect = true;

  constructor(
    private onEvent: (envelope: GatewayEnvelope) => void,
    private onStatusChange?: (connected: boolean) => void,
  ) {
    this.url = getWsUrl();
  }

  connect(): void {
    if (!this.url) return;
    this.shouldReconnect = true;

    try {
      this.ws = new WebSocket(this.url);
    } catch {
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this.onStatusChange?.(true);
    };

    this.ws.onmessage = (e) => {
      try {
        const envelope: GatewayEnvelope = JSON.parse(e.data);
        this.onEvent(envelope);
      } catch {
        // Ignore unparseable messages
      }
    };

    this.ws.onclose = () => {
      this.onStatusChange?.(false);
      if (this.shouldReconnect) {
        this.scheduleReconnect();
      }
    };

    this.ws.onerror = () => {
      // onclose will fire after onerror
    };
  }

  disconnect(): void {
    this.shouldReconnect = false;
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = undefined;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  send(envelope: GatewayEnvelope): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(envelope));
    }
  }

  sendCommand(command: string, text: string, extra?: Record<string, unknown>): void {
    this.send({
      type: "command",
      payload: { command, text, ...extra },
      id: nextEnvelopeId(),
    });
  }

  subscribe(channel: string, lastSeenId?: number): void {
    this.send({
      type: "subscribe",
      payload: { channel, ...(lastSeenId ? { last_seen_id: lastSeenId } : {}) },
      id: nextEnvelopeId(),
    });
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimeout) return;
    this.reconnectTimeout = setTimeout(() => {
      this.reconnectTimeout = undefined;
      this.connect();
    }, 3000);
  }
}
