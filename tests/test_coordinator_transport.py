"""Coordinator integration contracts between REST, push, and HA lifecycle."""

import asyncio
from copy import deepcopy
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed

from custom_components.aqara_studio.api import AqaraAuthError, AqaraConnectionError
from custom_components.aqara_studio.const import (
    CONF_INVENTORY_INTERVAL,
    CONF_POLL_INTERVAL,
    CONF_RECONCILE_INTERVAL,
)
from custom_components.aqara_studio.coordinator import AqaraStudioCoordinator
from custom_components.aqara_studio.device import TraitKey

CONTACT = TraitKey("synthetic-contact", 1, "Contact", "ContactSensorState")
LEAK = TraitKey("synthetic-leak", 1, "WaterLeak", "LeakState")


async def test_reconnect_snapshot_is_an_availability_barrier(coordinator, mock_client):
    started = asyncio.Event()
    release = asyncio.Event()
    original_read = mock_client.async_read_traits.side_effect
    mock_client.state_values[CONTACT].update(value=True, time=200)

    async def held_read(addresses):
        started.set()
        await release.wait()
        return await original_read(addresses)

    mock_client.async_read_traits.side_effect = held_read
    task = asyncio.create_task(coordinator.async_handle_connection(True))
    try:
        await asyncio.wait_for(started.wait(), 2)
        assert not coordinator.entity_available(CONTACT)
        release.set()
        await asyncio.wait_for(task, 2)
        assert coordinator.entity_available(CONTACT)
        assert coordinator.get_trait(CONTACT).value is True
        assert coordinator.push_connected
        assert coordinator.update_interval == timedelta(
            seconds=min(
                coordinator.options[CONF_RECONCILE_INTERVAL],
                coordinator.options[CONF_INVENTORY_INTERVAL],
            )
        )
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_rest_reply_cannot_overwrite_a_newer_inflight_push(
    coordinator, mock_client
):
    started = asyncio.Event()
    release = asyncio.Event()
    original_read = mock_client.async_read_traits.side_effect
    mock_client.state_values[CONTACT].update(value=False, time=100)

    async def stale_read(addresses):
        snapshot = await original_read(addresses)
        started.set()
        await release.wait()
        return snapshot

    mock_client.async_read_traits.side_effect = stale_read
    task = asyncio.create_task(coordinator.async_refresh())
    try:
        await asyncio.wait_for(started.wait(), 2)
        await coordinator.async_handle_updates(
            [{**CONTACT.as_dict(), "value": True, "time": 200}]
        )
        release.set()
        await asyncio.wait_for(task, 2)
        assert coordinator.get_trait(CONTACT).value is True
        assert coordinator.get_trait(CONTACT).time == 200
        assert coordinator.entity_available(CONTACT)
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_disconnect_selects_polling_and_rest_recovers(coordinator, mock_client):
    await coordinator.async_handle_connection(True)
    assert coordinator.push_connected
    await coordinator.async_handle_connection(False)
    assert not coordinator.push_connected
    assert not coordinator.entity_available(CONTACT)
    assert coordinator.update_interval == timedelta(
        seconds=coordinator.options[CONF_POLL_INTERVAL]
    )
    mock_client.state_values[CONTACT].update(value=True, time=300)
    await asyncio.wait_for(coordinator._buffer_snapshot_task, timeout=2)
    assert coordinator.get_trait(CONTACT).value is True
    assert coordinator.entity_available(CONTACT)


async def test_failed_reconnect_snapshot_never_restores_old_safe_state(
    coordinator, mock_client
):
    assert coordinator.get_trait(CONTACT).value is False
    mock_client.async_read_traits.side_effect = AqaraConnectionError(
        "synthetic disconnected transport"
    )
    with pytest.raises(AqaraConnectionError, match="snapshot"):
        await coordinator.async_handle_connection(True)
    assert not coordinator.push_connected
    assert not coordinator.entity_available(CONTACT)
    assert not coordinator.entity_available(LEAK)


async def test_revoked_websocket_token_starts_reauth_and_blocks_states(coordinator):
    with (
        patch.object(
            coordinator.websocket,
            "async_run",
            new=AsyncMock(side_effect=AqaraAuthError("synthetic revoked token")),
        ),
        patch.object(coordinator.config_entry, "async_start_reauth") as reauth,
    ):
        await coordinator._async_run_websocket()
        reauth.assert_called_once_with(coordinator.hass)
    assert not coordinator.entity_available(CONTACT)
    assert not coordinator.entity_available(LEAK)
    assert not coordinator.push_connected
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_partial_batch_failure_is_isolated_and_concurrency_bounded(
    coordinator, mock_client
):
    original_read = mock_client.async_read_traits.side_effect
    active = 0
    peak = 0

    async def sometimes_fail(addresses):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(0)
            if addresses == [CONTACT.as_dict()]:
                raise AqaraConnectionError("synthetic one-batch failure")
            return await original_read(addresses)
        finally:
            active -= 1

    mock_client.async_read_traits.side_effect = sometimes_fail
    with patch("custom_components.aqara_studio.coordinator.STATE_BATCH_SIZE", 1):
        await coordinator.async_refresh()
    assert 1 < peak <= 4
    assert coordinator.last_update_success
    assert not coordinator.entity_available(CONTACT)
    assert coordinator.entity_available(LEAK)
    assert coordinator.partial_read_failures == 1
    mock_client.async_read_traits.side_effect = original_read
    await coordinator.async_refresh()
    assert coordinator.entity_available(CONTACT)


async def test_empty_install_keeps_discovery_alive_without_entities(
    hass, config_entry, mock_client
):
    inventory = deepcopy(mock_client.inventory)
    mock_client.inventory.clear()
    config_entry.add_to_hass(hass)
    coordinator = AqaraStudioCoordinator(hass, config_entry, mock_client)
    try:
        await coordinator.async_refresh()
        assert coordinator.last_update_success
        assert coordinator.data == {}
        await coordinator.async_start()
        assert coordinator._remove_keepalive is not None
        assert coordinator._listeners
        mock_client.inventory.extend(inventory)
        coordinator._last_inventory = float("-inf")
        await coordinator.async_refresh()
        assert CONTACT.device_id in coordinator.data
        assert coordinator.entity_available(CONTACT)
        assert mock_client.async_get_devices.await_count == 2
    finally:
        await coordinator.async_shutdown()
    assert not coordinator._listeners


async def test_rest_poll_uses_cached_definitions(coordinator, mock_client):
    definition_reads = mock_client.async_get_definitions.await_count
    inventory_reads = mock_client.async_get_devices.await_count
    mock_client.state_values[CONTACT].update(value=True, time=400)
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    assert coordinator.get_trait(CONTACT).value is True
    assert mock_client.async_get_definitions.await_count == definition_reads
    assert mock_client.async_get_devices.await_count == inventory_reads
