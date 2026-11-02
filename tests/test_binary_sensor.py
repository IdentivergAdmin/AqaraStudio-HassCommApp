"""No missing, malformed or unconfirmed sensor value becomes falsely safe."""

import pytest
from homeassistant.helpers import device_registry as dr

from custom_components.aqara_studio.binary_sensor import AqaraStudioBinarySensor
from custom_components.aqara_studio.device import discover_capabilities, strict_bool

from .entity_helpers import FakeCoordinator


def entity_for(coordinator, device_id, kind):
    capability = next(
        c for c in discover_capabilities(coordinator.data[device_id]) if c.kind == kind
    )
    return AqaraStudioBinarySensor(coordinator, capability)


@pytest.mark.parametrize(
    "value", [None, "", "closed", "open", "unknown", 2, -1, 1.5, [], {}, float("nan")]
)
def test_strict_bool_does_not_guess(value):
    assert strict_bool(value) is None


async def test_contact_requires_confirmed_polarity(hass):
    coordinator = FakeCoordinator(hass)
    sensor = entity_for(coordinator, "synthetic-contact", "contact")
    assert sensor.is_on is None
    assert sensor.extra_state_attributes["raw_value"] is False
    assert sensor.extra_state_attributes["polarity_confirmation_required"] is True
    coordinator.options["contact_polarity"] = "true_is_open"
    assert sensor.is_on is False
    sensor.trait.value = True
    assert sensor.is_on is True
    coordinator.options["contact_polarity"] = "false_is_open"
    assert sensor.is_on is False
    sensor.trait.value = False
    assert sensor.is_on is True


async def test_contact_unknown_unavailable_and_zero_timestamp(hass):
    coordinator = FakeCoordinator(hass, {"contact_polarity": "true_is_open"})
    sensor = entity_for(coordinator, "synthetic-contact", "contact")
    assert sensor.trait.time == 0
    assert sensor.available
    assert sensor.is_on is False
    sensor.trait.value = None
    assert sensor.is_on is None
    for key, trait in sensor.device.traits.items():
        if key.trait_code == "Reachable":
            trait.value = False
    assert not sensor.available
    assert sensor.is_on is None


async def test_leak_polarity_never_defaults_dry(hass):
    coordinator = FakeCoordinator(hass)
    sensor = entity_for(coordinator, "synthetic-leak", "leak")
    assert sensor.is_on is None
    coordinator.options["leak_polarity"] = "true_is_wet"
    assert sensor.is_on is False
    sensor.trait.value = "1"
    assert sensor.is_on is True
    sensor.trait.value = "not-a-value"
    assert sensor.is_on is None
    coordinator.transport_available = False
    assert not sensor.available


async def test_device_registry_identity_and_rename(hass):
    coordinator = FakeCoordinator(hass)
    sensor = entity_for(coordinator, "synthetic-contact", "contact")
    original = sensor.unique_id
    gateway = dr.async_get(hass).async_get_or_create(
        config_entry_id=coordinator.config_entry.entry_id,
        identifiers={("aqara_studio", "synthetic-studio:synthetic-studio")},
    )
    assert sensor.device_info["via_device_id"] == gateway.id
    sensor.device.name = "New device name"
    assert sensor.unique_id == original
    assert sensor.device_info["name"] == "New device name"
