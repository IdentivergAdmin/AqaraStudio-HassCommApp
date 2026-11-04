# Move from the retired Installer App to HACS / Marketplace

This migration changes **who manages integration updates**, not what runs your
devices. The existing native integration under
`custom_components/aqara_studio` is the same Python code installed by
the old one-shot Home Assistant OS App.

**Your current working Studio connection, API token, entity IDs, devices,
areas, automations and paired Zigbee hardware do not need to be recreated.**
The config entry belongs to Home Assistant Core and is independent of
the old Installer App.

## Important limits

- This process has **not** been executed remotely against your specific HA
  installation. Stop if your UI differs or a download reports a conflict.
- Do **not** remove the Aqara Studio config entry under
  **Settings → Devices & services**, and do **not** delete
  `custom_components/aqara_studio` to make HACS see the repository.
- Do **not** run the old one-shot App again once HACS / Marketplace has
  downloaded the integration; two installers would compete to own the same
  files.
- Do **not** use **Tools → States → Set state** as a physical command.
- The new distribution does not eliminate **Home Assistant Core restarts
  after Python integration updates**. It eliminates the separate App,
  its Start button, and its redundant version mapping.

## Step 1. Prepare

1. Take a **Home Assistant backup** at **Settings → System → Backups**.
   Save a copy off the HA host. This is your supported full rollback.
2. Confirm **Settings → Devices & services → Aqara Studio** shows the
   currently installed native version (for example `0.1.4b1`).
3. Under **Tools → States**, record `light.closetlight`, one known
   contact entity, and the existing functional states. Record any
   dashboard/automation references you would need to check.
4. Retain the existing REST/Matter paths until they have individually
   passed acceptance. The native integration does not edit them.

## Step 2. Install through the supported manager

### On Home Assistant 2026.10 and older

Open **HACS → Custom repositories**, select **Integration**, and add:

`https://github.com/IdentivergAdmin/AqaraStudio-HassCommApp`

Open the **Aqara Studio** repository and select **Download**.
If the beta GitHub release does not appear, enable **Pre-release**
for this repository, or select an offered version deliberately.
The source folder remains `custom_components/aqara_studio`.

### On Home Assistant 2026.11 and newer

Open **Settings → Marketplace**, add the same URL as a
**custom integration repository** if not yet catalog-listed, and
download Aqara Studio. Custom repositories require a GitHub
connection. Select the beta release if pre-release opt-in is needed.

**If the manager reports that a custom integration is already installed:**
do not uninstall/remove the integration config entry or delete the folder.
Check whether HACS/Marketplace already lists Aqara Studio as
**Downloaded/Installed**. If it does, use that repository entry's
**Redownload/Install** action. If it does not, stop and report the exact
error with a sanitized screenshot. Do not perform an unverified
manual HACS registry edit.

## Step 3. Verify ownership, then reload Core once if required

1. Confirm HACS / Marketplace lists **Aqara Studio** as an installed
   **Integration**, with a repository-managed update entity or update status.
   A visible GitHub link alone is not evidence the download completed.
2. Confirm the native integration version from the downloaded version's
   `manifest.json` or the integration page.
3. Follow the UI's restart request **once** after files have been
   installed or updated. For an already running Python integration,
   a Core restart normally loads the new files.
4. Return to **Settings → Devices & services → Aqara Studio**.
   The existing config entry must remain configured; there should be
   no request to re-enter the API token or recreate devices.
5. Confirm both `light.closetlight` and the existing contact entity
   retain their entity IDs, states and availability. Check one
   harmless physical light command and normal contact transitions.

If an entity disappears or a new config entry is requested, **stop**.
Do not create a duplicate installation. Keep the original Home
Assistant backup, then inspect Aqara Studio and HACS/Marketplace logs.

## Step 4. Retire the redundant App only after verification

When HACS/Marketplace shows the repository as installed and the
existing config entry and devices have passed the checks:

1. In **Settings → Apps**, uninstall only
   **Aqara Studio Integration Installer (Beta)** (the one-shot
   installer App, not Aqara Studio under Devices & services).
2. Remove the legacy Apps **repository URL** under
   **Settings → Apps → Repositories** if it remains. This is distinct
   from the HACS/Marketplace custom repository.
3. Future updates are handled by **HACS/Marketplace**, not by the old
   App. Never run the old installer again.

Deleting the installer App is only housekeeping: it does not run
the integration at runtime. The original app implementation is
preserved on GitHub branch
[`legacy/supervisor-installer-v0.1.5`](https://github.com/IdentivergAdmin/AqaraStudio-HassCommApp/tree/legacy/supervisor-installer-v0.1.5)
and in Git history. It is **not an active supported update channel**.

## Rollback

If a manager download or Core restart causes a problem, use the
Home Assistant backup from Step 1 to restore the working state.
An alternative is to install an earlier **known-good GitHub release**
from HACS/Marketplace, then restart Core. That option requires
an earlier release to exist and should not be assumed for this
project's initial public release.

Do not delete entity registries or reset/re-pair the M300 as a
routine rollback. Report the exact manager error, native version,
HA version and sanitized integration diagnostics instead.

## New ongoing update model

1. Maintainer merges tested code and publishes a version-matched
   GitHub release.
2. HACS / Marketplace discovers newer compatible releases and
   creates a Home Assistant update notification.
3. User reviews release notes and selects **Install/Update**.
4. Home Assistant requests a Core restart only when required
   for updated Python code.
5. All Studio runtime networking and entities remain managed
   by the native integration inside Core.

A custom GitHub repository is installable by anyone with the link.
It is **not** automatically listed in the default catalog:
catalog admission is a separate public review process.
