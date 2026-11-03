"""Async client for the documented Aqara Studio local Open API.

Only HTTP transport and protocol normalization live here. Callers own capability
authorization, availability, caching, and the lifecycle of the aiohttp session.
"""

from __future__ import annotations

import asyncio
import json
import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import aiohttp

API_PATH = "/open/api/v1"
PAGE_SIZE = 100
DEFINITION_BATCH_SIZE = 50
TRAIT_BATCH_SIZE = 100
MAX_PAGES = 1000
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class AqaraError(Exception):
    """Base error with a deliberately non-sensitive message."""


class AqaraAuthError(AqaraError):
    """The token is invalid, expired, or lacks the required access scope."""


class AqaraConnectionError(AqaraError):
    """Studio could not be reached or returned a transient server error."""


class AqaraResponseError(AqaraError):
    """The server returned an unsupported or malformed response."""

    def __init__(self, message: str, *, code: int | None = None) -> None:
        """Retain a numeric status without retaining server response text."""
        super().__init__(message)
        self.code = code


class AqaraRateLimitError(AqaraError):
    """The caller must defer further requests until the retry delay elapses."""

    def __init__(self, retry_after: float = 60) -> None:
        """Provide a delay for the coordinator without exposing a response."""
        super().__init__("Studio API rate limit reached")
        self.retry_after = max(1.0, retry_after)


def normalize_host(value: str) -> str:
    """Return an HTTP(S) origin; reject credentials and unrelated URL paths."""
    if not isinstance(value, str) or not (value := value.strip()):
        raise ValueError("Enter a hostname, IP address, or HTTP(S) URL")
    if any(character.isspace() or ord(character) < 32 for character in value):
        raise ValueError("The Studio address contains whitespace")
    if "://" not in value:
        value = f"http://{value}"
    try:
        parsed = urlsplit(value)
        port = parsed.port
        hostname = parsed.hostname
    except ValueError:
        raise ValueError("Invalid Studio address") from None
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") not in {"", API_PATH}
        or any(character in hostname for character in "\\/?#@%")
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise ValueError("Use an HTTP(S) Studio origin without credentials or query")
    hostname = hostname.lower().encode("idna").decode("ascii")
    if ":" in hostname:
        hostname = f"[{hostname}]"
    netloc = f"{hostname}:{port}" if port is not None else hostname
    return urlunsplit((parsed.scheme.lower(), netloc, "", "", ""))


