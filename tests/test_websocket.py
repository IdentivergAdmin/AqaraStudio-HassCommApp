"""Exercise real aiohttp WebSocket frames against a loopback-only test server."""

import asyncio
from unittest.mock import AsyncMock

import aiohttp
import pytest
from aiohttp import web

from custom_components.aqara_studio.api import (
    AqaraAuthError,
    AqaraResponseError,
    AqaraStudioClient,
)
from custom_components.aqara_studio.websocket import AqaraWebSocket

ADDRESS = {
    "deviceId": "synthetic-door-1",
    "endpointId": 1,
    "functionCode": "Contact",
    "traitCode": "ContactSensorState",
}


def response(request, message_type, *, code=0):
    return {
        "type": message_type,
        "version": "v1",
        "msgId": request["msgId"],
        "code": code,
        "data": "pong" if message_type == "pong" else None,
        "message": "",
    }


async def test_header_auth_subscription_push_and_keepalive(
    aiohttp_server, socket_enabled
):
    received = []
    callbacks = []
    pinged = asyncio.Event()
    update_seen = asyncio.Event()
    object_seen = asyncio.Event()

    async def handler(request):
        assert request.headers["Authorization"] == "Bearer synthetic-token"
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for message in ws:
            payload = message.json()
            received.append(payload)
            if payload["type"] == "SubscribeAllRequest":
                assert payload["data"] is None
                # A device-add push can arrive immediately after authentication,
                # before subscription confirmation or the REST snapshot finishes.
                await ws.send_json(
                    {
                        "type": "objectEvent",
                        "version": "v1",
                        "msgId": "push-1",
                        "code": 0,
                        "data": {
                            "eventType": "DEVICE_ADDED",
                            "objectId": "synthetic-door-1",
                            "time": 1,
                            "data": {"deviceId": "synthetic-door-1"},
                        },
                    }
                )
                await ws.send_json(response(payload, "SubscribeAllResponse"))
                await ws.send_json(
                    {
                        "type": "TraitValueUpdate",
                        "version": "v1",
                        "msgId": "push-2",
                        "code": 0,
                        "data": [dict(ADDRESS, value=False, time=0)],
                    }
                )
            elif payload["type"] == "ping":
                await ws.send_json(response(payload, "pong"))
                pinged.set()
        return ws

    async def on_update(updates):
        callbacks.append("update")
        assert updates == [dict(ADDRESS, value=False, time=0)]
        update_seen.set()

    async def on_object(event):
        callbacks.append("object")
        assert event["eventType"] == "DEVICE_ADDED"
        object_seen.set()

    async def on_connection(connected):
        callbacks.append("snapshot" if connected else "disconnected")
        if connected:
            assert not update_seen.is_set()
            assert not object_seen.is_set()
            await asyncio.sleep(0)

    app = web.Application()
    app.router.add_get("/open/ws", handler)
    server = await aiohttp_server(app)
    async with aiohttp.ClientSession() as session:
        client = AqaraStudioClient(session, str(server.make_url("")), "synthetic-token")
        transport = AqaraWebSocket(
            client, on_update, on_object, on_connection, heartbeat_interval=0.01
        )
        task = asyncio.create_task(transport.async_run())
        try:
            await asyncio.wait_for(update_seen.wait(), 2)
            await asyncio.wait_for(object_seen.wait(), 2)
            await asyncio.wait_for(pinged.wait(), 2)
            assert transport.connected
            assert transport.received_updates == 1
            assert callbacks[0] == "snapshot"
            assert received[0]["type"] == "SubscribeAllRequest"
            assert len({message["msgId"] for message in received}) == len(received)
        finally:
            await transport.async_stop()
        assert task.done()
        assert not transport.connected
        assert callbacks[-1] == "disconnected"
        assert transport._pending == {}
        assert not session.closed


async def test_first_message_auth_uses_bearer_and_precedes_subscribe(
    aiohttp_server, socket_enabled
):
    order = []
    connected = asyncio.Event()

    async def handler(request):
        assert "Authorization" not in request.headers
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for message in ws:
            payload = message.json()
            order.append(payload["type"])
            if payload["type"] == "AuthRequest":
                assert payload["data"] == {
                    "authType": "token",
                    "token": "Bearer synthetic-token",
                }
                await ws.send_json(response(payload, "AuthResponse"))
            elif payload["type"] == "SubscribeAllRequest":
                await ws.send_json(response(payload, "SubscribeAllResponse"))
        return ws

    async def on_connection(value):
        if value:
            connected.set()

    app = web.Application()
    app.router.add_get("/open/ws", handler)
    server = await aiohttp_server(app)
    async with aiohttp.ClientSession() as session:
        transport = AqaraWebSocket(
            AqaraStudioClient(session, str(server.make_url("")), "synthetic-token"),
            AsyncMock(),
            AsyncMock(),
            on_connection,
            auth_mode="message",
        )
        asyncio.create_task(transport.async_run())
        try:
            await asyncio.wait_for(connected.wait(), 2)
            assert order[:2] == ["AuthRequest", "SubscribeAllRequest"]
        finally:
            await transport.async_stop()


