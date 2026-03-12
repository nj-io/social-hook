"""Tests for the WebSocket gateway hub and envelope."""

from unittest.mock import AsyncMock

import pytest

pytest_asyncio = pytest.importorskip("pytest_asyncio", reason="pytest-asyncio required")

from social_hook.messaging.gateway import GatewayEnvelope, GatewayHub  # noqa: E402


class TestGatewayEnvelope:
    def test_auto_id(self):
        env = GatewayEnvelope(type="event", payload={"key": "val"})
        assert env.id  # non-empty
        assert len(env.id) == 36  # UUID format

    def test_auto_timestamp(self):
        env = GatewayEnvelope(type="event", payload={})
        assert env.timestamp
        assert "T" in env.timestamp  # ISO format

    def test_explicit_id_preserved(self):
        env = GatewayEnvelope(type="event", payload={}, id="my-id")
        assert env.id == "my-id"

    def test_serialization_round_trip(self):
        env = GatewayEnvelope(type="event", payload={"foo": "bar"}, channel="web")
        d = env.to_dict()
        restored = GatewayEnvelope.from_dict(d)
        assert restored.type == "event"
        assert restored.payload == {"foo": "bar"}
        assert restored.channel == "web"

    def test_from_dict_ignores_unknown(self):
        d = {"type": "event", "payload": {}, "unknown_field": 123}
        env = GatewayEnvelope.from_dict(d)
        assert env.type == "event"


@pytest.fixture
def hub():
    return GatewayHub()


def _mock_transport():
    t = AsyncMock()
    t.send_json = AsyncMock()
    return t


class TestGatewayHub:
    @pytest.mark.asyncio
    async def test_connect_disconnect(self, hub):
        t = _mock_transport()
        conn = await hub.connect(t, "c1", channels=["web"])
        assert hub.connection_count == 1
        assert conn.client_id == "c1"
        await hub.disconnect("c1")
        assert hub.connection_count == 0

    @pytest.mark.asyncio
    async def test_broadcast_to_channel(self, hub):
        t1 = _mock_transport()
        t2 = _mock_transport()
        await hub.connect(t1, "c1", channels=["web"])
        await hub.connect(t2, "c2", channels=["telegram"])
        env = GatewayEnvelope(type="event", payload={"msg": "hello"})
        await hub.broadcast(env, channel="web")
        t1.send_json.assert_called_once()
        t2.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_broadcast_all(self, hub):
        t1 = _mock_transport()
        t2 = _mock_transport()
        await hub.connect(t1, "c1", channels=["web"])
        await hub.connect(t2, "c2", channels=["telegram"])
        env = GatewayEnvelope(type="event", payload={})
        await hub.broadcast(env)  # no channel filter
        t1.send_json.assert_called_once()
        t2.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_to_specific_client(self, hub):
        t1 = _mock_transport()
        t2 = _mock_transport()
        await hub.connect(t1, "c1")
        await hub.connect(t2, "c2")
        env = GatewayEnvelope(type="ack", payload={})
        await hub.send("c1", env)
        t1.send_json.assert_called_once()
        t2.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_subscribe_unsubscribe(self, hub):
        t = _mock_transport()
        await hub.connect(t, "c1", channels=["web"])
        hub.subscribe("c1", "system")
        env = GatewayEnvelope(type="event", payload={})
        await hub.broadcast(env, channel="system")
        assert t.send_json.call_count == 1
        hub.unsubscribe("c1", "system")
        await hub.broadcast(env, channel="system")
        assert t.send_json.call_count == 1  # no new calls

    @pytest.mark.asyncio
    async def test_connection_count(self, hub):
        assert hub.connection_count == 0
        t = _mock_transport()
        await hub.connect(t, "c1")
        assert hub.connection_count == 1
        await hub.connect(_mock_transport(), "c2")
        assert hub.connection_count == 2
        await hub.disconnect("c1")
        assert hub.connection_count == 1
