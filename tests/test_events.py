"""Documented button enums and strict live-event semantics."""

from unittest.mock import Mock

import pytest

from custom_components.aqara_studio.device import discover_capabilities
from custom_components.aqara_studio.event import AqaraStudioEvent, decode_button_event

from .entity_helpers import FakeCoordinator


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "single_press"),
        ("0", "single_press"),
        ("SinglePress", "single_press"),
        (1, "double_press"),
        ("DoublePress", "double_press"),
        (2, "long_press"),
        ("LongPress", "long_press"),
        (3, "long_press_release"),
        ("0x03", "long_press_release"),
        (True, None),
        (False, None),
        (255, None),
        ("unknown", None),
        (1.0, None),
    ],
)
def test_documented_button_enum(value, expected):
    assert decode_button_event(value, {}) == expected


def test_advertised_button_values_restrict_events():
    parameter = {"supportedValues": [{"key": "SinglePress", "value": "0"}]}
    assert decode_button_event("0", parameter) == "single_press"
    assert decode_button_event("SinglePress", parameter) == "single_press"
    assert decode_button_event(1, parameter) is None
    assert (
        decode_button_event(
            "unsupported",
            {"supportedValues": [{"key": "Unknown", "value": "unsupported"}]},
        )
        is None
    )
    assert (
        decode_button_event(1, {"supportedValues": [{"key": [], "value": 1}]}) is None
    )


async def test_cached_event_is_not_replayed_and_live_events_are_distinct(hass):
    coordinator = FakeCoordinator(hass, {"enable_button_events": True})
    cap = discover_capabilities(
        coordinator.data["synthetic-button"], coordinator.options
    )[0]
    entity = AqaraStudioEvent(coordinator, cap)
    entity.async_write_ha_state = Mock()
    assert entity.trait.value == "SinglePress"
    assert entity.state is None
    assert entity.extra_state_attributes["live_event_received"] is False
    assert await entity.async_get_last_event_data() is None
    entity._async_live_event("0", 1000)
    first = entity.state
    assert first is not None
    assert entity.state_attributes["event_type"] == "single_press"
    entity._async_live_event("0", 1000)
    assert entity.state == first
    entity._async_live_event("1", 999)
    assert entity.state == first
    entity._async_live_event("0", 1001)
    assert entity.state != first
    assert entity.async_write_ha_state.call_count == 2
    assert entity.extra_state_attributes["live_event_received"] is True


async def test_unknown_live_timestamps_and_values(hass):
    coordinator = FakeCoordinator(hass, {"enable_button_events": True})
    cap = discover_capabilities(
        coordinator.data["synthetic-button"], coordinator.options
    )[0]
    entity = AqaraStudioEvent(coordinator, cap)
    entity.async_write_ha_state = Mock()
    entity._async_live_event("SinglePress", 0)
    entity._async_live_event("SinglePress", 0)
    assert entity.state is None
    assert entity.extra_state_attributes["unverified_event_count"] == 2
    entity._async_live_event("SinglePress", 1000)
    prior = entity.state
    entity._async_live_event("UnknownVendorValue", 1002)
    assert entity.state == prior
    assert entity.extra_state_attributes["unrecognized_event_count"] == 1
    coordinator.transport_available = False
    entity._async_live_event("DoublePress", 1003)
    assert entity.state == prior


async def test_button_entities_are_opt_in(hass):
    coordinator = FakeCoordinator(hass)
    assert (
        discover_capabilities(coordinator.data["synthetic-button"], coordinator.options)
        == []
    )
