"""Aqara Studio: a local, capability-driven Home Assistant integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntry

from .api import AqaraStudioClient
from .const import CONF_TOKEN, PLATFORMS
from .coordinator import AqaraStudioCoordinator

type AqaraStudioConfigEntry = ConfigEntry[AqaraStudioCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: AqaraStudioConfigEntry) -> bool:
    """Authenticate and discover before adding any entity or starting push."""
    client = AqaraStudioClient(
        async_get_clientsession(hass), entry.data["host"], entry.data[CONF_TOKEN]
    )
    coordinator = AqaraStudioCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        await coordinator.async_start()
    except Exception:
        await coordinator.async_shutdown()
        raise
    return True


async def _async_options_updated(
    hass: HomeAssistant, entry: AqaraStudioConfigEntry
) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: AqaraStudioConfigEntry
) -> bool:
    """Unload entities before releasing the shared client and subscriptions."""
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_shutdown()
        return True
    return False


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: AqaraStudioConfigEntry, device_entry: DeviceEntry
) -> bool:
    """Permit user-requested removal only after repeated complete absence."""
    return entry.runtime_data.can_remove_registry_device(device_entry)
