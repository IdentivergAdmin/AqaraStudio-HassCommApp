"""Export useful capability metadata without household or credential data."""

import json

from custom_components.aqara_studio.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .test_coordinator import BUTTON


async def test_diagnostics_allowlist_omits_sensitive_values(
    hass, config_entry, coordinator
):
    coordinator.client.host = "http://private-host.example"
    for device in coordinator.data.values():
        device.name = "Private household room"
        device.model = "PRIVATE-MODEL-SECRET"
    coordinator.event_observations.append(
        {
            "device_id": BUTTON.device_id,
            "value": "synthetic-test-token",
            "has_ordering_timestamp": False,
        }
    )
    report = await async_get_config_entry_diagnostics(hass, config_entry)
    encoded = json.dumps(report)
    for secret in (
        "synthetic-test-token",
        "private-host.example",
        "Private household room",
        "PRIVATE-MODEL-SECRET",
        "synthetic-contact",
        "synthetic-studio",
        BUTTON.device_id,
    ):
        assert secret not in encoded
    assert "ContactSensorState" in encoded
    assert any(
        not trait["entity_mapped"]
        for device in report["devices"]
        for trait in device["traits"]
    )


async def test_unknown_numeric_button_value_remains_observable(
    hass, config_entry, coordinator
):
    await coordinator.async_handle_updates(
        [{**BUTTON.as_dict(), "value": 99, "time": 1000}]
    )
    report = await async_get_config_entry_diagnostics(hass, config_entry)
    assert report["live_button_observations"][0]["numeric_value"] == 99
    assert report["live_button_observations"][0]["device"].startswith("device_")

async def test_lighting_eligibility_is_redacted_and_actionable(
    hass, config_entry, coordinator
):
    report = await async_get_config_entry_diagnostics(hass, config_entry)
    assert isinstance(report["lighting"]["eligible_lights"], int)
    assert isinstance(report["lighting"]["enabled_lights"], int)
    assert report["lighting"]["enabled_lights"] <= report["lighting"]["eligible_lights"]
    assert isinstance(report["lighting"]["controls_opted_in"], bool)
