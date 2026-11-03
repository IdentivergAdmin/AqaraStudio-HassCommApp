# Aqara Studio for Home Assistant

[![Add Aqara Studio App repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FIdentivergAdmin%2FAqaraStudio-HassCommApp)
[![Open Aqara Studio integration in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=IdentivergAdmin&repository=AqaraStudio-HassCommApp&category=integration)
[![Configure Aqara Studio integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=aqara_studio)

**Three different actions:** the first adds the **Apps installer repository**; the second opens the **HACS custom integration repository**; the third starts the **native integration's configuration wizard** *after it has been installed and Home Assistant Core restarted*.

An independent community integration that connects Home Assistant directly to the
**Aqara Studio local Open API**. It discovers devices and their advertised
capabilities, creates native Home Assistant devices/entities, and receives local
state updates without a separate REST YAML sensor for every device.

**This is not an official Aqara product.** It has no Aqara cloud dependency,
telemetry, external callbacks, or Docker runtime requirement. It does not require
the M300 to advertise an outward Matter Bridge role.

## Beta status

Version **0.1.1b1** is a beta update. Automated tests use synthetic fixtures
derived from the current vendor contract. A successful test suite is not a live
hub compatibility certification. Physical device acceptance is still required;
see [the acceptance runbook](docs/ACCEPTANCE.md).

**Keep your existing working REST/Matter entities and automations in place while
you validate the new entities.** This integration never removes another
integration's entities and never edits Home Assistant's `.storage` files.

### Contact/leak polarity requires confirmation

Aqara's current public data model declares `ContactSensorState` and `LeakState` as
booleans but does not explicitly define which value means open or wet. The beta
therefore starts these entities as **Unknown** until you confirm their polarity.
An exposed `raw_value` attribute supports comparison with Studio and a physical
state change. Missing or unrecognized values never mean closed or dry.

1. Add the integration and leave the working REST entity enabled. Leave the
   polarity settings **Unconfirmed** during setup unless you have already
   verified the actual raw values.
2. Inspect the new contact entity's `raw_value` under **Developer tools → States**.
3. Close and open a test contact, checking both Studio and the working entity.
4. In the Aqara Studio integration options, set **Contact polarity** to the
   mapping you actually observed: true means open, or false means open.
5. Repeat with a safe manufacturer-approved dry/wet test before selecting
   **Leak polarity**. Leave leak polarity unconfirmed until that test is complete.

Each mapping applies to **all included sensors of that type in the Studio
entry**. Validate every device, especially mixed models or bridge sources, before
relying on it. If devices use incompatible encodings, exclude mismatched devices
or leave that entire type unconfirmed and report sanitized evidence. This beta
does not provide per-device polarity overrides.

## Requirements

- Home Assistant **2026.10.0 or newer**. The reproducible automated test target is
  Home Assistant **2026.10.4** with Python **3.14.2 or newer**.
- Aqara Studio with the local Developer API enabled and a Developer API token.
- Network access **from Home Assistant** to the Studio HTTP(S) and WebSocket
  endpoint. The integration uses `/open/api/v1` and `/open/ws`.
- Supported capabilities advertised by the actual Studio device definitions.
  A marketing model name alone is not sufficient to create an entity.

The token is entered locally in the Home Assistant UI and stored in its config
entry. Do not put it in this repository, YAML examples, issues, screenshots or
captures. HTTP sends bearer tokens without encryption; use HTTPS with a trusted
certificate where supported and restrict network access. TLS verification stays
enabled for HTTPS. See [SECURITY.md](SECURITY.md).

## Installation

### Home Assistant OS: one-click Apps installer

Use the **Add app repository** badge at the top or add
`https://github.com/IdentivergAdmin/AqaraStudio-HassCommApp` at **Settings → Apps → Repositories**.
Install **Aqara Studio Integration Installer (Beta)** from **Apps**, then press
**Start** once. When the log says the native integration was installed, restart
**Home Assistant Core** and use the **Configure integration** badge above.
The one-shot installer stopping is normal. **Do not put your API token in the
installer**; only enter it in the native Aqara Studio config flow.

**Upgrading from an earlier installer:** back up Home Assistant, update the
Aqara Studio installer App from Apps, open its Configuration tab, explicitly set
`replace_existing: true`, press Start once, verify the success log and restart
Home Assistant Core. An old integration folder is backed up under
`aqara_studio_installer_backups/` before replacement. Leaving
`replace_existing: false` safely leaves an existing integration untouched.

### HACS custom integration

Use the **Open in HACS** badge above, or enter `https://github.com/IdentivergAdmin/AqaraStudio-HassCommApp` in
**HACS → Custom repositories** as type **Integration**. Download Aqara Studio,
restart Home Assistant Core, and use the **Configure integration** badge.
You only need one installation method. Custom HACS repositories are separate
from inclusion in the HACS catalog / Home Assistant Marketplace.

### Manual installation

Copy `custom_components/aqara_studio/` from this repository's current
`main` branch into your HA config directory so that
`/config/custom_components/aqara_studio/manifest.json` exists. Restart Home
Assistant Core. For upgrades, back up the previous folder first.
Keep your existing REST/Matter integrations active until physical acceptance
has passed.

## Configuration

1. Open **Settings → Devices & services → Add integration**.
2. Search for **Aqara Studio**.
3. Enter the Studio hostname, IP address, or HTTP(S) URL, for example
   `studio.example.local` or `https://studio.example.local`.
4. Paste the Developer API token into the token field.
5. Complete the polarity confirmation step, leaving it unconfirmed if you have
   not validated the physical device's raw values.
6. Open the integration's devices and inspect its entities.
7. Complete contact/leak calibration as described above.

No `configuration.yaml` entry is required. Stable gateway IDs from Studio
identify the config entry; names and addresses are not identity. Duplicate
gateway identities are rejected. Multiple independent Studio installations can
be configured. Reconfiguration changes connection details while preserving
identity. Reauthentication handles credentials rejected by Studio.

### Options

| Option | Default | Effect |
| --- | --- | --- |
| REST fallback polling interval | 15 seconds | Current-state polling when push is disabled/disconnected; 5–300 seconds |
| State reconciliation interval | 300 seconds | REST repair of state while push operates; 60–3,600 seconds |
| Inventory reconciliation interval | 300 seconds | Discover new/changed devices; 60–3,600 seconds |
| Enable WebSocket | On | Use local push and restore subscriptions after reconnect |
| Experimental button events | Off | Enable live button event entities and decoding |
| Enable supported controls | Off | Permit verified writable light/switch controls |
| Excluded devices | None | Skip selected devices without deleting other integrations |
| Contact polarity | Unconfirmed | Explicit true/open or false/open mapping |
| Leak polarity | Unconfirmed | Explicit true/wet or false/wet mapping |

Keep the defaults during initial read-only acceptance. Enabling controls cannot
override missing writable access flags or add unsupported vendor operations.

## Native lights, color control, and Studio management

A device advertising a writable `Output/OnOff` trait can become a **native
`light` entity** when its endpoint is classified as a light or advertises
same-endpoint Lighting/ColorControl functions. A writable `Switch`/`Outlet`
endpoint can become a native `switch`. Unknown or hazardous endpoints never
get an actuator based on an OnOff trait alone.

To **enable physical light/switch control**, open **Settings → Devices & services
→ Aqara Studio → Configure/Options → Enable verified light and switch controls**.
Save, allow the config entry to reload, and open the light device. With this
option off, only the safe read-only output state appears. This switch remains
off by default even after upgrading.

For eligible lighting endpoints:

- Basic on/off is supported where `Output/OnOff` is explicitly writable.
- Brightness appears only with a compatible writable percentage
  `LevelControl/CurrentLevel` trait.
- XY color control uses Aqara's documented packed uint32 CIE XY encoding,
  only where `ColorControl/ColorXY` is explicitly readable/writable with a
  verified compatible data type.
- White color temperature uses documented **mired** units and
  hardware-advertised `ColorControl/ColorTemperature` min/max/step.
- The optional read-only `ColorControl/ColorMode` value identifies the active
  XY vs white-temperature presentation where supplied. Invalid values remain
  unknown, not guessed.
- Individual LED/pixel or addressable strip **segment control is not
  implemented**. Reporting a segment count alone does not prove commands for
  independently addressable segments.

**Open Aqara Studio directly:** under **Settings → Devices & services → Aqara
Studio → Devices**, open the gateway or any discovered device and select its
**Visit / Configuration URL** link. The link uses the configured local Studio
HTTP(S) origin and does not include or expose your API token. It opens in your
browser; remote users still need network access to the Studio host.

If lights do not appear, download sanitized integration diagnostics and inspect
`lighting.eligible_lights` and `lighting.enabled_lights`, without posting any
raw tokens or device identifiers. The device model may advertise functions that
this release cannot safely control; unsupported traits are intentionally skipped.

## Supported capabilities

The registry matches exact function/trait pairs and appropriate access metadata.
All listed device behavior still requires physical acceptance on your firmware.
Unsupported traits are skipped and summarized in diagnostics instead of creating
hundreds of unnecessary entities.

| Aqara function / trait | Home Assistant behavior | Qualification |
| --- | --- | --- |
| `Contact / ContactSensorState` | Door contact binary sensor | Polarity must be confirmed; invalid/missing remains unknown |
| `WaterLeak / LeakState` | Moisture binary sensor | Wet/dry polarity must be confirmed |
| `BasicInformation / Reachable` | Device availability evidence | Missing reachability is not a fabricated online/offline value |
| `Temperature / CurrentTemperature` | Temperature sensor | Verified numeric/unit mapping |
| `RelativeHumidity / CurrentHumidity` | Humidity sensor | Percent with numeric validation |
| `PowerSource / BatPercentRemaining` | Battery sensor | Percent with numeric validation; out-of-range/sentinel values remain unknown |
| `PowerSource / CurrentVoltage` | Voltage sensor | Volts, or advertised mV converted to V; diagnostic disabled by default |
| `Illuminance / CurrentIlluminance` | Illuminance sensor | Lux with numeric validation |
| `Output / OnOff` | Read-only power state; opt-in controls | Exact endpoint type `Light`, `Switch` or `Outlet` and writable access required for controls |
| `LevelControl / CurrentLevel` | Brightness with eligible lights | Same light endpoint, readable/writable, advertised percentage range with min 0/1 and max 100 |
| `ColorControl / ColorXY` | XY color picker on eligible lights | Packed uint32 CIE XY, explicit writable access and safe bounds |
| `ColorControl / ColorTemperature` | Warm/cool white selector | Mired values within the device-advertised min/max/step |
| `ColorControl / ColorMode` | Current color-mode readback | Read-only mode mapping when reported (XY 1 / color temperature 2) |
| `Button / ButtonEvent` | Experimental event entity | Documented single/double/long/release types; fresh positive timestamps required |

No lock/unlock, garage actuation, commissioning, unbinding, arbitrary commands or
destructive Studio operations are exposed. Cover controls, occupancy/motion
mappings and unverified manufacturer-specific capabilities are outside this beta.
Occupancy is deferred until its value semantics are evidenced explicitly.

## Updates, availability, and identity

REST supplies initial inventory, definitions and current values. WebSocket
authenticates, subscribes, maintains a heartbeat and restores subscriptions after
reconnecting. REST reconciliation repairs gaps after disconnections. If push is
unavailable, the configured polling fallback continues.

Definitions are cached for up to six hours. Normal polling reads traits in
batches; it does not download every definition every 15 seconds. Inventory
reconciliation and debounced object events discover newly paired devices without
YAML edits or an HA restart. Missing inventory records never automatically delete
registry records.

| Condition | Expected Home Assistant result |
| --- | --- |
| Valid value, confirmed polarity, available transport/device | Open/closed, wet/dry or numeric state |
| Missing/unrecognized value or unconfirmed polarity | Unknown; no fabricated safe value |
| Confirmed `Reachable = false` | Unavailable |
| Transport failure without fresh state confirmation | Unavailable until successful reconciliation |
| Sleeping battery device with no recent change | Not offline solely because it is quiet |

Entity unique IDs use stable gateway, device, endpoint, function and trait IDs.
Renaming a device or moving it between Studio spaces does not change identity.
HA preserves its entity ID and user-customized name through ordinary rediscovery.
A reset that changes physical identifiers may require migration.

An event entity's presence does not prove a button works. Press it and inspect a
newly received live event. A button report must carry a **positive vendor
timestamp strictly newer than the cached value or reconnect snapshot** before it
can drive an automation. Reports with missing or zero timestamps remain
diagnostic observations and never generate button presses. Firmware/bridges
without reliable event timestamps therefore have no usable button automation in
this beta. Startup and polling never replay cached button values. This event
freshness rule is separate from ordinary sensor values, where timestamp zero
alone does not invalidate a reading.

## Migration

Follow [MIGRATION.md](MIGRATION.md) before renaming or removing anything. Run the
integration alongside the working REST sensor, compare both physical states and
offline behavior, then release and reuse the old entity ID. Reusing an entity ID
does **not** preserve the old internal `device_id`; repair and test device-based
automations separately. Keep the private REST backup until acceptance is complete.

## Troubleshooting

| Symptom | Checks |
| --- | --- |
| Aqara Studio absent from Add integration | Check exact folder path, restart HA, refresh browser, inspect log for import/manifest errors |
| Invalid authentication | Verify Developer API access/token and expiration/revocation; reauthenticate |
| Cannot connect | Check reachability from the HA host/container, VLAN/firewall rules, scheme/port and HTTPS certificate trust |
| Contact/leak remains Unknown | Confirm polarity and inspect boolean `raw_value`; missing or malformed readings intentionally stay unknown |
| Device has no entities | Check supported function/trait pairs and access flags in sanitized diagnostics |
| Light only shows Output state | Enable verified light/switch controls in integration options; check lighting eligibility in diagnostics |
| Studio link is missing | Reload the Aqara Studio integration and open the physical device's Visit/Configuration link |
| Entities unavailable | Check transport and Studio reachability; a cached value alone does not prove current availability |
| Updates arrive only on polling | Inspect push diagnostics, proxy support for `/open/ws`, and token permissions |
| Button has no events | Enable experimental events and confirm live vendor events arrive when pressed |
| New device has not appeared | Allow an inventory cycle; confirm Studio lists it and it is not excluded |
| Automation fails after migration | Check both `entity_id` and internal `device_id`; inspect automation traces |

Download diagnostics from the integration entry's menu under **Settings →
Devices & services**. The export contains selected redacted metadata, not whole
API payloads or credentials. Review attachments before posting them publicly.
Model codes, function/trait names and versions are useful; personal identifiers,
room names and network details are not.

To remove the integration, first migrate/disable dependent automations, remove
the Aqara Studio config entry, then uninstall through HACS or remove its custom
component folder and restart HA. This does not unpair devices from Studio or
remove separate REST/Matter integrations.

## Development and verification

See the [executed verification report and exact file inventory](docs/TEST_REPORT.md)
for the initial beta results and remaining hardware/publication gates.

```sh
python3.14 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements_test.txt
python -m ruff check .
python -m ruff format --check .
python -m pytest -q --cov=custom_components.aqara_studio --cov-report=term-missing
```

CI runs those checks plus official HACS and hassfest validation. Dependencies and
action revisions are pinned. The official validator actions track upstream
validation containers, so future requirements can change. See
[CONTRIBUTING.md](CONTRIBUTING.md).

The manifest's `local_push` classification describes the implemented local
WebSocket primary transport, with REST fallback. It does not claim every device
or firmware has passed live tests.

## References

- [Aqara local API introduction](https://docs.aqara.com/docs/aqara-developer/data-export-api/introduction/)
- [Aqara device API](https://docs.aqara.com/docs/aqara-developer/data-export-api/device/)
- [Aqara WebSocket API](https://docs.aqara.com/docs/aqara-developer/data-export-api/websocket-api/)
- [Verified protocol and source discrepancies](docs/PROTOCOL.md)
- [Home Assistant manifest](https://contributors.home-assistant.io/core/integrations/manifest/)
- [Home Assistant config flows](https://contributors.home-assistant.io/core/integrations/config-flow/)
- [HACS integration packaging](https://www.hacs.dev/docs/publish/integration/)
- [HACS validation action](https://www.hacs.dev/docs/publish/action/)

Code and original community icon assets use the [MIT license](LICENSE). Aqara and
Home Assistant names remain the property of their respective owners.

## Install from Home Assistant's Apps repository screen

**This is a native custom integration, not an always-running App.** For Home Assistant OS/Supervisor users who are already at **Settings > Apps > Repositories**, this repository also includes a small **Aqara Studio Integration Installer (Beta)** App.

1. Add https://github.com/IdentivergAdmin/AqaraStudio-HassCommApp to the Apps repository manager.
2. Find **Aqara Studio Integration Installer (Beta)** under **Settings > Apps > Install app**.
3. Install it, leave the default **replace_existing = false**, and press **Start** once.
4. Read its Logs; **Stopped** after a successful copy is normal for this one-shot installer.
5. Restart **Home Assistant Core**, then add **Aqara Studio** under **Settings > Devices & services**.
6. Enter your local Studio host and Developer API token in the native integration setup, **not** in the installer.

The installer carries a frozen copy of the exact integration source in its Docker build context, and has no runtime GitHub download or background process. It writes only the native custom_components/aqara_studio folder and, on explicitly requested upgrades, saves the previous folder in aqara_studio_installer_backups/. No existing REST or Matter entities are removed. See the [App installation and security guide](aqara_studio_installer/DOCS.md).

The alternative **HACS custom repository** workflow continues to work for users who prefer HACS (HACS is separate from the Apps repository manager). Both methods install the same native integration. Do not install it with both package managers at the same time.

