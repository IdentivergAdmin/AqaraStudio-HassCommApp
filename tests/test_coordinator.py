"""Discovery, state ordering, and live event tests using real coordinator code."""

import asyncio
from copy import deepcopy
from unittest.mock import Mock, patch

import pytest

from custom_components.aqara_studio.coordinator import AqaraStudioCoordinator
from custom_components.aqara_studio.device import TraitKey, parse_device
from custom_components.aqara_studio.entity import device_identifier

CONTACT = TraitKey("synthetic-contact", 1, "Contact", "ContactSensorState")
REACHABLE = TraitKey("synthetic-contact", 0, "BasicInformation", "Reachable")
BUTTON = TraitKey("synthetic-button", 1, "Button", "ButtonEvent")


async def test_initial_snapshot_and_state_poll_do_not_reload_definitions(
    coordinator, mock_client
):
    assert len(coordinator.data) == 7
    assert coordinator.entity_available(CONTACT)
    assert coordinator.get_trait(CONTACT).value is False
    mock_client.async_get_definitions.assert_awaited_once()
    mock_client.state_values[CONTACT]["value"] = True
    await coordinator.async_refresh()
    assert coordinator.get_trait(CONTACT).value is True
    mock_client.async_get_definitions.assert_awaited_once()
    mock_client.async_get_devices.assert_awaited_once()


async def test_live_push_updates_without_http_and_does_not_reset_poll_timer(
    coordinator, mock_client
):
    calls = mock_client.async_read_traits.await_count
    with patch.object(coordinator, "_async_unsub_refresh") as cancel:
        await coordinator.async_handle_updates(
            [{**CONTACT.as_dict(), "value": True, "time": 100}]
        )
        cancel.assert_not_called()
    assert coordinator.get_trait(CONTACT).value is True
    assert mock_client.async_read_traits.await_count == calls


async def test_old_push_and_conflicting_equal_timestamp_are_safe(coordinator):
    await coordinator.async_handle_updates(
        [{**CONTACT.as_dict(), "value": True, "time": 200}]
    )
    await coordinator.async_handle_updates(
        [{**CONTACT.as_dict(), "value": False, "time": 199}]
    )
    assert coordinator.get_trait(CONTACT).value is True
    await coordinator.async_handle_updates(
        [{**CONTACT.as_dict(), "value": False, "time": 200}]
    )
    assert coordinator.get_trait(CONTACT).value is True
    assert not coordinator.entity_available(CONTACT)


async def test_zero_timestamp_is_valid_state(coordinator):
    await coordinator.async_handle_updates(
        [{**CONTACT.as_dict(), "value": True, "time": 0}]
    )
    assert coordinator.get_trait(CONTACT).value is True
    assert coordinator.entity_available(CONTACT)


async def test_unordered_reconnect_buffer_cannot_overwrite_snapshot(
    coordinator, mock_client
):
    mock_client.state_values[CONTACT]["value"] = True
    await coordinator.async_refresh()
    coordinator.websocket.replaying_buffer = True
    await coordinator.async_handle_updates(
        [{**CONTACT.as_dict(), "value": False, "time": 0}]
    )
    assert coordinator.get_trait(CONTACT).value is True
    assert not coordinator.entity_available(CONTACT)
    coordinator.websocket.replaying_buffer = False
    await coordinator._buffer_snapshot_task
    assert coordinator.get_trait(CONTACT).value is True
    assert coordinator.entity_available(CONTACT)


async def test_old_button_timestamp_cannot_trigger_after_restart(coordinator):
    coordinator.options["enable_button_events"] = True
    listener = Mock()
    coordinator.async_add_event_listener(BUTTON, listener)
    await coordinator.async_handle_updates(
        [{**BUTTON.as_dict(), "value": 0, "time": 1}]
    )
    listener.assert_not_called()


async def test_http_response_cannot_overwrite_newer_push(coordinator, mock_client):
    started = asyncio.Event()
    release = asyncio.Event()
    original = mock_client.async_read_traits.side_effect

    async def delayed(addresses):
        result = await original(addresses)
        started.set()
        await release.wait()
        return result

    mock_client.async_read_traits.side_effect = delayed
    task = asyncio.create_task(coordinator.async_refresh())
    await started.wait()
    await coordinator.async_handle_updates(
        [{**CONTACT.as_dict(), "value": True, "time": 0}]
    )
    release.set()
    await task
    assert coordinator.get_trait(CONTACT).value is True
    assert coordinator.entity_available(CONTACT)


async def test_dynamic_device_and_renames_keep_identity(coordinator, mock_client):
    definition = deepcopy(mock_client.definitions[0])
    record = deepcopy(mock_client.inventory[0])
    record["deviceId"] = definition["deviceId"] = "synthetic-new"
    record["deviceName"] = "Added after startup"
    mock_client.inventory.append(record)
    mock_client.definitions.append(definition)
    new_device = parse_device(record, definition)
    for key, trait in new_device.traits.items():
        mock_client.state_values[key] = {
            **key.as_dict(),
            "value": trait.value,
            "time": 0,
        }
    coordinator._last_inventory = float("-inf")
    await coordinator.async_refresh()
    assert "synthetic-new" in coordinator.data
    old_id = CONTACT.unique_id(coordinator.studio_id)
    mock_client.inventory[0]["deviceName"] = "Renamed Contact"
    mock_client.inventory[0]["space"] = {"name": "Another space"}
    coordinator._last_inventory = float("-inf")
    await coordinator.async_refresh()
    assert coordinator.data[CONTACT.device_id].name == "Renamed Contact"
    assert CONTACT.unique_id(coordinator.studio_id) == old_id
    assert len(coordinator.data) == 8


