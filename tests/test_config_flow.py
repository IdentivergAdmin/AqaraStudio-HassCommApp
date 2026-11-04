"""Exercise Home Assistant's actual flow manager and credential lifecycle."""

from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aqara_studio.api import (
    AqaraAuthError,
    AqaraConnectionError,
    AqaraRateLimitError,
    AqaraResponseError,
)
from custom_components.aqara_studio.config_flow import async_validate_connection
from custom_components.aqara_studio.const import DEFAULT_OPTIONS, DOMAIN

VALIDATED = {
    "host": "http://studio.test",
    "token": "synthetic-test-token",
    "gateway_id": "synthetic-studio",
    "gateway_ids": ["synthetic-studio"],
}
FLOW_MODULE = "custom_components.aqara_studio.config_flow"


@pytest.fixture
def validate_connection():
    """Mock only network validation, keeping HA forms and entry handling real."""
    with patch(
        f"{FLOW_MODULE}.async_validate_connection",
        new_callable=AsyncMock,
        return_value=deepcopy(VALIDATED),
    ) as validate:
        yield validate


async def test_user_flow_defaults_unconfirmed(hass, validate_connection):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "studio.test", "token": "synthetic-test-token"}
    )
    assert result["step_id"] == "mapping"
    assert not hass.config_entries.async_entries(DOMAIN)

    with patch("custom_components.aqara_studio.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == VALIDATED
    assert result["options"] == {
        "contact_polarity": "unconfirmed",
        "leak_polarity": "unconfirmed",
    }
    assert result["result"].unique_id == "synthetic-studio"
    validate_connection.assert_awaited_once_with(
        hass, "studio.test", "synthetic-test-token"
    )


async def test_user_flow_confirmed_polarity(hass, validate_connection):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
        data={"host": "studio.test", "token": "synthetic-test-token"},
    )
    options = {"contact_polarity": "false_is_open", "leak_polarity": "true_is_wet"}
    with patch("custom_components.aqara_studio.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], options
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == options


@pytest.mark.parametrize(
    ("exception", "errors"),
    [
        (ValueError("Invalid URL"), {"host": "invalid_host"}),
        (AqaraAuthError("Rejected"), {"base": "invalid_auth"}),
        (AqaraConnectionError("Unreachable"), {"base": "cannot_connect"}),
        (AqaraResponseError("Malformed"), {"base": "unsupported_response"}),
        (AqaraRateLimitError(60), {"base": "cannot_connect"}),
    ],
)
async def test_user_errors_do_not_create_entry(
    hass, validate_connection, exception, errors
):
    validate_connection.side_effect = exception
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
        data={"host": "studio.test", "token": "synthetic-test-token"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == errors
    assert not hass.config_entries.async_entries(DOMAIN)
    # Submitted credentials must not become form defaults after an error.
    assert "synthetic-test-token" not in str(result["data_schema"].schema)


async def test_duplicate_host_alias_is_rejected(
    hass, config_entry, validate_connection
):
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
        data={"host": "alternate-studio.test", "token": "synthetic-test-token"},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_overlap_of_multi_gateway_identity_rejected(hass, validate_connection):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="original-anchor",
        data={
            **VALIDATED,
            "gateway_id": "original-anchor",
            "gateway_ids": ["original-anchor", "shared-gateway"],
        },
    )
    entry.add_to_hass(hass)
    validate_connection.return_value = {
        **VALIDATED,
        "gateway_id": "new-anchor",
        "gateway_ids": ["new-anchor", "shared-gateway"],
    }
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
        data={"host": "studio.test", "token": "synthetic-test-token"},
    )
    assert result["reason"] == "already_configured"


async def test_validate_normalizes_and_authenticates(hass, mock_client):
    mock_client.async_get_gateways.return_value = [
        {"deviceId": "z-gateway"},
        {"deviceId": "a-gateway"},
        {"deviceId": "z-gateway"},
    ]
    with patch(f"{FLOW_MODULE}.AqaraStudioClient", return_value=mock_client) as factory:
        result = await async_validate_connection(
            hass, "https://STUDIO.TEST/open/api/v1/", " synthetic-test-token "
        )
    assert result["host"] == "https://studio.test"
    assert result["token"] == "synthetic-test-token"
    assert result["gateway_id"] == "a-gateway"
    assert result["gateway_ids"] == ["a-gateway", "z-gateway"]
    assert factory.call_args.args[1:] == ("https://studio.test", "synthetic-test-token")
    mock_client.async_get_gateways.assert_awaited_once()
    mock_client.async_get_devices.assert_awaited_once()


