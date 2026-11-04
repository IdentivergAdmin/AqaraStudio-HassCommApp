# Distribution and release contract — HACS / Marketplace

Aqara Studio is **one native Home Assistant integration**, not a
Home Assistant OS App. The public GitHub repository publishes
`custom_components/aqara_studio` using `hacs.json`, and HACS /
Home Assistant Marketplace installs and updates it.

**Release contract:**

- Native integration version and GitHub Release tag are both
  **`0.1.4b1`** (no `v` prefix).
- `custom_components/aqara_studio/manifest.json`,
  `pyproject.toml`, and `release_contract.json` must agree.
- `hacs.json` minimum Home Assistant version is `2026.10.0`.
- The root of the default branch must have **no `repository.yaml`
  or `aqara_studio_installer/`**. Marketplace refuses mixed
  repositories containing Home Assistant OS Apps.
- The old installer remains available in Git history and the branch
  `legacy/supervisor-installer-v0.1.5`, but **not** as a second
  installation/update manager.

## CI / publication gates

The [test workflow](../.github/workflows/ci.yml) exercises the native
Python integration against Home Assistant 2026.10.4. The
[validator workflow](../.github/workflows/validate.yml) runs
hassfest and HACS repository validation.

The [release workflow](../.github/workflows/release.yml), triggered
on a native-manifest version change to `main` or manual dispatch,
runs lint, the full test suite, HACS validation and hassfest again
before publishing **one immutable GitHub release**.

The release workflow refuses to publish when:

1. The Git reference is not the default `main` branch.
2. The manifest, `pyproject.toml`, release contract and expected
   tag disagree.
3. A legacy Home Assistant OS App definition still exists in
   the default branch.
4. HACS, hassfest, Ruff or Python tests fail.
5. The version already has a GitHub Release. Existing releases are
   never silently overwritten or retagged.

GitHub Actions requires write permission to `contents` in the
release job. If this repository's policy prevents the workflow
from creating releases, the job will fail; a maintainer must
address repository permission settings explicitly. Do not
pretend a PR merge created a GitHub Release.

## Pre-releases and compatibility

This release is `0.1.4b1`, and automated release publication
marks it as a **GitHub pre-release**, because the project has not
completed independent physical acceptance across all device types.

HACS / Marketplace normally only offers GitHub pre-releases when
the user enables **Pre-release** for that repository. When there
are no GitHub Releases, the default branch's commit hash may
be offered instead. GitHub Releases are necessary for a
human-readable version/update cadence and eventual default
catalog submission.

Custom repositories can be installed by anyone with a GitHub
connection, but **default catalog listing** requires a separate
submission to the public
[`hacs/default` catalog](https://github.com/hacs/default)
and its own review; this project does not claim catalog inclusion.

## Update and restart behavior

HACS (HA 2026.10 and earlier) and Marketplace (2026.11+) own
installation, version tracking and update discovery. Home
Assistant Core owns runtime WebSocket, REST, entity state and
automation interactions.

After installing new Python integration files, **Home Assistant
Core normally needs a restart** to load the new code. This
is the same as other community Python integrations. No
one-shot App is involved. An App cannot safely hot-swap
already imported Python modules to eliminate the restart.

## User-facing acceptance and data safety

- Existing installer users adopt HACS/Marketplace via
  [MIGRATE_LEGACY_INSTALLER.md](MIGRATE_LEGACY_INSTALLER.md).
  Do not delete the existing HA config entry, native folder,
  or automations during migration.
- Sensitive contact/leak mappings stay explicitly calibrated.
  The integration must not invent safe states or replay stale
  button press events.
- M300 light strip on/off and color have been physically observed
  in the owner's environment; this **does not** certify all
  models and firmware revisions.
- The real M300 diagnostic is not committed. Only the sanitized
  metadata fixture remains in `tests/fixtures`.
- Never include tokens, local addresses, raw device IDs, or
  household topology in GitHub issues or release notes.

See [ACCEPTANCE.md](ACCEPTANCE.md) and [CHANGELOG.md](../CHANGELOG.md).
