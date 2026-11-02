"""Explicitly enabled, advertised writable switch/outlet endpoints."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .device import strict_bool
from .entity import AqaraStudioEntity, async_setup_platform_entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_setup_platform_entities(
        entry, entry.runtime_data, "switch", async_add_entities, AqaraStudioSwitch
    )


class AqaraStudioSwitch(AqaraStudioEntity, SwitchEntity):
    """Control verified Output/OnOff without optimistic state changes."""

    @property
    def is_on(self) -> bool | None:
        return strict_bool(self.trait.value) if self.trait else None

    async def _async_set(self, value: bool) -> None:
        if not self.available or not self.trait or not self.trait.writable:
            raise HomeAssistantError("The Aqara output is unavailable or read-only")
        await self.coordinator.async_write_trait(self.capability.key, value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set(False)
