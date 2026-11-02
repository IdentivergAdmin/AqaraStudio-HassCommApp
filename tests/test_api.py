"""HTTP contract tests using synthetic, non-household responses."""

import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qsl

import aiohttp
import pytest
from aiohttp import web
from yarl import URL

from custom_components.aqara_studio.api import (
    AqaraAuthError,
    AqaraConnectionError,
    AqaraRateLimitError,
    AqaraResponseError,
    AqaraStudioClient,
    group_trait_addresses,
    normalize_host,
)

HOST = "http://studio.example"
BASE = f"{HOST}/open/api/v1"
ADDRESS = {
    "deviceId": "synthetic-door-1",
    "endpointId": 1,
    "functionCode": "Contact",
    "traitCode": "ContactSensorState",
}


class HttpResponses:
    """Stub only aiohttp's public session request/context-manager interface.

    Avoids depending on ClientResponse constructor internals; a separate real
    loopback test below checks streamed HTTP handling with the installed aiohttp.
    """

    def __init__(self):
        self._routes = []
        self.requests = defaultdict(list)

    @staticmethod
    def _url(url, params=None):
        target = URL(url).update_query(params or {})
        return target.with_query(sorted(parse_qsl(target.query_string)))

    def get(self, url, **kwargs):
        self._routes.append(("GET", self._url(url), kwargs))

    def post(self, url, **kwargs):
        self._routes.append(("POST", self._url(url), kwargs))

    def __enter__(self):
        self._patch = patch.object(
            aiohttp.ClientSession, "request", side_effect=self._request
        )
        self._patch.start()
        return self

    def __exit__(self, *_):
        self._patch.stop()

    def _request(self, method, url, **kwargs):
        target = self._url(url, kwargs.get("params"))
        self.requests[(method, target)].append(SimpleNamespace(kwargs=kwargs))
        for index, (expected_method, expected_url, response) in enumerate(self._routes):
            if method != expected_method or target != expected_url:
                continue
            if not response.get("repeat"):
                self._routes.pop(index)
            if error := response.get("exception"):
                raise error
            return StubResponse(response)
        raise AssertionError(f"Unexpected synthetic HTTP request: {method} {target}")


class StubResponse:
    def __init__(self, response):
        self.status = response.get("status", 200)
        self.headers = response.get("headers", {})
        self._body = (
            json.dumps(response["payload"]).encode()
            if "payload" in response
            else response.get("body", b"")
        )
        if isinstance(self._body, str):
            self._body = self._body.encode()
        self.content = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def iter_chunked(self, size):
        for start in range(0, len(self._body), size):
            yield self._body[start : start + size]


@pytest.fixture
async def api_client() -> AsyncGenerator[AqaraStudioClient]:
    async with aiohttp.ClientSession() as session:
        yield AqaraStudioClient(session, HOST, "synthetic-token")


def envelope(data):
    return {
        "type": "SyntheticResponse",
        "version": "v1",
        "msgId": "test-1",
        "code": 0,
        "data": data,
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("studio.example", "http://studio.example"),
        ("https://STUDIO.example:8443/", "https://studio.example:8443"),
        ("http://studio.example/open/api/v1/", "http://studio.example"),
        ("[2001:db8::1]:8080", "http://[2001:db8::1]:8080"),
    ],
)
def test_normalize_host(value, expected):
    assert normalize_host(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "ftp://studio.example",
        "http://user:secret@studio.example",
        "http://studio.example?token=x",
        "http://studio.example/other",
        "http://studio.example#fragment",
        "http://studio.example:0",
        "http://studio.example:99999",
        "http://studio.example bad",
        "http://studio.example\\evil",
    ],
)
def test_reject_unsafe_host(value):
    with pytest.raises(ValueError):
        normalize_host(value)


async def test_gateway_auth_header_and_session_ownership(api_client):
    with HttpResponses() as mock:
        mock.get(
            f"{BASE}/gateways",
            payload=envelope(
                [{"deviceId": "synthetic-hub-1", "deviceName": "Test hub"}]
            ),
        )
        gateways = await api_client.async_get_gateways()
        assert gateways[0]["deviceId"] == "synthetic-hub-1"
        call = next(iter(mock.requests.values()))[0]
        assert call.kwargs["headers"]["Authorization"] == "Bearer synthetic-token"
        assert call.kwargs["allow_redirects"] is False
        assert not api_client.session.closed


