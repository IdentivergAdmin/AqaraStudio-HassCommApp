"""Regression tests for discovered Aqara light strips and safe local color writes."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.light import ColorMode
from homeassistant.exceptions import HomeAssistantError

from custom_components.aqara_studio.device import (
    Trait,
    TraitKey,
    discover_capabilities,
)
from custom_components.aqara_studio.light import AqaraStudioLight

from .entity_helpers import FakeCoordinator


def add_color(coordinator: FakeCoordinator):
    """Add vendor-documented mired and packed XY traits to a light endpoint."""
    device = coordinator.data["synthetic-light"]
    primary = next(
        t for t in device.traits.values() if t.key.trait_code == "OnOff"
    )
    for code, metadata, value in (
        (
            "ColorTemperature",
            {"type": "Integer", "min": 153, "max": 500, "step": 1, "unit": "mired"},
            250,
        ),
        (
            "ColorXY",
            {"type": "Integer", "min": 0, "max": 4294967295, "step": 1},
            (round(0.3 * 65535) << 16) | round(0.4 * 65535),
        ),
        ("ColorMode", {"type": "Enum", "writable": False}, 2),
    ):
        key = TraitKey(primary.key.device_id, primary.key.endpoint_id, "ColorControl", code)
        device.traits[key] = Trait(
            key,
            {"readable": True, "writable": True, "subscribable": True} | metadata,
            value=value,
            time=1,
            endpoint_type="LightStrip",
        )
    return primary


def light_entity(coordinator: FakeCoordinator) -> AqaraStudioLight:
    capability = next(
        item
        for item in discover_capabilities(
            coordinator.data["synthetic-light"], coordinator.options
        )
        if item.platform == "light"
    )
    return AqaraStudioLight(coordinator, capability)


async def test_light_strip_classifies_by_real_lighting_capabilities(hass):
    coordinator = FakeCoordinator(hass, {"enable_controls": True})
    primary = add_color(coordinator)
    primary.endpoint_type = "ProprietaryAddressableStrip"
    entity = light_entity(coordinator)
    assert entity.capability.xy_color_key is not None
    assert entity.capability.color_temp_key is not None
    assert entity.capability.brightness_key is not None
    assert entity.supported_color_modes == {ColorMode.XY, ColorMode.COLOR_TEMP}


async def test_color_mode_and_reporting(hass):
    coordinator = FakeCoordinator(hass, {"enable_controls": True})
    add_color(coordinator)
    entity = light_entity(coordinator)
    assert entity.color_mode is ColorMode.COLOR_TEMP
    assert entity.color_temp_kelvin == 4000
    assert entity.min_color_temp_kelvin == 2000
    assert entity.max_color_temp_kelvin == 6535
    assert entity.xy_color == pytest.approx((0.3, 0.4), abs=0.00002)


async def test_packed_xy_write_and_invalid_geometry(hass):
    coordinator = FakeCoordinator(hass, {"enable_controls": True})
    add_color(coordinator)
    entity = light_entity(coordinator)
    await entity.async_turn_on(xy_color=(0.3, 0.4))
    call = coordinator.async_write_trait.await_args_list[0]
    assert call.args == (
        entity.capability.xy_color_key,
        (round(0.3 * 65535) << 16) | round(0.4 * 65535),
    )
    assert coordinator.async_write_trait.await_args_list[1].args == (
        entity.capability.key,
        True,
    )
    coordinator.async_write_trait.reset_mock()
    for bad in ((0.7, 0.5), (True, 0.2), (float("nan"), 0.5), ("0.3", 0.4)):
        with pytest.raises(HomeAssistantError):
            await entity.async_turn_on(xy_color=bad)
    coordinator.async_write_trait.assert_not_awaited()


async def test_color_temperature_write_and_bounds(hass):
    coordinator = FakeCoordinator(hass, {"enable_controls": True})
    add_color(coordinator)
    entity = light_entity(coordinator)
    await entity.async_turn_on(color_temp_kelvin=4000)
    coordinator.async_write_trait.assert_any_await(
        entity.capability.color_temp_key, 250
    )
    coordinator.async_write_trait.reset_mock()
    for invalid in (0, 900, True):
        with pytest.raises(HomeAssistantError):
            await entity.async_turn_on(color_temp_kelvin=invalid)
    coordinator.async_write_trait.assert_not_awaited()


async def test_color_write_does_not_accept_unadvertised_capability(hass):
    coordinator = FakeCoordinator(hass, {"enable_controls": True})
    primary = add_color(coordinator)
    ct = next(
        trait for trait in coordinator.data["synthetic-light"].traits.values()
        if trait.key.trait_code == "ColorTemperature"
    )
    ct.parameter["writable"] = False
    # A supported light can still use XY, but not unadvertised temperature writes.
    entity = light_entity(coordinator)
    assert entity.capability.color_temp_key is None
    with pytest.raises(HomeAssistantError):
        await entity.async_turn_on(color_temp_kelvin=3500)
    coordinator.async_write_trait.assert_not_awaited()
    # Excluding unsafe endpoint types always wins over nominal light metadata.
    primary.endpoint_type = "DoorLock"
    assert not any(
        c.platform == "light"
        for c in discover_capabilities(
            coordinator.data["synthetic-light"], coordinator.options
        )
    )


async def test_invalid_or_missing_color_values_remain_unknown(hass):
    coordinator = FakeCoordinator(hass, {"enable_controls": True})
    add_color(coordinator)
    entity = light_entity(coordinator)
    ct = coordinator.get_trait(entity.capability.color_temp_key)
    xy = coordinator.get_trait(entity.capability.xy_color_key)
    ct.value = None
    xy.value = "invalid"
    assert entity.color_temp_kelvin is None
    assert entity.xy_color is None


async def test_studio_configuration_link_on_existing_device(hass):
    coordinator = FakeCoordinator(hass, {"enable_controls": True})
    coordinator.client = SimpleNamespace(host="https://studio.example.local")
    entity = light_entity(coordinator)
    assert entity.device_info["configuration_url"] == "https://studio.example.local"


async def test_switch_still_requires_opt_in(hass):
    coordinator = FakeCoordinator(hass)
    assert not any(
        c.platform == "switch"
        for c in discover_capabilities(coordinator.data["synthetic-switch"])
    )
    coordinator.async_write_trait = AsyncMock()
