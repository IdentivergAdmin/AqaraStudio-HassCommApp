"""Allowlisted diagnostics without tokens, hostnames, names, or device IDs."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant

from .const import CONF_EXCLUDED_DEVICES, DEFAULT_OPTIONS
from .device import discover_capabilities

if TYPE_CHECKING:
    from . import AqaraStudioConfigEntry

_CODE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


def _code(value: Any) -> str:
    """Only model codes, never arbitrary descriptions, URLs, or metadata."""
    return value if isinstance(value, str) and _CODE.fullmatch(value) else "<redacted>"


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: AqaraStudioConfigEntry
) -> dict[str, Any]:
    """Export a useful shape with no copies of arbitrary API/config payloads."""
    coordinator = entry.runtime_data
    aliases = {
        device_id: f"device_{index}"
        for index, device_id in enumerate(coordinator.data, 1)
    }
    devices = []
    light_candidates = 0
    enabled_lights = 0
    for device in coordinator.data.values():
        capabilities = discover_capabilities(device, coordinator.options)
        supported = {cap.key for cap in capabilities}
        eligible = discover_capabilities(device, {**coordinator.options, "enable_controls": True})
        potential_light = sum(cap.platform == "light" for cap in eligible)
        light_candidates += potential_light
        enabled_lights += sum(cap.platform == "light" for cap in capabilities)
        devices.append(
            {
                "device": aliases[device.device_id],
                "present": device.present,
                "reachable": device.reachable,
                "eligible_lights": potential_light,
                "capabilities": [
                    {
                        "platform": cap.platform,
                        "kind": cap.kind,
                    }
                    for cap in capabilities
                ],
                "traits": [
                    {
                        "endpoint": key.endpoint_id,
                        "function": _code(key.function_code),
                        "trait": _code(key.trait_code),
                        "readable": trait.readable,
                        "writable": trait.writable,
                        "subscribable": trait.subscribable,
                        "entity_mapped": key in supported,
                        "has_value": trait.value is not None,
                        "timestamp_zero": trait.time == 0,
                        "available": coordinator.entity_available(key),
                    }
                    for key, trait in device.traits.items()
                ],
            }
        )
    # Values are selected individually. Even a future options field cannot
    # accidentally expose credentials or an inclusion/exclusion device list.
    options = {
        key: coordinator.options[key]
        for key in DEFAULT_OPTIONS
        if key != CONF_EXCLUDED_DEVICES
    }
    options["excluded_device_count"] = len(coordinator.options[CONF_EXCLUDED_DEVICES])
    return {
        "options": options,
        "transport": {
            "push_connected": coordinator.push_connected,
            "last_refresh_succeeded": coordinator.last_update_success,
            "http_request_count": coordinator.client.request_count,
            "websocket_reconnect_attempts": coordinator.websocket.reconnect_attempts,
            "websocket_ignored_messages": coordinator.websocket.ignored_messages,
            "ignored_trait_updates": coordinator.ignored_updates,
            "partial_read_failures": coordinator.partial_read_failures,
        },
        "devices": devices,
        "lighting": {
            "eligible_lights": light_candidates,
            "enabled_lights": enabled_lights,
            "controls_opted_in": bool(coordinator.options.get("enable_controls", False)),
        },
        "live_button_observations": [
            {
                "device": aliases.get(item["device_id"], "unknown_device"),
                "numeric_value": item["value"]
                if type(item["value"]) is int and 0 <= item["value"] <= 65535
                else None,
                "value_type": type(item["value"]).__name__,
                "has_ordering_timestamp": item["has_ordering_timestamp"],
            }
            for item in coordinator.event_observations
        ],
        "privacy": "Names, addresses, identifiers, credentials, and raw sensor values omitted",
    }
