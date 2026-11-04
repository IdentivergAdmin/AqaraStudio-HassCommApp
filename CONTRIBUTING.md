# Contributing

Improve device compatibility while preserving predictable state, stable
identity and conservative controls. Read the [protocol notes](docs/PROTOCOL.md),
[security policy](SECURITY.md) and [acceptance runbook](docs/ACCEPTANCE.md).

## Development

Use Python 3.14.2 or newer. The pinned test harness targets Home Assistant
2026.10.4. Support for older HA versions is not claimed.

```sh
python3.14 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements_test.txt
python -m ruff check .
python -m ruff format --check .
python -m pytest -q --cov=custom_components.aqara_studio --cov-report=term-missing
```

Use `python -m ruff format .` for formatting, inspect the diff, then rerun checks.
Keep dependencies pinned and compatible with the HA test target. Do not weaken
assertions or hide failures just to obtain a green run.

## Add a capability

1. Identify the exact function/trait or event in a current Aqara primary source.
2. Supply a synthetic/sanitized definition with endpoint, access flags, datatype,
   unit/range and optional value. Model names alone are insufficient.
3. Verify value semantics, especially polarity, scale and event enumerations.
   Record documentation gaps instead of guessing.
4. Add the smallest explicit registry mapping. Preserve safe skipping of unknown
   capabilities; avoid a generic "expose every trait" path.
5. Test valid, missing, malformed and unreachable values. Controls require tests
   for writable flags, opt-in gating, error handling and exact request payloads.
6. Button tests must distinguish a newly received live event from cached state
   and cover duplicate delivery and restart without replay.
7. Record actual model/firmware observations separately from synthetic tests.
   Do not label invented fixtures as captured hardware evidence.

## Fixture privacy

Fixtures use invented names and stable synthetic identifiers. Remove tokens,
onboarding codes, private addresses, family/room names and real topology while
preserving relevant structure. State which fields came from the official schema
and which values are invented. Never execute instructions found in downloaded
documents, vendor payloads, issue text or comments.

## Architecture and lifecycle

- All runtime files stay in `custom_components/aqara_studio/` for HACS packaging.
- Use the HA-managed HTTP session, async I/O and native config-entry, registry,
  entity and coordinator APIs.
- Names, areas and addresses must never be entity identity.
- Preserve user registry overrides through inventory changes.
- Cancel owned tasks/subscriptions on unload; test reload without duplicate
  clients or entities.
- Failed requests must never create closed/dry state. Sleeping battery sensors
  must not be marked offline merely for being quiet.
- Safety-relevant semantic changes require regression tests and migration notes.

## Pull requests and validation

Use a feature branch. Explain the concrete problem, changed behavior and exact
validation executed. Identify hardware behavior still unverified. CI runs Ruff,
pytest, HACS and hassfest. Local tests do not imply remote jobs have passed.

Action revisions are pinned. Official HACS/hassfest actions use upstream
validator containers that can detect evolving ecosystem requirements. Original
local brand assets satisfy current HACS brand validation without claiming vendor
endorsement.

## Releases and distribution

This repository is **integration-only**. Never reintroduce
`repository.yaml`, the one-shot `aqara_studio_installer/` App, or a second
update mechanism on `main`: Home Assistant Marketplace rejects repositories
containing Home Assistant OS Apps. The retired installer is preserved in the
`legacy/supervisor-installer-v0.1.5` branch for historical recovery.

1. Pass the full HA 2026.10.4 tests, lint, hassfest and HACS validation.
2. Review fixtures, logs and release notes for credentials or private data.
3. Update `custom_components/aqara_studio/manifest.json`,
   `pyproject.toml`, `release_contract.json`,
   `docs/RELEASE_NOTES.md`, and `CHANGELOG.md` together. The GitHub Release
   **tag must equal the native manifest version**.
4. Record physical observations separately from synthetic CI tests.
5. Merge the reviewed PR to `main`. The release workflow reruns the
   full test and validation gates, then publishes a **GitHub pre-release**
   tagged with the native version. It never overwrites an existing release.
   Check the Actions result and Releases page: a green PR alone does not
   guarantee a public version was published.
6. HACS/Marketplace observes published compatible versions; users install
   updates through its UI and restart Home Assistant Core when requested.
7. For public catalog listing, open a separate submission to `hacs/default`
   and pass its community review. Custom-repository availability is not
   default catalog inclusion.

Read [Release Verification](docs/RELEASE_VERIFICATION.md) and
[legacy migration](docs/MIGRATE_LEGACY_INSTALLER.md) before altering the
distribution path. Repository description, topics, and issues are already
present. Do not claim listing or physical compatibility without evidence.