async def test_validate_requires_stable_gateway(hass, mock_client):
    mock_client.async_get_gateways.return_value = [{"name": "Name is not identity"}]
    with patch(f"{FLOW_MODULE}.AqaraStudioClient", return_value=mock_client):
        with pytest.raises(AqaraResponseError):
            await async_validate_connection(hass, "studio.test", "synthetic-test-token")
    mock_client.async_get_devices.assert_not_awaited()


async def test_validate_rejects_empty_token_before_network(hass):
    with patch(f"{FLOW_MODULE}.AqaraStudioClient") as factory:
        with pytest.raises(AqaraAuthError):
            await async_validate_connection(hass, "studio.test", "  ")
    factory.assert_not_called()


@pytest.mark.parametrize("source", [SOURCE_REAUTH, SOURCE_RECONFIGURE])
async def test_reauthentication_and_reconfigure_keep_identity(
    hass, config_entry, validate_connection, source
):
    config_entry.add_to_hass(hass)
    original_unique_id = config_entry.unique_id
    validate_connection.return_value = {
        **VALIDATED,
        "token": "replacement-synthetic-token",
        "host": "https://moved-studio.test",
        "gateway_id": "a-new-gateway",
        "gateway_ids": ["a-new-gateway", "synthetic-studio"],
    }
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": source, "entry_id": config_entry.entry_id},
        data=dict(config_entry.data) if source == SOURCE_REAUTH else None,
    )
    user_input = {"token": "replacement-synthetic-token"}
    if source == SOURCE_RECONFIGURE:
        user_input["host"] = "https://moved-studio.test"
    with patch.object(hass.config_entries, "async_reload", return_value=True) as reload:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    expected = (
        "reauth_successful" if source == SOURCE_REAUTH else "reconfigure_successful"
    )
    assert result["reason"] == expected
    assert config_entry.unique_id == original_unique_id
    assert config_entry.data["gateway_id"] == original_unique_id
    assert config_entry.data["token"] == "replacement-synthetic-token"
    assert config_entry.data["host"] == (
        "http://studio.test" if source == SOURCE_REAUTH else "https://moved-studio.test"
    )
    reload.assert_awaited_once_with(config_entry.entry_id)


@pytest.mark.parametrize("source", [SOURCE_REAUTH, SOURCE_RECONFIGURE])
async def test_changed_gateway_rejected_on_reconfigure_or_reauth(
    hass, config_entry, validate_connection, source
):
    config_entry.add_to_hass(hass)
    original_data = dict(config_entry.data)
    validate_connection.return_value = {
        **VALIDATED,
        "gateway_id": "other-studio",
        "gateway_ids": ["other-studio"],
    }
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": source, "entry_id": config_entry.entry_id},
        data=original_data if source == SOURCE_REAUTH else None,
    )
    user_input = {"token": "replacement-synthetic-token"}
    if source == SOURCE_RECONFIGURE:
        user_input["host"] = "other-studio.test"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )
    assert result["reason"] == "wrong_instance"
    assert dict(config_entry.data) == original_data


async def test_reconfigure_blank_token_retains_existing(
    hass, config_entry, validate_connection
):
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": config_entry.entry_id},
    )
    with patch.object(hass.config_entries, "async_reload", return_value=True):
        await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "studio.test", "token": ""}
        )
        await hass.async_block_till_done()
    validate_connection.assert_awaited_once_with(
        hass, "studio.test", "synthetic-test-token"
    )


async def test_options_update_and_invalid_interval_relationship(hass, config_entry):
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    options = {**DEFAULT_OPTIONS, "poll_interval": 120, "reconcile_interval": 60}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], options
    )
    assert result["errors"] == {"base": "invalid_intervals"}
    options.update({"poll_interval": 20, "reconcile_interval": 300})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], options
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options["poll_interval"] == 20
    assert config_entry.options["enable_controls"] is False
    assert config_entry.options["enable_light_controls"] is True


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("poll_interval", 4),
        ("poll_interval", 301),
        ("reconcile_interval", 59),
        ("reconcile_interval", 3601),
        ("inventory_interval", 59),
        ("inventory_interval", 3601),
        ("contact_polarity", "invented"),
        ("leak_polarity", "invented"),
    ],
)
async def test_options_schema_rejects_invalid_values(hass, config_entry, key, value):
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {**DEFAULT_OPTIONS, key: value}
        )
