# Changelog

## 0.1.3 — 2026-11-04

- Bundle native Aqara Studio integration v0.1.2b1.
- Native lighting controls enabled by default only for positively identified Light devices with writable OnOff traits.
- Add device-page diagnostic for blocked light controls; switches/outlets remain opt-in.
- Preserve version-aware, automatically backed-up, one-start upgrades without configuration toggles.

## 0.1.2 — 2026-11-03

- **No configuration form or replace_existing toggle.** One Start handles a missing, outdated or already-current native integration.
- Compare installed and bundled PEP 440 beta/release versions; refuse accidental downgrade.
- Auto-backup before actual upgrades, verified staging, and rollback attempt if activation fails.
- Idempotent re-runs avoid redundant copies, backups and Core restarts.
- Minimal Alpine one-shot image removes irrelevant S6 startup/shutdown messages.
- Concise action/result logs and simplified first-install/upgrade documentation.
- Add isolated negative-path, version-ordering and rollback regression tests.
- Bundled **native integration stays at v0.1.1b1**; this release improves installation, not Aqara behavior.

## 0.1.1

- Package Aqara Studio native integration v0.1.1b1, including color-capable lights and direct Studio management links.
- Retain opt-in replacement/backup and one-shot operation.

## 0.1.0

- Initial Home Assistant Apps repository and one-shot installer for native Aqara Studio integration v0.1.0b1.
- Include a local snapshot of the integration and non-destructive upgrade safeguards.
