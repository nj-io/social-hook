"""Reusable WebSocket gateway: hub, envelope, and transport protocol.

Zero project-specific imports — only stdlib + typing. Copy-paste safe.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class GatewayTransport(Protocol):
    """Protocol for WebSocket-like transports."""

    async def send_json(self, data: Any, **kwargs: Any) -> None: ...
    async def receive_json(self, **kwargs: Any) -> Any: ...


@dataclass
class GatewayEnvelope:
    """Protocol-agnostic message envelope."""

    type: str  # "event", "command", "subscribe", "unsubscribe", "ack", "error"
    payload: dict  # Type-specific data
    id: str = ""  # Auto-generated UUID if empty
    channel: str = ""  # Routing channel
    timestamp: str = ""  # ISO 8601
    reply_to: str = ""  # ID of envelope this replies to

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    @classmethod
    def from_dict(cls, data: dict) -> "GatewayEnvelope":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


class GatewayConnection:
    """Wraps a transport connection with metadata."""

    def __init__(
        self, client_id: str, transport: GatewayTransport, channels: list[str] | None = None
    ):
        self.client_id = client_id
        self.transport = transport
        self.channels: set[str] = set(channels or [])


class GatewayHub:
    """Manages WebSocket connections and message routing.

    Designed for asyncio single-event-loop use. The async lock protects
    dict mutation in connect/disconnect/broadcast/send. The synchronous
    subscribe/unsubscribe/connection_count methods are safe because asyncio
    is cooperative — no concurrent mutation can occur mid-call.
    """

    def __init__(self):
        self._connections: dict[str, GatewayConnection] = {}
        self._lock = asyncio.Lock()

    async def connect(
        self, transport: GatewayTransport, client_id: str, channels: list[str] | None = None
    ) -> GatewayConnection:
        conn = GatewayConnection(client_id, transport, channels)
        async with self._lock:
            self._connections[client_id] = conn
        return conn

    async def disconnect(self, client_id: str) -> None:
        async with self._lock:
            self._connections.pop(client_id, None)

    async def broadcast(self, envelope: GatewayEnvelope, channel: str | None = None) -> None:
        data = envelope.to_dict()
        async with self._lock:
            targets = list(self._connections.values())
        for conn in targets:
            if channel and channel not in conn.channels:
                continue
            try:
                await conn.transport.send_json(data)
            except Exception:
                logger.debug("Failed to send to %s", conn.client_id)

    async def send(self, client_id: str, envelope: GatewayEnvelope) -> None:
        async with self._lock:
            conn = self._connections.get(client_id)
        if conn:
            try:
                await conn.transport.send_json(envelope.to_dict())
            except Exception:
                logger.debug("Failed to send to %s", client_id)

    def subscribe(self, client_id: str, channel: str) -> None:
        conn = self._connections.get(client_id)
        if conn:
            conn.channels.add(channel)

    def unsubscribe(self, client_id: str, channel: str) -> None:
        conn = self._connections.get(client_id)
        if conn:
            conn.channels.discard(channel)

    @property
    def connection_count(self) -> int:
        return len(self._connections)
