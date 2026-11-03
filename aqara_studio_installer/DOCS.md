# Aqara Studio Integration Installer (Beta)

This is a **one-shot Home Assistant Supervisor app** for people using **Settings > Apps > Repositories**. It installs the **native** aqara_studio custom integration into Home Assistant Core. It is **not** a persistent service, REST proxy, Matter bridge, or replacement for the HACS custom-integration installation path.

## Installation

[Add this App repository to My Home Assistant](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FIdentivergAdmin%2FAqaraStudio-HassCommApp)


1. In Home Assistant, open **Settings > Apps > Repositories**, add https://github.com/IdentivergAdmin/AqaraStudio-HassCommApp, and close the dialog.
2. Open **Settings > Apps > Install app**; select **Aqara Studio Integration Installer (Beta)**, then **Install**.
3. On its **Configuration** tab leave replace_existing: false for a first install. Press **Start** once.
4. Read the **Log** tab. A success message confirms that files were copied. The app will stop automatically: this is normal.
5. **Restart Home Assistant Core** from the Home Assistant UI (a YAML reload is not enough).
6. Open **Settings > Devices & services > Add integration > Aqara Studio** and enter your local Studio host and Developer API token. Do not enter the token in this app.
7. Keep old Matter and REST sensors until you compare real contact transitions and unavailable states. See the repository MIGRATION.md.

## What the installer changes

- Creates or replaces only <Home Assistant config>/custom_components/aqara_studio/.
- Includes the integration code inside the app package: no GitHub download, API token, extra network service, or runtime internet connection is needed.
- Does not edit configuration.yaml, .storage, existing sensor/entity IDs, integrations, automations, or devices.
- Does **not** automatically restart Home Assistant Core.

## Upgrades and rollback

Update the Aqara Studio Installer App to **0.1.1** in the Apps screen before
using it to upgrade the integration. The updater never overwrites the installed
integration unless `replace_existing: true` is selected. After the log reports
v0.1.1b1 installed, restart Home Assistant Core. In the native integration's
**Configure/Options** menu, enable verified light and switch controls only
after checking the device eligibility and testing the actual light safely.


If aqara_studio already exists, the default action does **not** overwrite it. For an intentional upgrade, set replace_existing: true and press **Start**. The old directory is moved to aqara_studio_installer_backups/ under the Home Assistant configuration directory before the new directory is activated. Back up Home Assistant first; restore the backed-up folder and restart Home Assistant Core to roll back. The one-shot installer does not automatically remove old backups.

After copying the files, the App can be stopped or uninstalled. **Uninstalling the App does not remove the copied native integration.** To uninstall the native integration, remove its config entry and its custom_components/aqara_studio folder separately, following the main README.

## Security and limitations

This app requests **write access to the Home Assistant configuration directory**, because it must install code under custom_components/. It does not read or modify credentials or the .storage directory, but the mount is broad; review the code and only install from a trusted repository. It exposes no ports, requires no Supervisor API privilege, and never runs automatically at boot.

The integration is **0.1.1b1 beta** and is not hardware-certified. Live tests with the M300 (especially contact/leak polarity and offline-state handling) remain required.
