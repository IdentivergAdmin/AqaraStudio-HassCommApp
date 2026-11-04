"""Environmental and battery measurements with explicit units."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .device import Capability, finite_number, light_control_status
from .entity import AqaraStudioEntity, async_setup_platform_entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_setup_platform_entities(
        entry, entry.runtime_data, "sensor", async_add_entities, AqaraStudioSensor
    )


class AqaraStudioSensor(AqaraStudioEntity, SensorEntity):
    """A numeric reading; never substitute zero for invalid measurements."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, capability: Capability) -> None:
        super().__init__(coordinator, capability)
        self._attr_device_class = capability.device_class
        self._attr_native_unit_of_measurement = capability.unit
        if capability.kind == "light_readiness":
            self._attr_state_class = None

    @property
    def native_value(self) -> float | str | None:
        if self.trait is None:
            return None
        if self.capability.kind == "light_readiness":
            return light_control_status(
                self.device, self.trait, self.coordinator.options
            )
        value = finite_number(self.trait.value)
        if value is None:
            return None
        # Validate advertised raw range before unit conversion.
        minimum = finite_number(self.trait.parameter.get("min"))
        maximum = finite_number(self.trait.parameter.get("max"))
        if (minimum is not None and value < minimum) or (
            maximum is not None and value > maximum
        ):
            return None
        value *= self.capability.scale
        if (
            self.capability.minimum is not None and value < self.capability.minimum
        ) or (self.capability.maximum is not None and value > self.capability.maximum):
            return None
        return value
