"""Capability discovery and stable registry identities."""

from copy import deepcopy
from unittest.mock import Mock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aqara_studio.binary_sensor import AqaraStudioBinarySensor
from custom_components.aqara_studio.device import (
    TraitKey,
    discover_capabilities,
    parse_device,
    unknown_capabilities,
)
from custom_components.aqara_studio.entity import async_setup_platform_entities

from .entity_helpers import FakeCoordinator, fixture_data, fixture_devices


def test_exact_capabilities_and_access():
    devices = fixture_devices()
    contact = devices["synthetic-contact"]
    caps = discover_capabilities(contact)
    assert {cap.kind for cap in caps} == {"contact", "battery", "voltage"}
    assert contact.manufacturer == "Aqara"
    assert contact.model == "synthetic.model"
    assert contact.firmware == "example-1.0"
    assert discover_capabilities(devices["synthetic-unknown"]) == []
    assert (
        unknown_capabilities(devices["synthetic-unknown"])[0]["trait"]
        == "UnverifiedTrait"
    )
    assert "value" not in unknown_capabilities(devices["synthetic-unknown"])[0]
    trait = next(
        t for k, t in contact.traits.items() if k.trait_code == "ContactSensorState"
    )
    trait.parameter.pop("readable")
    assert "contact" not in {cap.kind for cap in discover_capabilities(contact)}


def test_duplicates_and_partial_definitions():
    raw = fixture_data()
    record, definition = raw["inventory"][0], raw["definitions"][0]
    definition["endpoints"].append(deepcopy(definition["endpoints"][1]))
    definition["endpoints"].extend([None, {"endpointId": True}, {"endpointId": "1"}])
    device = parse_device(record, definition)
    assert len(discover_capabilities(device)) == 3
    assert len(device.traits) == 7
    with pytest.raises(ValueError):
        parse_device({"deviceId": "different"}, definition)
    with pytest.raises(ValueError):
        parse_device({}, {})


def test_conflicting_duplicates_never_choose_closed():
    raw = fixture_data()
    record, definition = raw["inventory"][0], raw["definitions"][0]
    duplicate = deepcopy(definition["endpoints"][1])
    duplicate["functions"][0]["traits"][0]["value"] = True
    definition["endpoints"].append(duplicate)
    device = parse_device(record, definition)
    contact = next(
        t for k, t in device.traits.items() if k.trait_code == "ContactSensorState"
    )
    assert contact.value is None


def test_unique_id_stable_across_renames_and_space():
    raw = fixture_data()
    record, definition = raw["inventory"][0], raw["definitions"][0]
    old = discover_capabilities(parse_device(record, definition))[0]
    record.update(deviceName="Renamed", space={"name": "New room"})
    definition["name"] = "Changed again"
    new = discover_capabilities(parse_device(record, definition))[0]
    assert old.key.unique_id("studio") == new.key.unique_id("studio")
    assert old.key.unique_id("other-studio") != new.key.unique_id("studio")
    assert TraitKey("a:b", 1, "c", "d").unique_id("x") != TraitKey(
        "b", 1, "c", "d"
    ).unique_id("x:a")


def test_40_devices_and_multiple_endpoints():
    raw = fixture_data()
    seen = set()
    for i in range(40):
        record, definition = (
            deepcopy(raw["inventory"][0]),
            deepcopy(raw["definitions"][0]),
        )
        record["deviceId"] = definition["deviceId"] = f"synthetic-contact-{i}"
        extra = deepcopy(definition["endpoints"][1])
        extra["endpointId"] = 2
        definition["endpoints"].append(extra)
        caps = discover_capabilities(parse_device(record, definition))
        assert len(caps) == 6
        seen.update(cap.key.unique_id("studio") for cap in caps)
    assert len(seen) == 240


async def test_dynamic_platform_adds_without_duplicates(hass):
    coordinator = FakeCoordinator(hass)
    contact = coordinator.data["synthetic-contact"]
    coordinator.data = {contact.device_id: contact}
    entry = MockConfigEntry(domain="aqara_studio")
    added = Mock()
    async_setup_platform_entities(
        entry, coordinator, "binary_sensor", added, AqaraStudioBinarySensor
    )
    assert len(added.call_args.args[0]) == 1
    coordinator.async_update_listeners()
    assert added.call_count == 1
    new_device = fixture_devices()["synthetic-leak"]
    coordinator.data[new_device.device_id] = new_device
    coordinator.async_update_listeners()
    assert added.call_count == 2
    assert len(added.call_args.args[0]) == 1
    coordinator.async_update_listeners()
    assert added.call_count == 2
    await entry._async_process_on_unload(hass)