async def test_paginated_inventory_and_duplicate_prevention(api_client):
    with HttpResponses() as mock:
        for page, ids in [(1, ["device-1", "device-2"]), (2, ["device-2", "device-3"])]:
            mock.get(
                f"{BASE}/devices?pageNum={page}&pageSize=100&orderBy=createTime+asc",
                payload=envelope(
                    {
                        "totalCount": 3,
                        "pageNum": page,
                        "pageSize": 2,
                        "data": [{"deviceId": item} for item in ids],
                    }
                ),
            )
        result = await api_client.async_get_devices()
        assert [item["deviceId"] for item in result] == [
            "device-1",
            "device-2",
            "device-3",
        ]
        assert len(mock.requests) == 2


async def test_inventory_includes_gateway_filter(api_client):
    with HttpResponses() as mock:
        url = f"{BASE}/devices?pageNum=1&pageSize=100&orderBy=createTime+asc&gatewayId=synthetic-hub-1"
        mock.get(
            url,
            payload=envelope(
                {"totalCount": 0, "pageNum": 1, "pageSize": 100, "data": []}
            ),
        )
        assert await api_client.async_get_devices(gateway_id="synthetic-hub-1") == []


async def test_pagination_cannot_loop_on_repeated_page(api_client):
    with HttpResponses() as mock:
        for page in (1, 2):
            mock.get(
                f"{BASE}/devices?pageNum={page}&pageSize=100&orderBy=createTime+asc",
                payload=envelope(
                    {
                        "totalCount": 2,
                        "pageNum": page,
                        "pageSize": 1,
                        "data": [{"deviceId": "same-device"}],
                    }
                ),
            )
        with pytest.raises(AqaraResponseError, match="stopped"):
            await api_client.async_get_devices()


@pytest.mark.parametrize(
    "data",
    [
        [],
        None,
        {"totalCount": 10, "pageNum": 1, "pageSize": 100, "data": []},
        {
            "totalCount": 1,
            "pageNum": 2,
            "pageSize": 100,
            "data": [{"deviceId": "wrong-page"}],
        },
    ],
)
async def test_malformed_or_incomplete_inventory(api_client, data):
    with HttpResponses() as mock:
        mock.get(
            f"{BASE}/devices?pageNum=1&pageSize=100&orderBy=createTime+asc",
            payload=envelope(data),
        )
        with pytest.raises(AqaraResponseError):
            await api_client.async_get_devices()


async def test_include_values_extension_fallback_is_cached(api_client):
    with HttpResponses() as mock:
        mock.get(
            f"{BASE}/devices/definitions?deviceIds=device-1&includeValues=true",
            status=400,
        )
        mock.get(
            f"{BASE}/devices/definitions?deviceIds=device-1",
            payload=envelope([{"deviceId": "device-1", "endpoints": []}]),
        )
        mock.get(
            f"{BASE}/devices/definitions?deviceIds=device-2",
            payload=envelope([{"deviceId": "device-2", "endpoints": []}]),
        )
        assert len(await api_client.async_get_definitions(["device-1"])) == 1
        assert len(await api_client.async_get_definitions(["device-2"])) == 1
        assert len(mock.requests) == 3


async def test_definitions_batched_and_deduplicated(api_client):
    ids = [f"device-{index:03d}" for index in range(105)]
    with HttpResponses() as mock:
        for start in (0, 50, 100):
            batch = ids[start : start + 50]
            mock.get(
                f"{BASE}/devices/definitions?deviceIds={','.join(batch)}&includeValues=true",
                payload=envelope(
                    [{"deviceId": item, "endpoints": []} for item in batch]
                ),
            )
        assert len(await api_client.async_get_definitions([*ids, ids[0]])) == 105
        assert len(mock.requests) == 3


