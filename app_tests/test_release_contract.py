"""Prevent mismatched Installer App/native packages and outdated release advice."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_release_contract_matches_every_shipped_artifact():
    contract = json.loads((ROOT / "release_contract.json").read_text())
    native_version = contract["native_integration_version"]
    app_version = contract["installer_app_version"]
    source = json.loads(
        (ROOT / "custom_components/aqara_studio/manifest.json").read_text()
    )
    packed = json.loads(
        (
            ROOT / "aqara_studio_installer/rootfs/opt/aqara_studio/manifest.json"
        ).read_text()
    )
    options = yaml.safe_load((ROOT / "aqara_studio_installer/config.yaml").read_text())
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    docker = (ROOT / "aqara_studio_installer/Dockerfile").read_text()
    readme = (ROOT / "README.md").read_text()
    installer_docs = (ROOT / "aqara_studio_installer/DOCS.md").read_text()
    release_doc = (ROOT / "docs/RELEASE_VERIFICATION.md").read_text()

    assert source["domain"] == "aqara_studio"
    assert source["version"] == packed["version"] == native_version
    assert project["project"]["version"] == native_version
    assert options["version"] == app_version
    assert f'ARG BUILD_VERSION="{app_version}"' in docker
    assert native_version in readme
    assert app_version in readme
    assert native_version in installer_docs
    assert app_version in installer_docs
    assert native_version in release_doc
    assert app_version in release_doc
    assert contract["expected_upgrade_log"] in readme
    assert contract["expected_upgrade_log"] in release_doc
    assert contract["requires_physical_acceptance"] is True
    assert (ROOT / contract["diagnostic_fixture"]).exists()


def test_readme_uses_2026_tools_navigation_and_never_suggests_fake_state_test():
    readme = (ROOT / "README.md").read_text()
    runbook = (ROOT / "docs/ACCEPTANCE.md").read_text()
    release_doc = (ROOT / "docs/RELEASE_VERIFICATION.md").read_text()
    for text in (readme, runbook, release_doc):
        assert "Tools → States" in text
        assert "Developer Tools → States" not in text
        assert "Developer tools → States" not in text
    assert "Set state" in readme
    assert "Set state" in release_doc
    assert "Tools → Actions" in readme
    assert "Tools → Actions" in runbook
