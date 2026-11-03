"""Measurements, units, battery sentinel, and diagnostic defaults."""

import pytest

from custom_components.aqara_studio.device import discover_capabilities
from custom_components.aqara_studio.sensor import AqaraStudioSensor

from .entity_helpers import FakeCoordinator


def sensor_for(coordinator, device_id, kind):
    cap = next(
        c for c in discover_capabilities(coordinator.data[device_id]) if c.kind == kind
    )
    return AqaraStudioSensor(coordinator, cap)


async def test_environment_units_and_values(hass):
    coordinator = FakeCoordinator(hass)
    temperature = sensor_for(coordinator, "synthetic-environment", "temperature")
    humidity = sensor_for(coordinator, "synthetic-environment", "humidity")
    illuminance = sensor_for(coordinator, "synthetic-environment", "illuminance")
    assert (temperature.native_value, temperature.native_unit_of_measurement) == (
        22.5,
        "°C",
    )
    assert (humidity.native_value, humidity.native_unit_of_measurement) == (43.7, "%")
    assert (illuminance.native_value, illuminance.native_unit_of_measurement) == (
        55,
        "lx",
    )


@pytest.mark.parametrize("value", [None, True, "nan", float("inf"), -1, 101, 255])
async def test_battery_invalid_values_unknown(hass, value):
    coordinator = FakeCoordinator(hass)
    sensor = sensor_for(coordinator, "synthetic-contact", "battery")
    sensor.trait.value = value
    assert sensor.native_value is None


async def test_voltage_conversion_and_diagnostic_defaults(hass):
    coordinator = FakeCoordinator(hass)
    sensor = sensor_for(coordinator, "synthetic-contact", "voltage")
    assert sensor.native_value == pytest.approx(3.01)
    assert sensor.entity_category == "diagnostic"
    assert sensor.entity_registry_enabled_default is False
    sensor.trait.parameter.update(unit="mV", min=0, max=5000)
    sensor.trait.value = 3010
    sensor = sensor_for(coordinator, "synthetic-contact", "voltage")
    assert sensor.native_value == pytest.approx(3.01)
    assert sensor.native_unit_of_measurement == "V"
    sensor.trait.parameter["unit"] = "unrecognized"
    assert "voltage" not in {c.kind for c in discover_capabilities(sensor.device)}
