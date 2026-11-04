# Physical deployment acceptance runbook

This runbook is executed by the owner on the actual Home Assistant/Studio LAN.
The automated suite uses synthetic data and does not establish physical M300
compatibility. Do not remove a known-working REST sensor or stale migration
reference until the corresponding acceptance steps pass.

## Preparation

1. Back up HA and privately retain the existing working REST configuration.
2. Record actual HA version, integration commit/version, Studio version and hub
   firmware from the running systems. Do not assume historical versions.
3. Record a test contact's old entity ID and actual new entity ID privately.
4. Install the native integration with **HACS** (Home Assistant 2026.10
   and earlier) or **Marketplace** (2026.11+), using the verified GitHub
   pre-release when available. Do **not** use the retired Supervisor App.
   Check the installed `manifest.json` version matches the selected release.
5. Configure the integration in **Settings → Devices & services**, entering the
   local Studio host and Developer API token only for a genuinely new
   config entry. **Do not recreate an existing config entry merely because
   the distribution manager changed.** Do not share tokens with maintainers.
6. Keep experimental button events and advanced switch/outlet controls
   disabled initially. Writable, positively identified lights are enabled
   by default; do not invoke their actions before choosing a harmless
   device and confirming its writable traits.

## A. Critical contact path

| Test | Procedure | Pass condition |
| --- | --- | --- |
| Setup | Configure correct local host/token | Config flow completes; native devices and supported entities appear |
| Identity | Open the test contact's HA device page | One physical device; useful entities grouped; available model metadata shown |
| Calibration | Observe `raw_value` with contact physically closed and open; compare Studio and existing working REST entity | Both raw states are understood; select the matching contact polarity in options |
| Closed state | Close the contact | New state matches actual closure and the working oracle |
| Open state | Open the contact | New state matches actual opening; no false closed state |
| Repeatability | Perform at least five open/close cycles | No missed or inverted transitions; record observed latency |
| Push behavior | With WebSocket connected, change the contact state between polling intervals | Changes arrive promptly via live updates; record timing rather than assuming it |
| Reload | Reload only the Aqara Studio config entry | Same device/entity unique IDs; no duplicates; restored updates |
| HA restart | Restart HA after successful initial tests | Same entity IDs; no startup false closed/dry state |

**Stop migration if any comparison fails.** Keep the REST sensor operating. Export
sanitized integration diagnostics and report the exact failure without private
device/network details.

## B. Availability, fallback, and recovery

Choose a controlled test window and disable automations whose physical actions
would be unsafe during reconnects. These are manual owner tests, not automatic
operations performed by the integration.

1. **REST fallback:** Disable WebSocket in integration options. Change a contact
   and verify it updates within the configured fallback interval plus request
   time. Re-enable WebSocket and verify recovery.
2. **Hub/LAN loss:** Briefly interrupt the test connection or reboot Studio using
   its normal supported controls. Watch the entity during failure. A failed
   request must not generate closed/dry; transport loss should make entities
   unavailable once detected. Restore access and verify a fresh reconciliation.
3. **State changed during outage:** Open the contact while the transport is
   interrupted. Restore it while the contact remains open. Verify the new entity
   reports open after recovery, not the cached pre-outage closed value.
4. **Device unreachable:** Where Studio can reliably report a device offline,
   confirm `Reachable = false` makes its entities unavailable. Battery removal
   does not necessarily make Studio report offline immediately; record that
   vendor delay and do not infer a false result from a sleeping device.
5. **Sleeping sensor:** Leave a healthy battery sensor quiet through normal sleep
   and multiple reconciliation cycles. It should not become unavailable solely
   because its value has not changed.
6. **Token rejection:** If a controlled token rotation is practical, revoke the
   test token, verify HA requests reauthentication, supply the replacement
   locally, and confirm state recovery. Never include either token in a report.
7. **Reload cleanup:** Reload the entry several times. Confirm one active
   subscription/client behavior and no duplicate states or event deliveries.

Do not treat a timestamp of zero alone as proof a sensor is invalid. Compare
current API reachability, value semantics and the actual device behavior.

## C. Whole-home discovery and model validation

- Compare the Studio device inventory with HA. Unsupported capabilities may
  produce no entity; consult diagnostic capability summaries rather than assuming
  enumeration failed.
- Test each additional door/window contact in both directions, including garage
  contacts. A garage contact entity never actuates the garage.
- Add a supported sensor through Studio's normal pairing procedure. Wait for an
  inventory reconciliation cycle (five minutes by default), then verify it
  appears without YAML or an HA restart.
- Rename a device and change its Studio space. Verify its integration identity
  stays stable and existing HA entity IDs/custom names remain usable.
