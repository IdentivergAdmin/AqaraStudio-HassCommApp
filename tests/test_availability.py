"""Fail-safe availability and malformed-state behavior."""

import pytest

from custom_components.aqara_studio.api import AqaraAuthError, AqaraConnectionError
from custom_components.aqara_studio.binary_sensor import AqaraStudioBinarySensor
from custom_components.aqara_studio.device import discover_capabilities

from .test_coordinator import CONTACT, REACHABLE


def contact_entity(coordinator):
    cap = next(
        cap
        for cap in discover_capabilities(
            coordinator.data[CONTACT.device_id], coordinator.options
        )
        if cap.kind == "contact"
    )
    return AqaraStudioBinarySensor(coordinator, cap)


async def test_transport_loss_keeps_cached_value_but_entity_unavailable(
    coordinator, mock_client
):
    sensor = contact_entity(coordinator)
    assert sensor.is_on is False and sensor.available
    mock_client.async_read_traits.side_effect = AqaraConnectionError(
        "Synthetic timeout"
    )
    await coordinator.async_refresh()
    assert sensor.is_on is False  # cached only; HA renders unavailable
    assert not sensor.available


async def test_offline_reachable_and_recovery(coordinator):
    sensor = contact_entity(coordinator)
    await coordinator.async_handle_updates(
        [{**REACHABLE.as_dict(), "value": False, "time": 100}]
    )
    assert not sensor.available
    await coordinator.async_handle_updates(
        [{**REACHABLE.as_dict(), "value": True, "time": 101}]
    )
    assert sensor.available


@pytest.mark.parametrize("value", [None, "unrecognized", {}, 2])
async def test_malformed_advertised_reachable_is_unavailable(coordinator, value):
    await coordinator.async_handle_updates(
        [{**REACHABLE.as_dict(), "value": value, "time": 0}]
    )
    assert not contact_entity(coordinator).available


async def test_missing_reachable_capability_uses_inventory(coordinator):
    device = coordinator.data[CONTACT.device_id]
    del device.traits[REACHABLE]
    device.inventory_online = True
    assert contact_entity(coordinator).available
    device.inventory_online = False
    assert not contact_entity(coordinator).available


@pytest.mark.parametrize("value", [None, "garbage", {}, [], 2])
async def test_missing_or_corrupt_contact_is_unknown_never_closed(coordinator, value):
    await coordinator.async_handle_updates(
        [{**CONTACT.as_dict(), "value": value, "time": 0}]
    )
    sensor = contact_entity(coordinator)
    assert sensor.available
    assert sensor.is_on is None


async def test_missing_value_vs_omitted_trait(coordinator, mock_client):
    sensor = contact_entity(coordinator)
    del mock_client.state_values[CONTACT]["value"]
    await coordinator.async_refresh()
    assert sensor.available and sensor.is_on is None
    del mock_client.state_values[CONTACT]
    await coordinator.async_refresh()
    assert not sensor.available


async def test_auth_revocation_invalidates_all_states(coordinator, mock_client):
    mock_client.async_read_traits.side_effect = AqaraAuthError(
        "Synthetic revoked token"
    )
    await coordinator.async_refresh()
    assert not coordinator.entity_available(CONTACT)
    assert coordinator._auth_failed


async def test_sleepy_sensor_does_not_expire_from_source_timestamp(coordinator):
    trait = coordinator.get_trait(CONTACT)
    trait.time = 1
    assert coordinator.entity_available(CONTACT)
    trait.time = 0
    assert coordinator.entity_available(CONTACT)
