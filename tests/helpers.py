"""Synthetic Studio client for lifecycle and coordinator integration tests."""

from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock

from custom_components.aqara_studio.api import AqaraStudioClient
from custom_components.aqara_studio.device import TraitKey, parse_device

from .entity_helpers import fixture_data


def make_client():
    client = MagicMock(spec=AqaraStudioClient)
    client.host = "http://studio.test"
    client.request_count = 0
    raw = fixture_data()
    client.inventory = deepcopy(raw["inventory"])
    client.definitions = deepcopy(raw["definitions"])
    client.state_values = {}
    for record, definition in zip(client.inventory, client.definitions, strict=True):
        device = parse_device(record, definition)
        for key, trait in device.traits.items():
            client.state_values[key] = {
                **key.as_dict(),
                "value": trait.value,
                "time": trait.time,
            }
    client.async_get_gateways = AsyncMock(
        return_value=[
            {
                "deviceId": "synthetic-studio",
                "name": "Synthetic Studio",
                "supportZigbee": True,
            }
        ]
    )
    client.async_get_devices = AsyncMock(side_effect=lambda: deepcopy(client.inventory))
    client.async_get_definitions = AsyncMock(
        side_effect=lambda ids: [
            deepcopy(item) for item in client.definitions if item["deviceId"] in ids
        ]
    )

    async def read(addresses):
        keys = [
            TraitKey(
                item["deviceId"],
                item["endpointId"],
                item["functionCode"],
                item["traitCode"],
            )
            for item in addresses
        ]
        return [
            deepcopy(client.state_values[key])
            for key in keys
            if key in client.state_values
        ]

    client.async_read_traits = AsyncMock(side_effect=read)
    client.async_write_trait = AsyncMock()
    return client