async def test_header_rejection_falls_back_to_message_auth(
    aiohttp_server, socket_enabled
):
    connections = []
    connected = asyncio.Event()

    async def handler(request):
        connections.append(
            "header" if request.headers.get("Authorization") else "message"
        )
        if request.headers.get("Authorization"):
            return web.Response(status=401)
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for message in ws:
            payload = message.json()
            await ws.send_json(
                response(
                    payload,
                    "AuthResponse"
                    if payload["type"] == "AuthRequest"
                    else "SubscribeAllResponse",
                )
            )
        return ws

    async def on_connection(value):
        if value:
            connected.set()

    app = web.Application()
    app.router.add_get("/open/ws", handler)
    server = await aiohttp_server(app)
    async with aiohttp.ClientSession() as session:
        transport = AqaraWebSocket(
            AqaraStudioClient(session, str(server.make_url("")), "synthetic-token"),
            AsyncMock(),
            AsyncMock(),
            on_connection,
        )
        asyncio.create_task(transport.async_run())
        try:
            await asyncio.wait_for(connected.wait(), 2)
            assert connections == ["header", "message"]
        finally:
            await transport.async_stop()


@pytest.mark.parametrize("reply_type", ["AuthResponse", "ErrorMessage"])
async def test_failed_auth_is_correlated_and_propagated(
    aiohttp_server, socket_enabled, reply_type
):
    async def handler(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for message in ws:
            payload = message.json()
            await ws.send_json(response(payload, reply_type, code=1234))
        return ws

    app = web.Application()
    app.router.add_get("/open/ws", handler)
    server = await aiohttp_server(app)
    async with aiohttp.ClientSession() as session:
        transport = AqaraWebSocket(
            AqaraStudioClient(session, str(server.make_url("")), "synthetic-token"),
            AsyncMock(),
            AsyncMock(),
            AsyncMock(),
            auth_mode="message",
        )
        with pytest.raises(AqaraAuthError) as error:
            await asyncio.wait_for(transport.async_run(), 2)
        assert "synthetic-token" not in str(error.value)
        assert not transport.connected
        assert transport._socket is None


async def test_subscription_error_message_not_mistaken_for_success(
    aiohttp_server, socket_enabled
):
    async def handler(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for message in ws:
            await ws.send_json(response(message.json(), "ErrorMessage", code=1234))
        return ws

    app = web.Application()
    app.router.add_get("/open/ws", handler)
    server = await aiohttp_server(app)
    async with aiohttp.ClientSession() as session:
        connection_callback = AsyncMock()
        transport = AqaraWebSocket(
            AqaraStudioClient(session, str(server.make_url("")), "synthetic-token"),
            AsyncMock(),
            AsyncMock(),
            connection_callback,
        )
        with pytest.raises(AqaraResponseError):
            await asyncio.wait_for(transport._connect_once(), 2)
        assert not transport.connected
        connection_callback.assert_not_awaited()


async def test_selective_subscription_contract(aiohttp_server, socket_enabled):
    connected = asyncio.Event()
    requests = []

    async def handler(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for message in ws:
            payload = message.json()
            requests.append(payload)
            await ws.send_json(
                response(payload, payload["type"].replace("Request", "Response"))
            )
        return ws

    async def on_connection(value):
        if value:
            connected.set()

    app = web.Application()
    app.router.add_get("/open/ws", handler)
    server = await aiohttp_server(app)
    async with aiohttp.ClientSession() as session:
        transport = AqaraWebSocket(
            AqaraStudioClient(session, str(server.make_url("")), "synthetic-token"),
            AsyncMock(),
            AsyncMock(),
            on_connection,
        )
        asyncio.create_task(transport.async_run())
        try:
            await asyncio.wait_for(connected.wait(), 2)
            await transport.async_subscribe_traits([ADDRESS])
            assert requests[-1]["type"] == "SubscribeTraitValueRequest"
            assert requests[-1]["data"] == [
                {
                    "deviceId": ADDRESS["deviceId"],
                    "endpointId": 1,
                    "functionCode": "Contact",
                    "traitCodes": ["ContactSensorState"],
                }
            ]
        finally:
            await transport.async_stop()


async def test_snapshot_buffer_flag_distinguishes_replay_from_live_push(
    aiohttp_server, socket_enabled
):
    first_seen = asyncio.Event()
    second_seen = asyncio.Event()
    send_live = asyncio.Event()
    flags = []

    async def handler(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for message in ws:
            payload = message.json()
            if payload["type"] != "SubscribeAllRequest":
                continue
            update = {
                "type": "TraitValueUpdate",
                "version": "v1",
                "code": 0,
                "msgId": "reused-trace-id",
                "data": [dict(ADDRESS, value=False, time=0)],
            }
            await ws.send_json(update)
            await ws.send_json(response(payload, "SubscribeAllResponse"))
            await send_live.wait()
            # msgId is tracing, not a unique event identity: both pushes arrive.
            await ws.send_json(update)
        return ws

    async def on_update(_):
        flags.append(transport.replaying_buffer)
        if len(flags) == 1:
            first_seen.set()
        else:
            second_seen.set()

    app = web.Application()
    app.router.add_get("/open/ws", handler)
    server = await aiohttp_server(app)
    async with aiohttp.ClientSession() as session:
        transport = AqaraWebSocket(
            AqaraStudioClient(session, str(server.make_url("")), "synthetic-token"),
            on_update,
            AsyncMock(),
            AsyncMock(),
        )
        asyncio.create_task(transport.async_run())
        try:
            await asyncio.wait_for(first_seen.wait(), 2)
            assert not transport.replaying_buffer
            send_live.set()
            await asyncio.wait_for(second_seen.wait(), 2)
            assert flags == [True, False]
            assert not transport.replaying_buffer
        finally:
            send_live.set()
            await transport.async_stop()
