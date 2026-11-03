"""Reconnection, restored subscriptions, and cancellation guarantees."""

import asyncio
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from aiohttp import web

from custom_components.aqara_studio.api import AqaraStudioClient
from custom_components.aqara_studio.websocket import AqaraWebSocket, reconnect_delay


def test_backoff_grows_is_capped_and_jittered():
    with patch(
        "custom_components.aqara_studio.websocket.random.uniform", return_value=1.0
    ):
        assert reconnect_delay(0) == 1
        assert reconnect_delay(3) == 8
        assert reconnect_delay(100) == 120
    for attempt in range(10):
        assert (
            0.8 * min(120, 2 ** min(attempt, 7))
            <= reconnect_delay(attempt)
            <= 1.2 * min(120, 2 ** min(attempt, 7))
        )


async def test_disconnect_reconnect_resubscribes_and_reconciles(
    aiohttp_server, socket_enabled
):
    subscriptions = 0
    connection_events = []
    reconnected = asyncio.Event()

    async def handler(request):
        nonlocal subscriptions
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for message in ws:
            payload = message.json()
            assert payload["type"] == "SubscribeAllRequest"
            subscriptions += 1
            await ws.send_json(
                {
                    "type": "SubscribeAllResponse",
                    "version": "v1",
                    "msgId": payload["msgId"],
                    "code": 0,
                    "data": None,
                }
            )
            if subscriptions == 1:
                await ws.close()
        return ws

    async def on_connection(value):
        connection_events.append(value)
        if value and subscriptions == 2:
            reconnected.set()

    app = web.Application()
    app.router.add_get("/open/ws", handler)
    server = await aiohttp_server(app)
    async with aiohttp.ClientSession() as session:
        with patch(
            "custom_components.aqara_studio.websocket.reconnect_delay",
            return_value=0.01,
        ):
            transport = AqaraWebSocket(
                AqaraStudioClient(session, str(server.make_url("")), "synthetic-token"),
                AsyncMock(),
                AsyncMock(),
                on_connection,
            )
            asyncio.create_task(transport.async_run())
            try:
                await asyncio.wait_for(reconnected.wait(), 2)
                assert subscriptions == 2
                assert connection_events[:3] == [True, False, True]
                assert transport.reconnect_attempts == 1
            finally:
                await transport.async_stop()
            assert connection_events[-1] is False


async def test_stop_interrupts_long_reconnect_backoff():
    async with aiohttp.ClientSession() as session:
        transport = AqaraWebSocket(
            AqaraStudioClient(session, "http://studio.example", "synthetic-token"),
            AsyncMock(),
            AsyncMock(),
            AsyncMock(),
        )
        attempted = asyncio.Event()

        async def disconnect():
            attempted.set()
            raise TimeoutError

        with (
            patch.object(transport, "_connect_once", side_effect=disconnect),
            patch(
                "custom_components.aqara_studio.websocket.reconnect_delay",
                return_value=120,
            ),
        ):
            task = asyncio.create_task(transport.async_run())
            await attempted.wait()
            await asyncio.wait_for(transport.async_stop(), 1)
            assert task.done()
            assert not transport.connected


async def test_second_runner_is_rejected():
    async with aiohttp.ClientSession() as session:
        transport = AqaraWebSocket(
            AqaraStudioClient(session, "http://studio.example", "synthetic-token"),
            AsyncMock(),
            AsyncMock(),
            AsyncMock(),
        )
        attempted = asyncio.Event()

        async def block():
            attempted.set()
            await asyncio.Event().wait()

        with patch.object(transport, "_connect_once", side_effect=block):
            asyncio.create_task(transport.async_run())
            await attempted.wait()
            try:
                with pytest.raises(RuntimeError, match="already running"):
                    await transport.async_run()
            finally:
                await transport.async_stop()
