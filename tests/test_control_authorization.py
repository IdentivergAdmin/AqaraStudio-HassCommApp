"""Exercise the real coordinator's command boundary, not a mocked actuator."""

from unittest.mock import patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.aqara_studio.api import AqaraAuthError, AqaraResponseError
from custom_components.aqara_studio.device import TraitKey

POWER = TraitKey("synthetic-light", 1, "Output", "OnOff")
LEVEL = TraitKey("synthetic-light", 1, "LevelControl", "CurrentLevel")


async def test_explicitly_disabled_light_controls_deny_writes(
    coordinator, mock_client
):
    coordinator.options["enable_light_controls"] = False
    with pytest.raises(HomeAssistantError):
        await coordinator.async_write_trait(POWER, True)
    mock_client.async_write_trait.assert_not_awaited()


async def test_writable_light_is_allowed_by_default_without_global_switch_opt_in(
    coordinator, mock_client
):
    assert coordinator.options["enable_controls"] is False
    assert coordinator.options["enable_light_controls"] is True
    assert coordinator.get_trait(POWER).value is False
    await coordinator.async_write_trait(POWER, True)
    mock_client.async_write_trait.assert_awaited_once_with(POWER.as_dict(), True)
    assert coordinator.get_trait(POWER).value is False


@pytest.mark.parametrize("value", [0, 101, float("nan"), True, "50"])
async def test_invalid_levels_never_reach_api(coordinator, mock_client, value):
    coordinator.options["enable_controls"] = True
    with pytest.raises(HomeAssistantError):
        await coordinator.async_write_trait(LEVEL, value)
    mock_client.async_write_trait.assert_not_awaited()


async def test_invalid_boolean_and_sensitive_endpoint_denied(coordinator, mock_client):
    coordinator.options["enable_controls"] = True
    with pytest.raises(HomeAssistantError):
        await coordinator.async_write_trait(POWER, "true")
    coordinator.get_trait(POWER).endpoint_type = "GarageDoor"
    with pytest.raises(HomeAssistantError):
        await coordinator.async_write_trait(POWER, True)
    mock_client.async_write_trait.assert_not_awaited()


async def test_command_error_has_no_retry_or_optimistic_state(coordinator, mock_client):
    coordinator.options["enable_controls"] = True
    mock_client.async_write_trait.side_effect = AqaraResponseError("Synthetic failure")
    with pytest.raises(HomeAssistantError, match="did not confirm"):
        await coordinator.async_write_trait(POWER, True)
    mock_client.async_write_trait.assert_awaited_once()
    assert coordinator.get_trait(POWER).value is False


async def test_command_auth_failure_invalidates_state_and_requests_reauth(
    coordinator, mock_client
):
    coordinator.options["enable_controls"] = True
    mock_client.async_write_trait.side_effect = AqaraAuthError(
        "Synthetic revoked token"
    )
    with patch.object(type(coordinator.config_entry), "async_start_reauth") as reauth:
        with pytest.raises(HomeAssistantError, match="credentials"):
            await coordinator.async_write_trait(POWER, True)
        reauth.assert_called_once()
    assert not coordinator.entity_available(POWER)
