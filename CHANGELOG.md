# Changelog

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
