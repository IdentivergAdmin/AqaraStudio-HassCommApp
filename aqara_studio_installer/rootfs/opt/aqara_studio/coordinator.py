"""Share discovery, authoritative snapshots, and live updates across entities."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from collections.abc import Callable
from contextlib import suppress
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    AqaraAuthError,
    AqaraConnectionError,
    AqaraError,
    AqaraRateLimitError,
    AqaraResponseError,
    AqaraStudioClient,
    validate_address,
)
from .const import (
    CONF_ENABLE_BUTTON_EVENTS,
    CONF_ENABLE_WEBSOCKET,
    CONF_EXCLUDED_DEVICES,
    CONF_GATEWAY_ID,
    CONF_INVENTORY_INTERVAL,
    CONF_POLL_INTERVAL,
    CONF_RECONCILE_INTERVAL,
    DEFAULT_OPTIONS,
    DEFINITION_REFRESH_SECONDS,
    DOMAIN,
    MAX_RETRY_SECONDS,
    MIN_DISCOVERY_SECONDS,
    STATE_BATCH_SIZE,
)
from .device import (
    StudioDevice,
    Trait,
    TraitKey,
    discover_capabilities,
    finite_number,
    parse_device,
    strict_bool,
)
from .entity import device_identifier
from .websocket import AqaraWebSocket

_LOGGER = logging.getLogger(__name__)


def _key(raw: dict[str, Any]) -> TraitKey:
    address = validate_address(raw)
    return TraitKey(
        address["deviceId"],
        address["endpointId"],
        address["functionCode"],
        address["traitCode"],
    )


class AqaraStudioCoordinator(DataUpdateCoordinator[dict[str, StudioDevice]]):
    """One managed connection and shared cache for a Studio config entry."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: AqaraStudioClient
    ) -> None:
        self.options = {**DEFAULT_OPTIONS, **entry.options}
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=self.options[CONF_POLL_INTERVAL]),
            always_update=True,
        )
        self.client = client
        self.studio_id = entry.data[CONF_GATEWAY_ID]
        self.data = {}
        self.gateways: dict[str, dict[str, Any]] = {}
        self._definitions: dict[str, dict[str, Any]] = {}
        self._definition_times: dict[str, float] = {}
        self._inventory_history: deque[set[str]] = deque(maxlen=2)
        self._last_inventory = float("-inf")
        self._inventory_dirty = True
        self._definitions_dirty = False
        self._transport_ready = False
        self._push_connected = False
        self._auth_failed = False
        self._stopping = False
        self._retry_at = 0.0
        self._failures = 0
        self._refresh_lock = asyncio.Lock()
        self._unavailable_traits: set[TraitKey] = set()
        self._revisions: dict[TraitKey, int] = defaultdict(int)
        self._event_listeners: dict[TraitKey, set[Callable]] = defaultdict(set)
        self._event_last: dict[TraitKey, tuple[int, Any]] = {}
        self._event_not_before = int(time.time() * 1000)
        self._buffer_snapshot_task: asyncio.Task | None = None
        self.event_observations: deque[dict[str, Any]] = deque(maxlen=20)
        self.ignored_updates = 0
        self.partial_read_failures = 0
        self._ws_task: asyncio.Task | None = None
        self._discovery_task: asyncio.Task | None = None
        self._remove_keepalive: Callable | None = None
        self.websocket = AqaraWebSocket(
            client,
            self.async_handle_updates,
            self.async_handle_object_event,
            self.async_handle_connection,
        )

    @property
    def push_connected(self) -> bool:
        return self._push_connected

    @callback
    def get_trait(self, key: TraitKey) -> Trait | None:
        device = self.data.get(key.device_id)
        return device.traits.get(key) if device else None

    @callback
    def entity_available(self, key: TraitKey) -> bool:
        """An old safe value never substitutes for a failed transport/read."""
        device = self.data.get(key.device_id)
        if (
            self._auth_failed
            or not self._transport_ready
            or not (self.last_update_success or self._push_connected)
            or device is None
            or not device.present
            or device.device_id in self.options[CONF_EXCLUDED_DEVICES]
            or device.reachable is False
            or key not in device.traits
            or key in self._unavailable_traits
        ):
            return False
        # A failed Reachable read invalidates availability even when the contact
        # value arrived in a different, successful batch.
        return not any(
            point in self._unavailable_traits
            or strict_bool(device.traits[point].value) is None
            for point in device.traits
            if (point.function_code, point.trait_code)
            == ("BasicInformation", "Reachable")
        )

    async def _async_update_data(self) -> dict[str, StudioDevice]:
        async with self._refresh_lock:
            now = time.monotonic()
            if self._auth_failed:
                raise ConfigEntryAuthFailed("Aqara Studio credentials need renewal")
            if now < self._retry_at:
                raise UpdateFailed(
                    "Waiting before retrying Studio", retry_after=self._retry_at - now
                )
            try:
                if not self.gateways:
                    gateways = await self.client.async_get_gateways()
                    self.gateways = {item["deviceId"]: item for item in gateways}
                    if self.studio_id not in self.gateways:
                        self.gateways = {}
                        raise AqaraResponseError(
                            "The configured identity gateway is absent"
                        )
                    self._register_gateways()
                if now - self._last_inventory >= self.options[
                    CONF_INVENTORY_INTERVAL
                ] or (
                    self._inventory_dirty
                    and now - self._last_inventory >= MIN_DISCOVERY_SECONDS
                ):
                    await self._async_reconcile_inventory(now)
                await self._async_read_states()
            except AqaraAuthError as err:
                self._auth_failed = True
                self._transport_ready = False
                raise ConfigEntryAuthFailed(
                    "Aqara Studio rejected the API token"
                ) from err
            except AqaraRateLimitError as err:
                self._transport_ready = self._push_connected
                self._retry_at = time.monotonic() + err.retry_after
                raise UpdateFailed(
                    "Studio rate limit reached", retry_after=err.retry_after
                ) from err
            except AqaraError as err:
                self._transport_ready = self._push_connected
                self._failures += 1
                delay = min(
                    MAX_RETRY_SECONDS,
                    self.options[CONF_POLL_INTERVAL] * 2 ** min(self._failures - 1, 5),
                )
                self._retry_at = time.monotonic() + delay
                raise UpdateFailed(
                    "Cannot refresh Aqara Studio", retry_after=delay
                ) from err
            self._failures = 0
            self._transport_ready = True
            return self.data

    @callback
    def _register_gateways(self) -> None:
        registry = dr.async_get(self.hass)
        for device_id, gateway in self.gateways.items():
            registry.async_get_or_create(
                config_entry_id=self.config_entry.entry_id,
                identifiers={(DOMAIN, device_identifier(self.studio_id, device_id))},
                name=gateway.get("deviceName") or gateway.get("name") or "Aqara Studio",
                configuration_url=self.client.host,
            )

    @callback
    def _register_device_metadata(self, device: StudioDevice) -> None:
        registry = dr.async_get(self.hass)
        registered = registry.async_get_device_by_identifier(
            (DOMAIN, device_identifier(self.studio_id, device.device_id)),
            self.config_entry.entry_id,
        )
        if registered is None:
            return  # Entity registration creates supported physical devices.
        # Home Assistant retains name_by_user separately from the default name.
        registry.async_update_device(
            registered.id,
            name=device.name,
            manufacturer=device.manufacturer,
            model=device.model,
            sw_version=device.firmware,
            configuration_url=self.client.host,
        )

    async def _async_reconcile_inventory(self, now: float) -> None:
        """Apply a complete inventory, leaving absent registry entries intact."""
        records = await self.client.async_get_devices()
        excluded = set(self.options[CONF_EXCLUDED_DEVICES])
        records_by_id = {
            item["deviceId"]: item
            for item in records
            if item["deviceId"] not in excluded
        }
        needed = [
            device_id
            for device_id in records_by_id
            if device_id not in self._definitions
            or self._definitions_dirty
            or now - self._definition_times.get(device_id, 0)
            >= DEFINITION_REFRESH_SECONDS
        ]
        if needed:
            # The API client batches definitions; they are never part of a
            # normal 15-second state poll. Missing definitions are retried.
            definitions = await self.client.async_get_definitions(needed)
            for definition in definitions:
                device_id = definition["deviceId"]
                self._definitions[device_id] = definition
                self._definition_times[device_id] = now
        for device in self.data.values():
            if device.device_id not in records_by_id:
                device.present = False
        for device_id, record in records_by_id.items():
            definition = self._definitions.get(device_id)
            if definition is None:
                continue
            device = parse_device(record, definition)
            if old := self.data.get(device_id):
                for key, trait in device.traits.items():
                    if prior := old.traits.get(key):
                        # Definitions are metadata, not a license to overwrite a
                        # newer live value with a cached model snapshot.
                        trait.value, trait.time = prior.value, prior.time
            self.data[device_id] = device
            self._register_device_metadata(device)
        self._last_inventory = now
        self._inventory_history.append(
            {device_identifier(self.studio_id, item["deviceId"]) for item in records}
        )
        self._inventory_dirty = False
        self._definitions_dirty = False

    @callback
    def can_remove_registry_device(self, device: dr.DeviceEntry) -> bool:
        """Allow an explicit UI cleanup after two complete missing inventories."""
        if len(self._inventory_history) < 2:
            return False
        root_identifier = device_identifier(self.studio_id, self.studio_id)
        identifiers = {
            identifier for domain, identifier in device.identifiers if domain == DOMAIN
        }
        if not identifiers or root_identifier in identifiers:
            return False
        present = set.union(*self._inventory_history)
        return not (identifiers & present)

    def _read_keys(self) -> list[TraitKey]:
        keys: set[TraitKey] = set()
        for device in self.data.values():
            if not device.present:
                continue
            for cap in discover_capabilities(device, self.options):
                # Cached button values establish a replay barrier. Polling
                # them never emits an event.
                keys.add(cap.key)
                if cap.brightness_key:
                    keys.add(cap.brightness_key)
            keys.update(
                key
                for key in device.traits
                if (key.function_code, key.trait_code)
                == ("BasicInformation", "Reachable")
            )
        return sorted(
            key for key in keys if (trait := self.get_trait(key)) and trait.readable
        )

    async def _async_read_states(self) -> None:
        keys = self._read_keys()
        if not keys:
            return
        revisions = dict(self._revisions)
        batches = [
            keys[index : index + STATE_BATCH_SIZE]
            for index in range(0, len(keys), STATE_BATCH_SIZE)
        ]
        # Keep coordinator-level fan-out bounded as well as the client's socket
        # semaphore; partial failure in one batch need not hide all devices.
        semaphore = asyncio.Semaphore(4)

        async def read(batch: list[TraitKey]) -> list[dict[str, Any]]:
            async with semaphore:
                return await self.client.async_read_traits(
                    [key.as_dict() for key in batch]
                )

        results = await asyncio.gather(
            *(read(batch) for batch in batches), return_exceptions=True
        )
        succeeded = 0
        failure: AqaraError | None = None
        for batch, result in zip(batches, results, strict=True):
            if isinstance(result, AqaraAuthError):
                raise result
            if isinstance(result, AqaraError):
                self._unavailable_traits.update(batch)
                self.partial_read_failures += 1
                failure = result
                if isinstance(result, AqaraRateLimitError):
                    self._retry_at = max(
                        self._retry_at, time.monotonic() + result.retry_after
                    )
                continue
            if isinstance(result, BaseException):
                raise result
            succeeded += 1
            expected = set(batch)
            seen: set[TraitKey] = set()
            for item in result:
                try:
                    key = _key(item)
                except AqaraResponseError:
                    self.ignored_updates += 1
                    continue
                if key not in expected:
                    self.ignored_updates += 1
                    continue
                seen.add(key)
                # A push that arrived while this HTTP request was in flight wins.
                if self._revisions[key] != revisions.get(key, 0):
                    continue
                self._apply_value(key, item, live=False)
            for missing in expected - seen:
                if self._revisions[missing] == revisions.get(missing, 0):
                    self._unavailable_traits.add(missing)
        if not succeeded and failure:
            raise failure

    def _apply_value(self, key: TraitKey, item: dict[str, Any], *, live: bool) -> bool:
        trait = self.get_trait(key)
        if trait is None:
            return False
        stamp = item.get("time")
        if type(stamp) is not int or stamp < 0:
            stamp = None
        if (
            live
            and getattr(self.websocket, "replaying_buffer", False)
            and (not stamp or not trait.time)
        ):
            # This update predates completion of the reconnect snapshot, but
            # has no comparable timestamp. Neither arrival order nor zero can
            # establish which state is newer; recover with another REST read.
            self._unavailable_traits.add(key)
            self._request_buffer_snapshot()
            return False
        if stamp and trait.time and stamp < trait.time:
            self.ignored_updates += 1
            return False
        if live and stamp and stamp == trait.time and trait.value != item.get("value"):
            # Two conflicting values with the same timestamp have no ordering
            # evidence. Do not flip a door to closed on an ambiguous replay.
            self._unavailable_traits.add(key)
            self._request_inventory()
            return False
        # Zero is documented in real examples. It means no useful ordering
        # evidence here, not an invalid state or an offline sleepy sensor.
        trait.value = item.get("value")
        trait.time = stamp
        self._unavailable_traits.discard(key)
        if (
            not live
            and (key.function_code, key.trait_code) == ("Button", "ButtonEvent")
            and stamp
        ):
            self._event_last[key] = (stamp, trait.value)
        if live:
            self._revisions[key] += 1
        return True

    async def async_handle_updates(self, updates: list[dict[str, Any]]) -> None:
        """Process live pushes without resetting reconciliation timers."""
        if self._stopping or self._auth_failed:
            return
        for item in updates:
            try:
                key = _key(item)
            except AqaraResponseError:
                self.ignored_updates += 1
                continue
            trait = self.get_trait(key)
            if trait is None:
                self._request_inventory(definitions=True)
                continue
            if not trait.subscribable:
                self.ignored_updates += 1
                continue
            is_event = (key.function_code, key.trait_code) == ("Button", "ButtonEvent")
            previous = self._event_last.get(key)
            cutoff = max(
                trait.time or 0, previous[0] if previous else 0, self._event_not_before
            )
            if not self._apply_value(key, item, live=True):
                continue
            if is_event:
                stamp = trait.time
                self.event_observations.append(
                    {
                        "device_id": key.device_id,
                        "value": trait.value,
                        "has_ordering_timestamp": bool(stamp),
                    }
                )
                # A socket message is not proof of a fresh physical press.
                # Without an ordered timestamp, cached replay cannot be ruled
                # out; preserve observation metadata but do not run automations.
                if not stamp or stamp <= cutoff:
                    continue
                self._event_last[key] = (stamp, trait.value)
                if self.options[CONF_ENABLE_BUTTON_EVENTS] and self.entity_available(
                    key
                ):
                    for listener in tuple(self._event_listeners.get(key, ())):
                        listener(trait.value, stamp)
        # async_set_updated_data would postpone each poll on busy networks,
        # starving inventory reconciliation. Notify listeners without rescheduling.
        self.async_update_listeners()

    async def async_handle_object_event(self, event: dict[str, Any]) -> None:
        """Object events invalidate inventory; arbitrary payloads are not button presses."""
        if not self._stopping:
            self._request_inventory(definitions=True)

    @callback
    def _request_buffer_snapshot(self) -> None:
        if self._buffer_snapshot_task and not self._buffer_snapshot_task.done():
            return

        async def refresh() -> None:
            # Coalesce the reconnect queue; let its dispatcher finish before
            # fetching an authoritative replacement for unordered buffered data.
            await asyncio.sleep(0)
            if not self._stopping:
                await self.async_request_refresh()

        self._buffer_snapshot_task = self.config_entry.async_create_background_task(
            self.hass, refresh(), "Aqara Studio buffered state reconciliation"
        )

    @callback
    def _request_inventory(self, *, definitions: bool = False) -> None:
        self._inventory_dirty = True
        self._definitions_dirty |= definitions
        if self._discovery_task and not self._discovery_task.done():
            return

        async def discover() -> None:
            delay = max(
                0, MIN_DISCOVERY_SECONDS - (time.monotonic() - self._last_inventory)
            )
            if delay:
                await asyncio.sleep(delay)
            if not self._stopping:
                await self.async_request_refresh()

        self._discovery_task = self.config_entry.async_create_background_task(
            self.hass, discover(), "Aqara Studio inventory reconciliation"
        )

    async def async_handle_connection(self, connected: bool) -> None:
        if self._stopping:
            return
        self._push_connected = connected
        self._transport_ready = False
        self.update_interval = timedelta(
            seconds=(
                min(
                    self.options[CONF_RECONCILE_INTERVAL],
                    self.options[CONF_INVENTORY_INTERVAL],
                )
                if connected
                else self.options[CONF_POLL_INTERVAL]
            )
        )
        self.async_update_listeners()
        if connected:
            self._event_not_before = int(time.time() * 1000)
            # Subscribe before fetching the snapshot; the client buffers pushes
            # during this callback, eliminating the snapshot/subscription gap.
            await self.async_refresh()
            if not self.last_update_success:
                self._push_connected = False
                raise AqaraConnectionError("Reconnect snapshot failed")
        else:
            self._inventory_dirty = True
            self._request_buffer_snapshot()

    @callback
    def async_add_event_listener(self, key: TraitKey, listener: Callable) -> Callable:
        self._event_listeners[key].add(listener)

        @callback
        def remove() -> None:
            self._event_listeners[key].discard(listener)

        return remove

    async def async_write_trait(self, key: TraitKey, value: Any) -> None:
        """Permit only discovered writable light/switch traits."""
        trait = self.get_trait(key)
        if trait is None or not trait.writable:
            raise HomeAssistantError(
                "Aqara Studio controls are not enabled for this trait"
            )
        device = self.data[key.device_id]
        controls = [
            cap
            for cap in discover_capabilities(device, self.options)
            if cap.platform in {"light", "switch"}
        ]
        permitted = {cap.key for cap in controls} | {
            key
            for cap in controls
            for key in (cap.brightness_key, cap.color_temp_key, cap.xy_color_key)
            if key is not None
        }
        if key not in permitted or not self.entity_available(key):
            raise HomeAssistantError("This Aqara Studio control is unavailable")
        if key.trait_code == "OnOff" and type(value) is not bool:
            raise HomeAssistantError("On/off requires a boolean value")
        if key.trait_code == "CurrentLevel" and (
            type(value) not in (int, float) or not 1 <= value <= 100
        ):
            raise HomeAssistantError("Brightness is outside the supported range")
        if key.trait_code == "ColorTemperature":
            minimum = finite_number(trait.parameter.get("min"))
            maximum = finite_number(trait.parameter.get("max"))
            step = finite_number(trait.parameter.get("step", 1))
            if (
                type(value) is not int
                or minimum is None
                or maximum is None
                or step is None
                or not minimum <= value <= maximum
                or abs((value - minimum) / step - round((value - minimum) / step))
                > 1e-8
            ):
                raise HomeAssistantError(
                    "Color temperature is outside the supported range"
                )
        if key.trait_code == "ColorXY" and (
            type(value) is not int or not 0 <= value <= 4294967295
        ):
            raise HomeAssistantError(
                "XY color must be a packed unsigned 32-bit integer"
            )
        try:
            await self.client.async_write_trait(key.as_dict(), value)
        except AqaraAuthError as err:
            self._auth_failed = True
            self._transport_ready = False
            self.config_entry.async_start_reauth(self.hass)
            self.async_update_listeners()
            raise HomeAssistantError("Aqara Studio credentials need renewal") from err
        except AqaraError as err:
            raise HomeAssistantError(
                "Aqara Studio did not confirm the command"
            ) from err
        # No optimistic state: only a confirmed snapshot/push changes the entity.
        await self.async_request_refresh()

    async def async_start(self) -> None:
        # Keep discovery alive even if the initial inventory has zero supported
        # entities or the user disables every currently discovered entity.
        self._remove_keepalive = self.async_add_listener(lambda: None)
        if self.options[CONF_ENABLE_WEBSOCKET]:
            self._ws_task = self.config_entry.async_create_background_task(
                self.hass, self._async_run_websocket(), "Aqara Studio WebSocket"
            )

    async def _async_run_websocket(self) -> None:
        try:
            await self.websocket.async_run()
        except AqaraAuthError:
            self._auth_failed = True
            self._transport_ready = False
            self._push_connected = False
            self.async_set_update_error(
                ConfigEntryAuthFailed("Aqara Studio rejected the API token")
            )
            self.config_entry.async_start_reauth(self.hass)

    async def async_shutdown(self) -> None:
        """Idempotently stop timers, socket, pending reconnects, and listeners."""
        if self._stopping:
            return
        self._stopping = True
        if self._remove_keepalive:
            self._remove_keepalive()
        for task in (self._discovery_task, self._buffer_snapshot_task, self._ws_task):
            if task and not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        await self.websocket.async_stop()
        self._event_listeners.clear()
        await super().async_shutdown()
