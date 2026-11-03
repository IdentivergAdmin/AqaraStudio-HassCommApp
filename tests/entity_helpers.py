"""Shared synthetic entity-test helpers; no live hub access."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aqara_studio.const import DEFAULT_OPTIONS
from custom_components.aqara_studio.device import parse_device


def fixture_data():
    return json.loads(
        (Path(__file__).parent / "fixtures" / "capabilities.json").read_text()
    )


def fixture_devices():
    raw = fixture_data()
    inventory = {record["deviceId"]: record for record in raw["inventory"]}
    return {
        definition["deviceId"]: parse_device(
            inventory[definition["deviceId"]], definition
        )
        for definition in raw["definitions"]
    }


class FakeCoordinator(DataUpdateCoordinator):
    """Exercise real HA entity mixins without transport side effects."""

    def __init__(self, hass, options=None):
        entry = MockConfigEntry(domain="aqara_studio")
        entry.add_to_hass(hass)
        super().__init__(
            hass, logging.getLogger(__name__), name="aqara_test", config_entry=entry
        )
        self.data = fixture_devices()
        self.studio_id = "synthetic-studio"
        self.client = SimpleNamespace(host="http://studio.test")
        self.options = DEFAULT_OPTIONS | (options or {})
        self.transport_available = True
        self.async_write_trait = AsyncMock()
        self.event_listeners = {}

    def get_trait(self, key):
        device = self.data.get(key.device_id)
        return device.traits.get(key) if device else None

    def entity_available(self, key):
        device = self.data.get(key.device_id)
        return bool(
            self.transport_available
            and device
            and device.present
            and device.reachable is not False
            and self.get_trait(key)
        )

    def async_add_event_listener(self, key, listener):
        self.event_listeners.setdefault(key, []).append(listener)

        def unsub():
            self.event_listeners[key].remove(listener)

        return unsub
