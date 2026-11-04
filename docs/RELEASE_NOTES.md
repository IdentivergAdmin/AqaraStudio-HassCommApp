# Aqara Studio 0.1.4b1 — initial HACS / Marketplace beta release

## What is included

- Native Aqara Studio integration, installed directly into
  `custom_components/aqara_studio`.
- Confirmed on/off, brightness, XY and white-temperature support for
  the owner's M300 ClosetLight after real-device metadata compatibility work.
- Local WebSocket push, REST reconciliation, stable device and entity identities.
- Explicitly calibrated contact/leak polarity and conservatively gated
  experimental button and switch controls.

## Distribution change for previous Installer App users

**The one-shot Home Assistant OS Installer App is retired.** It previously
copied this same native integration into Home Assistant. Future updates are
managed through **HACS (HA 2026.10 and earlier)** or **Settings → Marketplace
(HA 2026.11 and later)**. The old App has no runtime role.

**Do not remove the existing Aqara Studio integration from Settings →
Devices & services, erase its `custom_components` directory, or
re-pair the M300.** Follow the
[legacy installer migration runbook](https://github.com/IdentivergAdmin/AqaraStudio-HassCommApp/blob/main/docs/MIGRATE_LEGACY_INSTALLER.md).
The user should verify HACS/Marketplace ownership before uninstalling the
legacy one-shot App.

## Updates and safety

- This is a **pre-release**. Enable Pre-release for this custom repository
  to receive it when necessary.
- HACS/Marketplace downloads compatible releases and shows updates through
  Home Assistant's update UI; installing Python integration changes may still
  require a **Home Assistant Core restart**.
- The integration never needs a separate background App or a second update
  version.
- Keep working REST/Matter entities until each critical contact/leak path
  passes independent physical acceptance.
- No locks, covers, valves or garage actuation.
- No official Aqara affiliation or default catalog listing is claimed.

See [CHANGELOG.md](https://github.com/IdentivergAdmin/AqaraStudio-HassCommApp/blob/main/CHANGELOG.md)
and [physical acceptance](https://github.com/IdentivergAdmin/AqaraStudio-HassCommApp/blob/main/docs/ACCEPTANCE.md).
