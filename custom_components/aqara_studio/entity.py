"""Shared entity identity, availability, and incremental platform discovery."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .device import Capability, StudioDevice, Trait, discover_capabilities

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import AqaraStudioCoordinator


def device_identifier(studio_id: str, device_id: str) -> str:
    """Namespace a physical device to a Studio, escaping delimiters."""
    return f"{quote(studio_id, safe='')}:{quote(device_id, safe='')}"


class AqaraStudioEntity(CoordinatorEntity):
    """Base entity; coordinator owns transport and state freshness policy."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: AqaraStudioCoordinator, capability: Capability
    ) -> None:
        super().__init__(coordinator)
        self.capability = capability
        self._attr_unique_id = capability.key.unique_id(coordinator.studio_id)
        self._attr_name = capability.name
        self._attr_entity_registry_enabled_default = capability.enabled_default
        if capability.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        device = self.device
        # Multiple channels receive stable endpoint suffixes; friendly names
        # still remain user-editable in Home Assistant's entity registry.
        same_kind = Counter(
            cap.kind for cap in discover_capabilities(device, coordinator.options)
        )
        if same_kind[capability.kind] > 1:
            self._attr_name = f"{capability.name} {capability.key.endpoint_id}"

    @property
    def device(self) -> StudioDevice:
        return self.coordinator.data[self.capability.key.device_id]

    @property
    def trait(self) -> Trait | None:
        return self.coordinator.get_trait(self.capability.key)

    @property
    def available(self) -> bool:
        return self.coordinator.entity_available(self.capability.key)

    @property
    def device_info(self) -> DeviceInfo:
        device = self.device
        info = DeviceInfo(
            identifiers={
                (
                    DOMAIN,
                    device_identifier(self.coordinator.studio_id, device.device_id),
                )
            },
            name=device.name,
            manufacturer=device.manufacturer,
            model=device.model,
            sw_version=device.firmware,
            configuration_url=self.coordinator.client.host,
        )
        # Root Studio is identified with the same physical device namespace.
        gateway_id = device.gateway_id or self.coordinator.studio_id
        if gateway_id != device.device_id:
            gateway = dr.async_get(
                self.coordinator.hass
            ).async_get_device_by_identifier(
                (DOMAIN, device_identifier(self.coordinator.studio_id, gateway_id)),
                self.coordinator.config_entry.entry_id,
            )
            if gateway is not None:
                info["via_device_id"] = gateway.id
        return info

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "endpoint": self.capability.key.endpoint_id,
            "function": self.capability.key.function_code,
            "trait": self.capability.key.trait_code,
        }


def async_setup_platform_entities(
    entry: ConfigEntry,
    coordinator: AqaraStudioCoordinator,
    platform: str,
    async_add_entities: AddConfigEntryEntitiesCallback,
    factory: Callable[[AqaraStudioCoordinator, Capability], AqaraStudioEntity],
) -> None:
    """Register existing and newly discovered entities once per platform load."""
    known: set[str] = set()

    def _discover() -> None:
        entities: list[AqaraStudioEntity] = []
        for device in coordinator.data.values():
            if not device.present:
                continue
            for capability in discover_capabilities(device, coordinator.options):
                unique_id = capability.key.unique_id(coordinator.studio_id)
                if capability.platform == platform and unique_id not in known:
                    known.add(unique_id)
                    entities.append(factory(coordinator, capability))
        if entities:
            async_add_entities(entities)

    _discover()
    entry.async_on_unload(coordinator.async_add_listener(_discover))
