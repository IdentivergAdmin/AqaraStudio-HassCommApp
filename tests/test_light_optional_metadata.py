"""Optional Aqara light metadata and Home Assistant feature diagnostics.

The current vendor data model defines min/max/step values as optional for
CurrentLevel, ColorXY and ColorTemperature. The API does not always include
those fields even when Studio exposes fully functional controls.
"""

from __future__ import annotations

import json

import pytest
from homeassistant.components.light import ColorMode
from homeassistant.exceptions import HomeAssistantError

from custom_components.aqara_studio.device import (
    discover_capabilities,
)
from custom_components.aqara_studio.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.aqara_studio.light import AqaraStudioLight

from .entity_helpers import FakeCoordinator
from .test_light_enhancements import add_color


def _light(coordinator):
    caps = discover_capabilities(
        coordinator.data["synthetic-light"], coordinator.options
    )
    return AqaraStudioLight(
        coordinator, next(cap for cap in caps if cap.platform == "light")
    )


async def test_brightness_optional_bounds_follow_spec_and_enable_slider(hass):
    coordinator = FakeCoordinator(hass)
    dev = coordinator.data["synthetic-light"]
    trait = next(t for t in dev.traits.values() if t.key.trait_code == "CurrentLevel")
    for field in ("min", "max", "step"):
        trait.parameter.pop(field, None)
    entity = _light(coordinator)
    assert entity.capability.brightness_key == trait.key
    assert entity.supported_color_modes == {ColorMode.BRIGHTNESS}
    assert entity.brightness == 128
    await entity.async_turn_on(brightness=127)
    assert coordinator.async_write_trait.await_args_list[0].args == (trait.key, 50)


async def test_color_optional_bounds_enable_all_advertised_modes(hass):
    coordinator = FakeCoordinator(hass)
    add_color(coordinator)
    dev = coordinator.data["synthetic-light"]
    for trait in dev.traits.values():
        if trait.key.trait_code in ("ColorTemperature", "ColorXY"):
            for field in ("min", "max", "step"):
                trait.parameter.pop(field, None)
    entity = _light(coordinator)
    assert entity.supported_color_modes == {ColorMode.XY, ColorMode.COLOR_TEMP}
    assert entity.capability.brightness_key is not None
    assert entity.capability.color_temp_key is not None
    assert entity.capability.xy_color_key is not None
    assert entity.min_color_temp_kelvin == 2000
    assert entity.max_color_temp_kelvin == 6535
    assert entity.color_temp_kelvin == 4000
    await entity.async_turn_on(color_temp_kelvin=4000)
    coordinator.async_write_trait.assert_any_await(
        entity.capability.color_temp_key, 250
    )
    coordinator.async_write_trait.reset_mock()
    await entity.async_turn_on(xy_color=(0.3, 0.4))
    assert coordinator.async_write_trait.await_args_list[0].args[0] == (
        entity.capability.xy_color_key
    )


@pytest.mark.parametrize("invalid_min", ["nonsense", -100, 400])
async def test_invalid_explicit_brightness_limits_fail_closed(hass, invalid_min):
    coordinator = FakeCoordinator(hass)
    dev = coordinator.data["synthetic-light"]
    trait = next(t for t in dev.traits.values() if t.key.trait_code == "CurrentLevel")
    trait.parameter["min"] = invalid_min
    entity = _light(coordinator)
    assert entity.capability.brightness_key is None
    assert entity.supported_color_modes == {ColorMode.ONOFF}
    with pytest.raises(HomeAssistantError):
        await entity.async_turn_on(brightness=128)
    coordinator.async_write_trait.assert_not_awaited()


async def test_invalid_explicit_temperature_limits_fail_closed(hass):
    coordinator = FakeCoordinator(hass)
    add_color(coordinator)
    dev = coordinator.data["synthetic-light"]
    ct = next(t for t in dev.traits.values() if t.key.trait_code == "ColorTemperature")
    ct.parameter["max"] = "unsafe"
    entity = _light(coordinator)
    assert entity.capability.color_temp_key is None
    assert ColorMode.COLOR_TEMP not in entity.supported_color_modes
    with pytest.raises(HomeAssistantError):
        await entity.async_turn_on(color_temp_kelvin=4000)
    coordinator.async_write_trait.assert_not_awaited()


async def test_diagnostics_show_feature_flags_not_light_values(
    hass, config_entry, coordinator
):
    report = await async_get_config_entry_diagnostics(hass, config_entry)
    features = [
        item for dev in report["devices"] for item in dev["light_features"]
    ]
    assert any(item["brightness"] is True for item in features)
    assert all(
        set(item) == {
            "endpoint", "on_off", "brightness", "xy_color", "color_temperature"
        }
        for item in features
    )
    metadata = [
        item for dev in report["devices"] for item in dev["light_trait_metadata"]
    ]
    assert any(item["trait"] == "CurrentLevel" for item in metadata)
    assert all(
        set(item) == {
            "endpoint", "function", "trait", "type", "unit",
            "min", "max", "step", "readable", "writable"
        }
        for item in metadata
    )
    assert "synthetic-light" not in json.dumps(report)
    assert "synthetic-studio" not in json.dumps(report)
