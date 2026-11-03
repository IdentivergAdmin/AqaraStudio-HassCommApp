"""Supervised WebSocket transport for Aqara Studio's published AsyncAPI.

Schema titles are not wire types: PingRequest is ``ping``, PongResponse is
``pong``, and ObjectEvent is ``objectEvent``. See docs/PROTOCOL.md.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any
from uuid import uuid4

import aiohttp

from .api import (
    AqaraAuthError,
    AqaraConnectionError,
    AqaraError,
    AqaraResponseError,
    AqaraStudioClient,
    group_trait_addresses,
    validate_address,
)

_LOGGER = logging.getLogger(__name__)
UpdateCallback = Callable[[list[dict[str, Any]]], Awaitable[None]]
ObjectCallback = Callable[[dict[str, Any]], Awaitable[None]]
ConnectionCallback = Callable[[bool], Awaitable[None]]


def reconnect_delay(attempt: int) -> float:
    """Exponential delay with jitter, capped below five minutes."""
    return min(120.0, 2.0 ** min(max(attempt, 0), 7)) * random.uniform(0.8, 1.2)


class AqaraWebSocket:
    """One reconnecting, cancellation-safe WebSocket client per config entry.

    ``on_connection(True)`` is awaited before dispatching buffered pushes. A
    coordinator can reconcile its REST snapshot in that callback, then merge
    buffered updates using vendor timestamps. Correlation IDs are for requests,
    not globally unique push-event identities.
    """

    def __init__(
        self,
        client: AqaraStudioClient,
        on_update: UpdateCallback,
        on_object_event: ObjectCallback,
        on_connection: ConnectionCallback,
        *,
        heartbeat_interval: float = 20,
        request_timeout: float = 10,
        auth_mode: str = "header",
    ) -> None:
        if auth_mode not in {"header", "message"}:
            raise ValueError("Invalid WebSocket authentication mode")
        if not 0 < heartbeat_interval < 30:
            raise ValueError("WebSocket keepalive must be below 30 seconds")
        self.client = client
        self._on_update = on_update
        self._on_object_event = on_object_event
        self._on_connection = on_connection
        self._heartbeat_interval = heartbeat_interval
        self._request_timeout = request_timeout
        self._auth_mode = auth_mode
        self._stop = asyncio.Event()
        self._ready = asyncio.Event()
        self._runner: asyncio.Task[Any] | None = None
        self._socket: aiohttp.ClientWebSocketResponse | None = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._pushes: asyncio.Queue[tuple[dict[str, Any], bool]] = asyncio.Queue(
            maxsize=2048
        )
        self.connected = False
        self.replaying_buffer = False
        self.reconnect_attempts = 0
        self.received_updates = 0
        self.ignored_messages = 0
        self.last_error: str | None = None
        self._connected_at: float | None = None

    async def async_run(self) -> None:
        """Run until stopped; propagate confirmed authentication failure."""
        if self._runner is not None and not self._runner.done():
            raise RuntimeError("Aqara WebSocket client already running")
        self._runner = asyncio.current_task()
        self._stop.clear()
        attempt = 0
        try:
            while not self._stop.is_set():
                try:
                    await self._connect_once()
                except asyncio.CancelledError:
                    raise
                except AqaraAuthError:
                    self.last_error = "authentication"
                    if self._auth_mode == "header":
                        # Some LAN deployments support first-message auth only.
                        self._auth_mode = "message"
                        continue
                    raise
                except AqaraError, aiohttp.ClientError, TimeoutError:
                    self.last_error = "connection"
                    if self._connected_at is None and self._auth_mode == "header":
                        self._auth_mode = "message"
                    _LOGGER.debug(
                        "Studio WebSocket unavailable; REST fallback remains active"
                    )
                if self._stop.is_set():
                    break
                if (
                    self._connected_at is not None
                    and asyncio.get_running_loop().time() - self._connected_at >= 60
                ):
                    attempt = 0
                self._connected_at = None
                self.reconnect_attempts += 1
                delay = reconnect_delay(attempt)
                attempt += 1
                with suppress(TimeoutError):
                    await asyncio.wait_for(self._stop.wait(), timeout=delay)
        finally:
            self._runner = None

    async def async_stop(self) -> None:
        """Close only this client's socket and await all its owned tasks."""
        self._stop.set()
        runner = self._runner
        if runner is not None and runner is not asyncio.current_task():
            runner.cancel()
            with suppress(asyncio.CancelledError, AqaraError):
                await runner
        elif self._socket is not None:
            await self._socket.close()

    async def _connect_once(self) -> None:
        """Authenticate, subscribe, reconcile, dispatch, and clean up one session."""
        tasks: list[asyncio.Task[Any]] = []
        self._ready.clear()
        self._pushes = asyncio.Queue(maxsize=2048)
        try:
            headers = (
                {"Authorization": self.client.authorization}
                if self._auth_mode == "header"
                else {}
            )
            try:
                async with asyncio.timeout(self._request_timeout):
                    self._socket = await self.client.session.ws_connect(
                        self.client.websocket_url,
                        headers=headers,
                        autoping=True,
                        max_msg_size=2 * 1024 * 1024,
                    )
            except aiohttp.WSServerHandshakeError as err:
                if err.status in (401, 403):
                    raise AqaraAuthError(
                        "Studio rejected WebSocket authentication"
                    ) from None
                raise AqaraConnectionError(
                    "Studio rejected the WebSocket connection"
                ) from None

            tasks.append(
                asyncio.create_task(self._receive(), name="aqara_studio_ws_receive")
            )
            tasks.append(
                asyncio.create_task(self._dispatch(), name="aqara_studio_ws_dispatch")
            )
            if self._auth_mode == "message":
                await self._request(
                    "AuthRequest",
                    {"authType": "token", "token": self.client.authorization},
                    "AuthResponse",
                    authentication=True,
                )
            await self._request("SubscribeAllRequest", None, "SubscribeAllResponse")
            self.connected = True
            self._connected_at = asyncio.get_running_loop().time()
            self.last_error = None
            tasks.append(
                asyncio.create_task(self._heartbeat(), name="aqara_studio_ws_heartbeat")
            )
            await self._on_connection(True)
            self._ready.set()
            finished, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in finished:
                task.result()
            raise AqaraConnectionError("Studio WebSocket closed")
        finally:
            was_connected = self.connected
            self.connected = False
            self._ready.clear()
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            for future in self._pending.values():
                if not future.done():
                    future.cancel()
            self._pending.clear()
            if self._socket is not None:
                await self._socket.close()
                self._socket = None
            if was_connected:
                await self._on_connection(False)

    async def _request(
        self,
        message_type: str,
        data: Any,
        expected_response: str,
        *,
        authentication: bool = False,
    ) -> dict[str, Any]:
        """Correlate all responses, including ErrorMessage, by msgId."""
        if self._socket is None:
            raise AqaraConnectionError("WebSocket is not connected")
        msg_id = uuid4().hex
        future = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = future
        try:
            await self._socket.send_json(
                {"type": message_type, "version": "v1", "msgId": msg_id, "data": data}
            )
            response = await asyncio.wait_for(future, timeout=self._request_timeout)
            code = response.get("code")
            if type(code) is not int:
                raise AqaraResponseError("WebSocket response has no valid status")
            if code != 0:
                if authentication or code in (401, 403):
                    raise AqaraAuthError(
                        "Studio rejected WebSocket authentication or scope"
                    )
                raise AqaraResponseError(
                    "Studio rejected a WebSocket request", code=code
                )
            if (
                response.get("type") != expected_response
                or response.get("version") != "v1"
            ):
                raise AqaraResponseError("Unexpected WebSocket response")
            return response
        finally:
            self._pending.pop(msg_id, None)

    async def async_subscribe_traits(self, addresses: list[dict[str, Any]]) -> None:
        """Add documented trait subscriptions when a caller uses selective mode.

        The default all-device subscription already includes these traits. This
        method does not narrow that subscription; no destructive unsubscribe is
        performed implicitly.
        """
        queries = group_trait_addresses(addresses)
        if queries:
            await self._request(
                "SubscribeTraitValueRequest", queries, "SubscribeTraitValueResponse"
            )

    async def _heartbeat(self) -> None:
        loop = asyncio.get_running_loop()
        next_ping = loop.time() + self._heartbeat_interval
        while True:
            await asyncio.sleep(max(0.0, next_ping - loop.time()))
            await self._request("ping", None, "pong")
            # Response latency does not extend the interval between outbound
            # messages. The request timeout still bounds a silent connection.
            next_ping += self._heartbeat_interval

    async def _receive(self) -> None:
        """Read immediately, even during authentication/snapshot reconciliation."""
        assert self._socket is not None
        try:
            async for message in self._socket:
                if message.type == aiohttp.WSMsgType.ERROR:
                    raise AqaraConnectionError("Studio WebSocket receive error")
                if message.type != aiohttp.WSMsgType.TEXT:
                    continue
                try:
                    payload = json.loads(message.data)
                except TypeError, ValueError:
                    raise AqaraResponseError(
                        "Studio WebSocket sent invalid JSON"
                    ) from None
                if not isinstance(payload, dict):
                    raise AqaraResponseError(
                        "Studio WebSocket sent a malformed message"
                    )
                msg_id = payload.get("msgId")
                if (
                    isinstance(msg_id, str)
                    and (future := self._pending.get(msg_id)) is not None
                ):
                    if not future.done():
                        future.set_result(payload)
                    continue
                if payload.get("type") == "ErrorMessage":
                    if payload.get("code") in (401, 403):
                        raise AqaraAuthError("Studio WebSocket authorization failed")
                    raise AqaraResponseError("Studio WebSocket reported an error")
                if payload.get("type") not in {"TraitValueUpdate", "objectEvent"}:
                    self.ignored_messages += 1
                    continue
                if (
                    payload.get("version") != "v1"
                    or type(payload.get("code")) is not int
                    or payload["code"] != 0
                ):
                    raise AqaraResponseError("Studio WebSocket push has invalid status")
                try:
                    self._pushes.put_nowait((payload, not self._ready.is_set()))
                except asyncio.QueueFull:
                    # Reconnect and reconcile instead of silently losing events.
                    raise AqaraConnectionError(
                        "Studio WebSocket buffer overflow"
                    ) from None
        finally:
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(
                        AqaraConnectionError("Studio WebSocket closed")
                    )

    async def _dispatch(self) -> None:
        await self._ready.wait()
        while True:
            payload, buffered = await self._pushes.get()
            self.replaying_buffer = buffered
            try:
                await self._dispatch_payload(payload)
            finally:
                self.replaying_buffer = False

    async def _dispatch_payload(self, payload: dict[str, Any]) -> None:
        """Dispatch a validated push; replay metadata remains local, off-wire."""
        data = payload.get("data")
        if payload["type"] == "TraitValueUpdate":
            if not isinstance(data, list):
                raise AqaraResponseError("Invalid WebSocket trait update")
            updates = []
            for item in data:
                address = validate_address(item)
                if "value" in item:
                    address["value"] = item["value"]
                if "time" in item:
                    address["time"] = item["time"]
                updates.append(address)
            self.received_updates += len(updates)
            if updates:
                await self._on_update(updates)
        else:
            if (
                not isinstance(data, dict)
                or not isinstance(data.get("eventType"), str)
                or not isinstance(data.get("objectId"), str)
            ):
                raise AqaraResponseError("Invalid WebSocket object event")
            await self._on_object_event(data)
