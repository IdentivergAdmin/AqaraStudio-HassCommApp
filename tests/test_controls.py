"""Opt-in actuators with verified access, endpoint types, and units."""

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.aqara_studio.device import discover_capabilities
from custom_components.aqara_studio.light import AqaraStudioLight
from custom_components.aqara_studio.switch import AqaraStudioSwitch

from .entity_helpers import FakeCoordinator


async def test_controls_disabled_by_default_and_type_gated(hass):
    coordinator = FakeCoordinator(hass)
    device = coordinator.data["synthetic-light"]
    assert {c.platform for c in discover_capabilities(device)} == {"binary_sensor"}
    options = {"enable_controls": True}
    assert {c.platform for c in discover_capabilities(device, options)} == {
        "binary_sensor",
        "light",
    }
    trait = next(t for k, t in device.traits.items() if k.trait_code == "OnOff")
    trait.parameter["writable"] = False
    assert {c.platform for c in discover_capabilities(device, options)} == {
        "binary_sensor"
    }
    trait.parameter["writable"] = True
    trait.parameter["type"] = "Enum"
    assert {c.platform for c in discover_capabilities(device, options)} == {
        "binary_sensor"
    }
    trait.parameter["type"] = "Bool"
    for endpoint_type in ("Lock", "GarageDoor", "Valve", "Unknown", "Public"):
        trait.endpoint_type = endpoint_type
        assert {c.platform for c in discover_capabilities(device, options)} == {
            "binary_sensor"
        }


async def test_switch_writes_real_boolean_not_optimistic(hass):
    coordinator = FakeCoordinator(hass, {"enable_controls": True})
    cap = next(
        c
        for c in discover_capabilities(
            coordinator.data["synthetic-switch"], coordinator.options
        )
        if c.platform == "switch"
    )
    entity = AqaraStudioSwitch(coordinator, cap)
    assert entity.is_on is True
    await entity.async_turn_off()
    coordinator.async_write_trait.assert_awaited_once_with(cap.key, False)
    assert entity.is_on is True
    coordinator.transport_available = False
    with pytest.raises(HomeAssistantError):
        await entity.async_turn_on()
    assert coordinator.async_write_trait.await_count == 1


async def test_percentage_brightness_and_zero_turns_off(hass):
    coordinator = FakeCoordinator(hass, {"enable_controls": True})
    cap = next(
        c
        for c in discover_capabilities(
            coordinator.data["synthetic-light"], coordinator.options
        )
        if c.platform == "light"
    )
    entity = AqaraStudioLight(coordinator, cap)
    assert entity.brightness == 128
    available = coordinator.entity_available
    coordinator.entity_available = lambda key: (
        key != cap.brightness_key and available(key)
    )
    assert entity.brightness is None
    coordinator.entity_available = available
    await entity.async_turn_on(brightness=128)
    calls = coordinator.async_write_trait.await_args_list
    assert calls[0].args == (cap.brightness_key, 50)
    assert calls[1].args == (cap.key, True)
    assert entity.is_on is False
    coordinator.async_write_trait.reset_mock()
    await entity.async_turn_on(brightness=0)
    coordinator.async_write_trait.assert_awaited_once_with(cap.key, False)
    with pytest.raises(HomeAssistantError):
        await entity.async_turn_on(brightness=256)


async def test_unknown_brightness_range_is_not_enabled(hass):
    coordinator = FakeCoordinator(hass, {"enable_controls": True})
    device = coordinator.data["synthetic-light"]
    brightness = next(
        t for k, t in device.traits.items() if k.trait_code == "CurrentLevel"
    )
    brightness.parameter["max"] = 254
    cap = next(
        c
        for c in discover_capabilities(device, coordinator.options)
        if c.platform == "light"
    )
    assert cap.brightness_key is None
    entity = AqaraStudioLight(coordinator, cap)
    with pytest.raises(HomeAssistantError):
        await entity.async_turn_on(brightness=200)
    coordinator.async_write_trait.assert_not_awaited()


async def test_low_nonzero_brightness_does_not_send_zero_level(hass):
    coordinator = FakeCoordinator(hass, {"enable_controls": True})
    device = coordinator.data["synthetic-light"]
    brightness = next(
        t for k, t in device.traits.items() if k.trait_code == "CurrentLevel"
    )
    brightness.parameter.update(min=0, step=1)
    cap = next(
        c
        for c in discover_capabilities(device, coordinator.options)
        if c.platform == "light"
    )
    entity = AqaraStudioLight(coordinator, cap)
    await entity.async_turn_on(brightness=1)
    assert coordinator.async_write_trait.await_args_list[0].args == (
        cap.brightness_key,
        1,
    )


async def test_brightness_step_and_integer_wire_value(hass):
    coordinator = FakeCoordinator(hass, {"enable_controls": True})
    device = coordinator.data["synthetic-light"]
    brightness = next(
        t for k, t in device.traits.items() if k.trait_code == "CurrentLevel"
    )
    brightness.parameter.update(type="Integer", min=0, step=2)
    cap = next(
        c
        for c in discover_capabilities(device, coordinator.options)
        if c.platform == "light"
    )
    entity = AqaraStudioLight(coordinator, cap)
    await entity.async_turn_on(brightness=1)
    written = coordinator.async_write_trait.await_args_list[0].args[1]
    assert written == 2
    assert type(written) is int
    brightness.parameter["min"] = 1
    coordinator.async_write_trait.reset_mock()
    await entity.async_turn_on(brightness=255)
    assert coordinator.async_write_trait.await_args_list[0].args[1] == 99
