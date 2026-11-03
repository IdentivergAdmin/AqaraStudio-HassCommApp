"""Experimental buttons: only live events can trigger event entities."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .device import Capability
from .entity import AqaraStudioEntity, async_setup_platform_entities

BUTTON_TYPES = {
    "SinglePress": "single_press",
    "DoublePress": "double_press",
    "LongPress": "long_press",
    "LongPressRelease": "long_press_release",
}
BUTTON_VALUES = {index: event for index, event in enumerate(BUTTON_TYPES.values())}


def decode_button_event(value: Any, parameter: dict[str, Any]) -> str | None:
    """Decode only Aqara's documented ButtonEventEnum8 meanings."""
    if isinstance(value, bool):
        return None
    supported = parameter.get("supportedValues")
    if isinstance(supported, list) and supported:
        for item in supported:
            if not isinstance(item, dict):
                continue
            if value == item.get("key") or str(value) == str(item.get("value")):
                name = item.get("key")
                return BUTTON_TYPES.get(name) if isinstance(name, str) else None
        return None
    if isinstance(value, str):
        if value in BUTTON_TYPES:
            return BUTTON_TYPES[value]
        try:
            value = int(value, 16 if value.startswith("0x") else 10)
        except ValueError:
            return None
    return BUTTON_VALUES.get(value) if isinstance(value, int) else None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_setup_platform_entities(
        entry, entry.runtime_data, "event", async_add_entities, AqaraStudioEvent
    )


class AqaraStudioEvent(AqaraStudioEntity, EventEntity):
    """No cached definition/REST value is ever emitted as a button press."""

    _attr_device_class = EventDeviceClass.BUTTON
    _attr_event_types = list(BUTTON_TYPES.values())

    def __init__(self, coordinator, capability: Capability) -> None:
        super().__init__(coordinator, capability)
        self._live_event_received = False
        self._last_timestamp: int | None = None
        self._last_type: str | None = None
        self._unrecognized_events = 0
        self._unverified_events = 0

    async def async_get_last_event_data(self):
        """Deliberately do not restore a cached event as a live observation."""
        return None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_event_listener(
                self.capability.key, self._async_live_event
            )
        )

    @callback
    def _async_live_event(self, value: Any, timestamp: int | None = None) -> None:
        if self.trait is None or not self.available:
            return
        # Cached events may be replayed at subscription time. Zero is valid for
        # state traits, but cannot establish event freshness.
        if type(timestamp) is not int or timestamp <= 0:
            self._unverified_events += 1
            self.async_write_ha_state()
            return
        event_type = decode_button_event(value, self.trait.parameter)
        if event_type is None:
            self._unrecognized_events += 1
            self.async_write_ha_state()
            return
        if (
            isinstance(timestamp, int)
            and not isinstance(timestamp, bool)
            and timestamp > 0
        ):
            if self._last_timestamp is not None and (
                timestamp < self._last_timestamp
                or (timestamp == self._last_timestamp and event_type == self._last_type)
            ):
                return
            self._last_timestamp = timestamp
            self._last_type = event_type
        self._live_event_received = True
        self._trigger_event(event_type)
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            **super().extra_state_attributes,
            "live_event_received": self._live_event_received,
            "unrecognized_event_count": self._unrecognized_events,
            "unverified_event_count": self._unverified_events,
        }
