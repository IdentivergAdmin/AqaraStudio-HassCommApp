"""Native ClosetLight discovery and self-explanatory light status entities."""

from __future__ import annotations

from custom_components.aqara_studio.device import (
    Trait,
    TraitKey,
    discover_capabilities,
    light_control_status,
)
from custom_components.aqara_studio.light import AqaraStudioLight
from custom_components.aqara_studio.sensor import AqaraStudioSensor

from .entity_helpers import FakeCoordinator


def add_lightstrip_traits(device) -> None:
    """Model the writable same-endpoint capabilities seen in M300 diagnostics."""
    onoff = next(
        trait for trait in device.traits.values() if trait.key.trait_code == "OnOff"
    )
    for fn, code, parameter, value in (
        ("Lighting", "EnableFlowMode", {"type": "Bool"}, False),
        ("ColorControl", "ColorXY", {"type": "UInt32", "min": 0, "max": 4294967295}, 0),
        ("ColorControl", "ColorTemperature", {"type": "UInt32", "min": 153, "max": 500}, 270),
    ):
        key = TraitKey(onoff.key.device_id, onoff.key.endpoint_id, fn, code)
        device.traits[key] = Trait(
            key, {"readable": True, "writable": True, **parameter}, value,
            endpoint_type="Unknown",
        )


async def test_m300_lightstrip_becomes_light_without_legacy_global_toggle(hass):
    coordinator = FakeCoordinator(hass, {"enable_controls": False})
    device = coordinator.data["synthetic-light"]
    primary = next(t for t in device.traits.values() if t.key.trait_code == "OnOff")
    primary.endpoint_type = "Unknown"
    add_lightstrip_traits(device)
    capabilities = discover_capabilities(device, coordinator.options)
    assert [cap.platform for cap in capabilities].count("light") == 1
    cap = next(cap for cap in capabilities if cap.platform == "light")
    assert cap.brightness_key
    assert cap.xy_color_key
    assert cap.color_temp_key
    entity = AqaraStudioLight(coordinator, cap)
    assert entity.name is None
    await entity.async_turn_on()
    coordinator.async_write_trait.assert_awaited_once_with(cap.key, True)
    coordinator.async_write_trait.reset_mock()
    await entity.async_turn_off()
    coordinator.async_write_trait.assert_awaited_once_with(cap.key, False)


async def test_light_readiness_is_visible_even_when_controls_disabled(hass):
    coordinator = FakeCoordinator(hass, {"enable_light_controls": False})
    device = coordinator.data["synthetic-light"]
    status = next(
        cap for cap in discover_capabilities(device, coordinator.options)
        if cap.kind == "light_readiness"
    )
    entity = AqaraStudioSensor(coordinator, status)
    assert entity.native_value == "disabled_in_options"
    assert entity.state_class is None
    coordinator.options["enable_light_controls"] = True
    assert entity.native_value == "ready"
    primary = coordinator.get_trait(status.key)
    primary.parameter["writable"] = False
    assert entity.native_value == "api_read_only"
    primary.parameter["writable"] = True
    primary.parameter["type"] = "Enum"
    assert entity.native_value == "unsupported_onoff_type"


async def test_light_fallback_requires_unambiguous_device_type(hass):
    coordinator = FakeCoordinator(hass)
    device = coordinator.data["synthetic-light"]
    primary = next(t for t in device.traits.values() if t.key.trait_code == "OnOff")
    primary.endpoint_type = "Unknown"
    assert any(cap.platform == "light" for cap in discover_capabilities(device))
    device.device_types = ("Light", "Switch")
    assert not any(cap.platform == "light" for cap in discover_capabilities(device))
    device.device_types = ("Unknown",)
    assert not any(cap.platform == "light" for cap in discover_capabilities(device))
    add_lightstrip_traits(device)
    assert any(cap.platform == "light" for cap in discover_capabilities(device))


async def test_legacy_switch_setting_does_not_override_explicit_light_off(hass):
    coordinator = FakeCoordinator(
        hass, {"enable_controls": True, "enable_light_controls": False}
    )
    light = coordinator.data["synthetic-light"]
    assert light_control_status(
        light, next(t for t in light.traits.values() if t.key.trait_code == "OnOff"),
        coordinator.options
    ) == "disabled_in_options"
    assert not any(cap.platform == "light" for cap in discover_capabilities(light, coordinator.options))
    switch = coordinator.data["synthetic-switch"]
    assert any(cap.platform == "switch" for cap in discover_capabilities(switch, coordinator.options))
