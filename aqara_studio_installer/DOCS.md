# Aqara Studio Integration Installer (Beta)

**Version 0.1.2 — no upgrade toggles.** This is a small, one-shot Home Assistant App that installs or upgrades the **native** Aqara Studio custom integration. It is not a second integration, proxy, Matter bridge, or background service.

## Install for the first time

1. In **Settings → Apps → Repositories**, add https://github.com/IdentivergAdmin/AqaraStudio-HassCommApp (or use the **Add to My Home Assistant** badge on GitHub).
2. In **Settings → Apps**, install **Aqara Studio Integration Installer (Beta)**.
3. Press **Start** once, then check **Logs** for `FIRST INSTALL` and `SUCCESS`.
4. Restart **Home Assistant Core** (not the whole host).
5. Open **Settings → Devices & services → Add integration → Aqara Studio**. Configure your local Studio host and API token there, **never in the installer**.

## Upgrade an existing installation

**Update the Installer App to 0.1.2 or newer in Settings → Apps, then press Start once. That's it.** There is no Configuration toggle, saved confirmation, delete/reinstall, token entry, or re-pairing step.

The installer checks the version in `custom_components/aqara_studio/manifest.json` against its bundled native integration and reports one of four results:

| Installer log | Meaning | Next action |
| --- | --- | --- |
| `FIRST INSTALL` + `SUCCESS` | No existing integration; copied the bundled version | Restart Core; add the native integration |
| `UPGRADE old -> new` + `SUCCESS` | Older native code safely backed up and replaced | Restart Core; existing Aqara Studio config and entities remain |
| `ALREADY CURRENT` | Exact same native version | **Nothing to do**; Core restart not needed |
| `DOWNGRADE BLOCKED` | Installed native version is newer than the App's bundled version | Update the Installer App; no files changed |

**Existing users:** If you have already installed native **0.1.1b1**, the new **Installer App 0.1.2** will log **ALREADY CURRENT**. App version and bundled integration version are different release numbers, by design. You do **not** need another Core restart for a no-op.

## Data safety and recovery

- No `replace_existing` option is needed or honored. Settings saved by older Apps are ignored; the Configuration form is removed.
- Each real **version upgrade** automatically moves the previous native code directory to `/homeassistant/aqara_studio_installer_backups/` with the old version and timestamp in its name.
- Files are copied into a temporary folder and checked before replacement. If activation fails after the old folder is moved, the installer tries to restore it automatically.
- Downgrades, an unknown/corrupt installed manifest, symlinked directories, or unrecognized version syntax are refused **without replacing code**.
- Re-running the current version does not make another backup or reinstall anything.
- Existing REST/Matter entities, Home Assistant `configuration.yaml`, registry, automations, credentials, and `.storage` remain unchanged by this App. The installer never automatically restarts Core.
- Backups are **not deleted automatically**. If you need manual rollback, restore a backup directory to `custom_components/aqara_studio` with Home Assistant Core stopped, then start Core. Take a full HA backup before upgrading.

The App needs read/write access to the Home Assistant configuration directory to install native Python code; review its source and use only your trusted repository. No port exposure, Supervisor API access, API credentials, runtime GitHub downloads, or telemetry are required.

## Noise-free operation

Since version 0.1.2, the one-shot App uses a minimal Alpine image instead of an S6-supervised service. It prints short `FIRST INSTALL` / `UPGRADE` / `ALREADY CURRENT` / `SUCCESS` messages and exits. An App status of **Stopped** after the run is expected.

## Validation boundary

The bundled integration remains **v0.1.1b1 beta**, with physical M300 acceptance outstanding. Keep working contact/leak REST sensors until you have confirmed raw contact/leak polarity and transport recovery. Enable light controls in the native integration's **Options** only after checking the actual device capabilities.

**HACS is another supported installation method.** Use either HACS **or** this one-shot installer to manage the native files, not both at once.
