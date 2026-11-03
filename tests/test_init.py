"""Load real HA platforms and verify lifecycle, identities and task cleanup."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.aqara_studio import async_setup_entry, async_unload_entry
from custom_components.aqara_studio.api import AqaraAuthError, AqaraConnectionError
from custom_components.aqara_studio.const import DOMAIN
from custom_components.aqara_studio.device import TraitKey
from custom_components.aqara_studio.entity import device_identifier

CLIENT_PATH = "custom_components.aqara_studio.AqaraStudioClient"
CONTACT = TraitKey("synthetic-contact", 1, "Contact", "ContactSensorState")


async def test_native_setup_and_reload_preserve_registry(
    hass, config_entry, mock_client
):
    config_entry.add_to_hass(hass)
    with patch(CLIENT_PATH, return_value=mock_client):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
        assert config_entry.state is ConfigEntryState.LOADED
        registry = er.async_get(hass)
        entity_id = registry.async_get_entity_id(
            "binary_sensor", DOMAIN, CONTACT.unique_id("synthetic-studio")
        )
        assert entity_id is not None
        assert hass.states.get(entity_id).state == "off"
        entries_before = {
            entity.unique_id: entity.entity_id
            for entity in er.async_entries_for_config_entry(
                registry, config_entry.entry_id
            )
        }
        registry.async_update_entity(entity_id, name="Owner custom name")
        device = dr.async_get(hass).async_get_device_by_identifier(
            (DOMAIN, device_identifier("synthetic-studio", "synthetic-contact")),
            config_entry.entry_id,
        )
        assert device is not None
        gateway = dr.async_get(hass).async_get_device_by_identifier(
            (DOMAIN, device_identifier("synthetic-studio", "synthetic-studio")),
            config_entry.entry_id,
        )
        assert gateway is not None
        assert device.via_device_id == gateway.id
        original_device_id = device.id
        first_coordinator = config_entry.runtime_data

        assert await hass.config_entries.async_reload(config_entry.entry_id)
        await hass.async_block_till_done()
        assert first_coordinator._stopping
        assert config_entry.runtime_data is not first_coordinator
        entries_after = {
            entity.unique_id: entity.entity_id
            for entity in er.async_entries_for_config_entry(
                registry, config_entry.entry_id
            )
        }
        assert entries_after == entries_before
        assert registry.async_get(entity_id).name == "Owner custom name"
        assert registry.async_get(entity_id).device_id == original_device_id
        assert hass.states.get(entity_id).state == "off"

        coordinator = config_entry.runtime_data
        assert await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()
        assert coordinator._stopping
        assert not coordinator._event_listeners
        assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_unconfirmed_polarity_never_starts_as_safe(
    hass, config_entry, mock_client
):
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry, options={"enable_websocket": False}
    )
    with patch(CLIENT_PATH, return_value=mock_client):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
        entity_id = er.async_get(hass).async_get_entity_id(
            "binary_sensor", DOMAIN, CONTACT.unique_id("synthetic-studio")
        )
        state = hass.states.get(entity_id)
        assert state.state == "unknown"
        assert state.attributes["raw_value"] is False
        assert state.attributes["polarity_confirmation_required"] is True
        assert await hass.config_entries.async_unload(config_entry.entry_id)


@pytest.mark.parametrize(
    ("failure", "expected_state"),
    [
        (AqaraConnectionError("Offline"), ConfigEntryState.SETUP_RETRY),
        (AqaraAuthError("Rejected"), ConfigEntryState.SETUP_ERROR),
    ],
)
async def test_first_refresh_failure_adds_no_entities(
    hass, config_entry, mock_client, failure, expected_state
):
    config_entry.add_to_hass(hass)
    mock_client.async_get_gateways.side_effect = failure
    with patch(CLIENT_PATH, return_value=mock_client):
        assert not await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    assert config_entry.state is expected_state
    assert not er.async_entries_for_config_entry(
        er.async_get(hass), config_entry.entry_id
    )


async def test_websocket_task_single_per_entry_and_cancelled_on_reload(
    hass, config_entry, mock_client
):
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry, options={**config_entry.options, "enable_websocket": True}
    )
    started = asyncio.Event()

    async def run_socket():
        started.set()
        await asyncio.Event().wait()

    with (
        patch(CLIENT_PATH, return_value=mock_client),
        patch(
            "custom_components.aqara_studio.websocket.AqaraWebSocket.async_run",
            side_effect=run_socket,
        ) as socket,
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await asyncio.wait_for(started.wait(), timeout=5)
        first = config_entry.runtime_data
        assert first._ws_task is not None and not first._ws_task.done()
        socket.assert_awaited_once()
        started.clear()
        assert await hass.config_entries.async_reload(config_entry.entry_id)
        await asyncio.wait_for(started.wait(), timeout=5)
        assert first._ws_task.done()
        assert first._stopping
        assert socket.await_count == 2
        second = config_entry.runtime_data
        assert second is not first
        assert await hass.config_entries.async_unload(config_entry.entry_id)
        assert second._ws_task.done()


async def test_platform_setup_failure_shuts_down_coordinator(hass, config_entry):
    config_entry.add_to_hass(hass)
    coordinator = MagicMock()
    coordinator.async_config_entry_first_refresh = AsyncMock()
    coordinator.async_shutdown = AsyncMock()
    with (
        patch(
            "custom_components.aqara_studio.AqaraStudioCoordinator",
            return_value=coordinator,
        ),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            side_effect=RuntimeError("Failure"),
        ),
    ):
        with pytest.raises(RuntimeError, match="Failure"):
            await async_setup_entry(hass, config_entry)
    coordinator.async_shutdown.assert_awaited_once()


async def test_failed_platform_unload_keeps_transport(hass, config_entry):
    coordinator = MagicMock()
    coordinator.async_shutdown = AsyncMock()
    config_entry.runtime_data = coordinator
    with patch.object(
        hass.config_entries, "async_unload_platforms", return_value=False
    ):
        assert not await async_unload_entry(hass, config_entry)
    coordinator.async_shutdown.assert_not_awaited()
