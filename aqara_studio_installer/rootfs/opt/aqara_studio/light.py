"""Capability-gated local Aqara lights: power, brightness, XY and white temperature."""

from __future__ import annotations

import math
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_XY_COLOR,
    ColorMode,
    LightEntity,
)
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
    """Write only advertised traits on the matching light endpoint."""

    def __init__(self, coordinator, capability: Capability) -> None:
        super().__init__(coordinator, capability)
        modes = set()
        if capability.xy_color_key:
            modes.add(ColorMode.XY)
        if capability.color_temp_key:
            modes.add(ColorMode.COLOR_TEMP)
        if not modes:
            modes.add(
                ColorMode.BRIGHTNESS if capability.brightness_key else ColorMode.ONOFF
            )
        self._attr_supported_color_modes = modes
        self._attr_color_mode = next(iter(modes))

    @property
    def is_on(self) -> bool | None:
        return strict_bool(self.trait.value) if self.trait else None

    @property
    def color_mode(self) -> ColorMode:
        if len(self.supported_color_modes) == 1:
            return next(iter(self.supported_color_modes))
        if key := self.capability.color_mode_key:
            trait = self.coordinator.get_trait(key)
            if trait and type(trait.value) is int:
                if trait.value == 1 and ColorMode.XY in self.supported_color_modes:
                    return ColorMode.XY
                if (
                    trait.value == 2
                    and ColorMode.COLOR_TEMP in self.supported_color_modes
                ):
                    return ColorMode.COLOR_TEMP
        return self._attr_color_mode

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

    @property
    def min_color_temp_kelvin(self) -> int | None:
        trait = self._color_trait(self.capability.color_temp_key)
        if trait is None:
            return None
        maximum = finite_number(trait.parameter.get("max"))
        return math.ceil(1000000 / maximum) if maximum else None

    @property
    def max_color_temp_kelvin(self) -> int | None:
        trait = self._color_trait(self.capability.color_temp_key)
        if trait is None:
            return None
        minimum = finite_number(trait.parameter.get("min"))
        return math.floor(1000000 / minimum) if minimum else None

    @property
    def color_temp_kelvin(self) -> int | None:
        key = self.capability.color_temp_key
        if key is None or not self.coordinator.entity_available(key):
            return None
        trait = self._color_trait(key)
        value = finite_number(trait.value) if trait else None
        minimum = finite_number(trait.parameter.get("min")) if trait else None
        maximum = finite_number(trait.parameter.get("max")) if trait else None
        if (
            value is None
            or minimum is None
            or maximum is None
            or not minimum <= value <= maximum
            or value <= 0
        ):
            return None
        return round(1000000 / value)

    @property
    def xy_color(self) -> tuple[float, float] | None:
        key = self.capability.xy_color_key
        if key is None or not self.coordinator.entity_available(key):
            return None
        trait = self._color_trait(key)
        value = trait.value if trait else None
        if type(value) is not int or not 0 <= value <= 4294967295:
            return None
        x, y = (value >> 16) / 65535, (value & 65535) / 65535
        if x + y > 1.0001:
            return None
        return (x, y)

    def _color_trait(self, key):
        return self.coordinator.get_trait(key) if key else None

    def _check_write(self) -> None:
        if not self.available or not self.trait or not self.trait.writable:
            raise HomeAssistantError("The Aqara light is unavailable or read-only")

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._check_write()
        if ATTR_COLOR_TEMP_KELVIN in kwargs and ATTR_XY_COLOR in kwargs:
            raise HomeAssistantError("Specify either color temperature or XY color")
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
        else:
            brightness = None

        brightness_write = None
        if brightness is not None:
            key = self.capability.brightness_key
            trait = self._color_trait(key)
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
            brightness_write = (key, value)

        color_write = None
        selected_mode = None
        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            key = self.capability.color_temp_key
            trait = self._color_trait(key)
            kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
            if (
                key is None
                or trait is None
                or not trait.writable
                or type(kelvin) is not int
                or kelvin <= 0
            ):
                raise HomeAssistantError(
                    "This light does not support that color temperature"
                )
            mired = round(1000000 / kelvin)
            minimum = finite_number(trait.parameter.get("min"))
            maximum = finite_number(trait.parameter.get("max"))
            step = finite_number(trait.parameter.get("step", 1))
            if (
                minimum is None
                or maximum is None
                or step is None
                or not minimum <= mired <= maximum
            ):
                raise HomeAssistantError("Color temperature outside advertised range")
            mired = int(minimum + round((mired - minimum) / step) * step)
            mired = min(int(maximum), max(int(minimum), mired))
            color_write = (key, mired)
            selected_mode = ColorMode.COLOR_TEMP
        elif ATTR_XY_COLOR in kwargs:
            key = self.capability.xy_color_key
            trait = self._color_trait(key)
            xy = kwargs[ATTR_XY_COLOR]
            if (
                key is None
                or trait is None
                or not trait.writable
                or not isinstance(xy, (tuple, list))
                or len(xy) != 2
            ):
                raise HomeAssistantError("This light does not support that XY color")
            x, y = xy
            if (
                type(x) not in (int, float)
                or type(y) not in (int, float)
                or not math.isfinite(x)
                or not math.isfinite(y)
                or not 0 <= x <= 1
                or not 0 <= y <= 1
                or x + y > 1
            ):
                raise HomeAssistantError(
                    "XY color must be a valid CIE chromaticity pair"
                )
            packed = (round(x * 65535) << 16) | round(y * 65535)
            color_write = (key, packed)
            selected_mode = ColorMode.XY

        if color_write:
            await self.coordinator.async_write_trait(*color_write)
            self._attr_color_mode = selected_mode
        if brightness_write:
            await self.coordinator.async_write_trait(*brightness_write)
        await self.coordinator.async_write_trait(self.capability.key, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._check_write()
        await self.coordinator.async_write_trait(self.capability.key, False)