async def test_batch_read_contract_preserves_zero_timestamp_and_missing_value(
    api_client,
):
    second = dict(ADDRESS, traitCode="SyntheticMissingValue")
    with HttpResponses() as mock:
        mock.post(
            f"{BASE}/devices/trait/read",
            payload=envelope([dict(ADDRESS, value=False, time=0), second]),
        )
        result = await api_client.async_read_traits([ADDRESS, second])
        assert result[0]["value"] is False
        assert result[0]["time"] == 0
        assert "value" not in result[1]
        call = next(iter(mock.requests.values()))[0]
        assert call.kwargs["json"] == {
            "data": [
                {
                    "deviceId": ADDRESS["deviceId"],
                    "endpointId": 1,
                    "functionCode": "Contact",
                    "traitCodes": ["ContactSensorState", "SyntheticMissingValue"],
                }
            ]
        }


def test_grouped_and_individual_queries():
    grouped = dict(ADDRESS)
    grouped.pop("traitCode")
    grouped["traitCodes"] = ["ContactSensorState", "Other"]
    assert group_trait_addresses([ADDRESS, grouped])[0]["traitCodes"] == [
        "ContactSensorState",
        "Other",
    ]


@pytest.mark.parametrize(
    "address",
    [
        dict(ADDRESS, endpointId=True),
        dict(ADDRESS, endpointId="1"),
        dict(ADDRESS, deviceId=None),
        dict(ADDRESS, traitCode=""),
    ],
)
def test_invalid_trait_addresses(address):
    with pytest.raises(AqaraResponseError):
        group_trait_addresses([address])


@pytest.mark.parametrize("status", [401, 403])
async def test_http_auth_errors(api_client, status):
    with HttpResponses() as mock:
        mock.get(f"{BASE}/gateways", status=status, body="sensitive server response")
        with pytest.raises(AqaraAuthError) as error:
            await api_client.async_get_gateways()
        assert "sensitive" not in str(error.value)
        assert "synthetic-token" not in str(error.value)


async def test_business_auth_error(api_client):
    with HttpResponses() as mock:
        mock.get(
            f"{BASE}/gateways", payload={"code": 401, "message": "synthetic-token"}
        )
        with pytest.raises(AqaraAuthError):
            await api_client.async_get_gateways()


async def test_rate_limit_propagates_retry_delay_without_immediate_retry(api_client):
    with HttpResponses() as mock:
        mock.get(f"{BASE}/gateways", status=429, headers={"Retry-After": "123"})
        with pytest.raises(AqaraRateLimitError) as error:
            await api_client.async_get_gateways()
        assert error.value.retry_after == 123
        assert api_client.request_count == 1


@pytest.mark.parametrize("header", ["inf", "+inf", "-inf", "nan", "bad-value"])
async def test_nonfinite_retry_delay_cannot_disable_recovery(api_client, header):
    with HttpResponses() as mock:
        mock.get(f"{BASE}/gateways", status=429, headers={"Retry-After": header})
        with pytest.raises(AqaraRateLimitError) as error:
            await api_client.async_get_gateways()
        assert error.value.retry_after == 60


async def test_boolean_page_number_rejected(api_client):
    with HttpResponses() as mock:
        mock.get(
            f"{BASE}/devices?pageNum=1&pageSize=100&orderBy=createTime+asc",
            payload=envelope(
                {"totalCount": 0, "pageNum": True, "pageSize": 100, "data": []}
            ),
        )
        with pytest.raises(AqaraResponseError, match="pagination"):
            await api_client.async_get_devices()


async def test_transient_read_retry(api_client):
    with (
        HttpResponses() as mock,
        patch(
            "custom_components.aqara_studio.api.asyncio.sleep", new_callable=AsyncMock
        ) as sleep,
    ):
        mock.get(f"{BASE}/gateways", status=503)
        mock.get(f"{BASE}/gateways", payload=envelope([]))
        assert await api_client.async_get_gateways() == []
        sleep.assert_awaited_once_with(0.5)