def _list_of_dicts(value: Any, context: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise AqaraResponseError(f"Malformed {context} response")
    return value


def _integer(value: Any, *, minimum: int = 0) -> bool:
    return type(value) is int and value >= minimum


def validate_address(address: Mapping[str, Any]) -> dict[str, Any]:
    """Copy the four documented address fields, rejecting ambiguous addresses."""
    if not isinstance(address, Mapping):
        raise AqaraResponseError("Invalid trait address")
    result = {
        key: address.get(key)
        for key in ("deviceId", "endpointId", "functionCode", "traitCode")
    }
    if not all(
        isinstance(result[key], str) and result[key]
        for key in ("deviceId", "functionCode", "traitCode")
    ) or not _integer(result["endpointId"]):
        raise AqaraResponseError("Invalid trait address")
    return result


def group_trait_addresses(
    addresses: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Group individual addresses into documented function/traitCodes requests."""
    grouped: dict[tuple[str, int, str], list[str]] = defaultdict(list)
    for item in addresses:
        codes = item.get("traitCodes") if isinstance(item, Mapping) else None
        if codes is not None:
            if not isinstance(codes, list) or not codes:
                raise AqaraResponseError("Invalid trait query")
            expanded = [dict(item, traitCode=code) for code in codes]
        else:
            expanded = [item]
        for raw in expanded:
            address = validate_address(raw)
            key = (address["deviceId"], address["endpointId"], address["functionCode"])
            if address["traitCode"] not in grouped[key]:
                grouped[key].append(address["traitCode"])
    return [
        {
            "deviceId": key[0],
            "endpointId": key[1],
            "functionCode": key[2],
            "traitCodes": codes,
        }
        for key, codes in grouped.items()
    ]


def _retry_after(header: str | None) -> float:
    """Honor Retry-After seconds or an HTTP date without trusting error text."""
    if header:
        try:
            seconds = float(header)
            return max(1.0, seconds) if math.isfinite(seconds) else 60.0
        except ValueError:
            try:
                date = parsedate_to_datetime(header)
                return max(1.0, (date - datetime.now(UTC)).total_seconds())
            except TypeError, ValueError, OverflowError:
                pass
    return 60.0


class AqaraStudioClient:
    """Use an externally managed aiohttp session; never close that session."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        token: str,
        *,
        request_timeout: float = 15,
    ) -> None:
        self.session = session
        self.host = normalize_host(host)
        self._token = token.strip()
        if self._token.lower().startswith("bearer "):
            self._token = self._token[7:].strip()
        if not self._token or "\n" in self._token or "\r" in self._token:
            raise ValueError("Enter a valid API token")
        self._timeout = aiohttp.ClientTimeout(total=request_timeout)
        self._semaphore = asyncio.Semaphore(4)
        self._include_values = True
        self.request_count = 0

    @property
    def authorization(self) -> str:
        """Credential for HTTP headers and the documented WS auth message."""
        return f"Bearer {self._token}"

    @property
    def websocket_url(self) -> str:
        """Translate the configured origin without changing TLS verification."""
        parsed = urlsplit(self.host)
        return urlunsplit(
            (
                "wss" if parsed.scheme == "https" else "ws",
                parsed.netloc,
                "/open/ws",
                "",
                "",
            )
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        retryable: bool = True,
    ) -> Any:
        """Validate envelopes and retry only idempotent transient read failures."""
        attempts = 2 if retryable else 1
        for attempt in range(attempts):
            try:
                async with self._semaphore:
                    self.request_count += 1
                    async with self.session.request(
                        method,
                        f"{self.host}{API_PATH}{path}",
                        params=params,
                        json=body,
                        headers={"Authorization": self.authorization},
                        timeout=self._timeout,
                        allow_redirects=False,
                    ) as response:
                        if response.status in (401, 403):
                            raise AqaraAuthError(
                                "Studio rejected the API token or scope"
                            )
                        if response.status == 429:
                            raise AqaraRateLimitError(
                                _retry_after(response.headers.get("Retry-After"))
                            )
                        if response.status >= 500:
                            raise AqaraConnectionError("Studio returned a server error")
                        if response.status != 200:
                            raise AqaraResponseError(
                                "Studio rejected the API request", code=response.status
                            )
                        chunks: list[bytes] = []
                        length = 0
                        async for chunk in response.content.iter_chunked(64 * 1024):
                            length += len(chunk)
                            if length > MAX_RESPONSE_BYTES:
                                raise AqaraResponseError(
                                    "Studio response exceeded the size limit"
                                )
                            chunks.append(chunk)
                        raw = b"".join(chunks)
                        try:
                            payload = json.loads(raw)
                        except ValueError, UnicodeDecodeError:
                            raise AqaraResponseError(
                                "Studio returned invalid JSON"
                            ) from None
                        if (
                            not isinstance(payload, dict)
                            or type(payload.get("code")) is not int
                        ):
                            raise AqaraResponseError(
                                "Studio returned an invalid response envelope"
                            )
                        code = payload["code"]
                        if code in (401, 403):
                            raise AqaraAuthError(
                                "Studio rejected the API token or scope"
                            )
                        if code == 429:
                            raise AqaraRateLimitError()
                        if code != 0:
                            raise AqaraResponseError(
                                "Studio reported an API error", code=code
                            )
                        return payload.get("data")
            except aiohttp.ClientError, TimeoutError:
                error = AqaraConnectionError("Cannot communicate with Studio")
            except AqaraConnectionError as err:
                error = err
            if attempt == attempts - 1:
                raise error from None
            await asyncio.sleep(0.5 * (2**attempt))
        raise AqaraConnectionError("Cannot communicate with Studio")  # pragma: no cover

    async def async_get_gateways(self) -> list[dict[str, Any]]:
        """Return gateway records with stable vendor device identifiers."""
        records = _list_of_dicts(await self._request("GET", "/gateways"), "gateway")
        if any(
            not isinstance(item.get("deviceId"), str) or not item["deviceId"]
            for item in records
        ):
            raise AqaraResponseError("Gateway identity is missing")
        return list({item["deviceId"]: item for item in records}.values())

    async def async_get_devices(
        self, *, gateway_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Read every inventory page and fail safely if pagination makes no progress."""
        devices: dict[str, dict[str, Any]] = {}
        for page in range(1, MAX_PAGES + 1):
            params: dict[str, Any] = {
                "pageNum": page,
                "pageSize": PAGE_SIZE,
                "orderBy": "createTime asc",
            }
            if gateway_id:
                params["gatewayId"] = gateway_id
            data = await self._request("GET", "/devices", params=params)
            if not isinstance(data, dict):
                raise AqaraResponseError("Device inventory is not paginated")
            # Documented nested container is response.data.data, not response.data.
            items = _list_of_dicts(data.get("data"), "device inventory")
            total, size, number = (
                data.get("totalCount"),
                data.get("pageSize"),
                data.get("pageNum"),
            )
            if (
                not _integer(total)
                or not _integer(size, minimum=1)
                or not _integer(number, minimum=1)
                or number != page
            ):
                raise AqaraResponseError("Invalid device pagination metadata")
            previous = len(devices)
            for item in items:
                identity = item.get("deviceId")
                if not isinstance(identity, str) or not identity:
                    raise AqaraResponseError("Device identity is missing")
                devices[identity] = item
            if len(devices) >= total:
                return list(devices.values())
            if not items or len(devices) == previous:
                raise AqaraResponseError("Device pagination stopped before completion")
        raise AqaraResponseError("Device pagination exceeded the safety limit")

    async def async_get_definitions(
        self, device_ids: Iterable[str]
    ) -> list[dict[str, Any]]:
        """Read cached model inputs in small URL-safe batches (vendor max: 200)."""
        identities = list(dict.fromkeys(device_ids))
        if any(
            not isinstance(item, str) or not item or "," in item for item in identities
        ):
            raise AqaraResponseError("Invalid device identity")
        definitions: dict[str, dict[str, Any]] = {}
        for start in range(0, len(identities), DEFINITION_BATCH_SIZE):
            batch = identities[start : start + DEFINITION_BATCH_SIZE]
            params = {"deviceIds": ",".join(batch)}
            if self._include_values:
                params["includeValues"] = "true"
            try:
                data = await self._request("GET", "/devices/definitions", params=params)
            except AqaraResponseError as err:
                if not self._include_values or err.code != 400:
                    raise
                # User-validated older extension; current OpenAPI omits it.
                self._include_values = False
                params.pop("includeValues", None)
                data = await self._request("GET", "/devices/definitions", params=params)
            records = _list_of_dicts(data, "device definitions")
            for item in records:
                identity = item.get("deviceId")
                if identity not in batch:
                    raise AqaraResponseError("Unexpected device in definition response")
                definitions[identity] = item
        return list(definitions.values())

    async def async_read_traits(
        self, addresses: Iterable[Mapping[str, Any]]
    ) -> list[dict[str, Any]]:
        """Batch current values without reloading complete device definitions."""
        queries = group_trait_addresses(addresses)
        results: list[dict[str, Any]] = []
        for start in range(0, len(queries), TRAIT_BATCH_SIZE):
            data = await self._request(
                "POST",
                "/devices/trait/read",
                body={"data": queries[start : start + TRAIT_BATCH_SIZE]},
            )
            records = _list_of_dicts(data, "trait values")
            for item in records:
                address = validate_address(item)
                # A missing value stays missing: the coordinator makes it unknown.
                result = dict(address)
                if "value" in item:
                    result["value"] = item["value"]
                if "time" in item:
                    result["time"] = item["time"]
                results.append(result)
        return results

    async def async_write_trait(self, address: Mapping[str, Any], value: Any) -> None:
        """Execute one caller-authorized trait write, without automatic retry."""
        item = validate_address(address)
        item["value"] = value
        data = await self._request(
            "POST", "/devices/trait/execute", body={"data": [item]}, retryable=False
        )
        # Per the contract, data contains failures; top-level code=0 can be partial.
        if data not in (None, []):
            _list_of_dicts(data, "trait execution")
            raise AqaraResponseError("Studio did not confirm the trait write")
