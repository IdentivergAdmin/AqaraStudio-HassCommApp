# Changelog

## 0.1.2b1 — 2026-11-04

ClosetLight native-control fix based on user-supplied, redacted M300 diagnostics.

- Make writable, positively identified Light devices appear as native `light` entities by default without enabling unrelated switches/outlets.
- Recognize official device-level Light classification for unambiguous single-output endpoints; preserve denylist for lock, garage, cover, valve and root types.
- Show a read-only `Light control status` diagnostic on the device page with an actionable reason when native control is not available.
- Accept explicitly advertised boolean type aliases without inventing permissions; continue to require writable metadata and device availability.
- Keep existing Output state entities, custom entity names, contact/leak mappings, and automations intact.
- Give a single-light device its natural Home Assistant name instead of "Power".
- Add synthetic M300 light-strip discovery, readiness and option regression coverage.

**Validation boundary:** Real control writes and physical color output are not yet certified.


## 0.1.1b1 — 2026-11-03

Usability and native-light beta update.

- Three explicit My Home Assistant buttons for Apps, HACS, and initial config flow.
- Direct Studio management URL available on gateway and physical device pages.
- Light strip discovery from positive lighting-function evidence, without
  actuating unrelated writable outputs such as locks, valves, or covers.
- Capability-gated XY color and mired color-temperature write/read support.
- Lighting eligibility diagnostics distinguish writable capabilities from enabled controls.
- Retained explicit control opt-in, read-only defaults and physical acceptance gates.
- Updated Apps installer, one-shot upgrade/backup procedure and regression tests.

**Validation boundary:** Actual M300 light writes, color encoding, hardware
firmware variations and strip-segment controls have not been certified.

## 0.1.0b1 — 2026-11-02

Initial community beta of the `aqara_studio` custom integration.

- Local configuration, reauthentication and reconfiguration flows.
- Capability-based device/entity discovery with stable identity.
- Contact, leak and environmental/battery sensors using explicit mappings.
- Contact/leak polarity confirmation; invalid/missing values never default to
  closed/dry.
- REST initialization, batched reconciliation, WebSocket push/reconnect and
  polling fallback.
- Experimental live button events and opt-in supported controls.
- Availability handling, redacted diagnostics and lifecycle cleanup.
- Synthetic automated tests, Ruff, HACS and hassfest workflows.
- HACS metadata, original local community icon assets, installation and migration
  guides.

**Validation boundary:** Physical M300/device acceptance remains outstanding.
No official Aqara support, HACS default listing or HA Marketplace/core inclusion
is claimed. Cover/lock/garage actuation and arbitrary commands are unsupported.