- Confirm that a temporarily absent device is not silently deleted from HA.
- If testing removal/re-add, record whether Studio preserves the device ID. A
  reset that changes the identifier can legitimately create a new identity;
  migrate references explicitly instead of claiming continuity.
- Verify temperature, humidity, battery, voltage and illuminance units/ranges
  against Studio or a trustworthy reading. Test each model; no model is certified
  by a similar device's successful result.
- For leak sensors, use a safe manufacturer-approved test, calibrate wet/dry,
  and verify both transition directions and recovery before relying on alerts.

Contact/leak calibration is shared by type across the entry. Check every included
device, especially those coming through different bridges or using different
models. Exclude any device whose observed polarity differs, or leave the entire
type unconfirmed. Per-device polarity overrides are not implemented.

## D. Buttons and optional controls

### Button events

1. Enable experimental button events only after the critical sensor path passes.
2. Locate the event entity and physically trigger each supported press type.
3. Confirm a **new live event** with the expected type arrives for each press.
   It must have a positive vendor timestamp strictly newer than the cached
   value/reconnect snapshot. A capability or cached last-event value is not a
   pass. Missing/zero timestamps are retained as diagnostic observations only
   and cannot trigger button automations.
4. Trigger the same press type twice. Both physical presses should be delivered,
   while a duplicate of one transport message should not produce extra events.
5. Reload HA/Studio and wait without pressing. No cached press should be emitted.
6. Repeat through the actual device connection path. A bridge can behave
   differently from a directly paired Zigbee device.

Unverified event values or freshness should remain visible only in selected
diagnostics and must not become invented single/double/long-press actions. A
bridge that never supplies fresh positive timestamps is unsupported for button
automation even when it advertises `ButtonEvent`. Timestamp zero on an ordinary
state trait is a different case and is not automatically invalid.

### Supported switch/light controls

1. Choose a harmless test light or noncritical load; confirm its actual
   advertised writable traits. Keep locks, garage actuators and other
   sensitive devices outside this beta's control scope.
2. Native light control is enabled by default for positively identified
   writable lights. **Advanced switches/outlets remain opt-in**.
3. Check the running native integration version. On **v0.1.4b1**, the
   anonymized M300 strip regression expects `supported_color_modes` to
   contain `xy` and `color_temp`, with
   `min_color_temp_kelvin: 2703` and
   `max_color_temp_kelvin: 6536`.
4. Under **Tools → States**, inspect the `light` entity attributes. The
   **Set state** control does **not** communicate with hardware. A light
   that is Off may legitimately show `brightness: null` and
   `color_mode: null`. `supported_features: 0` does not mean
   brightness/color is unsupported.
5. For **actual** hardware control, click the light name in the device's
   Controls card or use **Tools → Actions** with `light.turn_on`.
   Test and physically confirm: on/off, brightness 50%, 4000 K white,
   then a safe XY color.
6. After each action, verify the physical strip changes and that Studio
   and Home Assistant eventually report consistent values.
   An API acknowledgement or entity state transition alone is not
   sufficient to prove color control.
7. Verify unavailable/read-only targets cannot be actuated.
   Disable light controls in Options and verify writes are blocked;
   re-enable only after completing physical acceptance.

**Stop and keep the working REST/Matter state path** if the documented
modes are absent, physical color does not change, or write errors occur.
Export the sanitized diagnostics showing `light_features` and
`light_profiles`. Do not expose private tokens, raw device IDs or
your complete Studio configuration.

Cover controls, lock operations and arbitrary device commands are not supported.

## E. Automation migration

Use [MIGRATION.md](../MIGRATION.md) only after the relevant physical tests pass.
Release the old entity ID through HA's UI/provider configuration, give it to the
new entity, and repair internal `device_id` references separately. Validate each
automation with a physical transition and inspect its trace. Keep rollback
material until restart/recovery and all critical automations pass.

## Recording results

Keep a private record of timestamps, versions, model codes, test outcomes and
observed latency. A sanitized public result should include:

| Field | Record |
| --- | --- |
| Integration version/commit | Actual installed revision |
| Home Assistant version | Actual running version |
| Studio version / hub firmware | Actual displayed values |
| Device model / connection protocol | Model code, direct Zigbee or bridge path |
| Capability and calibration | Exact function/trait and observed polarity |
| Test result | Pass/fail with reproduction; distinguish unexecuted tests |
| Transport | WebSocket push or fallback; measured latency |
| Remaining limitations | Missed events, unavailable metadata, vendor delays |

Do not include API tokens, private addresses, personal names, device serials/IDs
or detailed household topology. A release remains beta until the maintainers
have reviewed the relevant actual results.
