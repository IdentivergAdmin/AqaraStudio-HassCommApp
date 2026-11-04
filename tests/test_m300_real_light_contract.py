"""Regression contract from real, anonymized M300 light-strip diagnostics.

The user's actual Home Assistant report advertised XY max 0x100000007
and ColorTemperature bounds 2703..6536; the unit was sanitized, so tests
exercise common Kelvin spellings and the narrowly scoped real-shape fallback.
No raw device identifiers, credentials, or sensor observations are stored here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from homeassistant.components.light import ColorMode
from homeassistant.exceptions import HomeAssistantError

from custom_components.aqara_studio.device import (
    TraitKey,
    color_temperature_profile,
    discover_capabilities,
)
from custom_components.aqara_studio.light import AqaraStudioLight

from .entity_helpers import FakeCoordinator
from .test_light_enhancements import add_color

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "m300_lightstrip_redacted.json"
UINT32_MAX = 4294967295


def prepare_real_metadata(coordinator, unit: str = "K"):
    """Recreate exact numeric bounds with synthetic IDs and synthetic values."""
    payload = json.loads(FIXTURE_PATH.read_text())
    device = coordinator.data["synthetic-light"]
    add_color(coordinator)
    for item in payload["traits"]:
        original = next(
            trait
            for trait in device.traits.values()
            if (
                trait.key.function_code == item["function"]
                and trait.key.trait_code == item["trait"]
            )
        )
        original.parameter = {
            "readable": item["readable"],
            "writable": item["writable"],
            "type": item["type"],
            "unit": unit if item["trait"] == "ColorTemperature" else item["unit"],
            "min": item["min"],
            "max": item["max"],
            "step": item["step"],
        }
        if item["trait"] == "ColorTemperature":
            original.value = 4000  # synthetic Kelvin value, not copied from user
    # The real M300 strip's light traits are all on endpoint 2.
    remapped = {}
    for key, trait in device.traits.items():
        if key.endpoint_id == 1:
            key = TraitKey(
                key.device_id, payload["endpoint"], key.function_code, key.trait_code
            )
            trait.key = key
        remapped[key] = trait
    device.traits = remapped
    return device


def get_light(coordinator):
    device = coordinator.data["synthetic-light"]
    cap = next(
        c
        for c in discover_capabilities(device, coordinator.options)
        if c.platform == "light"
    )
    return AqaraStudioLight(coordinator, cap)


@pytest.mark.parametrize("unit", ["K", "kelvin", "Kelvin", "°K", "<redacted>"])
async def test_exact_m300_shape_exposes_both_color_modes(hass, unit):
    coordinator = FakeCoordinator(hass)
    prepare_real_metadata(coordinator, unit)
    light = get_light(coordinator)
    assert light.capability.key.endpoint_id == 2
    assert light.supported_color_modes == {ColorMode.XY, ColorMode.COLOR_TEMP}
    assert light.brightness == 128
    assert light.min_color_temp_kelvin == 2703
    assert light.max_color_temp_kelvin == 6536
    assert light.color_temp_kelvin == 4000
    assert light.color_mode == ColorMode.COLOR_TEMP
    profile = color_temperature_profile(
        coordinator.get_trait(light.capability.color_temp_key)
    )
    assert profile is not None and profile.unit == "kelvin"


async def test_real_m300_kelvin_write_is_not_wrongly_converted_to_mired(hass):
    coordinator = FakeCoordinator(hass)
    prepare_real_metadata(coordinator)
    light = get_light(coordinator)
    await light.async_turn_on(color_temp_kelvin=4000)
    assert coordinator.async_write_trait.await_args_list[0].args == (
        light.capability.color_temp_key,
        4000,
    )
    assert coordinator.async_write_trait.await_args_list[1].args == (
        light.capability.key,
        True,
    )
    coordinator.async_write_trait.reset_mock()
    await light.async_turn_on(color_temp_kelvin=2703)
    assert coordinator.async_write_trait.await_args_list[0].args[1] == 2703
    coordinator.async_write_trait.reset_mock()
    await light.async_turn_on(color_temp_kelvin=6536)
    assert coordinator.async_write_trait.await_args_list[0].args[1] == 6536


async def test_real_m300_xy_metadata_overshoot_keeps_uint32_wire_bounds(hass):
    coordinator = FakeCoordinator(hass)
    device = prepare_real_metadata(coordinator)
    xy = next(t for t in device.traits.values() if t.key.trait_code == "ColorXY")
    light = get_light(coordinator)
    assert light.capability.xy_color_key == xy.key
    assert xy.parameter["max"] == UINT32_MAX + 8
    await light.async_turn_on(xy_color=(0.3, 0.4))
    write = coordinator.async_write_trait.await_args_list[0].args
    assert write[0] == xy.key
    assert type(write[1]) is int and 0 <= write[1] <= UINT32_MAX


@pytest.mark.parametrize("bad_max", [UINT32_MAX - 1, UINT32_MAX + 9, 2**40, -1])
async def test_xy_out_of_contract_metadata_is_rejected(hass, bad_max):
    coordinator = FakeCoordinator(hass)
    device = prepare_real_metadata(coordinator)
    xy = next(t for t in device.traits.values() if t.key.trait_code == "ColorXY")
    xy.parameter["max"] = bad_max
    light = get_light(coordinator)
    assert light.capability.xy_color_key is None
    assert light.supported_color_modes == {ColorMode.COLOR_TEMP}
    with pytest.raises(HomeAssistantError):
        await light.async_turn_on(xy_color=(0.3, 0.4))
    coordinator.async_write_trait.assert_not_awaited()


@pytest.mark.parametrize(
    ("unit", "minimum", "maximum"),
    [
        ("mired", 2703, 6536),
        ("°C", 2703, 6536),
        ("K", 100, 500),
        ("unsupported", 3000, 7000),
        ("Kelvin", 0, 65535),
    ],
)
async def test_incompatible_color_temperature_units_fail_closed(
    hass, unit, minimum, maximum
):
    coordinator = FakeCoordinator(hass)
    device = prepare_real_metadata(coordinator, unit)
    temperature = next(
        t for t in device.traits.values() if t.key.trait_code == "ColorTemperature"
    )
    temperature.parameter["min"] = minimum
    temperature.parameter["max"] = maximum
    light = get_light(coordinator)
    assert light.capability.color_temp_key is None
    with pytest.raises(HomeAssistantError):
        await light.async_turn_on(color_temp_kelvin=4000)
    coordinator.async_write_trait.assert_not_awaited()


async def test_legacy_mired_metadata_still_writes_correct_raw_value(hass):
    coordinator = FakeCoordinator(hass)
    device = prepare_real_metadata(coordinator, "mired")
    temperature = next(
        t for t in device.traits.values() if t.key.trait_code == "ColorTemperature"
    )
    temperature.parameter["min"] = 153
    temperature.parameter["max"] = 500
    temperature.value = 250
    light = get_light(coordinator)
    assert light.min_color_temp_kelvin == 2000
    assert light.max_color_temp_kelvin == 6535
    assert light.color_temp_kelvin == 4000
    await light.async_turn_on(color_temp_kelvin=4000)
    assert coordinator.async_write_trait.await_args_list[0].args == (
        temperature.key,
        250,
    )


async def test_cannot_send_32_bit_overflow_or_unapproved_color_writes(
    coordinator, mock_client
):
    """Exercise the real coordinator authorization path, not an AsyncMock."""
    device = prepare_real_metadata(coordinator)
    temperature = next(
        t for t in device.traits.values() if t.key.trait_code == "ColorTemperature"
    )
    xy = next(t for t in device.traits.values() if t.key.trait_code == "ColorXY")
    await coordinator.async_write_trait(temperature.key, 4000)
    mock_client.async_write_trait.assert_awaited_once_with(
        temperature.key.as_dict(), 4000
    )
    mock_client.async_write_trait.reset_mock()
    for bad in (UINT32_MAX + 1, -1, 1.5, True):
        with pytest.raises(HomeAssistantError):
            await coordinator.async_write_trait(xy.key, bad)
    mock_client.async_write_trait.assert_not_awaited()
    for bad in (2702, 6537, 250, True):
        with pytest.raises(HomeAssistantError):
            await coordinator.async_write_trait(temperature.key, bad)
    mock_client.async_write_trait.assert_not_awaited()
