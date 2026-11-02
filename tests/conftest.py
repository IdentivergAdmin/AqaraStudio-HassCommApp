"""Home Assistant test fixtures; no personal data or live device access."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aqara_studio.const import DOMAIN
from custom_components.aqara_studio.coordinator import AqaraStudioCoordinator

from .helpers import make_client


@pytest.fixture(autouse=True)
def enable_integration(enable_custom_integrations):
    """Allow Home Assistant to discover this custom integration in tests."""
    yield


@pytest.fixture
def mock_client():
    return make_client()


@pytest.fixture
def config_entry():
    return MockConfigEntry(
        domain=DOMAIN,
        title="Aqara Studio",
        unique_id="synthetic-studio",
        data={
            "host": "http://studio.test",
            "token": "synthetic-test-token",
            "gateway_id": "synthetic-studio",
            "gateway_ids": ["synthetic-studio"],
        },
        options={
            "enable_websocket": False,
            "contact_polarity": "true_is_open",
            "leak_polarity": "true_is_wet",
        },
    )


@pytest.fixture
async def coordinator(hass, config_entry, mock_client):
    config_entry.add_to_hass(hass)
    coordinator = AqaraStudioCoordinator(hass, config_entry, mock_client)
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    config_entry.runtime_data = coordinator
    yield coordinator
    await coordinator.async_shutdown()
