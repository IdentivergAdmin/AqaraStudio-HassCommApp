# Changelog

## Distribution architecture — 2026-11-04 (native 0.1.4b1 unchanged)

- Adopt the conventional **HACS / Home Assistant Marketplace** custom
  integration distribution model, with one integration and no Supervisor
  App in the default branch.
- Retire the one-shot App Installer after preserving its last code in
  Git branch `legacy/supervisor-installer-v0.1.5`.
- Make HACS/Marketplace the only update manager, with versioned GitHub
  pre-releases and standard Home Assistant update entities/notifications.
- Add automatic, gated beta publication from `main` and enforce
  one-version release contract. The native runtime `aqara_studio`
  domain, config entry, API, device IDs and entities remain unchanged.
- Document in-place migration from App-installed native code without
  re-pairing, deleting integration config or touching REST/Matter entities.
- Prepare for the built-in Home Assistant Marketplace in 2026.11;
  custom repository remains public-link installable pending default
  catalog submission.

**No change to device operation or color encoding in this distribution
refactor.**


## 0.1.4b1 — 2026-11-04

**M300 real-diagnostic color compatibility fix.** Addresses writable
ColorXY and ColorTemperature points previously rejected despite
brightness and on/off working.

- Permit the observed M300 ColorXY metadata maximum **4294967303**
  (uint32 maximum + 8) while continuing to constrain every outgoing
  XY value to the actual uint32 range **0–4294967295**.
- Recognize separately validated **Kelvin (2703–6536 K)** and
  **mired (typically 153–500)** ColorTemperature representations.
  Convert requests and readback using the correct raw representation.
- Add fail-closed checks for contradictory units, invalid metadata,
  unsupported endpoints and out-of-range writes.
- Add a public **anonymized M300 capability fixture** matching the
  actual diagnostics, plus physical boundary and coordinator
  authorization regression coverage.
- Correct **Tools → States / Tools → Actions** guidance and explain
  App vs native version numbers and expected upgrade logs.
- Bundle with **Installer App 0.1.5**, retaining automatic backup and
  no-toggle idempotent upgrades. See
  [Release Verification](docs/RELEASE_VERIFICATION.md).

**CI is not physical certification**: actual LED-strip color writes must
still be verified on hardware before declaring acceptance.


## 0.1.3b1 — 2026-11-04

- Recognize Aqara-spec **optional min/max/step metadata** for writable
  CurrentLevel, ColorXY and ColorTemperature, using documented defaults
  only when the API omits those fields.
- Preserve fail-closed behavior for explicit invalid bounds and nonwritable traits.
- Publish sanitized, per-light support flags and numeric parameter metadata in
  integration diagnostics, allowing on/off-only UI issues to be diagnosed
  without exposing credentials or live device values.
- Verify brightness slider and two color modes against synthetic HA light entities.
- No change to on/off access, button events, contact/leak polarity, or entity IDs.

**Acceptance:** Color and brightness writes remain unverified on actual M300 hardware.


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
