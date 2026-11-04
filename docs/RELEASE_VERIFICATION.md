# Release verification: installer, native integration and real M300 light

This is a **blocking release checklist**. Do not publish, recommend a restart,
or declare physical light control fixed unless the relevant gates have passed.

## Exact release pair

| Artifact | Version | Location |
| --- | --- | --- |
| Home Assistant Installer App | **0.1.5** | `aqara_studio_installer/config.yaml` |
| Bundled native Aqara Studio | **0.1.4b1** | `aqara_studio_installer/rootfs/opt/aqara_studio/manifest.json` |
| Source native Aqara Studio | **0.1.4b1** | `custom_components/aqara_studio/manifest.json` |
| Build release contract | Both versions | `release_contract.json` |

These are **intentionally different version numbers**. Updating the App does
not install or reload the native integration by itself. The owner must press
**Start** and check **Logs**. For a running v0.1.3b1 native installation,
the expected log is:

```text
[Aqara Studio] UPGRADE 0.1.3b1 -> 0.1.4b1 (automatic backup).
[Aqara Studio] BACKUP: /homeassistant/aqara_studio_installer_backups/...
[Aqara Studio] SUCCESS — native integration 0.1.4b1 installed. Restart Home Assistant Core to load the new code.
```

Only after that log should the owner restart **Home Assistant Core once**.
Then confirm native **0.1.4b1** at **Settings → Devices & services →
Aqara Studio** or in the integration's sanitized diagnostics
(`integration_manifest.version`).

## Root cause, from actual sanitized diagnostics

On **2026-11-04** Home Assistant **2026.10.4** reported one writable light
on endpoint 2. `CurrentLevel` was already accepted as brightness.
Two additional writable traits were previously rejected:

- **ColorXY**, type `Integer`: min 0, max **4294967303**, step 1,
  versus the Aqara uint32 specification max **4294967295**.
  This is an eight-unit metadata overshoot, **not** permission to send
  larger values. Actual writes must remain `0..0xffffffff`.
- **ColorTemperature**, type `Integer`: min **2703**, max **6536**,
  step 1. The diagnostic sanitized the unit; Aqara Studio presented
  Kelvin, and these exact values correspond to 370 and 153 mired.
  Native 0.1.3b1 wrongly required 153–500 mired metadata. The new
  parser explicitly distinguishes valid Kelvin and mired profiles,
  with an evidence-specific fallback for the exact M300 descriptor.

The real diagnostic file **must not be committed**. Only
`tests/fixtures/m300_lightstrip_redacted.json` may be committed; it
contains numeric trait metadata but no raw device IDs, tokens, names,
network addresses or physical sensor readings. Its sanitized unit
placeholder is **not claimed to be the raw API unit**.

## Required quality gates

Before a PR can merge:

1. `pytest` covers the real redacted metadata fixture, `ColorMode.XY`,
   `ColorMode.COLOR_TEMP`, brightness, Kelvin readback, raw Kelvin
   writes, mired regression and coordinator authorization.
2. Outgoing XY is always uint32, even when advertised max is
   `0x100000007`. Larger descriptors and out-of-range values are denied.
3. Invalid/contradictory temperature units and ranges fail closed.
4. `ruff check`, `ruff format --check`, hassfest and HACS pass.
5. App installer tests and real Alpine container smoke run pass; the
   packaged native integration matches source **byte for byte**.
6. The release-contract test verifies exact App/native pair across
   manifests, Docker build metadata, documentation and
   `release_contract.json`.
7. PR merges into `main`; re-read `main` to verify release versions
   and source/package parity. Feature-branch success is not deployment.

**These are simulated software gates. They do not contact the owner's LAN,
M300, physical LED strip or Aqara Studio API.**

## User-side physical acceptance after one restart

1. Navigate to **Tools → States** and select `light.closetlight`.
   Check `supported_color_modes` includes `xy` and `color_temp`.
   For this specific light, expect minimum **2703 K** and maximum
   **6536 K**; the two modes can appear in either order.
2. `supported_features: 0` is normal: this field covers extra effects,
   transition and flash support, **not** color and brightness.
   `color_mode: null` and `brightness: null` while Off are normal.
3. **Do not click "Set state" to test hardware.** That UI changes HA's
   local state representation, not the physical light.
4. Click the ClosetLight entity **name** on its device page for the
   controls. If necessary, use **Tools → Actions**, targeting
   `light.closetlight`, with `light.turn_on` and
   `brightness_pct: 50`; then `color_temp_kelvin: 4000`; then a
   color through the UI. Confirm physical changes and subsequent
   Studio/HA readback for each operation.
5. If the UI still shows brightness only, download **sanitized
   diagnostics** and inspect `devices[].light_features`,
   `light_profiles`, and `light_trait_metadata`.
6. Do not retire working REST/Matter automations until physical
   acceptance succeeds.

For broader regression and recovery, see [ACCEPTANCE.md](ACCEPTANCE.md).
