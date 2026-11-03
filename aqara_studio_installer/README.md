# Aqara Studio Integration Installer (Beta)

**Install or upgrade native Aqara Studio in one Start.** No `replace_existing` toggle or API key needed.

1. Update this Installer App in **Settings → Apps** if a newer App version is available.
2. Press **Start** once.
3. Read the final **Log** message:
   - **SUCCESS** after FIRST INSTALL/UPGRADE: restart Home Assistant Core.
   - **ALREADY CURRENT**: nothing else to do; no restart needed.
   - **DOWNGRADE BLOCKED / ERROR**: files remain unchanged; read the log.
4. For a first-time installation, configure Aqara Studio in **Settings → Devices & services** after the Core restart.

This one-shot App intentionally stops after running. Actual version upgrades create backups automatically. It does not edit your existing REST/Matter integrations or automations. Read the **Documentation** tab for full safety and rollback notes.
