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

## Releases

1. Pass tests, lint, hassfest and HACS validation for the release commit.
2. Set the repository's **About** description and at least one relevant topic.
   HACS validates GitHub metadata as well as committed files. Suggested
   description: "Independent local Aqara Studio integration for Home Assistant".
   Suggested topics: `home-assistant`, `hacs`, `aqara`, `aqara-studio`,
   `custom-integration`. These settings are changed in GitHub's About gear;
   editing a README cannot supply them.
3. Review diagnostics and fixtures for private information.
4. Execute and record relevant physical tests in `docs/ACCEPTANCE.md`.
5. Update `manifest.json`, `pyproject.toml` and `CHANGELOG.md` together.
6. Merge reviewed code to the default branch, or publish a release explicitly
   targeting the reviewed implementation commit.
7. Mark releases **prerelease/beta** until hardware acceptance is complete.
8. Confirm HACS installs the intended version, a clean HA setup works, and
   upgrading preserves identity.

Custom-repository installation is independent of a future HACS default catalog
or Marketplace submission. Claim external listing only after actual acceptance.
