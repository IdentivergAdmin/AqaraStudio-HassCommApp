"""Contact, leak, and read-only output states."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .device import Capability, strict_bool
from .entity import AqaraStudioEntity, async_setup_platform_entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_setup_platform_entities(
        entry,
        entry.runtime_data,
        "binary_sensor",
        async_add_entities,
        AqaraStudioBinarySensor,
    )


class AqaraStudioBinarySensor(AqaraStudioEntity, BinarySensorEntity):
    """A boolean trait; missing/corrupt/unconfirmed data stays unknown."""

    def __init__(self, coordinator, capability: Capability) -> None:
        super().__init__(coordinator, capability)
        self._attr_device_class = capability.device_class

    @property
    def is_on(self) -> bool | None:
        if self.trait is None:
            return None
        value = strict_bool(self.trait.value)
        if value is None:
            return None
        if self.capability.kind == "contact":
            polarity = self.coordinator.options.get("contact_polarity", "unconfirmed")
            if polarity == "true_is_open":
                return value
            if polarity == "false_is_open":
                return not value
            return None
        if self.capability.kind == "leak":
            polarity = self.coordinator.options.get("leak_polarity", "unconfirmed")
            if polarity == "true_is_wet":
                return value
            if polarity == "false_is_wet":
                return not value
            return None
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attributes = super().extra_state_attributes
        if self.capability.kind in {"contact", "leak"}:
            kind = self.capability.kind
            polarity = self.coordinator.options.get(f"{kind}_polarity", "unconfirmed")
            attributes.update(
                {
                    "raw_value": strict_bool(self.trait.value) if self.trait else None,
                    "polarity": polarity,
                    "polarity_confirmation_required": polarity
                    not in (
                        {"true_is_open", "false_is_open"}
                        if kind == "contact"
                        else {"true_is_wet", "false_is_wet"}
                    ),
                }
            )
        return attributes