async def test_missing_inventory_retains_device_until_readded(coordinator, mock_client):
    saved = mock_client.inventory.pop(0)
    coordinator._last_inventory = float("-inf")
    await coordinator.async_refresh()
    assert CONTACT.device_id in coordinator.data
    assert not coordinator.data[CONTACT.device_id].present
    assert not coordinator.entity_available(CONTACT)
    mock_client.inventory.append(saved)
    coordinator._last_inventory = float("-inf")
    await coordinator.async_refresh()
    assert coordinator.data[CONTACT.device_id].present
    assert coordinator.entity_available(CONTACT)


async def test_definition_refresh_adds_new_traits(coordinator, mock_client):
    definition = mock_client.definitions[0]
    definition["endpoints"][1]["functions"].append(
        {
            "functionCode": "Temperature",
            "traits": [
                {
                    "traitCode": "CurrentTemperature",
                    "value": 21.5,
                    "time": 0,
                    "parameter": {
                        "readable": True,
                        "writable": False,
                        "subscribable": True,
                        "unit": "°C",
                    },
                }
            ],
        }
    )
    new_key = TraitKey(CONTACT.device_id, 1, "Temperature", "CurrentTemperature")
    mock_client.state_values[new_key] = {**new_key.as_dict(), "value": 21.5, "time": 0}
    coordinator._definitions_dirty = True
    coordinator._last_inventory = float("-inf")
    await coordinator.async_refresh()
    assert coordinator.get_trait(new_key).value == 21.5


async def test_manual_cleanup_requires_two_complete_absences(coordinator, mock_client):
    device = Mock(
        identifiers={
            (
                "aqara_studio",
                device_identifier(coordinator.studio_id, CONTACT.device_id),
            )
        }
    )
    root = Mock(
        identifiers={
            (
                "aqara_studio",
                device_identifier(coordinator.studio_id, coordinator.studio_id),
            )
        }
    )
    assert not coordinator.can_remove_registry_device(device)
    mock_client.inventory.pop(0)
    coordinator._last_inventory = float("-inf")
    await coordinator.async_refresh()
    assert not coordinator.can_remove_registry_device(device)
    coordinator._last_inventory = float("-inf")
    await coordinator.async_refresh()
    assert coordinator.can_remove_registry_device(device)
    assert not coordinator.can_remove_registry_device(root)
    assert CONTACT.device_id in coordinator.data


async def test_cached_and_unordered_button_values_never_fire(coordinator, mock_client):
    coordinator.options["enable_button_events"] = True
    # This synthetic clock value stands for the last confirmed connection epoch.
    coordinator._event_not_before = 100
    mock_client.state_values[BUTTON]["time"] = 100
    mock_client.state_values[BUTTON]["value"] = 0
    listener = Mock()
    remove = coordinator.async_add_event_listener(BUTTON, listener)
    await coordinator.async_refresh()
    listener.assert_not_called()
    await coordinator.async_handle_updates(
        [{**BUTTON.as_dict(), "value": 0, "time": 100}]
    )
    await coordinator.async_handle_updates(
        [{**BUTTON.as_dict(), "value": 0, "time": 0}]
    )
    listener.assert_not_called()
    await coordinator.async_handle_updates(
        [{**BUTTON.as_dict(), "value": 0, "time": 101}]
    )
    listener.assert_called_once_with(0, 101)
    await coordinator.async_handle_updates(
        [{**BUTTON.as_dict(), "value": 0, "time": 101}]
    )
    listener.assert_called_once()
    await coordinator.async_handle_updates(
        [{**BUTTON.as_dict(), "value": 0, "time": 102}]
    )
    assert listener.call_count == 2
    remove()
    await coordinator.async_handle_updates(
        [{**BUTTON.as_dict(), "value": 1, "time": 103}]
    )
    assert listener.call_count == 2


@pytest.mark.parametrize(("count", "max_batches"), [(40, 4), (100, 8)])
async def test_whole_home_load_batched(
    hass, config_entry, mock_client, count, max_batches
):
    config_entry.add_to_hass(hass)
    original_record, original_definition = (
        deepcopy(mock_client.inventory[0]),
        deepcopy(mock_client.definitions[0]),
    )
    mock_client.inventory = []
    mock_client.definitions = []
    mock_client.state_values = {}
    for index in range(count):
        record, definition = deepcopy(original_record), deepcopy(original_definition)
        record["deviceId"] = definition["deviceId"] = f"synthetic-load-{index}"
        mock_client.inventory.append(record)
        mock_client.definitions.append(definition)
        for key, trait in parse_device(record, definition).traits.items():
            mock_client.state_values[key] = {
                **key.as_dict(),
                "value": trait.value,
                "time": 0,
            }
    coordinator = AqaraStudioCoordinator(hass, config_entry, mock_client)
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert len(coordinator.data) == count
    assert mock_client.async_read_traits.await_count <= max_batches
    assert all(
        len(call.args[0]) <= 50
        for call in mock_client.async_read_traits.await_args_list
    )
    mock_client.async_get_definitions.assert_awaited_once()
    await coordinator.async_shutdown()
