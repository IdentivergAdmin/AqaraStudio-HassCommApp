"""Explicitly enabled on/off and verified percentage brightness control."""

from __future__ import annotations

import math
from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .device import Capability, finite_number, strict_bool
from .entity import AqaraStudioEntity, async_setup_platform_entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_setup_platform_entities(
        entry, entry.runtime_data, "light", async_add_entities, AqaraStudioLight
    )


class AqaraStudioLight(AqaraStudioEntity, LightEntity):
    """Use Output/OnOff and an advertised percentage CurrentLevel."""

    def __init__(self, coordinator, capability: Capability) -> None:
        super().__init__(coordinator, capability)
        mode = ColorMode.BRIGHTNESS if capability.brightness_key else ColorMode.ONOFF
        self._attr_supported_color_modes = {mode}
        self._attr_color_mode = mode

    @property
    def is_on(self) -> bool | None:
        return strict_bool(self.trait.value) if self.trait else None

    @property
    def brightness(self) -> int | None:
        if self.capability.brightness_key is None:
            return None
        if not self.coordinator.entity_available(self.capability.brightness_key):
            return None
        trait = self.coordinator.get_trait(self.capability.brightness_key)
        value = finite_number(trait.value) if trait else None
        if value is None or not 0 <= value <= 100:
            return None
        return round(value * 255 / 100)

    def _check_write(self) -> None:
        if not self.available or not self.trait or not self.trait.writable:
            raise HomeAssistantError("The Aqara light is unavailable or read-only")

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._check_write()
        if ATTR_BRIGHTNESS in kwargs:
            brightness = kwargs[ATTR_BRIGHTNESS]
            if (
                isinstance(brightness, bool)
                or not isinstance(brightness, int)
                or not 0 <= brightness <= 255
            ):
                raise HomeAssistantError("Brightness must be an integer from 0 to 255")
            if brightness == 0:
                await self.async_turn_off()
                return
            key = self.capability.brightness_key
            trait = self.coordinator.get_trait(key) if key else None
            if key is None or trait is None or not trait.writable:
                raise HomeAssistantError(
                    "This light does not advertise writable percentage brightness"
                )
            advertised_minimum = finite_number(trait.parameter.get("min")) or 0
            minimum = max(1, advertised_minimum)
            maximum = 100
            value = max(minimum, brightness * 100 / 255)
            step = finite_number(trait.parameter.get("step"))
            if step and step > 0:
                minimum = (
                    advertised_minimum
                    + math.ceil((minimum - advertised_minimum) / step) * step
                )
                maximum = (
                    advertised_minimum
                    + math.floor((100 - advertised_minimum) / step) * step
                )
                value = (
                    advertised_minimum
                    + round((value - advertised_minimum) / step) * step
                )
            value = min(maximum, max(minimum, value))
            if trait.parameter.get("type") == "Integer":
                value = int(round(value))
            await self.coordinator.async_write_trait(key, value)
        await self.coordinator.async_write_trait(self.capability.key, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._check_write()
        await self.coordinator.async_write_trait(self.capability.key, False)
