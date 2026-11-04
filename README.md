# Aqara Studio for Home Assistant

[![Install Aqara Studio with HACS / Marketplace](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=IdentivergAdmin&repository=AqaraStudio-HassCommApp&category=integration)
[![Configure Aqara Studio](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=aqara_studio)

**A native Home Assistant custom integration for the local Aqara Studio Developer API.**
Discovers devices through Studio, models supported sensor and light capabilities
as normal Home Assistant entities, and uses local WebSocket push with REST
reconciliation and polling fallback.

**This is a community project, not an official Aqara integration.**
The device API token stays in Home Assistant's integration config entry. No
Aqara cloud account, separate runtime container, broker, or Supervisor App
is necessary.

## Status

- **Native integration version:** `0.1.4b1` (beta).
- **Home Assistant compatibility:** tested against `2026.10.4`, requires
  `2026.10.0` or newer.
- **Known working example:** M300-connected ClosetLight supports actual on/off
  and color control, with `xy` and `color_temp` modes, plus 2703–6536 K
  temperature bounds. Other device models and sensitive automations require
  their own physical acceptance checks.
- **Distribution:** [HACS](https://www.hacs.xyz/) on HA 2026.10 and earlier,
  **Settings → Marketplace** on HA 2026.11 and newer.
- **Availability:** this is a **custom repository**. Public availability via
  this link is not the same as inclusion in the default Marketplace catalog.

## Install and updates

<!-- ha-marketplace:exclude-start -->

### HACS on Home Assistant 2026.10 or earlier

1. Open HACS in Home Assistant. Select **Custom repositories**.
2. Add `https://github.com/IdentivergAdmin/AqaraStudio-HassCommApp` with
   category **Integration**. You can also use the badge above.
3. Open **Aqara Studio** in HACS, select **Download**, and select the
   beta/pre-release version if prompted. This project's release may require
   enabling **Pre-release** in the repository's options.
4. Follow Home Assistant's restart instruction to load the new Python
   integration. Under **Settings → Devices & services**, add **Aqara Studio**
   and complete the config flow.

### Marketplace on Home Assistant 2026.11 or newer

1. Open **Settings → Marketplace**.
2. Add the same GitHub URL as a **custom integration repository** if it is
   not yet in the default catalog. Custom repositories require a GitHub
   connection.
3. Download **Aqara Studio**, select its beta version if required, then use
   **Settings → Devices & services** to configure it. A new config-flow
   integration may load without a first-install restart; follow the UI.

### Already installed using the retired Supervisor App?

**Do not remove the Aqara Studio config entry or delete
`custom_components/aqara_studio`.** The App previously copied this exact
native integration into the standard location. To make HACS/Marketplace the
update manager, follow the [legacy App migration runbook](docs/MIGRATE_LEGACY_INSTALLER.md).
Do not run the legacy one-shot App again after HACS/Marketplace takes ownership.

<!-- ha-marketplace:exclude-end -->

### How updates work

HACS/Marketplace monitors the GitHub repository's published releases and
creates a Home Assistant **update entity/notification**. When a newer compatible
release is available, select **Install/Update** in the HACS/Marketplace UI.
It downloads the integration to `custom_components/aqara_studio`. Then
**restart Home Assistant Core if requested** to load updated Python code.
That restart is normal for custom integrations, not something a Supervisor
App can eliminate.

**There is no installer App to start, separate App version, or second
runtime service.** Aqara Studio's native config entry continues running
between updates: WebSocket push, REST fallback, inventory reconciliation,
and Home Assistant entities are managed by Home Assistant Core.

For now, GitHub releases are marked **pre-release** because the full
device family has not been physically certified. Users may need to enable
pre-release versions in HACS/Marketplace. Release notes describe safety
and migration changes.

## Configuration

Open **Settings → Devices & services → Add integration → Aqara Studio**.
Enter the local Studio address (HTTP/HTTPS) and Developer API token into
Home Assistant's configuration flow—not YAML or a GitHub issue.

The integration supports multiple independent Studio installations, stable
gateway/device/endpoint identities, config-entry reconfiguration and token
reauthentication. There is no `configuration.yaml` entry required.

### Options

| Option | Default | What it controls |
| --- | --- | --- |
| REST fallback polling | 15 sec | State polling when push is unavailable |
| State reconciliation | 300 sec | Repair state while push is active |
| Inventory reconciliation | 300 sec | Discover added or changed devices |
| WebSocket push | On | Local push updates and reconnects |
| Experimental live button events | Off | Live button events, never cached presses |
| Native light controls | **On** | Only positively identified writable lights |
| Advanced switches/outlets | Off | Non-light actuation must be explicitly enabled |
| Excluded devices | None | Skip selected devices |
| Contact polarity | Unconfirmed | Explicit open/closed mapping |
| Leak polarity | Unconfirmed | Explicit wet/dry mapping |

### Device support and safety

- **Lights:** On/off, brightness and supported XY color or white color
  temperature; only capabilities the local API actually reports as readable
  and writable are exposed. M300 strips can report Kelvin metadata rather
  than mired, and slightly oversized XY metadata; values are validated before
  writes.
- **Sensors:** Contacts, leaks, battery, voltage, environmental readings
  where confirmed traits are available.
- **Buttons:** Experimental events require fresh live timestamps; cached
  values do not trigger presses.
- **No actuation of locks, covers, garage doors or valves.**

**Contact and leak polarity is not inferred from a model name.**
The Studio API does not specify which boolean means open or wet for every
device. Until you physically verify raw behavior and select the correct
polarity, the native entity must show Unknown. Keep your existing working
REST/Matter sensors until each critical device passes testing.

## Home Assistant light controls

The device page's Controls card often shows only the on/off switch. Click
the **light entity name**, not the switch, to open the full light dialog.
For example, M300 ClosetLight exposes these attributes:

```yaml
supported_color_modes:
  - xy
  - color_temp
min_color_temp_kelvin: 2703
max_color_temp_kelvin: 6536
```

The order of the modes is irrelevant; brightness control is implicit in
color-capable light modes. A light that is Off can correctly report
`color_mode: null`, `brightness: null` and `xy_color: null`.
`supported_features: 0` is normal if extra effects/flash/transition
features are not implemented.

Inspect state under **Tools → States**. **Set state** modifies the Home
Assistant representation only; it does not command the physical device.
For a physical test use **Tools → Actions** and `light.turn_on`:

```yaml
action: light.turn_on
target:
  entity_id: light.closetlight
data:
  brightness_pct: 50
```

Physically verify light changes and Studio readback before relying on
automations. Do not copy a device ID or API token into public issues.

## Troubleshooting

| Symptom | Where to start |
| --- | --- |
| HACS/Marketplace cannot find the repository | Add it as **custom Integration**, not as an App repository |
| Light only shows On/Off | Open the light name; inspect `supported_color_modes` in **Tools → States** |
| A writable capability is missing | Download **sanitized diagnostics** from Aqara Studio integration and inspect `light_features` and `light_profiles` |
| Contact reads Unknown | Physically confirm raw polarity in Studio, then set the matching integration option |
| State updates stop | Inspect `push_connected`, REST fallback and device `reachable` in sanitized diagnostics |
| Update was downloaded but code looks old | Verify manifest version in **Devices & services** and restart **Core** if required |
| HACS says the integration already exists | **Stop before deleting files or the config entry**; follow the [legacy migration guide](docs/MIGRATE_LEGACY_INSTALLER.md) |

The integration never modifies unrelated Matter/REST integrations or
Home Assistant's `.storage` files.

## Maintenance and participation

- [Architecture and local API notes](docs/PROTOCOL.md)
- [Physical device acceptance checklist](docs/ACCEPTANCE.md)
- [Migration from the old one-shot App](docs/MIGRATE_LEGACY_INSTALLER.md)
- [How releases, checks and updates work](docs/RELEASE_VERIFICATION.md)
- [Migrating existing REST/Matter automations](MIGRATION.md)
- [Contributing](CONTRIBUTING.md)
- [Security and private reporting](SECURITY.md)
- [Changelog](CHANGELOG.md)

Development requires Python 3.14, the pinned Home Assistant test harness,
Ruff, hassfest, HACS validation and sanitized fixture coverage. A
passing CI build does not certify every device on real hardware.
