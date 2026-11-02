# Verified protocol contract

This implementation was checked against Aqara's public documentation repository,
commit [`4ae46306d219f1f5e01d0f1b1dcc0540fd4f9a16`](https://github.com/aqara/aqara-developer-docs/tree/4ae46306d219f1f5e01d0f1b1dcc0540fd4f9a16).
The source schemas are preferable to guessing details omitted by the JavaScript
documentation renderer:

- [HTTP OpenAPI](https://github.com/aqara/aqara-developer-docs/blob/4ae46306d219f1f5e01d0f1b1dcc0540fd4f9a16/openapi/data-export-api/en/data-export-api.yaml)
- [WebSocket AsyncAPI](https://github.com/aqara/aqara-developer-docs/blob/4ae46306d219f1f5e01d0f1b1dcc0540fd4f9a16/asyncapi/data-export-api/en/asyncapi-AqaraLife-websocket.yaml)
- [Function definitions](https://github.com/aqara/aqara-developer-docs/blob/4ae46306d219f1f5e01d0f1b1dcc0540fd4f9a16/versioned_docs/version-Beta/aqara-developer/aqara-data-model-specification/function-codes.mdx)
- [Trait definitions](https://github.com/aqara/aqara-developer-docs/blob/4ae46306d219f1f5e01d0f1b1dcc0540fd4f9a16/versioned_docs/version-Beta/aqara-developer/aqara-data-model-specification/trait-codes.mdx)
- [Rendered WebSocket guidance](https://docs.aqara.com/docs/aqara-developer/data-export-api/websocket-api/)

The trait/function MDX files are vendor-authored but marked `draft: true` upstream.
Their historical rendered URLs currently return the documentation homepage. A
mapping grounded in these definitions remains **hardware unverified** until the
corresponding device has been exercised. Synthetic tests are not recordings of a
customer's M300.

## HTTP

The base path is `/open/api/v1`; authentication is the `Authorization` bearer
header. The client accepts HTTP or HTTPS and preserves TLS certificate validation.
It rejects credentials embedded in URLs, unrelated paths, queries, fragments, and
redirects. It does not log token values, response text, or request URLs.

| Operation | Verified contract | Implementation |
| --- | --- | --- |
| Gateway inventory | `GET /gateways`, `data` is a list | Deduplicates by `deviceId`; missing identity is an error |
| Device inventory | `GET /devices`, `pageNum`, `pageSize`; optional `gatewayId` | Uses all pages; `data` contains `totalCount`, `pageNum`, `pageSize`, and another `data` list |
| Model definitions | `GET /devices/definitions`, `deviceIds` list, maximum 200 | Batches of 50; nested endpoints, functions, and traits |
| Current values | `POST /devices/trait/read`, body `data` list | Groups `traitCodes` by device, endpoint, and function; returns flat value records |
| Trait control | `POST /devices/trait/execute`, body `data` list of addressed values | One caller-authorized write at a time; never automatically retried |

All successful envelopes have numeric `code: 0`. Device inventory pagination
must complete; a repeated or prematurely empty page is an error, not evidence
that previously known devices should be removed. Definition responses may omit
an unavailable child; missing returned definitions are left for the coordinator
to handle. No management, pairing, unbinding, or arbitrary command API is exposed.

`includeValues=true` is a **historically user-validated compatibility extension**,
not a parameter in the current OpenAPI. The current schema already includes
trait `value` and `time`. The client initially requests the extension; if the
server rejects it with status/code 400, it retries without it and remembers that
choice for the client lifetime. Subsequent state reads use the documented batch
read endpoint, not repeated full model downloads.

Trait execution has a significant partial-failure rule: top-level `code: 0` alone
does not prove the write succeeded. Non-empty `data` identifies failed writes.
The client rejects any such response. An absent/null or empty list of failures is
the success form used by the implementation.

HTTP 401/403 and their documented business-code equivalents are authentication
errors. Rate limiting propagates `Retry-After` to the coordinator without an
immediate retry. Transient read failures receive one delayed retry; writes do not.
Concurrency is bounded to four requests and response bodies to 8 MiB.

## Identity and timestamp limitations

The gateway endpoint documents a stable gateway `deviceId`, but no stable Studio
installation UUID. The config flow chooses the lexicographically first gateway
ID at initial setup and persists that identity; it never uses a host address or
display name. Reconfiguration retains the original anchor instead of selecting
a different gateway when inventory order or membership changes. Overlapping
gateway IDs prevent duplicate entries for the same multi-gateway inventory.

Trait `time` is an update timestamp in milliseconds. The published definition
example contains non-null values with `time: 0`. The client preserves this value;
zero by itself does not mean the sensor is unavailable. The coordinator must use
transport validation and Reachable evidence instead of a short battery-device
inactivity timer. A missing value remains missing and cannot become false/closed.

## WebSocket

The URL is `/open/ws` using `ws` for HTTP and `wss` for HTTPS. The initial mode
authenticates in the handshake header. Deployments that require a first-message
flow are retried using `AuthRequest` with `data.authType: token` and
`data.token: Bearer <token>`. No subscription or heartbeat precedes successful
first-message authentication. Invalid message authentication stops the runner so
Home Assistant can request reauthentication.

| Schema title | Actual wire `type` | Relevant payload |
| --- | --- | --- |
| AuthRequest | `AuthRequest` | `data` contains bearer token |
| SubscribeAllRequest | `SubscribeAllRequest` | `data: null` selects all accessible device data |
| SubscribeTraitValueRequest | `SubscribeTraitValueRequest` | Grouped address records with `traitCodes` |
| PingRequest | `ping` | `data: null` |
| PongResponse | `pong` | `data: pong`, correlated `msgId` |
| TraitValueUpdate | `TraitValueUpdate` | `data` is a list of addressed values |
| ObjectEvent | `objectEvent` | `data` contains `eventType`, `objectId`, `time`, and event-specific `data` |

Responses are matched by `msgId` and checked for numeric success status, including
correlated `ErrorMessage` frames. Heartbeats use a fixed 20-second schedule, below the
documented 30-second outbound-traffic limit. A missing heartbeat response causes
reconnection. Subscriptions are restored on each connection. Backoff is
exponential, with jitter; unload interrupts backoff and awaits owned tasks.

The receive task starts before authentication finishes. Pushes are buffered while
authentication, subscription, and the coordinator's reconnect snapshot run, then
dispatched. A local `replaying_buffer` flag distinguishes those buffered pushes
from messages received after reconciliation; it does not change the wire schema.
A bounded-buffer overflow forces reconnection and reconciliation.
This avoids silently dropping device-add events during startup. Timestamp ordering
and button-event deduplication belong to the coordinator, where state and event
semantics can be distinguished.

The AsyncAPI explicitly says that push `msgId` is for tracing, not a globally
unique event ID. The transport therefore does not deduplicate pushes solely by
message ID. `DEVICE_ADDED` and `DEVICE_REMOVED` arrive on authenticated sessions by
default; endpoint and trait-parameter changes accompany device subscriptions.
Space and automation subscriptions are outside this release's device-state scope.
There is no verified button-press `objectEvent` schema, so those events must not be
invented from the object event envelope.

Experimental button events require a positive vendor timestamp newer than both
the cached/delivered event and the connection's wall-clock cutoff. This prevents
initial subscription snapshots and reconnect replays from becoming false button
presses, including when ButtonEvent is subscribable but not readable. **Studio
and Home Assistant clocks must be synchronized** for this conservative policy.
Zero/missing timestamps and events older than the connection are observable in
redacted diagnostic metadata but do not fire event entities. Devices that do not
supply usable event timestamps remain unsupported for button actions. This event
rule does not invalidate normal sensor state values whose timestamp is zero.

## Validation boundary

Transport tests use synthetic HTTP responses and a loopback aiohttp WebSocket
server. They verify pagination, batching, errors, auth, buffering, keepalive,
reconnection, subscription restoration, and cancellation. They do not prove that
a particular firmware emits these messages correctly, that all battery devices
report Reachable promptly, or that a specific button delivers every press.
Use the deployment runbook and the existing working REST contact as the physical
acceptance oracle before changing any automation references.
