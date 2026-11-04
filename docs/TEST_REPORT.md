# v0.1.0b1 engineering verification — historical snapshot

**Historical only:** this report captures the initial 2026-11-02 beta.
The current public distribution uses HACS/Marketplace and release-gated
CI. See [RELEASE_VERIFICATION.md](RELEASE_VERIFICATION.md) for the
current process; the values below must not be presented as the most
recent test count, distribution architecture or repo metadata.


Recorded 2026-11-02. This report covers automated local verification, not a live
M300 certification. No private LAN, production Home Assistant, or physical device
was accessed. All fixtures are synthetic; loopback servers are test-only.

## Executed gates

| Gate | Executed result |
| --- | --- |
| `python -m pytest -q --cov=custom_components.aqara_studio --cov-report=term-missing` | **200 passed**, 6.17 seconds |
| Coverage | **90% combined statement/branch coverage** (1,526 statements; 562 branches) |
| `ruff check .` | **Passed** |
| `ruff format --check .` | **Passed** |
| `git diff --check` | **Passed** |
| Official HA 2026.10.4 hassfest | **Passed**; 23 validators, 1 integration, 0 invalid integrations |
| HACS remote validation | Workflow supplied; requires GitHub Actions execution and repository metadata |
| Hardware acceptance | **Not executed**; follow `docs/ACCEPTANCE.md` |

Test environment: Python 3.14.8, Home Assistant 2026.10.4,
pytest-homeassistant-custom-component 0.13.375, pytest 9.0.3,
pytest-asyncio 1.4.0, Ruff 0.17.3. The pinned test dependencies are in
`requirements_test.txt`. The integration requires Home Assistant 2026.10.0+.

The tested official hassfest source is Home Assistant core tag `2026.10.4`,
commit `357cae5c598dfcd7a0ea7dc5b1facccd4ec6037b`. Its source runner used:

```sh
python -m script.hassfest --action validate \
  --integration-path /absolute/path/to/custom_components/aqara_studio
```

## What the tests establish

- Actual Home Assistant config flow, native platform setup, reload and unload.
- Stable registry identities, user-customized names, gateway relationships,
  dynamic addition, and synthetic 40- and 100-device workloads.
- Paginated REST inventory, batching, error envelopes, bounded reads, finite
  rate-limit delays, and read-only defaults.
- Real loopback HTTP streaming and WebSocket authentication, subscription,
  heartbeat, reconnection, and task cancellation.
- Unknown/unavailable safety, missing and malformed data, offline devices,
  partial batch failures, and zero timestamps on ordinary state traits.
- Out-of-order updates, concurrent REST/push races, and unordered reconnect
  buffers that require another authoritative read.
- Contact/leak explicit polarity settings; fixtures do not establish hardware
  polarity. Tests establish behavior after a selected mapping only.
- Cached button replay suppression, timestamp freshness gates, enum decoding,
  and withholding unverified events.
- Opt-in control authorization, exact writable capability checks, invalid
  command rejection, no command retries, and no optimistic state changes.
- Diagnostic redaction and explicitly requested stale-device cleanup after two
  complete inventory absences. No automatic device deletion occurs.

## Publication and acceptance gates

At the time of the local check, GitHub repository metadata had no description or
topics. HACS validates these separately from repository files. Set the About
fields described in `CONTRIBUTING.md`; no HACS checks are disabled here.
The implementation belongs on its feature branch until review and hardware
acceptance. Installing an unchanged initial `main` cannot install the integration.
No release, formal HACS listing, or hardware compatibility certification is
implied by this report.

## Exact source file inventory

The following paths make up this initial implementation; `README.md` replaces
the initial one-line README, and the remaining paths are new.

- `.github/ISSUE_TEMPLATE/bug_report.yml`
- `.github/ISSUE_TEMPLATE/config.yml`
- `.github/ISSUE_TEMPLATE/device_support.yml`
- `.github/workflows/ci.yml`
- `.github/workflows/validate.yml`
- `.gitignore`
- `CHANGELOG.md`
- `CONTRIBUTING.md`
- `LICENSE`
- `MIGRATION.md`
- `README.md`
- `SECURITY.md`
- `custom_components/aqara_studio/__init__.py`
- `custom_components/aqara_studio/api.py`
- `custom_components/aqara_studio/binary_sensor.py`
- `custom_components/aqara_studio/brand/icon.png`
- `custom_components/aqara_studio/brand/icon.svg`
- `custom_components/aqara_studio/brand/icon@2x.png`
- `custom_components/aqara_studio/config_flow.py`
- `custom_components/aqara_studio/const.py`
- `custom_components/aqara_studio/coordinator.py`
- `custom_components/aqara_studio/device.py`
- `custom_components/aqara_studio/diagnostics.py`
- `custom_components/aqara_studio/entity.py`
- `custom_components/aqara_studio/event.py`
- `custom_components/aqara_studio/light.py`
- `custom_components/aqara_studio/manifest.json`
- `custom_components/aqara_studio/sensor.py`
- `custom_components/aqara_studio/strings.json`
- `custom_components/aqara_studio/switch.py`
- `custom_components/aqara_studio/translations/en.json`
- `custom_components/aqara_studio/websocket.py`
- `docs/ACCEPTANCE.md`
- `docs/PROTOCOL.md`
- `docs/TEST_REPORT.md`
- `hacs.json`
- `pyproject.toml`
- `requirements_test.txt`
- `tests/__init__.py`
- `tests/conftest.py`
- `tests/entity_helpers.py`
- `tests/fixtures/capabilities.json`
- `tests/helpers.py`
- `tests/test_api.py`
- `tests/test_availability.py`
- `tests/test_binary_sensor.py`
- `tests/test_config_flow.py`
- `tests/test_control_authorization.py`
- `tests/test_controls.py`
- `tests/test_coordinator.py`
- `tests/test_coordinator_transport.py`
- `tests/test_diagnostics.py`
- `tests/test_discovery.py`
- `tests/test_events.py`
- `tests/test_init.py`
- `tests/test_reconnection.py`
- `tests/test_sensors.py`
- `tests/test_websocket.py`