async def test_timeout_after_bounded_retries(api_client):
    with (
        HttpResponses() as mock,
        patch(
            "custom_components.aqara_studio.api.asyncio.sleep", new_callable=AsyncMock
        ),
    ):
        mock.get(f"{BASE}/gateways", exception=TimeoutError(), repeat=True)
        with pytest.raises(AqaraConnectionError):
            await api_client.async_get_gateways()
        assert api_client.request_count == 2


@pytest.mark.parametrize(
    "payload", [{}, {"code": False}, {"code": "0"}, [], {"code": 0, "data": {}}]
)
async def test_malformed_envelopes(api_client, payload):
    with HttpResponses() as mock:
        mock.get(f"{BASE}/gateways", payload=payload)
        with pytest.raises(AqaraResponseError):
            await api_client.async_get_gateways()


async def test_invalid_json_and_redirects_rejected(api_client):
    with HttpResponses() as mock:
        mock.get(f"{BASE}/gateways", body="not JSON")
        with pytest.raises(AqaraResponseError):
            await api_client.async_get_gateways()
        mock.get(
            f"{BASE}/gateways",
            status=302,
            headers={"Location": "http://another.example"},
        )
        with pytest.raises(AqaraResponseError) as error:
            await api_client.async_get_gateways()
        assert error.value.code == 302


async def test_control_write_contract_and_partial_failure(api_client):
    with HttpResponses() as mock:
        mock.post(f"{BASE}/devices/trait/execute", payload=envelope(None))
        await api_client.async_write_trait(ADDRESS, True)
        call = next(iter(mock.requests.values()))[0]
        assert call.kwargs["json"] == {"data": [dict(ADDRESS, value=True)]}
        mock.post(
            f"{BASE}/devices/trait/execute",
            payload=envelope([dict(ADDRESS, code=1103, message="device offline")]),
        )
        with pytest.raises(AqaraResponseError, match="confirm"):
            await api_client.async_write_trait(ADDRESS, False)


async def test_control_write_never_retried(api_client):
    with HttpResponses() as mock:
        mock.post(f"{BASE}/devices/trait/execute", exception=TimeoutError())
        with pytest.raises(AqaraConnectionError):
            await api_client.async_write_trait(ADDRESS, True)
        assert api_client.request_count == 1


async def test_forty_device_inventory_and_initial_definitions(api_client):
    devices = [
        {
            "deviceId": f"synthetic-{index}",
            "deviceName": f"Synthetic {index}",
            "state": True,
        }
        for index in range(40)
    ]
    with HttpResponses() as mock:
        mock.get(
            f"{BASE}/devices?pageNum=1&pageSize=100&orderBy=createTime+asc",
            payload=envelope(
                {"totalCount": 40, "pageNum": 1, "pageSize": 100, "data": devices}
            ),
        )
        ids = [device["deviceId"] for device in devices]
        mock.get(
            f"{BASE}/devices/definitions?deviceIds={','.join(ids)}&includeValues=true",
            payload=envelope([dict(device, endpoints=[]) for device in devices]),
        )
        inventory = await api_client.async_get_devices()
        definitions = await api_client.async_get_definitions(
            [item["deviceId"] for item in inventory]
        )
        assert len(inventory) == len(definitions) == 40
        assert api_client.request_count == 2


async def test_real_http_streamed_response(aiohttp_server, socket_enabled):
    """Read all chunks, not merely the first currently available TCP segment."""

    async def handler(request):
        assert request.headers["Authorization"] == "Bearer synthetic-token"
        response = web.StreamResponse(headers={"Content-Type": "application/json"})
        await response.prepare(request)
        await response.write(b'{"code":0,"data":[')
        await asyncio.sleep(0.01)
        await response.write(b'{"deviceId":"synthetic-hub-1"}]}')
        await response.write_eof()
        return response

    app = web.Application()
    app.router.add_get("/open/api/v1/gateways", handler)
    server = await aiohttp_server(app)
    async with aiohttp.ClientSession() as session:
        client = AqaraStudioClient(session, str(server.make_url("")), "synthetic-token")
        assert await client.async_get_gateways() == [{"deviceId": "synthetic-hub-1"}]
